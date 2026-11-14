Unreleased
==========

### Fixed
- Revalidate service JWTs under launch admission locks, including revocation,
  record/JWT expiry, issuer existence and legacy cutoff, before creating a run.
- Refuse malformed JWT identity claims before repository access with 401.
- Admit timezone-aware step start times with a five-minute future-skew bound;
  normalize starts to UTC while preserving server finish times and retry identity.
- Share the API database engine for one lifespan, with isolated request sessions
  and explicit CLI schema setup instead of per-request table creation. The shared
  engine uses no connection pool (NullPool): each request or websocket still opens
  its own connection, so long-lived websockets cannot exhaust a shared pool.
- Remove raw exception messages and tracebacks from message-bus failure logs,
  preserving bounded categories, IDs and command/event outcomes.
- Keep pending login reservations through window expiry and key pruning until
  verification settles, including cancellation waiting for hash work.
- Upgrade soupsieve 2.9 to 4.1 for CVE-2026-126190 and related selector denial-of-service
  advisories, with beautifulsoup4 4.14.2 to 4.15.0. Require Python 3.11.5+ to support
  soupsieve's regular-expression implementation; refresh the frozen uv lock.
- Admit complete step REST snapshots before reconciling any indexes. Reject malformed,
  duplicate or wrong-deployment rows and project declared fields while preserving live
  event/session fences and last-good state. Requires a frontend rebuild.
- Validate service rows and available-name lists before publication; retain last-good
  state with bounded request-local feedback for invalid responses. Requires a frontend rebuild.
- Reject non-boolean `deleted` flags in step/service REST snapshots, matching websocket
  admission; both paths share one set of wire predicates. Requires a frontend rebuild.
- Keep websocket activity visible for a full second after the latest message with
  one owned timer; cancel activity expiry on store/session reset. Requires a frontend rebuild.
- Bound frontend HTTP calls, including response decoding, to 30 seconds. Compose
  caller cancellation, retire request timers/listeners and release loading/event
  fences on timeout without retrying ambiguous mutations. Requires a frontend rebuild.
- Refuse ambiguous, excessively nested or invalid numeric runner JSON records while
  continuing stdout draining. Only malformed lines opening a JSON object with a member
  name count as protocol records; other console output such as Ansible `[WARNING]:`
  lines stays ignored. Named JSON lines that are not valid step reports fail the run. Prevent exit-zero scripts with invalid protocol or
  unacknowledged step reports from finishing successfully; require an accepted
  failure report or leave the deployment unfinished. Requires a runner package update.
- Settle remaining owned descendants after successful script exit as well as failure.
  Keep one bounded process cleanup task alive through repeated cancellation, retire
  credentials afterwards and preserve the original cancellation. Unconfirmed cleanup
  prevents success; service-manager sessions remain outside runner ownership.
  Requires a runner package update.
- Refresh authoritative frontend snapshots after authenticated websocket reconnect;
  remove absent steps/history rows while preserving intervening live events and
  deployments started during the request; a history refresh that loses ownership
  shows the retry message instead of an empty list.
- Fence service-name requests by generation and session, retain confirmed names on
  failure and show a retry action. Requires a frontend rebuild.
- Serialize service sync source reads and database decisions through commit using a
  transaction advisory lock; refuse duplicate private runner JSON members at every depth.
  Requires an API/CLI and runner package update.
- Reject startup when the deployment token cannot cover the configured runtime
  plus bounded teardown/final reporting (2731 seconds). The default runtime
  requires at least 76 token minutes; defaults are unchanged. The runner process
  receives the token lifetime so it validates the same combination. Requires an API restart.
- Reject duplicate JSON/YAML mapping keys (and repeated `<<` merge keys) and malformed
  deploy_script/steps before service sync changes records or emits events. Preserve
  extension fields, bounded ordinary YAML aliases and standard merge overrides.
  Requires an API/CLI update.
- Track event-bearing objects independently of mutable entity hashes and transient ids.
- Revoke service tokens transactionally on service deletion/sync deletion; serialize
  issuance with deletion so name reuse does not restore recorded token authority.
- Bound service config/playbook reads, validate shapes and refuse aliases or traversal
  outside approved roots before sync writes. Add explicit SERVICE_PLAYBOOK_ROOTS approval.
