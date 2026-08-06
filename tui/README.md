# Y62DB Bindings TUI

A terminal (Textual) client for the same `RULE_BINDING` CRUD API the web
UI (`../ui/`) talks to — search, create, edit, and delete bindings from
the command line, with mouse support.

Scope is core CRUD only (search/create/edit/delete), matching
`ui/src/pages/BindingsBrowser.tsx` and `ui/src/components/BindingForm.tsx`
behavior and error wording as closely as possible. Deliberately **not**
included (explicit decision, see `docs/BLUEPRINT.md` §12.13): the
read-only rule-catalog drill-in, and the too-many-matches picker/batched
fan-out (this TUI fans out to every match directly).

## Setup

```bash
cd tui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m tui.app        # from the repo root, with .venv active
# or
cd tui && python app.py
```

Sign in with your Cognito username/password (same user pool the web UI
uses). AWS credentials are **not** required to run the TUI itself — it
calls Cognito's public `InitiateAuth` API directly via `boto3`, which
doesn't need IAM credentials for the `USER_PASSWORD_AUTH` flow used here.

## Mouse support

Textual enables mouse reporting by default in any terminal that supports
it (iTerm2, Terminal.app, Windows Terminal, most Linux terminals) — no
extra configuration needed. Click a table row to select it, then use the
"Edit selected" / "Delete selected" buttons, or click "+ New binding" /
"Search" directly. If running inside `tmux`, add `set -g mouse on` to
your tmux config first, or mouse clicks won't reach the app.

Keyboard shortcuts: `s` focuses the search box, `n` opens the create
form, `Tab`/`Shift+Tab` move focus, `Enter` activates the focused
button/input, arrow keys move the table cursor.

## Layout

- `config.py` — live AWS identifiers (Cognito client ID, API base URL) — kept in
  sync with `ui/src/amplify-config.ts`.
- `auth.py` — Cognito sign-in (`InitiateAuth`, `USER_PASSWORD_AUTH`).
- `api_client.py` — async REST client, a direct port of `ui/src/api/bindingsApi.ts`.
- `fuzzy_match.py` — search matchers, a direct port of `ui/src/fuzzyMatch.ts`.
- `app.py` — the Textual `App` and all screens (Login, Browse, BindingForm, ConfirmDelete).
- `tests/` — unit tests for the matcher port + a headless app-boot smoke test.
