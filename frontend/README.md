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
a newer fetch.

Run `npm test` and `npm run build`. The native browser regression uses only intercepted
synthetic API/WebSocket fixtures: run `npx playwright install chromium` then
`npm run test:browser`. CI installs Chromium and runs the same keyboard check on Linux.