- Reject malformed JWT numeric dates as invalid credentials, including overflow.
- Give browser login submissions latest-attempt ownership and private request options.
- Validate service-token origins against storage limits before issuance or cleanup.
- Recheck current credentials after password verification before issuing a login token.
- Fence browser WebSocket callbacks and reconnect waits to the current socket.
  Validate domain/control envelopes and allowlist converted fields before dispatch; invalid frames close the
  connection with a payload-free diagnostic and require a refresh. Requires a frontend build.
- Serialize per-connection WebSocket sends, including the lock wait in the send
  deadline; discard stale queued frames on disconnect. Drain manager-owned sockets,
  expiry timers and close tasks during FastAPI lifespan shutdown. Requires a backend restart.
- Stop/reap the owned detached process group and remove its config when the
  launcher supervisor cannot start, with a 300 ms total cleanup budget. Preserve
  the startup error as the failure cause.
- Bound private config reads/writes to 1 MiB and validate UTF-8/JSON and required field
  shapes. Configured invalid files fail closed before task startup with value-free
  diagnostics. Unset config paths retain environment fallback. Requires a task-runner update.
- Limit history reconciliation to 50 oldest eligible deployments per request,
  selecting ids with a single bulk activity query before locked rechecks.
- Refuse overlapping/reentrant calls on one message bus before replacing its
  active queue; release ownership after success, failure or cancellation.
- Preserve handler/commit failures and cancellation when UOW rollback also fails;
  record a bounded cleanup category and retain request resource teardown.
- Load the deployment launch definition under the service lock and retain it
  through planning and admission, avoiding stale scripts after concurrent sync.
- Censor task names and result payloads in the retained Ansible JSON callback when
  task `no_log` or result `_ansible_no_log` is set. Add skipped/unreachable
  observations using supported states, explicit outcomes and ignored-failure
  metadata. Requires installing the updated callback with retained runners.
- Reconcile service refreshes authoritatively, retaining intervening websocket
  mutations and confirmed deletions; ignore superseded fetch results/errors.
- Preserve newer step updates/deletions during hydration and deduplicate running
  scroll history. Retain route/session guards and retry cleanup.
- Retire launch navigation when the originating view/route changes; retain a
  confirmed deployment without redirecting from a newer page or retrying it.
  These UI fixes require a frontend build; no deploy is performed here.
- Confirm named service/history deletion, await its result, retain rows on failure
  and show retryable row errors; prevent duplicate pending deletion/launch actions.
- Show contextual launch failures and navigate only on current-session success.
- Roundtrip service history filters through deployment URL queries, resetting
  paging on navigation and rejecting obsolete responses. Requires a frontend build.
- Use a labeled native login form with credential autocomplete, announced errors
  and duplicate-submit protection; add a Chromium keyboard regression to CI.
- Keep service/deployment details reactive to route and store changes, with explicit
  loading, missing and retry states. Fence token results and step fetches so late
  responses cannot replace the current identity/result. Requires a frontend build.
- Preserve generic 500 responses for unexpected service-delete and deployment
  start/finish failures; only established missing/conflict/validation cases are 4xx.
- Close partially initialized bootstrap resources on startup failures, preserving
  the primary exception if cleanup also fails. Requires an API/tool update.
- Authentication backend failures now return a safe 500 with category-only diagnostics,
  preserving the failed-password allowance. Invalid credentials still return 401.
- Bound process-wide login work with `LOGIN_MAX_CONCURRENT` (default 4, 1–64).
  Saturation returns 429/Retry-After without queuing work; cancellation retains the
  slot until a running password check exits. Requires an API restart.
- Validate task retry counts (1–8) and finite initial backoff (0–10 seconds) before
  deployment-script startup, on assignment and at the request helper boundary.
  Defaults and exponential retry delays are unchanged; invalid inputs no longer
  silently skip API calls. Requires a task-runner update.
- Forget and close websocket connections after ordinary broadcast send errors,
  cancelling expiry timers while preserving healthy peers and replacements.
  Requires updating/restarting the backend.
- Bound deployment output/reporting and process exit with `DEPLOYMENT_MAX_RUNTIME_SECONDS`
  (default 1800, finite >0 and <=86400). Expiry uses owned-group termination,
  secure-config cleanup and failure reporting. Requires a task-runner update.
- Stream report/finish responses with 4096-byte wire and 10-second elapsed limits per
  attempt, closing responses and retrying budget failures as transport errors.
