# Security Issue #07: Concurrency & Queuing Strategy

## Issue Overview

**Severity**: HIGH
**Category**: Resource Exhaustion / Denial of Service
**Status**: CONFIRMED
**Date**: 2024-09-03

## Security Review Feedback

> "Concurrency & queuing unspecified. Requirements hint at queueing and parallelism, but you don't define fairness/per-service limits. The recommendation is to add: 'The system SHALL enforce a per-service concurrency limit (default 1) and a global worker pool (default N). Queue discipline: FIFO; retries: up to R with exponential backoff.'"

## Factual Analysis

**The critique is CONFIRMED as accurate.** The fastDeploy system currently has **no concurrency controls, no queuing mechanism, and no limits** on deployment execution.

### Current Implementation Analysis

#### 1. Deployment Execution Model
- **File**: `/Users/jochen/projects/fastdeploy/src/deploy/domain/model.py` (lines 375-385)
- **File**: `/Users/jochen/projects/fastdeploy/src/deploy/tasks.py` (lines 20-22)

```python
def start_deployment_task(self, service: Service):
    # ... setup code ...
    from ..tasks import get_deploy_environment, run_deploy
    environment = get_deploy_environment(self, service.get_deploy_script())
    run_deploy(environment)  # subprocess.Popen(...) - NO LIMITS!
    self.record(events_module.DeploymentStarted)

def run_deploy(environment):  # pragma no cover
    command = [sys.executable, "-m", "deploy.tasks"]
    subprocess.Popen(command, start_new_session=True, env=environment)
```

**Key Finding**: Every deployment request immediately spawns a new subprocess via `subprocess.Popen()` with **no concurrency limits whatsoever**.

#### 2. Request Processing Flow
- **File**: `/Users/jochen/projects/fastdeploy/src/deploy/entrypoints/routers/deployments.py` (lines 79-116)
- **File**: `/Users/jochen/projects/fastdeploy/src/deploy/service_layer/handlers.py` (lines 65-100)

```python
@router.post("/")
async def start_deployment(...):
    cmd = commands.StartDeployment(...)
    await bus.handle(cmd)  # No queuing - immediate execution

async def start_deployment(command: commands.StartDeployment, uow: AbstractUnitOfWork):
    # ... database operations ...
    deployment.start_deployment_task(service)  # Immediate subprocess spawn
```

**Key Finding**: The message bus processes deployment commands immediately with no queuing or rate limiting.

#### 3. Current "Queue" Implementation
- **File**: `/Users/jochen/projects/fastdeploy/src/deploy/service_layer/messagebus.py` (lines 29-38)

```python
async def handle(self, message: Message):
    self.queue = [message]  # This is NOT a persistent queue!
    while self.queue:
        message = self.queue.pop(0)
        # ... immediate processing ...
```

**Key Finding**: The `self.queue` is just a temporary in-memory list for handling cascading events within a single request - it's NOT a job queue.

#### 4. No Worker Pool System
**Analysis**: Searched for worker pool implementations, background job systems (Celery, RQ), or async task queues.
**Finding**: **NONE EXIST**. No worker pool, no job queue, no background task system.

#### 5. No Concurrency Configuration
- **File**: `/Users/jochen/projects/fastdeploy/src/deploy/config.py`
**Finding**: No configuration settings for concurrency limits, worker pools, or queue parameters.

## Impact Assessment

### 1. Resource Exhaustion (HIGH RISK)

#### CPU & Memory Exhaustion
```bash
# Attack scenario: Rapid deployment requests
for i in {1..100}; do
  curl -X POST /deployments/ -H "Authorization: Bearer $TOKEN" &
done
# Result: 100 concurrent subprocess deployments = system overload
```

**Impact**: Each deployment spawns:
- Python subprocess running deployment script
- Ansible playbook execution (CPU intensive)
- SSH connections to target hosts
- Database connections for step updates

#### Process Table Exhaustion
**Risk**: No limit on concurrent `subprocess.Popen()` calls can exhaust the system's process table.

#### File Descriptor Exhaustion
**Risk**: Each deployment opens multiple file descriptors (stdout pipes, SSH connections, database connections).

### 2. Denial of Service Vulnerabilities

#### Resource-Based DoS
- **Attack**: Authenticated user submits multiple deployment requests
- **Result**: Server becomes unresponsive due to resource exhaustion
- **Mitigation**: Currently **NONE**

#### Service-Specific DoS
- **Attack**: Target specific service with rapid deployments
- **Result**: Service becomes unusable, deployments fail/interfere
- **Mitigation**: Currently **NONE**

