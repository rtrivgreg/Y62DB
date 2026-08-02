# Y62DB Bindings UI

A Vite + React + TypeScript app for browsing and (eventually) managing
`RULE_BINDING` records via the Y62DB CRUD API. This is the frontend
described in the repo root's `docs/BLUEPRINT.md` §12 (form-UI roadmap).

## What's real here

- **Auth: real Cognito User Pool**, not a mock. `src/amplify-config.ts`
  points `Amplify.configure()` at the actual Terraform-provisioned pool
  (`us-east-1_5OUP1L4hf`) and app client (`2eruh11a9kc2lbdd286q282ofb`) —
  the same ones the API Gateway authorizer trusts. Signing in here gets you
  a real ID token accepted by the live API.
- **API: real API Gateway endpoint**, not a mock. `src/api/bindingsApi.ts`
  calls `https://3lkxt728eh.execute-api.us-east-1.amazonaws.com/dev`
  directly with `fetch()`, attaching the signed-in user's ID token via
  `fetchAuthSession()`. Every function in that file maps 1:1 to a route in
  the repo root's `api/README.md` contract.
- **No separate Amplify Gen 2 backend project** (no `amplify/` folder, no
  `npx ampx sandbox`). Both Auth and the REST API already exist and are
  Terraform-managed at the repo root — this app just points Amplify's
  client libraries at them, per Amplify's documented "use existing AWS
  resources" pattern. If that ever changes, `src/amplify-config.ts` is the
  one place to update.

## What's scaffolded but not yet built

`src/pages/BindingsBrowser.tsx` is a **read-only** smoke-test screen — look
up bindings by rule ID or by group. It exists to prove the auth + API
wiring works end-to-end from a browser, not as the finished product. Still
to come (see `docs/BLUEPRINT.md` §12.1 steps 7–9):

- Create / edit (with optimistic-locking conflict handling) / delete forms
  for bindings, using `@aws-amplify/ui-react` field components.
- A read-only browser for `RULE_PROFILE` / `PARAMETER_DEF` so a user can
  see what parameters a rule expects before creating a binding for it.
- Amplify Hosting CI/CD, with this folder (`ui/`) set as the monorepo app
  root.

## Local development

```bash
cd ui
npm install
npm run dev      # http://localhost:5173
```

Sign in with a real Cognito user in pool `us-east-1_5OUP1L4hf` (e.g. the
`testuser` account created for CLI smoke-testing — see
`docs/BLUEPRINT.md` §12.2). The Authenticator's default sign-up flow also
works against the same pool if you want to create a new user from the UI.

```bash
npm run build     # type-check + production build to ui/dist
```

## Why plain `fetch()` instead of Amplify's `API` (REST) category

This API was hand-built outside Amplify and its `COGNITO_USER_POOLS`
authorizer expects the raw Cognito **ID token** in the `Authorization`
header — not IAM SigV4 signing, which is what Amplify's `API` category
does by default for REST endpoints. Pulling the ID token from
`fetchAuthSession()` and attaching it directly is simpler and more
explicit than fighting the category's default auth mode for an API this
small, and keeps `bindingsApi.ts` a plain, dependency-light module that's
easy to unit test later.
