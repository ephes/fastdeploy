"""Shared runner bounds used to admit a deployment token at API startup."""

DEPLOY_STOP_TIMEOUT = 10.0
REPORT_RESPONSE_TIMEOUT_SECONDS = 10.0
RETRY_MAX_ATTEMPTS = 8
RETRY_MAX_BACKOFF_SECONDS = 10.0
# TERM, KILL, reap; then failure report and finish, each at maximum retries.
# One extra second covers integer JWT expiry rounding.
DEPLOYMENT_FINALIZATION_SECONDS = (
    3 * DEPLOY_STOP_TIMEOUT
    + 2
    * (
        RETRY_MAX_ATTEMPTS * REPORT_RESPONSE_TIMEOUT_SECONDS
        + RETRY_MAX_BACKOFF_SECONDS * (2 ** (RETRY_MAX_ATTEMPTS - 1) - 1)
    )
    + 1
)
