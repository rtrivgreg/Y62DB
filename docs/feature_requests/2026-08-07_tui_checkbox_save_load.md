# Feature Request: TUI multi-select checkboxes with save/load to JSON

## 1. Objective

Wire up the currently-inert checkbox placeholder column in the TUI's
full-catalog list (`BrowseScreen.all_rules_table` in `tui/app.py`) so a
user can multi-select rules, save the selected rule IDs to a
user-named JSON file, and later load a previously saved file to
restore that exact selection.

## 2. Scope boundary

**In:**
- Toggleable checkbox per row in `all_rules_table` (the existing ☐
  glyph becomes interactive; toggling flips it to ☑ and adds/removes
  that `rule_id` from an in-memory selection set).
- Multi-select across the full 810-rule list (not limited to
  contiguous rows or the current single-cursor selection).
- A **`/JSON` folder at the repo root** (existing, not new — sibling
  to `tui/`, `ui/`, `api/`, `docs/`) holds one file per named rule
  set, e.g. `compute.json`, `containers.json`. Each file is a **plain
  JSON array of rule-name strings**, e.g.
  `["ec2-instance-managed-by-ssm", "ec2-volume-inuse-check"]` — not
  an object wrapper.
- A "Load selection" action shows a **dropdown populated from every
  `*.json` file currently in `/JSON`**, labeled by base filename
  without the extension (today: "compute", "containers"). Picking one
  reads that file and checks every rule name in it that still exists
  in the current 810-rule catalog. Any name in the file that no
  longer exists in the catalog is skipped, and a warning notice lists
  which name(s) were skipped (does not block loading the rest). The
  app tracks which file was most recently loaded ("the active file").
- A "Save selection" action:
  - **If a file is currently active** (was loaded this session via the
    dropdown), Save writes the exact set of currently-checked rule
    names back to that same file, overwriting it — e.g. after loading
    "compute" and toggling checkboxes, Save writes the new checked set
    back to `compute.json`. Only the checked rules are written; nothing
    outside the current selection carries over from the old file
    contents.
  - **If no file is active** (nothing loaded yet this session, or a
    fresh selection was built from scratch), Save opens a modal text
    input for a new filename and writes the checked rule names to a
    new `/JSON/<name>.json`, which then becomes the active file and
    also becomes selectable in the Load dropdown going forward.
  - **If zero rules are checked, Save is blocked** with a client-side
    error (e.g. "select at least one rule before saving") — no file is
    written or overwritten in this case, active or not.

**Out (explicitly not built in this pass):**
- No bulk action performed *on* the selection (no bulk create/delete
  of bindings) — this feature only persists and restores which
  checkboxes are checked, exactly as scoped in the original
  §12.13 amendment that reserved the checkbox column "for a future
  bulk action... not wired to anything yet."
- Checkboxes are not added to the search-results table or the
  catalog-search table — only `all_rules_table` (the full-catalog
  landing view) gets checkboxes.
- No rename/delete of existing `/JSON/*.json` files from within the
  TUI — Save either overwrites the active file or creates a new one;
  managing/removing files is a filesystem-level task outside this
  feature.
- No cloud storage — local JSON files in `/JSON` at the repo root
  only.

## 3. Source of truth