### 3. Fairness and Starvation Issues

#### Service Monopolization
- High-frequency services can monopolize deployment resources
- Low-priority services may never get deployment slots
- No fair scheduling between different services

#### User Starvation
- Single user can consume all deployment capacity
- No per-user limits or quotas

### 4. Interference and Race Conditions

#### Concurrent Service Deployments
```python
# Current code allows this dangerous scenario:
deployment_1 = start_deployment(service_id=1)  # Modifies service state
deployment_2 = start_deployment(service_id=1)  # Concurrent modification!
```

**Risk**: Multiple deployments of the same service can interfere with each other.

## Proposed Queuing Architecture

### 1. Queue System Design

#### Core Components
```python
# Proposed architecture
class DeploymentQueue:
    def __init__(self, max_workers: int = 4, per_service_limit: int = 1):
        self.max_workers = max_workers
        self.per_service_limit = per_service_limit
        self.global_queue = asyncio.Queue()
        self.service_queues = defaultdict(asyncio.Queue)
        self.active_deployments = defaultdict(int)
        self.worker_pool = []

class QueuedDeploymentTask:
    deployment_id: int
    service_id: int
    priority: int = 0
    submitted_at: datetime
    retry_count: int = 0
    max_retries: int = 3
```

#### Queue Discipline: FIFO with Priority
- **Primary**: First-In-First-Out within same priority level
- **Priority Levels**:
  - 0: Critical deployments (rollbacks)
  - 1: Normal deployments
  - 2: Bulk operations
- **Per-Service FIFO**: Maintain order for same service

### 2. Concurrency Limits

#### Global Worker Pool
```python
# Configuration
DEFAULT_MAX_WORKERS = 4  # Global concurrent deployments
MAX_WORKERS_CONFIG = "FASTDEPLOY_MAX_WORKERS"
```

#### Per-Service Limits
```python
# Configuration
DEFAULT_PER_SERVICE_LIMIT = 1  # Max concurrent deployments per service
PER_SERVICE_LIMIT_CONFIG = "FASTDEPLOY_PER_SERVICE_LIMIT"
```

#### Per-User Rate Limiting
```python
# Additional protection
DEFAULT_USER_RATE_LIMIT = 10  # Deployments per minute
RATE_LIMIT_WINDOW = 60  # seconds
```

### 3. Retry Strategy with Exponential Backoff

#### Retry Parameters
```python
DEFAULT_MAX_RETRIES = 3
BASE_DELAY = 2.0  # seconds
MAX_DELAY = 300.0  # seconds (5 minutes)
BACKOFF_MULTIPLIER = 2.0
JITTER = True  # Add randomization to prevent thundering herd
```

#### Implementation
```python
async def calculate_retry_delay(attempt: int) -> float:
    delay = min(BASE_DELAY * (BACKOFF_MULTIPLIER ** attempt), MAX_DELAY)
    if JITTER:
        delay *= (0.5 + random.random() * 0.5)  # 50-100% of calculated delay
    return delay

async def retry_deployment(task: QueuedDeploymentTask) -> bool:
    if task.retry_count >= DEFAULT_MAX_RETRIES:
        await mark_deployment_failed(task.deployment_id, "Max retries exceeded")
        return False

    task.retry_count += 1
    delay = await calculate_retry_delay(task.retry_count)
    await asyncio.sleep(delay)
    await queue_deployment_task(task)
    return True
```

## Implementation Recommendations

### Phase 1: Critical Mitigations (Immediate)

#### 1.1. Basic Rate Limiting
```python
# Add to deployment router
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

@router.post("/", dependencies=[
    Depends(get_current_active_user),
    Depends(RateLimiter(times=10, minutes=1))  # 10 deployments per minute
])
async def start_deployment(...):
    # Existing code
```

#### 1.2. Per-Service Deployment Lock
```python
# Add to model.py
class Service(EventsMixin):
    _deployment_locks = {}  # Class-level lock registry

    def acquire_deployment_lock(self) -> bool:
        if self.id in self._deployment_locks:
            return False  # Already deploying
        self._deployment_locks[self.id] = True
        return True

    def release_deployment_lock(self):
        self._deployment_locks.pop(self.id, None)
```

### Phase 2: Queue Implementation (Short-term)

#### 2.1. Add Dependencies
```bash
# Add to pyproject.toml
dependencies = [
    # existing dependencies...
    "dramatiq[redis]>=1.13.0",  # For production-ready queuing
    "redis>=4.0.0",
]
```

