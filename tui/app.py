"""
Y62DB Bindings TUI — a terminal client for the same CRUD API the web UI
(`ui/`) talks to. Core CRUD parity by design (see docs/BLUEPRINT.md
§12.13): search (rule/group), create, edit, delete, with the same
validation rules and error wording as `ui/src/components/BindingForm.tsx`
and `ui/src/pages/BindingsBrowser.tsx`. Deliberately NOT in scope for v1
(explicit user decision): the read-only rule-catalog drill-in and the
too-many-matches picker/batched fan-out — this TUI fans out to every
match directly, which is fine at this project's current data scale.

Everything here is stock Textual — no third-party widgets, no custom
mouse-handling code. Textual enables mouse support by default in any
terminal that supports xterm mouse reporting (iTerm2, Terminal.app,
Windows Terminal, most Linux terminals; tmux users need `set -g mouse on`
in their tmux config). Clicking buttons, DataTable rows, and Select
dropdowns all just work.

Run with:  python -m tui.app        (from the repo root)
       or: cd tui && python app.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Select,
    Static,
    TextArea,
)
from textual.widgets.data_table import RowKey

from . import auth
from .api_client import Binding, BindingsApiClient, BindingsApiError
from .fuzzy_match import fuzzy_filter, substring_filter

# Repo-root /JSON folder holding named rule sets (plain JSON arrays of rule
# names), e.g. JSON/compute.json, JSON/storage.json. Committed to the repo
# by the repo owner — see docs/BLUEPRINT.md §12.14.
JSON_DIR = Path(__file__).resolve().parent.parent / "JSON"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class LoginScreen(Screen):
    """Cognito sign-in — same USER_PASSWORD_AUTH flow the web UI's Authenticator uses."""

    CSS = """
    LoginScreen {
        align: center middle;
    }
    #login-box {
        width: 50;
        height: auto;
        border: round $primary;
        padding: 1 2;
    }
    #login-error {
        color: $error;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="login-box"):
            yield Static("Y62DB — Rule Bindings", id="login-title")
            yield Static("Sign in with your Cognito username and password.")
            yield Input(placeholder="Username", id="username")
            yield Input(placeholder="Password", password=True, id="password")
            yield Button("Sign in", variant="primary", id="signin-btn")
            yield Static("", id="login-error")

    def on_mount(self) -> None:
        self.query_one("#username", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._attempt_sign_in()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "signin-btn":
            self._attempt_sign_in()

    def _attempt_sign_in(self) -> None:
        username = self.query_one("#username", Input).value.strip()
        password = self.query_one("#password", Input).value
        if not username or not password:
            self.query_one("#login-error", Static).update("Username and password are both required.")
            return
        self.query_one("#signin-btn", Button).disabled = True
        self.query_one("#login-error", Static).update("Signing in...")
        self._do_sign_in(username, password)

    @work(exclusive=True)
    async def _do_sign_in(self, username: str, password: str) -> None:
        try:
            id_token = await asyncio.to_thread(auth.sign_in, username, password)
        except auth.AuthError as e:
            self.query_one("#login-error", Static).update(str(e))
            self.query_one("#signin-btn", Button).disabled = False
            return
        self.app.switch_screen(BrowseScreen(id_token))


# ---------------------------------------------------------------------------
# Confirm delete (stock Textual modal-dialog pattern)
# ---------------------------------------------------------------------------


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Yes/no confirmation dialog — the standard Textual ModalScreen pattern.

    Unlike the web UI's native browser confirm() popup, this is a regular
    in-app screen: it's just Textual widgets, not a browser-chrome-level
    dialog, so it's also more automatable/scriptable than a native popup.
    """

    CSS = """
    ConfirmDeleteScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 60;
        height: auto;
        border: round $error;
        padding: 1 2;
    }
    #confirm-buttons {
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self.message)
            with Horizontal(id="confirm-buttons"):
                yield Button("Delete", variant="error", id="confirm-yes")
                yield Button("Cancel", variant="primary", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


# ---------------------------------------------------------------------------
# Save-as (new rule-set file name) — same modal-dialog pattern as
# ConfirmDeleteScreen, used only when Save is pressed with no active file
# loaded yet (docs/BLUEPRINT.md §12.14).
# ---------------------------------------------------------------------------


class SaveAsScreen(ModalScreen[Optional[str]]):
    """Prompts for a new /JSON/<name>.json file name.

    Returns the trimmed name via dismiss() on Save, or None on Cancel.
    """

    CSS = """
    SaveAsScreen {
        align: center middle;
    }
    #saveas-dialog {
        width: 60;
        height: auto;
        border: round $primary;
        padding: 1 2;
    }
    #saveas-error {
        color: $error;
        margin-top: 1;
    }
    #saveas-buttons {
        margin-top: 1;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="saveas-dialog"):
            yield Static("No rule set is currently loaded. Save as a new file in /JSON:")
            yield Input(placeholder="e.g. storage", id="saveas-name")
            yield Static("", id="saveas-error")
            with Horizontal(id="saveas-buttons"):
                yield Button("Save", variant="primary", id="saveas-yes")
                yield Button("Cancel", id="saveas-no")

    def on_mount(self) -> None:
        self.query_one("#saveas-name", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._attempt_submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "saveas-yes":
            self._attempt_submit()
        else:
            self.dismiss(None)

    def _attempt_submit(self) -> None:
        name = self.query_one("#saveas-name", Input).value.strip()
        if not name:
            self.query_one("#saveas-error", Static).update("A file name is required.")
            return
        self.dismiss(name)


# ---------------------------------------------------------------------------
# Create / edit form
# ---------------------------------------------------------------------------


class BindingFormScreen(ModalScreen[bool]):
    """Shared create/edit form — mirrors ui/src/components/BindingForm.tsx.

    Returns True via dismiss() if a save succeeded (caller should
    re-search), False/None if cancelled.
    """

    CSS = """
    BindingFormScreen {
        align: center middle;
    }
    #form-box {
        width: 76;
        height: auto;
        border: round $primary;
        padding: 1 2;
    }
    #form-error {
        color: $error;
        margin-top: 1;
    }
    #extra-label {
        margin-top: 1;
    }
    #extra-area {
        height: 8;
        border: round $surface-lighten-1;
    }
    #form-buttons {
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(
        self,
        api: BindingsApiClient,
        mode: str,
        existing: Optional[Binding] = None,
        default_rule_id: str = "",
    ) -> None:
        super().__init__()
        self.api = api
        self.mode = mode  # "create" | "edit"
        self.existing = existing
        self.default_rule_id = default_rule_id

    def compose(self) -> ComposeResult:
        is_edit = self.mode == "edit"
        ex = self.existing
        rule_id = ex.rule_id if ex else self.default_rule_id
        group = ex.group if ex else ""
        binding = ex.binding if ex else "default"
        status = ex.status if ex and ex.status in ("ACTIVE", "INACTIVE") else "ACTIVE"
        version_label = (
            f"Version (current: {ex.version}, will become: {ex.version + 1})"
            if is_edit and ex
            else "Version"
        )
        version_value = str(ex.version + 1) if is_edit and ex else "1"
        extra_json = "{}"
        if ex:
            extra = {k: v for k, v in ex.payload.items() if k not in ("status", "version")}
            extra_json = json.dumps(extra, indent=2)

        with Vertical(id="form-box"):
            yield Static("Edit binding" if is_edit else "New binding", id="form-title")
            yield Static("Rule ID")
            yield Input(value=rule_id, id="rule_id_input", disabled=is_edit, placeholder="e.g. access-keys-rotated")
            yield Static("Group")
            yield Input(value=group, id="group_input", disabled=is_edit, placeholder="e.g. corp")
            yield Static("Binding name")
            yield Input(value=binding, id="binding_input", disabled=is_edit, placeholder="default")
            yield Static("Status")
            yield Select(
                [("ACTIVE", "ACTIVE"), ("INACTIVE", "INACTIVE")],
                value=status,
                id="status_select",
                allow_blank=False,
            )
            yield Static(version_label, id="version_label")
            yield Input(value=version_value, id="version_input", disabled=is_edit)
            yield Static(
                "Extra payload fields (JSON object, optional — e.g. rule-specific keys)",
                id="extra-label",
            )
            yield TextArea(extra_json, id="extra_area")
            yield Static("", id="form-error")
            with Horizontal(id="form-buttons"):
                yield Button("Save changes" if is_edit else "Create binding", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(False)
        elif event.button.id == "save-btn":
            self._attempt_save()

    def _attempt_save(self) -> None:
        extra_raw = self.query_one("#extra_area", TextArea).text or "{}"
        try:
            extra = json.loads(extra_raw)
            if not isinstance(extra, dict):
                raise ValueError("must be a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            self.query_one("#form-error", Static).update(
                f"Extra payload fields must be valid JSON (an object): {e}"
            )
            return

        rule_id = self.query_one("#rule_id_input", Input).value.strip()
        group = self.query_one("#group_input", Input).value.strip()
        binding = self.query_one("#binding_input", Input).value.strip()
        if not rule_id or not group:
            self.query_one("#form-error", Static).update("Rule ID and group are both required.")
            return

        status = self.query_one("#status_select", Select).value
        self.query_one("#save-btn", Button).disabled = True
        self.query_one("#form-error", Static).update("Saving...")
        self._do_save(rule_id, group, binding, str(status), extra)

    @work(exclusive=True)
    async def _do_save(self, rule_id: str, group: str, binding: str, status: str, extra: dict[str, Any]) -> None:
        try:
            if self.mode == "edit" and self.existing:
                next_version = self.existing.version + 1
                payload = {"status": status, "version": next_version, **extra}
                await self.api.update_binding(rule_id, group, binding, payload, self.existing.version)
            else:
                version_value = self.query_one("#version_input", Input).value.strip()
                try:
                    version = int(version_value) if version_value else 1
                except ValueError:
                    version = 1
                payload = {"status": status, "version": version, **extra}
                await self.api.create_binding(rule_id, group, binding or None, payload)
            self.dismiss(True)
        except BindingsApiError as e:
            if e.code == "conflict" and self.mode == "edit":
                msg = (
                    "Conflict (409): this binding was updated by someone else since you loaded it. "
                    "Re-search and reopen edit to get the latest version before retrying."
                )
            elif e.code == "conflict":
                msg = "Conflict (409): a binding already exists for this rule + group + binding name."
            else:
                msg = f"{e.code} (HTTP {e.status}): {e}"
            self.query_one("#form-error", Static).update(msg)
            self.query_one("#save-btn", Button).disabled = False
        except Exception as e:  # noqa: BLE001
            self.query_one("#form-error", Static).update(str(e))
            self.query_one("#save-btn", Button).disabled = False


# ---------------------------------------------------------------------------
# Browse / search / list — the main screen
# ---------------------------------------------------------------------------


class BrowseScreen(Screen):
    """Full CRUD screen for RULE_BINDING entities — mirrors ui/src/pages/BindingsBrowser.tsx
    (core CRUD only; see module docstring for the two features deliberately left out)."""

    CSS = """
    #toolbar {
        height: auto;
        margin-bottom: 1;
    }
    #mode_select {
        width: 20;
    }
    #query_input {
        width: 1fr;
    }
    #notice {
        color: $success;
    }
    #error {
        color: $error;
    }
    #row-actions {
        height: auto;
        margin-top: 1;
    }
    #catalog-label {
        margin-top: 1;
        color: $text-muted;
    }
    #catalog-actions {
        height: auto;
        margin-top: 1;
    }
    #all-rules-label {
        margin-top: 1;
    }
    #all_rules_table {
        height: 12;
        border: round $primary;
        margin-bottom: 1;
    }
    #selection-toolbar {
        height: auto;
        margin-bottom: 1;
    }
    #json_select {
        width: 1fr;
    }
    """

    BINDINGS = [
        ("s", "focus_search", "Search"),
        ("n", "new_binding", "New binding"),
    ]

    # Checkbox glyphs for the multi-select column (§12.14: save/load rule
    # sets to/from /JSON). Unchecked was previously an inert placeholder;
    # both glyphs are now live and toggleable by clicking the column.
    _CHECKBOX_PLACEHOLDER = "\u2610"  # ☐ unchecked
    _CHECKBOX_CHECKED = "\u2611"  # ☑ checked

    def __init__(self, id_token: str) -> None:
        super().__init__()
        self.api = BindingsApiClient(id_token)
        self._bindings_by_key: dict[str, Binding] = {}
        self.selected_binding: Optional[Binding] = None
        self._unbound_rule_ids: dict[str, str] = {}
        self.selected_catalog_rule_id: Optional[str] = None
        # Rule currently selected from the full-catalog list (as opposed to
        # via the search box) — tracked so "refresh after save/delete" knows
        # which view to reload.
        self._current_rule_id: Optional[str] = None
        # §12.14: checkbox multi-select + save/load to /JSON.
        self._checkbox_column_key = None
        self._selected_rule_ids: set[str] = set()
        self._catalog_rule_ids: set[str] = set()
        self._active_json_file: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "All config rules — click the checkbox column to multi-select, "
            "or click elsewhere in a row to manage its bindings:",
            id="all-rules-label",
        )
        yield DataTable(id="all_rules_table", cursor_type="cell", zebra_stripes=True)
        with Horizontal(id="selection-toolbar"):
            yield Select(
                [],
                prompt="Load a saved rule set from /JSON...",
                id="json_select",
                allow_blank=True,
            )
            yield Button("Save selection", id="save-json-btn")
        with Horizontal(id="toolbar"):
            yield Select(
                [("By rule ID", "rule"), ("By group", "group")],
                value="rule",
                id="mode_select",
                allow_blank=False,
            )
            yield Input(placeholder="e.g. access-keys-rotated", id="query_input")
            yield Button("Search", variant="primary", id="search-btn")
            yield Button("+ New binding", id="new-btn")
            yield Button("Sign out", id="signout-btn")
        yield Static("", id="notice")
        yield Static("", id="error")
        yield Static("Existing bindings matching your search:")
        yield DataTable(id="results_table", cursor_type="row", zebra_stripes=True)
        with Horizontal(id="row-actions"):
            yield Button("Edit selected", id="edit-btn", disabled=True)
            yield Button("Delete selected", id="delete-btn", disabled=True)
        yield Static(
            "Catalog rules matching your search with no binding yet (rule-ID search only):",
            id="catalog-label",
        )
        yield DataTable(id="catalog_table", cursor_type="row", zebra_stripes=True)
        with Horizontal(id="catalog-actions"):
            yield Button("Create binding for selected", id="create-from-catalog-btn", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#results_table", DataTable)
        table.add_columns("Rule", "Group", "Binding", "Payload")
        catalog_table = self.query_one("#catalog_table", DataTable)
        catalog_table.add_column("Rule ID (no binding yet)", key="rule_id")
        all_rules_table = self.query_one("#all_rules_table", DataTable)
        cols = all_rules_table.add_columns("", "Rule ID", "Bound")
        self._checkbox_column_key = cols[0]
        self._refresh_json_dropdown()
        self.query_one("#query_input", Input).focus()
        self._load_all_rules()

    @work(exclusive=True)
    async def _load_all_rules(self) -> None:
        """Populates the initial-view scrollable list of every catalog rule."""
        self.set_notice("Loading rule catalog...")
        self.set_error(None)
        try:
            rules = await self.api.list_all_rule_ids()
            table = self.query_one("#all_rules_table", DataTable)
            table.clear()
            self._catalog_rule_ids = {r["rule_id"] for r in rules}
            for r in rules:
                rule_id = r["rule_id"]
                bound = "Yes" if r.get("has_binding") else "No"
                glyph = self._CHECKBOX_CHECKED if rule_id in self._selected_rule_ids else self._CHECKBOX_PLACEHOLDER
                table.add_row(glyph, rule_id, bound, key=rule_id)
            self.set_notice(f"{len(rules)} config rule(s) loaded. Select a row to manage its bindings.")
        except BindingsApiError as e:
            self.set_notice(None)
            self.set_error(f"{e.code} (HTTP {e.status}): {e}")
        except Exception as e:  # noqa: BLE001
            self.set_notice(None)
            self.set_error(str(e))

    def action_focus_search(self) -> None:
        self.query_one("#query_input", Input).focus()

    def action_new_binding(self) -> None:
        self._open_create_form()

    def set_notice(self, text: Optional[str]) -> None:
        self.query_one("#notice", Static).update(text or "")

    def set_error(self, text: Optional[str]) -> None:
        self.query_one("#error", Static).update(f"Error: {text}" if text else "")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "query_input":
            self._run_search()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-btn":
            self._run_search()
        elif event.button.id == "new-btn":
            self._open_create_form()
        elif event.button.id == "signout-btn":
            self.app.switch_screen(LoginScreen())
        elif event.button.id == "edit-btn":
            self._open_edit_form()
        elif event.button.id == "delete-btn":
            self._confirm_delete()
        elif event.button.id == "create-from-catalog-btn":
            self._open_create_form_for_catalog_rule()
        elif event.button.id == "save-json-btn":
            self._on_save_pressed()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "json_select" and event.value != Select.BLANK:
            self._load_json_selection(str(event.value))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "results_table":
            key = str(event.row_key.value)
            self.selected_binding = self._bindings_by_key.get(key)
            has_selection = self.selected_binding is not None
            self.query_one("#edit-btn", Button).disabled = not has_selection
            self.query_one("#delete-btn", Button).disabled = not has_selection
        elif event.data_table.id == "catalog_table":
            key = str(event.row_key.value)
            self.selected_catalog_rule_id = self._unbound_rule_ids.get(key)
            self.query_one("#create-from-catalog-btn", Button).disabled = (
                self.selected_catalog_rule_id is None
            )
        # all_rules_table uses cursor_type="cell" (see on_data_table_cell_selected)
        # so that the checkbox column (col 0) can be distinguished from the
        # rest of the row — it never posts RowSelected.

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """§12.14: all_rules_table is cell-cursor so clicking the checkbox
        column (col 0) toggles multi-select, while clicking anywhere else in
        the row still drives the existing "load bindings for this rule" flow
        that on_data_table_row_selected handled before this column existed."""
        if event.data_table.id != "all_rules_table":
            return
        row_key = event.cell_key.row_key
        if event.coordinate.column == 0:
            self._toggle_checkbox(row_key)
        else:
            self._load_bindings_for_rule_id(str(row_key.value))

    def _toggle_checkbox(self, row_key: RowKey) -> None:
        rule_id = str(row_key.value)
        table = self.query_one("#all_rules_table", DataTable)
        if rule_id in self._selected_rule_ids:
            self._selected_rule_ids.discard(rule_id)
            glyph = self._CHECKBOX_PLACEHOLDER
        else:
            self._selected_rule_ids.add(rule_id)
            glyph = self._CHECKBOX_CHECKED
        table.update_cell(row_key, self._checkbox_column_key, glyph)

    def _show_results(self, results: list[Binding], unbound_rule_ids: Optional[list[str]] = None) -> None:
        table = self.query_one("#results_table", DataTable)
        table.clear()
        self._bindings_by_key.clear()
        self.selected_binding = None
        self.query_one("#edit-btn", Button).disabled = True
        self.query_one("#delete-btn", Button).disabled = True
        for b in results:
            self._bindings_by_key[b.key] = b
            table.add_row(b.rule_id, b.group, b.binding, json.dumps(b.payload), key=b.key)

        catalog_table = self.query_one("#catalog_table", DataTable)
        catalog_table.clear()
        self._unbound_rule_ids.clear()
        self.selected_catalog_rule_id = None
        self.query_one("#create-from-catalog-btn", Button).disabled = True
        unbound_rule_ids = unbound_rule_ids or []
        for rid in unbound_rule_ids:
            self._unbound_rule_ids[rid] = rid
            catalog_table.add_row(rid, key=rid)

        notice = f"{len(results)} binding(s) found."
        if unbound_rule_ids:
            notice += f" {len(unbound_rule_ids)} catalog rule(s) matched with no binding yet."
        self.set_notice(notice)

    def _run_search(self) -> None:
        query = self.query_one("#query_input", Input).value.strip()
        if not query:
            return
        self._current_rule_id = None
        mode = str(self.query_one("#mode_select", Select).value)
        self.set_notice("Loading...")
        self.set_error(None)
        self._do_search(mode, query)

    @work(exclusive=True)
    async def _load_bindings_for_rule_id(self, rule_id: str) -> None:
        """Selecting a row in the full-catalog list acts like searching for
        that exact rule: its existing bindings (if any) populate the results
        table for edit/delete, or it shows up as an unbound catalog match so
        "Create binding for selected" can be used."""
        self._current_rule_id = rule_id
        self.set_notice(f"Loading bindings for {rule_id}...")
        self.set_error(None)
        try:
            results = await self.api.list_bindings_for_rule(rule_id)
            if results:
                self._show_results(results, unbound_rule_ids=[])
            else:
                self._show_results([], unbound_rule_ids=[rule_id])
        except BindingsApiError as e:
            self.set_notice(None)
            self.set_error(f"{e.code} (HTTP {e.status}): {e}")
        except Exception as e:  # noqa: BLE001
            self.set_notice(None)
            self.set_error(str(e))

    def _refresh_current_view(self) -> None:
        """Re-runs whichever data-flow is currently active — a rule selected
        from the full-catalog list, or a search — after a save/delete."""
        if self._current_rule_id:
            self._load_bindings_for_rule_id(self._current_rule_id)
        else:
            self._run_search()

    @work(exclusive=True)
    async def _do_search(self, mode: str, query: str) -> None:
        try:
            if mode == "rule":
                rules = await self.api.list_all_rule_ids()
                all_ids = [r["rule_id"] for r in rules]
                matched = substring_filter(query, all_ids)
                has_binding = {r["rule_id"]: r.get("has_binding", False) for r in rules}
                bound = [rid for rid in matched if has_binding.get(rid)]
                unbound = [rid for rid in matched if not has_binding.get(rid)]
                results: list[Binding] = []
                for rid in bound:
                    results.extend(await self.api.list_bindings_for_rule(rid))
                self._show_results(results, unbound_rule_ids=unbound)
            else:
                groups = await self.api.list_all_groups()
                matched = fuzzy_filter(query, groups)
                results = []
                for g in matched:
                    results.extend(await self.api.list_bindings_for_group(g))
                # The catalog concept only applies to rules — groups are just
                # labels that exist on bindings, there's no separate group
                # catalog to drill into, so no unbound list here.
                self._show_results(results, unbound_rule_ids=[])
        except BindingsApiError as e:
            self.set_notice(None)
            self.set_error(f"{e.code} (HTTP {e.status}): {e}")
        except Exception as e:  # noqa: BLE001
            self.set_notice(None)
            self.set_error(str(e))

    def _open_create_form(self) -> None:
        self.set_notice(None)
        mode = str(self.query_one("#mode_select", Select).value)
        query = self.query_one("#query_input", Input).value.strip()
        default_rule_id = self._current_rule_id or (query if mode == "rule" else "")
        form = BindingFormScreen(self.api, mode="create", default_rule_id=default_rule_id)
        self.app.push_screen(form, self._on_form_dismissed)

    def _open_create_form_for_catalog_rule(self) -> None:
        if not self.selected_catalog_rule_id:
            return
        self.set_notice(None)
        form = BindingFormScreen(self.api, mode="create", default_rule_id=self.selected_catalog_rule_id)
        self.app.push_screen(form, self._on_form_dismissed)

    def _open_edit_form(self) -> None:
        if not self.selected_binding:
            return
        self.set_notice(None)
        form = BindingFormScreen(self.api, mode="edit", existing=self.selected_binding)
        self.app.push_screen(form, self._on_form_dismissed)

    def _on_form_dismissed(self, saved: Optional[bool]) -> None:
        if saved:
            self.set_notice("Binding saved. Refreshing results...")
            self._refresh_current_view()
            self._load_all_rules()

    def _confirm_delete(self) -> None:
        b = self.selected_binding
        if not b:
            return
        message = f"Delete binding {b.rule_id} / {b.group} / {b.binding}? This cannot be undone."

        def check_confirm(confirmed: Optional[bool]) -> None:
            if confirmed:
                self._do_delete(b)

        self.app.push_screen(ConfirmDeleteScreen(message), check_confirm)

    @work(exclusive=True)
    async def _do_delete(self, b: Binding) -> None:
        self.set_notice(None)
        self.set_error(None)
        try:
            await self.api.delete_binding(b.rule_id, b.group, b.binding)
            self.set_notice(f"Deleted {b.rule_id} / {b.group} / {b.binding}. Refreshing results...")
            self._refresh_current_view()
            self._load_all_rules()
        except BindingsApiError as e:
            self.set_error(f"{e.code} (HTTP {e.status}): {e}")
        except Exception as e:  # noqa: BLE001
            self.set_error(str(e))

    # -----------------------------------------------------------------
    # §12.14: checkbox multi-select, save/load rule sets to/from /JSON
    # -----------------------------------------------------------------

    def _list_json_files(self) -> list[str]:
        """Base names (no .json) of every rule-set file in /JSON, sorted.
        Returns an empty list if /JSON doesn't exist yet — it's never
        assumed to pre-exist (it lives outside this repo's git history)."""
        if not JSON_DIR.is_dir():
            return []
        return sorted(p.stem for p in JSON_DIR.glob("*.json"))

    def _refresh_json_dropdown(self, keep_value: Optional[str] = None) -> None:
        select = self.query_one("#json_select", Select)
        names = self._list_json_files()
        select.set_options([(n, n) for n in names])
        if keep_value is not None and keep_value in names:
            select.value = keep_value
        else:
            select.value = Select.BLANK

    def _load_json_selection(self, name: str) -> None:
        """Reads /JSON/<name>.json (a plain JSON array of rule names) and
        checks exactly the checkboxes for names that still exist in the
        current catalog. Names no longer in the catalog are skipped with a
        warning, not treated as an error."""
        path = JSON_DIR / f"{name}.json"
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, list):
                raise ValueError("file must contain a JSON array of rule names")
        except (OSError, json.JSONDecodeError, ValueError) as e:
            self.set_notice(None)
            self.set_error(f"Could not load '{name}.json': {e}")
            return

        found: set[str] = set()
        missing: list[str] = []
        for entry in data:
            rid = str(entry)
            if rid in self._catalog_rule_ids:
                found.add(rid)
            else:
                missing.append(rid)

        table = self.query_one("#all_rules_table", DataTable)
        self._selected_rule_ids = set(found)
        for row in table.ordered_rows:
            rid = str(row.key.value)
            checked = rid in found
            glyph = self._CHECKBOX_CHECKED if checked else self._CHECKBOX_PLACEHOLDER
            table.update_cell(row.key, self._checkbox_column_key, glyph)

        self._active_json_file = name
        self.set_error(None)
        if missing:
            shown = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
            self.set_notice(
                f"Loaded '{name}.json': {len(found)} rule(s) checked. "
                f"{len(missing)} name(s) no longer in the catalog were skipped: {shown}"
            )
        else:
            self.set_notice(f"Loaded '{name}.json': {len(found)} rule(s) checked.")

    def _on_save_pressed(self) -> None:
        if not self._selected_rule_ids:
            self.set_notice(None)
            self.set_error("Select at least one rule before saving.")
            return
        if self._active_json_file and self._active_json_file in self._list_json_files():
            self._write_json_file(self._active_json_file)
        else:
            self.app.push_screen(SaveAsScreen(), self._on_saveas_dismissed)

    def _on_saveas_dismissed(self, name: Optional[str]) -> None:
        if name:
            self._write_json_file(name)

    def _write_json_file(self, name: str) -> None:
        try:
            JSON_DIR.mkdir(parents=True, exist_ok=True)
            path = JSON_DIR / f"{name}.json"
            path.write_text(json.dumps(sorted(self._selected_rule_ids), indent=2) + "\n")
        except OSError as e:
            self.set_error(f"Could not save '{name}.json': {e}")
            return
        self._active_json_file = name
        self.set_error(None)
        self.set_notice(f"Saved {len(self._selected_rule_ids)} rule(s) to '{name}.json'.")
        self._refresh_json_dropdown(keep_value=name)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class BindingsTUI(App):
    TITLE = "Y62DB — Rule Bindings"

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())


def main() -> None:
    BindingsTUI().run()


if __name__ == "__main__":
    main()