- `createuser` exits with status 1 when creation fails, allowing automation to
  detect the failure. An existing username exits with status 0 without changing
  its password, preserving repeated bootstrap in the bundled Ansible tasks.
  Other automation that relied on creation errors returning success must handle
  the nonzero status. Successful creation still exits with status 0.
- Deployment list hydration preserves websocket updates and deletions received while a
  request is in flight; ordinary refreshes and logout guards are retained.

### Tests
- Inject mid-sync save/delete faults in real transactions to protect atomic service
  additions, edits, history cascades and post-commit service events.
- Cover both database lock orders for finishing versus the final step report,
  and admission rollback on flush, planned-step insertion and deferred commit faults.
- Race identical and conflicting step reports on independent PostgreSQL connections;
  assert actual row-lock blocking, one persisted result and one processed event.
- Synthetic message-bus regressions for FIFO follow-ups, initial command results,
  event-handler recovery, command failure and cancellation during handler awaits.
  Protects existing dispatch behavior; no runtime change or deployment required.
- Add database-free CLI regression coverage for service-token inventory,
  revocation, purge retention/validation and resource cleanup, plus initial-user
  environment and interactive credentials without exposing passwords or hashes.

### Security
- Require Python 3.11 or later and refresh dnspython 2.9.2, filelock 4.2.10, Tornado 6.6.1,
  virtualenv 21.15.6 and setuptools 84.2.1 (with distlib 0.4.4 and packaging 26.3, which
  virtualenv needs). This clears CVE-2026-114605 (dnspython, runtime through FastAPI's email
  validation), 13 filelock, 3 Tornado and 11 virtualenv CVEs and GHSA-xmj3-9gf7-h52w
  (setuptools). The fixed dnspython, filelock and Tornado releases need Python 3.11+, and
  Python 3.10 is end of life; nothing deploys or tests FastDeploy on 3.10 (production uses
  3.14, CI 3.13). Dropping 3.10 also clears the 3.10-only ansible-core 2.17.14 advisory
  PYSEC-2026-3458. Requires a dependency sync on deploy.
- Add independent frozen Python 3.11/3.14 and full npm lock audits on push and a weekly
  schedule, with fatal export failures and synthetic gate regressions.
- Refresh Vitest/UI and happy-dom and scope patched glob/minimatch overrides to
  js-beautify, clearing all eight affected frontend development dependency nodes.
  Verify glob/EditorConfig compatibility with synthetic CLI fixtures; no deploy needed.
- Bound websocket authentication/expiry control sends to 5 seconds and close handshakes
  waits (including endpoint cleanup) to 1 second, preserving connection and timer cleanup.
  Let the server finish transport teardown under its own deadline after that wait.
- Mark token issuance and full service/configuration responses private/no-store and vary
  by Authorization while preserving CORS variation. Credential roles are unchanged.
  These API and websocket protections take effect after updating/restarting the backend.
- Restrict HTTP service-token revocation to `SERVICE_TOKEN_ADMIN_USERS`, before looking
  up the token id. Administrator revocation remains idempotent; CLI revocation is unchanged.
- Apply CLI service-token issuance validation to the HTTP API: unknown services/users and
  blank origins return 422 without recording a token, after the administrator check.
- Update the locked certifi CA bundle to 2026.10.19 for the eMudhra/emSign CA compromise
  ([GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2)).
  Lock-only change. Re-sync deployed environments and restart long-running processes so they load
  the new bundle.
- Restrict `POST /service-token` to existing users named in `SERVICE_TOKEN_ADMIN_USERS`
  (default `[]`, non-admins receive 403). Existing tokens and server-local administrative
  issuance remain supported. The UI can start runs only for configured administrators; it shows
  issuance refusals without sending a deployment request with a missing token.