#### 2.2. Queue Service Implementation
```python
# New file: src/deploy/adapters/queue.py
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AgeLimit, TimeLimit, Retries

redis_broker = RedisBroker(host="localhost", port=6379, db=0)
dramatiq.set_broker(redis_broker)

@dramatiq.actor(
    max_retries=3,
    min_backoff=2000,  # 2 seconds
    max_backoff=300000,  # 5 minutes
    queue_name="deployments"
)
def process_deployment(deployment_id: int):
    # Move existing deployment logic here
    pass
```

#### 2.3. Update Handlers
```python
# Modify handlers.py
async def start_deployment(command: commands.StartDeployment, uow: AbstractUnitOfWork):
    # Create deployment record (existing code)
    # ...

    # Queue deployment instead of immediate execution
    process_deployment.send(deployment.id)
    # No longer call: deployment.start_deployment_task(service)
```

### Phase 3: Advanced Features (Long-term)

#### 3.1. Queue Monitoring Dashboard
- Queue length metrics
- Worker health status
- Failed job analysis
- Performance metrics

#### 3.2. Dynamic Scaling
- Auto-scale workers based on queue depth
- Resource-aware scheduling
- Load balancing across multiple instances

#### 3.3. Priority Queues
- Emergency deployment queue (rollbacks)
- Scheduled deployments
- Bulk operation queue

## Monitoring and Metrics

### 3.1. Key Metrics to Track

#### Queue Metrics
```python
# Prometheus metrics to implement
queue_depth = Gauge('deployment_queue_depth', 'Number of pending deployments')
active_workers = Gauge('deployment_active_workers', 'Number of active deployment workers')
deployment_duration = Histogram('deployment_duration_seconds', 'Time to complete deployment')
deployment_failures = Counter('deployment_failures_total', 'Number of failed deployments', ['service_id', 'reason'])
```

#### Resource Metrics
```python
concurrent_deployments = Gauge('concurrent_deployments', 'Currently running deployments')
per_service_active = Gauge('per_service_active_deployments', 'Active deployments per service', ['service_id'])
retry_attempts = Counter('deployment_retry_attempts_total', 'Deployment retry attempts', ['service_id'])
```

### 3.2. Health Checks

#### Queue Health Endpoint
```python
@router.get("/health/queue")
async def queue_health():
    return {
        "queue_depth": await get_queue_depth(),
        "active_workers": get_active_worker_count(),
        "failed_workers": get_failed_worker_count(),
        "oldest_queued_job": await get_oldest_queued_job_age(),
        "status": "healthy" if all_workers_healthy() else "degraded"
    }
```

#### Resource Monitoring
```python
@router.get("/health/resources")
async def resource_health():
    return {
        "cpu_usage": psutil.cpu_percent(),
        "memory_usage": psutil.virtual_memory().percent,
        "open_file_descriptors": len(psutil.Process().open_files()),
        "active_processes": len([p for p in psutil.process_iter() if 'deploy' in p.name()]),
    }
```

### 3.3. Alerting Rules

#### Critical Alerts
- Queue depth > 100 jobs
- No workers active for > 5 minutes
- Deployment failure rate > 50%
- Memory usage > 90%

#### Warning Alerts
- Queue depth > 50 jobs
- Average deployment time > 10 minutes
- Worker restart rate > 5/hour

## Security Considerations

### 3.1. Queue Security
- Encrypt queued job data containing sensitive deployment context
- Implement job authentication to prevent queue poisoning
- Audit trail for all queue operations

### 3.2. Resource Limits
- Container-level resource limits for deployment workers
- Timeout enforcement for stuck deployments
- Automatic cleanup of orphaned processes

### 3.3. Access Controls
- Queue management API requires admin privileges
- Per-service deployment quotas based on user roles
- Rate limiting based on authentication context

## Conclusion

The current fastDeploy implementation has **zero concurrency controls**, making it vulnerable to resource exhaustion attacks and creating poor user experience through resource contention. The immediate risk is **HIGH** as any authenticated user can easily overwhelm the system.

**Immediate Actions Required:**
1. Implement basic per-service deployment locking
2. Add rate limiting to deployment endpoint
3. Monitor system resources

**Short-term Implementation:**
1. Implement proper job queue system
2. Add worker pool with configurable limits
3. Implement retry mechanism with exponential backoff

**Long-term Enhancements:**
1. Advanced queue management and monitoring
2. Dynamic scaling and load balancing
3. Comprehensive metrics and alerting

The security review critique is completely accurate, and this issue should be prioritized due to its potential for system-wide impact.