- `tui/app.py`, `class BrowseScreen`, around lines 357–392 and the
  `on_mount`/`_load_all_rules` methods — this is where
  `all_rules_table` is built and where the placeholder checkbox glyph
  (`"\u2610"`, referenced in the code comment "checkbox column
  reserved for a future bulk action") currently lives, inert.
- `tui/app.py`, `class ConfirmDeleteScreen(ModalScreen[bool])` (lines
  117–159) — reuse this exact `ModalScreen` pattern for the new
  "Save selection" and "Load selection" filename-prompt modals, for
  visual/interaction consistency with the rest of the app.
- `tui/app.py`, `on_data_table_row_selected` (line 481) — existing
  row-selection handling to extend for per-row checkbox toggling
  (Textual's `DataTable` has no native checkbox widget; the toggle is
  a manual cell-glyph swap, matching how the placeholder is currently
  rendered).
- `docs/BLUEPRINT.md` §12.13 (the TUI's full history, including the
  "full-catalog list as initial view" amendment) — read this first so
  the new feature is additive to, not a rewrite of, the existing
  `all_rules_table`/`_refresh_current_view()` logic.

## 4. Non-negotiable constraints

- Never touch the legacy `config_rules`/`config_rule_parameters`
  DynamoDB tables — not applicable to this feature's file I/O, but
  restated as standing project policy.
- This feature must not make any new or different live API/DynamoDB
  calls — save/load is pure local file I/O against the in-memory
  catalog data already loaded into `all_rules_table`; it must not
  re-fetch `/rules` or touch bindings.
- No new AWS resources of any kind.
- Do not break the existing `_refresh_current_view()` /
  refresh-after-save/refresh-after-delete behavior fixed earlier in
  §12.13 — loading a selection file must not silently no-op the way
  the pre-fix `_run_search()` bug did against an empty query box.
- Validate with `pytest` (run from `tui/`) before commit;
  `python -m py_compile` on all changed/new modules.
- Get explicit confirmation of the exact diff and commit message
  before pushing to `rtrivgreg/Y62DB`.

## 5. Acceptance criteria / validation commands

- `python -m py_compile` clean on all changed/new modules.
- New tests added under `tui/tests/` (headless, fake data against a
  temp `/JSON`-equivalent directory, following the existing
  `test_full_catalog_list.py` pattern), covering:
  - Toggling a checkbox adds/removes that rule name from the in-memory
    selection set; toggling the same row twice returns to unchecked.
  - Load dropdown lists exactly the base names (no `.json`) of every
    file present in `/JSON`.
  - Loading "compute" checks exactly the rows whose rule name appears
    in `compute.json`'s array, and sets it as the active file.
  - Loading a file containing a mix of valid and now-nonexistent rule
    names checks every still-valid row and shows a warning notice
    naming the skipped name(s); does not raise or crash.
  - After loading "compute", toggling checkboxes, and hitting Save,
    `compute.json` is overwritten with exactly the new checked set (a
    plain JSON array), with no modal filename prompt shown.
  - With no file loaded/active, hitting Save with rules checked opens
    the new-filename modal, and submitting a name writes
    `/JSON/<name>.json` and makes it the active file.
  - Hitting Save with **zero rows checked** is blocked with a
    client-side error ("select at least one rule before saving") in
    both the active-file and no-active-file cases — no file is written
    or overwritten.
- Full `pytest` suite run from `tui/` passes (currently 21 passing;
  should grow, not shrink).
- No live AWS/API check required for this feature (pure local file
  I/O against already-loaded catalog data).

## 6. Output / documentation format

- Document as a new `docs/BLUEPRINT.md` §12.14 subsection (context,
  scope decision, implementation, validation performed) — same
  format as §12.13's amendments.
- Update `tui/README.md`'s "Layout"/feature description to mention
  the new checkbox save/load actions and the `selections/` folder.
- Commit message summarizes the change and lists files touched.
- Confirm the exact diff before pushing to `rtrivgreg/Y62DB`.

## 7. Known gotchas

- Textual's `DataTable` has no built-in checkbox widget — this must
  reuse the existing manual glyph-swap approach already established
  for the placeholder column, not introduce a different widget type
  reserved for a future bulk action.
- **Verified 2026-08-07: `/JSON` does not exist yet in `rtrivgreg/Y62DB`
  on GitHub** — `compute.json`/`containers.json` are described as
  already present, but a fresh clone of `main` has no `JSON/` folder
  at all. Either they exist only in an uncommitted local copy on the
  repo owner's machine (in which case they need to be added/committed
  as part of this feature, or the builder should ask before assuming
  their exact contents), or the two-file example was illustrative
  rather than literal. **Confirm which before writing the load-dropdown
  code against assumed file contents** — don't invent placeholder
  `compute.json`/`containers.json` content from guesswork alone.
- The existing files are **plain arrays of rule-name strings**, not
  objects — confirm the exact key used for rule identity in
  `compute.json`/`containers.json` matches `rule_id` as used elsewhere
  in the TUI (e.g. `access-keys-rotated`-style strings) before writing
  the load/match logic, in case the existing files use a different
  naming convention than the catalog's `rule_id`.
- Running the TUI two different ways (`python -m tui.app` from repo
  root vs. `cd tui && python app.py`) changes the working directory —
  `/JSON` must be resolved relative to the repo root consistently
  regardless of launch method, or Save/Load will silently read/write
  the wrong location depending on how the user launched it.
- Dropdown contents can go stale within a single running session if a
  new file is created via the no-active-file Save path — the Load
  dropdown should be refreshed (re-scan `/JSON`) after any Save that
  creates a new file, not just built once at app start.

---

*Based on the Y62DB Feature Request Template
(`docs/FEATURE_REQUEST_TEMPLATE.md`), filled out 2026-08-07 for the
TUI checkbox multi-select + save/load-to-JSON enhancement.*