- Validate Echoport restore bucket and archive key against `RESTORE_POLICIES`, keyed by the
  authenticated service name. Missing policy, wrong bucket, traversal, absolute paths and URL
  keys receive 422 before any run starts. A policy lists `prefixes`, so a runner shared by several
  targets, or a renamed target with older archives, can allow each prefix. All run types continue to select only the token's
  registered service. Unset, both settings fail closed (API issuance and UI-started runs get 403,
  restores get 422); existing tokens, backups and CLI issuance keep working. Configure the admin
  list and restore policies before restart; no migration or token rotation is needed. See [authentication docs](docs/auth.md#restore-input-policy).
- INFO logs in the service-layer and websocket publishers include only event class and identifiers,
  excluding context and configuration; the websocket publisher no longer prints events to stdout.
  Authorized websocket payloads are unchanged.
- Message-bus DEBUG and handler failure logs include only the message class and identifiers,
  retaining failure tracebacks without logging message or handler reprs. Deployed-service insertion
  emits no stdout output.
- A websocket connection that has not authenticated within `WEBSOCKET_AUTH_TIMEOUT_SECONDS` (default 10)
  after it was accepted is closed with code `1008` and the reason `authentication timeout`. The time
  covers waiting for the token and verifying it. Before, a client could keep any number of connections
  open without ever sending a token. Clients that send their token right after connecting (the web UI
  does) are not affected.
- Validate temporary configuration type and permissions on an open no-follow descriptor.
  Cleanup and exit cleanup refuse symlinks, hard links, untracked files and replaced
  paths, preserving the identity of configs created by this process. The launcher
  cleans its config after the detached task exits or fails to start. See the
  owner/group and trusted-directory contract in [deployment docs](docs/deployment.md).

### Breaking
- Lifecycle configuration now rejects nonfinite websocket timeouts and durations outside
  the [README ranges](README.md#configuration) at startup. Check existing environment values
  before upgrading; previously accepted zero, negative or oversized values may need adjustment.
  Defaults are unchanged.
- `GET /deployments/` returns the newest 50 rows by default (at most 200 with `limit`),
  ordered by descending id. Use exclusive `before_id` cursors to traverse history and
  optional `service_id` filtering. The JSON array shape is unchanged; consumers must
  request older pages explicitly. The UI provides Load more and resets paging on
  service navigation or logout. Orphan scans no longer load completed history.
- Step reports (`POST /steps/`) accept only the states `running`, `success` and `failure`; any other
  state (`pending`, an unknown or misspelled one) returns 422 without mutation, and domain processing
  rejects it as well. Before, `state` was any string of up to 20 characters. Deploy scripts that report
  `running` when a step starts and its result when it ends keep working unchanged; a line with another
  or an omitted state (the task defaults it to `pending`) receives a non-retried 422 and a dropped-step
  stderr diagnostic. This corrects the note of the first version of this change, which accepted only
  `success` and `failure` and asked for scripts to stop reporting `running`: that dropped the progress
  reports of every existing deploy script (each got a 422), while results were still recorded.
- A `running` report of a step that is already running no longer moves the next planned step to
  `running`; only a `success` result does. A `running` report never changes a step that has a result.
- `deploy_script` in a service's `config.json` is the path of one executable and no longer a shell
  command line. A value with spaces is now one path: `"deploy.sh --flag"` used to run `deploy.sh` with
  the argument `--flag` and now fails, because no file of that name exists. The same holds for shell
  syntax (`;`, `&&`, `$VAR`, quotes, globs), which is passed on literally. Values that are a plain
  relative or absolute path (all shipped and documented configs) behave as before. A script that needs
  fixed arguments has to be wrapped in a script of its own.

### Security
- Web UI: a logout ends the whole login session, not just the stored access token. Before, it cleared
  only the token: the services, deployments and steps stores kept their data and their HTTP clients with
  the old `Authorization` header, the websocket client was not kept anywhere and reconnected with the
  old token when its connection closed, and a response still in flight was written into the stores
  afterwards. Now the websocket client is disposed (handlers detached, connection closed, no reconnect,
  no message delivered, the old token is not sent on a connection that opens late), the stores and the
  websocket status are reset and get clients without `Authorization` header, the password is cleared
  (also from the login request options, and already after a successful login), and responses of
  requests started in an earlier session are dropped. A request for a deployment whose service token
  arrives after the logout is not sent, and a start response that arrives after the session ended no
  longer navigates the UI (possibly already the next user's) to that deployment. A client created while logged out no longer carries
  `Authorization: Bearer null`. The logout happens, as before, when the server rejects the websocket
  authentication; the next login starts with empty stores and a websocket of its own. Frontend assets
  only, no API change. See [docs/architecture.md](docs/architecture.md#login-session).
- `POST /steps/` rejects a `name` longer than 255 and a `message` longer than
  4096 characters with `422` (before: a database error answered as `400` on PostgreSQL, no limit
  elsewhere). `POST /deployments/` rejects a context whose JSON encoding is larger than
  `DEPLOYMENT_CONTEXT_MAX_BYTES` (default 65536) with `413` and starts nothing; before, a context of any
  size was stored and sent to every websocket client. The deploy task already cuts step messages to
  4096 characters. See [docs/endpoints.md](docs/endpoints.md).
- The deploy task starts the deploy script as an argument list (`sudo -u <SUDO_USER> <script> --config
  <file>`) instead of a shell command line, so shell syntax in a service's `deploy_script` or in
  `SUDO_USER` is no longer interpreted. sudo gets the same command as before; existing service configs
  and sudoers rules work unchanged.
- `POST /token` limits failed logins: after `LOGIN_FAILURE_LIMIT` (default 10) failed attempts for one
  user name from one client address, or `LOGIN_ADDRESS_FAILURE_LIMIT` (default 50) from one client address
  for any user names, inside `LOGIN_FAILURE_WINDOW_SECONDS` (default 900), it answers `429` with a
  `Retry-After` header and does not check the password. Before, passwords could be guessed without
  limit. The password hash check now runs in a worker thread instead of blocking the event loop (a
  stream of login attempts could stall step reports of running deployments), and it is also spent on
  unknown user names, so the response time no longer tells whether a user exists. Valid logins and
  issued tokens are unchanged; the web UI shows a message for `429`. See [docs/auth.md](docs/auth.md).
- Replace python-jose and its ecdsa dependency with PyJWT for all JWT issuance and verification.
  Preserve existing signed tokens, expiry handling, revocation and the legacy service-token grace
  window; restrict configuration to the supported HMAC algorithms.
- Upgrade dependencies with known advisories to fixed versions. Runtime: starlette 1.3.1 (with
  FastAPI 0.141.1), python-multipart 0.0.31, anyio 4.14.2, urllib3 2.8.0, orjson 3.11.6, idna 3.15,
  pygments 2.20.0 and python-dotenv 1.2.2; ujson is no longer installed. Development and docs:
  jupyterlab 4.6.4, notebook 7.6.3, jupyter-server 2.21.0, tornado 6.5.9, mistune 3.3.3, nbconvert
  7.17.1, bleach 6.4.0, pytest 9.0.3, mkdocs-material 9.7.7, pymdown-extensions 11.0.1, requests
  2.33.0, setuptools 83.0.0, soupsieve 2.9, filelock 3.32.7 and virtualenv 21.7.13. `pip-audit`
  reports no known advisories for the locked runtime and development sets afterwards. FastAPI stays
  below 0.142, which would add OpenTelemetry packages to the runtime install.

### Features
- `python commands.py issueservicetoken --service S --user U --days N [--origin O]` issues a recorded,
  revocable service token (with `jti`) from the command line, so playbooks and operators can replace
  legacy tokens without a web login. `--days` is capped by `SERVICE_TOKEN_MAX_EXPIRE_DAYS`; the user
  and the service must exist. Only the token is printed on stdout (its `jti` and expiry go to stderr);
  a refusal exits with status 1. See the legacy token cutover in [docs/auth.md](docs/auth.md).
- Single-flight deployments per service: `POST /deployments/` returns `409 Conflict` with the running
  deployment id while the service already has an active deployment, instead of spawning a second
  concurrent deploy. Check and insert are serialized by a database row lock on the service, orphaned
  deployments of the service do not block (they are finished as failed as part of a successful start), and deployments older than the deployment token
  lifetime no longer block. Addresses the per-service limit from security review #07.

### Bug Fixes
- Deploy scripts get the id of their deployment as `deployment_id` in the config file passed with
  `--config` (as a string, e.g. `"42"`), as the deployment docs promise. Before, it was always
  `"deploy_subprocess"`. The auth docs now state the deployment token lifetime of 480 minutes
  (`DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES`) and that the token is passed in the config file, not in an
  environment variable.
- The steps planned for a new deployment come from the last successful deployment of the service again.
  A deployment counted as successful as long as it had at most one failed step, so a deployment that
  failed in one step (or was finished as orphaned) became the plan for the next one, including its
  failure step and without the steps that never ran. Now a deployment with any failed step is not
  successful in either repository, and the plan comes from the last deployment whose steps all succeeded,
  or from the service config.
- Deploy task: a JSON object without a `name` on the deploy script's output is no longer printed as a
  whole to stdout. It is logged to the task's stderr like every other skipped or dropped result, with
  its size and up to 10 shortened keys and never its values, which may hold secrets.
- Web UI: a deployment started with the deploy button shows up under its service at once. The response of
  `POST /deployments/` was stored as received (`service_id`, dates as strings) while the store is read
  by `serviceId`, so the new row was missing from the service's deployments and its progress display
  until a websocket message for it arrived. The response is now converted like fetched and websocket
  deployments. It also no longer replaces a row the websocket already delivered: a deployment that
  finished before the start response arrived stays finished instead of showing as running again.
- `DELETE /services/{service_id}` no longer deletes a service whose deployment is still running. Deleting it removed
  the deployment and its steps while the detached deploy task kept running untracked. The delete now takes the same
  service lock as a deployment start, applies the same "active deployment" rule as the services sync, and answers
  `409 Conflict` with the running deployment id; nothing changes. Services without a running deployment are deleted
  as before.
- The deploy task no longer abandons a running deploy script. Output that was not valid UTF-8, an output line over
  10 MiB or a cancelled task ended the task before it waited for the script, which kept running while the deployment
  was already reported as failed. Invalid bytes are now replaced with U+FFFD (a step result containing them is still
  reported, other such lines are skipped), an over-limit line is skipped as a whole, the script runs in its own
  process group, and when the task stops reading early it terminates that group (`SIGTERM`, then `SIGKILL` for
  members still alive after 10 seconds, including descendants that outlive the script) and reaps the script before
  removing the config file. A script running as another user through `sudo` may refuse the signal; see
  [docs/deployment.md](docs/deployment.md).
- One slow websocket client can no longer hold back deployment events for everybody else. A broadcast sent to the
  clients one after another without a time limit, so a client that stopped reading blocked all later clients and the
  request that published the event. Sends now run concurrently with a 5 second budget each; a client that exceeds it
  is closed with code `1013` and removed, and has to reconnect.
- A services sync (`POST /services/sync`, `commands.py syncservices`) no longer wipes the
  deployment history when the services directory is empty or mis-pointed: it is refused (409 /
  exit status 1, nothing changed) when no services are found while the database has some, or when
  more than half of the services would be deleted, unless `force` (`?force=true` / `--force`) is
  given. Services with a running deployment are never deleted and are reported as skipped. The
  response and CLI output list the updated, deleted and skipped services. Deploy note: the Ansible
  deploy runs `syncservices`, so a deploy with an empty or mostly removed services directory now
  fails at that task instead of deleting the services.
- The web frontend shows a refused services sync (409) instead of only logging it: the refusal
  message and the services that would be deleted are displayed, with a "force sync" button that
  retries with `force=true` after confirmation. Other sync failures are shown as well.
- The deploy task no longer leaves a deployment "active" (blocking new deploys of the service until the deployment
  token expires) after a network error while reporting: posting a step retries connection errors and `5xx` with
  exponential backoff and never aborts reading the deploy script output, a step that cannot be reported is logged to
  stderr instead of being dropped silently, output lines that are not a JSON object are skipped, finishing the
  deployment has its own retries, and a failure there no longer replaces the original deploy error. A failed deploy
  whose failure step cannot be reported is not finished as an apparent success. A non-string `error_message` (for example an Ansible `msg` list) is
  converted to text instead of being rejected with 422.
- Repeated step reports are idempotent. When the response to a processed `POST /steps/` was lost and the deploy
  task sent the report again, the already finished step was treated as unknown and stored a second time (or the
  retry consumed a later planned step of the same name). A report is now identified by its step name and started
  timestamp: the same result again changes nothing and is answered like the first report; a different state or
  message for it is rejected with `409 Conflict`. Steps sharing a name with different started timestamps stay
  separate steps.
- Starting a deployment stores the deployment and its planned steps in one transaction before the detached deploy
  task is launched. Previously the task was launched first, so a fast task could report its first step before the
  planned steps existed and that step was stored twice. If the deploy task cannot be started, the deployment is now
  finished as failed immediately (a `deployment launch failed` step records the error type, details are logged) and
  `POST /deployments/` answers `500` with the deployment id, instead of `400` with an unfinished deployment that
  blocked the service until the orphan cleanup.
- Orphaned deployments are no longer recorded as successful. A deploy whose script failed after every step was
  already reported as successful, while the API was unreachable for the failure step, used to be finished by the
  orphan cleanup and then looked successful. The orphan cleanup (on `GET /deployments/`,
  `GET /deployments/{deployment_id}` and a successful start of the same service) now finishes such deployments as
  failed: it adds a `deployment orphaned` step with state `failure` whose message records the reason. The step is
  returned by the API with the other steps, broadcast over the websocket and shown as a failed step in the web
  frontend; a late finish from the deploy task does not change it, and it is not copied into the step list of the
  next deployment. `DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS` now counts from the latest activity (deployment start
  or last step start/finish) instead of only the start, so a long deployment whose task is still retrying to finish
  it is not finished early; until then it keeps blocking new deploys of the service and services sync keeps the
  service. The cleanup re-checks a deployment under the service lock and a row lock on the deployment before
  finishing it; finishing a deployment and processing a step take the same deployment row lock, so a deploy task
  finishing concurrently is never marked as orphaned.

### Security
- Frontend dependencies refreshed to clear all 20 `npm audit` advisories (2 critical, 15 high,
  3 moderate) without major upgrades: `npm audit fix` updates `vue` to 3.5.43, `vite` to 7.3.7 and
  their transitive packages (`rollup`, `postcss`, `nanoid`, `uuid`, `happy-dom` and others), and the
  `vitest`/`@vitest/ui` floors move to `^4.1.11`, since `npm audit fix` cannot move that pair on its
  own (`@vitest/ui` pins its exact `vitest` version). `npm audit` now reports 0 vulnerabilities.
- `GET /deployments/{deployment_id}` checks that the deployment belongs to the token's service before
  reconciling an orphaned deployment, so a service token can no longer finish another service's
  deployment by reading it. A deployment of another service now returns the same `404 Deployment not
  found` as an unknown id (was `403 Wrong service token`), so the endpoint no longer reveals which ids
  exist. `GET /steps/?deployment_id=` returns 404 instead of 500 for an unknown deployment.
- Websocket authentication hardening (`/deployments/ws/{client_id}`): any failed authentication
  (including a valid service, deployment or config token, or a token for a deleted user) now sends
  an authentication failure and closes the connection (code `1008`) instead of leaving it
  registered. Connection cleanup runs on every exit path, so rejected or server-closed sockets no
  longer accumulate in memory.
- A client id that is still connected can no longer be taken over: a second connection with the
  same id is refused, the id is bound to the authenticated user for the connection's lifetime
  (re-authenticating as another user closes the connection), and the "client left" broadcast no
  longer includes the client id. Only authenticated connections receive or trigger broadcasts.
- Service tokens can be revoked. Every issued service token carries a `jti` claim and is recorded
  in the new `service_token` table (service, origin, user, issue/expiry time, revocation time).
  Unknown or revoked token ids and tokens of deleted users are rejected with 401. Revoke via
  `DELETE /service-token/{jti}` or `python commands.py revokeservicetoken <jti>`; list with
  `python commands.py listservicetokens`. `POST /service-token` now also returns `jti` and
  `expires_at`. The maximum lifetime is lowered from 180 to 90 days (`SERVICE_TOKEN_MAX_EXPIRE_DAYS`)
  and the web frontend now suggests 7 instead of 30 days.
- Deploy note: legacy service tokens without `jti` (all tokens issued before this release, e.g. in
  CI secrets) are rejected unless `LEGACY_SERVICE_TOKENS_ACCEPTED_UNTIL` is set (ISO 8601) to give
  a time-limited transition window. The `service_token` table is created automatically on startup
  (`create_all`), no manual migration is needed.
- Each connection has at most one session expiry timer; re-authentication replaces it and
  disconnecting cancels it, so stale timers no longer close re-authenticated sessions or a newer
  connection reusing the id.
- Service token records no longer accumulate: records of tokens that expired or were revoked more
  than `SERVICE_TOKEN_RETENTION_DAYS` (default 30) days ago are deleted whenever a service token is
  issued, and on demand with `python commands.py purgeservicetokens [--older-than-days N]`.


### Development
- GitHub Actions CI (`.github/workflows/ci.yml`) runs `just lint`, `just typecheck` and the
  pytest suite against a `postgres:17` service container, plus the frontend Vitest suite and
  build, on every branch push and on pull requests. Actions are pinned by commit SHA, permissions
  are read-only and no secrets are used.
- The stale, manual-only `deploy.yml` workflow is removed. It posted to the staging deploy API
  with an unpinned third-party action and echoed the response through a shell line (a script
  injection pattern); deploys go through the Ansible playbooks.
- The test configuration only sets `DATABASE_URL` as a default, so it can be overridden from the
  environment (CI uses this to reach its service container).
- The Python test suite runs on a clean checkout without a frontend build: the test setup creates
  the git-ignored `frontend/dist` directory that the app mounts at import time.
- `just lint` / `just lint-fix` run the pinned ruff 0.14.0 via `uvx` (same version as the
  pre-commit hook) instead of expecting ruff in the virtualenv, and the code base is lint- and
  format-clean. FastAPI `Depends`/`Query` defaults are whitelisted for bugbear's B008. Domain
  models no longer share mutable default arguments (`context`, `steps`, `data`, `config`) between
  instances, and the service cascade test now actually asserts that deployments are deleted.

0.2.0 - 2025-09-01
==================

### Major Changes
- **Python Packaging**: Migrated to hybrid src layout with UV build backend
  - Backend code moved to `src/deploy/` following Python best practices
  - Frontend remains at root level to maintain JavaScript conventions
  - Package imports remain unchanged (`from deploy import ...`)
- **Frontend Testing**: Migrated from Jest to Vitest for better Vite integration
- **Python 3.13 Support**: Full compatibility with Python 3.13
- **Developer Experience**: Added comprehensive justfile for task automation
- **Code Quality**: Migrated from black/isort/flake8 to ruff for faster, unified linting

### Features
- Add justfile with comprehensive development commands
- Add support for Python 3.12 and 3.13
- Switch to UV for dependency management and lockfile handling
- Add deployment convenience commands to CLI
- Add CLAUDE.md for AI assistant instructions
- Frontend dependencies updated to latest versions (Vite 7.1, Vue 3.5, TypeScript 5.9)

### Refactoring
- Migrate to Pydantic v2 patterns (ConfigDict, model_dump, etc.)
- Migrate to hybrid src layout for better Python packaging
- Replace black/isort/flake8 with ruff
- Update all datetime.utcnow() to datetime.now(datetime.UTC)
- Modernize test fixtures for pytest-asyncio 1.1.0+

### Bug Fixes
- Fix httpx 0.28+ compatibility in e2e tests
- Fix pytest-asyncio 1.1.0 compatibility issues
- Fix UV build backend configuration for package name mismatch
- Fix pydantic URL validation from Starlette
- Update all Jest references to Vitest

### Documentation
- Comprehensive README update with current setup instructions
- Add project structure documentation
- Update MkDocs documentation for current project state
- Add CLI documentation for new commands
- Document trunk-based development workflow

### Dependencies Updates
- **Backend**: FastAPI 0.115+, SQLAlchemy 2.0+, Pydantic 2.0+, httpx 0.27+
- **Frontend**: Vite 7.1, Vue 3.5, TypeScript 5.9, Pinia 3.0
- **Testing**: pytest-asyncio 0.24+, Vitest (replacing Jest)
- **Build**: UV 0.8.14+ with uv_build backend

### Development Infrastructure
- Pre-commit hooks configuration with ruff and mypy
- Support for UV package management
- Improved Docker and deployment configurations
- Environment variable handling for tests

0.1.2 - 2022-03-21
===================

### Features
- use mixin to raise events after uow context manager exits
    - #9 issue by @ephes

### Refactoring
- increase coverage for adapters/filesystem.py
    - #22 issue by @ephes
- refactor command handlers
    - #18 issue by @ephes
- improve message bus dependency
    - #13 issue by @ephes
- use the same `get_user_by_name` function everywhere
    - #10 issue by @ephes
- use own message bus to sync services during deployment
    - #8 issue by @ephes
- fix repository method names
    - #6 issue by @ephes

### Fixes
- exception in `run_task` on long output
    - #24 issue by @ephes
- delete deployments and steps from frontend after service deleted event
    - #11 issue by @ephes

0.1.1 - 2022-02-29
==================

### Features
- add CHANGELOG.md
    - #3 - add CHANGELOG.md by @ephes

### Fixes
