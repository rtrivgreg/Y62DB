# Y62DB Bindings TUI

A terminal (Textual) client for the same `RULE_BINDING` CRUD API the web
UI (`../ui/`) talks to — search, create, edit, and delete bindings from
the command line, with mouse support.

Scope is core CRUD only (search/create/edit/delete), matching
`ui/src/pages/BindingsBrowser.tsx` and `ui/src/components/BindingForm.tsx`
behavior and error wording as closely as possible. Deliberately **not**
included (explicit decision, see `docs/BLUEPRINT.md` §12.13): the
read-only rule-catalog *details* drill-in (severity/description/scope
metadata), and the too-many-matches picker/batched fan-out (this TUI
fans out to every match directly).

The initial view (no search needed) is a scrollable list of every
catalog rule (`all_rules_table`, near the top of the screen), each row
showing a checkbox, the rule ID, and whether it's bound. **Clicking
anywhere in a row except the checkbox column drives the same CRUD flow a
search hit would**: a bound rule's existing binding(s) load into the
results table for edit/delete; an unbound rule surfaces in the catalog
table so "Create binding for selected" can pre-fill it.

### Saving and loading rule sets (checkboxes)

Clicking the checkbox column (leftmost, ☐/☑) toggles that rule in or out
of the current selection — this is independent of the CRUD flow above
and doesn't load any bindings.

- **Load a saved set**: the "Load a saved rule set from /JSON…" dropdown
  above the table lists every `*.json` file present in the `/JSON` folder
  at the repo root (sibling to `tui/`, `ui/`, `docs/`, etc. — e.g.
  `JSON/compute.json`, `JSON/storage.json`). Each file is a plain JSON
  array of rule-name strings, e.g.:

  ```json
  ["compute-rule-a", "compute-rule-b"]
  ```

  Picking `compute` from the dropdown loads `/JSON/compute.json` and
  checks every row whose rule ID appears in that array. If the file
  contains a rule name no longer in the live catalog, it's skipped and
  named in a warning notice — the rest still load normally.
- **Save the current selection**: click "Save selection". If you loaded
  a file this session, it's silently overwritten with exactly the
  currently-checked rows (no confirmation prompt). If nothing has been
  loaded yet, you're prompted for a new filename and `/JSON/<name>.json`
  is created; it then becomes the active file for the rest of the
  session and appears in the dropdown. Saving with **no rows checked is
  blocked** with an inline error — nothing is written or overwritten.

See `docs/BLUEPRINT.md` §12.14 and
`docs/feature_requests/2026-08-07_tui_checkbox_save_load.md` for the full
spec and design rationale.

The search box below it is an alternate way in, not a replacement: when
searching by rule ID, results are split into two tables: bindings that
already exist (top table, with Edit/Delete actions) and catalog rules
that matched your search but have no binding yet (bottom table, with a
"Create binding for selected" action). Search-by-group only shows the
top table, since groups are just labels on existing bindings — there's
no separate group catalog to browse.

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
- `tests/` — unit tests for the matcher port, headless app-boot smoke test, catalog-search tests, full-catalog-list tests (`test_full_catalog_list.py`), and the checkbox save/load tests (`test_checkbox_save_load.py`, uses a temp directory in place of `/JSON` — never your real local files). `tests/live_check_full_catalog.py` is a manual (non-pytest) live-API check, not run in CI.
