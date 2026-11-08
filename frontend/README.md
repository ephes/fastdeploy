# Vue 3 + Typescript + Vite

This template should help get you started developing with Vue 3 and Typescript in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

## Recommended IDE Setup

- [VSCode](https://code.visualstudio.com/) + [Volar](https://marketplace.visualstudio.com/items?itemName=johnsoncodehk.volar)

## Type Support For `.vue` Imports in TS

Since TypeScript cannot handle type information for `.vue` imports, they are shimmed to be a generic Vue component type by default. In most cases this is fine if you don't really care about component prop types outside of templates. However, if you wish to get actual prop types in `.vue` imports (for example to get props validation when using manual `h(...)` calls), you can enable Volar's `.vue` type support plugin by running `Volar: Switch TS Plugin on/off` from VSCode command palette.

## Login and detail pages

Login uses labeled username/password fields with credential autocomplete. Enter in
either field submits the form; one request runs at a time and failures are announced
without clearing the inputs. Service details follow the current route and show
loading/missing/error states; token results and errors from a former service are
discarded. Validation details stay on the current detail page, without leaking
alerts back to the service list.
Deployment details refetch steps on navigation, show loading/error/retry states,
and never display a former deployment's steps. Metadata absent from loaded history
is identified explicitly. Older responses for the same deployment cannot overwrite
a newer fetch. Step hydration also preserves updates/deletions received by
websocket while that request is pending; repeated hydration keeps each running
step only once in scroll history.

Run `npm test` and `npm run build`. The native browser regression uses only intercepted
synthetic API/WebSocket fixtures: run `npx playwright install chromium` then
`npm run test:browser`. CI installs Chromium and runs the same keyboard check on Linux.

## Service actions and history

Each delete action names its service and asks for confirmation that its deployment
history will also be deleted. While deletion is pending, the same action cannot
be repeated. A refusal or transport failure stays visible in the row, which is
removed only after a successful response or a confirmed deletion event. Refresh
before retrying an uncertain deletion. Refresh replaces the service snapshot,
removing absent rows while preserving add/update/delete events received during
the request. Only the latest refresh owns its result and loading/error state.

Deploy buttons run one launch request at a time per service and show contextual
feedback for token, active-deployment and transport failures. Check history before
retrying an uncertain start; the UI never retries launches automatically. Navigation
requires a confirmed result belonging to the current login session and the
view/route where the launch began. Leaving the view (including navigating away
and back or changing its query) retires that navigation intent. A late confirmed
deployment remains in the store without redirecting or retrying the launch.

Service history links use `/deployments?serviceId=7`. Reloading, sharing and browser
back/forward retain the filter. Each filter change starts a new bounded page from
the newest deployments and drops old cursor/response state.

## Dependency security

Use Node 24 and `npm ci`, then `npm audit --package-lock-only` to audit the
complete lock (including development dependencies). The November refresh uses
Vitest/UI 4.1.12 and happy-dom 21.0.4. Their mock server and DOM execution
advisories affect developer/CI tooling, not the shipped Vue bundle.

The remaining glob/minimatch advisories require scoped overrides under
`js-beautify`: glob 14.0.4 and its EditorConfig dependency's minimatch 11.0.5.
Upstream js-beautify still requests vulnerable major ranges; these overrides
apply only to that chain. `tests/toolchain.spec.ts` exercises its public CLI's
glob expansion and EditorConfig matching with synthetic files. Remove the
overrides when upstream accepts patched ranges. Full lock audit: zero findings.
The previous lock reported GHSA-qxg6-89mg-rqv8, GHSA-xp26-3454-mjgp,
GHSA-834v-8h66-3h79, GHSA-c8p4-j97h-3vg8, GHSA-5fpq-26gf-qwcr,
GHSA-3g3m-2fjr-6pw4 and GHSA-g3hv-75wg-m249 (eight affected package nodes).

## WebSocket recovery

Replacing a socket retires its callbacks and pending reconnect waits. Only the
current socket can authenticate or update stores. Incoming frames must match the
existing service, deployment, step, user, authentication or control shapes before
conversion/dispatch. Malformed JSON or fields close the connection and show
“Invalid websocket message; refresh to resynchronize.” Refresh the page to fetch
current state and reconnect; malformed frames never trigger logout or automatic
retry. Diagnostics exclude frame contents.
