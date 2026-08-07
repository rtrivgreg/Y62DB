"""
Headless tests for §12.14: multi-select checkboxes on the full-catalog list
plus save/load of the checked rule-name set to/from /JSON/<name>.json (a
plain JSON array of rule names). No live network or live filesystem paths —
JSON_DIR is monkeypatched to a pytest tmp_path for every test, and the
bindings API is a fake (no live AWS calls).
"""

import json

import pytest

import tui.app as tui_app
from tui.app import BindingsTUI, BrowseScreen, SaveAsScreen


class _FakeApi:
    async def list_all_rule_ids(self):
        return [
            {"rule_id": "compute-rule-a", "has_binding": False},
            {"rule_id": "compute-rule-b", "has_binding": False},
            {"rule_id": "storage-rule-c", "has_binding": True},
        ]

    async def list_bindings_for_rule(self, rule_id):
        return []

    async def list_all_groups(self):
        return []

    async def list_bindings_for_group(self, group):
        return []

    async def aclose(self):
        pass


async def _mounted_screen(app):
    screen = BrowseScreen("fake-token")
    screen.api = _FakeApi()
    await app.push_screen(screen)
    return screen


@pytest.fixture(autouse=True)
def _fake_json_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tui_app, "JSON_DIR", tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_toggle_checkbox_updates_selection_and_glyph():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        table = screen.query_one("#all_rules_table")
        row_key = next(r.key for r in table.ordered_rows if str(r.key.value) == "compute-rule-a")

        screen._toggle_checkbox(row_key)
        assert screen._selected_rule_ids == {"compute-rule-a"}
        assert table.get_row(row_key)[0] == screen._CHECKBOX_CHECKED

        # Toggling again unchecks it.
        screen._toggle_checkbox(row_key)
        assert screen._selected_rule_ids == set()
        assert table.get_row(row_key)[0] == screen._CHECKBOX_PLACEHOLDER


@pytest.mark.asyncio
async def test_cell_selected_on_checkbox_column_toggles_without_loading_bindings(monkeypatch):
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        called = []
        monkeypatch.setattr(screen, "_load_bindings_for_rule_id", lambda rid: called.append(rid))

        table = screen.query_one("#all_rules_table")
        row_key = next(r.key for r in table.ordered_rows if str(r.key.value) == "compute-rule-a")
        col_key = screen._checkbox_column_key

        from textual.widgets import DataTable
        from textual.widgets.data_table import CellKey
        from textual.coordinate import Coordinate

        event = DataTable.CellSelected(
            table,
            value=screen._CHECKBOX_PLACEHOLDER,
            coordinate=Coordinate(row=0, column=0),
            cell_key=CellKey(row_key, col_key),
        )
        screen.on_data_table_cell_selected(event)

        assert screen._selected_rule_ids == {"compute-rule-a"}
        assert called == []  # clicking the checkbox column must not trigger a bindings load


def test_list_json_files_returns_empty_when_dir_missing(_fake_json_dir):
    screen = BrowseScreen.__new__(BrowseScreen)  # no need to mount for a pure filesystem helper
    assert screen._list_json_files() == []


def test_list_json_files_lists_sorted_basenames(_fake_json_dir):
    (_fake_json_dir / "containers.json").write_text(json.dumps(["storage-rule-c"]))
    (_fake_json_dir / "compute.json").write_text(json.dumps(["compute-rule-a", "compute-rule-b"]))
    screen = BrowseScreen.__new__(BrowseScreen)
    assert screen._list_json_files() == ["compute", "containers"]


@pytest.mark.asyncio
async def test_load_checks_matching_rules_and_sets_active_file(_fake_json_dir):
    (_fake_json_dir / "compute.json").write_text(json.dumps(["compute-rule-a", "compute-rule-b"]))

    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        screen._load_json_selection("compute")

        assert screen._selected_rule_ids == {"compute-rule-a", "compute-rule-b"}
        assert screen._active_json_file == "compute"
        table = screen.query_one("#all_rules_table")
        for row in table.ordered_rows:
            rid = str(row.key.value)
            expected = screen._CHECKBOX_CHECKED if rid in ("compute-rule-a", "compute-rule-b") else screen._CHECKBOX_PLACEHOLDER
            assert table.get_row(row.key)[0] == expected


@pytest.mark.asyncio
async def test_load_with_stale_rule_name_warns_but_still_checks_the_rest(_fake_json_dir):
    (_fake_json_dir / "compute.json").write_text(
        json.dumps(["compute-rule-a", "no-longer-exists-rule"])
    )

    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        screen._load_json_selection("compute")

        assert screen._selected_rule_ids == {"compute-rule-a"}
        notice = str(screen.query_one("#notice").renderable)
        assert "no-longer-exists-rule" in notice
        assert "skipped" in notice
        # Loading still succeeds for the valid names — not treated as an error.
        assert str(screen.query_one("#error").renderable) == ""


@pytest.mark.asyncio
async def test_save_blocked_when_nothing_checked():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        screen._on_save_pressed()
        await pilot.pause()

        assert "select at least one rule" in str(screen.query_one("#error").renderable).lower()
        # No screen was pushed and nothing exists on disk.
        assert isinstance(app.screen, BrowseScreen)


@pytest.mark.asyncio
async def test_save_with_active_file_overwrites_it_directly_no_modal(_fake_json_dir):
    (_fake_json_dir / "compute.json").write_text(json.dumps(["compute-rule-a"]))

    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        screen._load_json_selection("compute")
        table = screen.query_one("#all_rules_table")
        row_key_b = next(r.key for r in table.ordered_rows if str(r.key.value) == "compute-rule-b")
        screen._toggle_checkbox(row_key_b)  # now checked: rule-a (from load) + rule-b

        screen._on_save_pressed()
        await pilot.pause()

        assert isinstance(app.screen, BrowseScreen)  # no SaveAsScreen modal shown
        saved = json.loads((_fake_json_dir / "compute.json").read_text())
        assert sorted(saved) == ["compute-rule-a", "compute-rule-b"]


@pytest.mark.asyncio
async def test_save_without_active_file_opens_saveas_modal_and_writes_new_file(_fake_json_dir):
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        table = screen.query_one("#all_rules_table")
        row_key = next(r.key for r in table.ordered_rows if str(r.key.value) == "storage-rule-c")
        screen._toggle_checkbox(row_key)

        screen._on_save_pressed()
        await pilot.pause()

        assert isinstance(app.screen, SaveAsScreen)

        app.query_one("#saveas-name").value = "storage"
        await pilot.click("#saveas-yes")
        await pilot.pause()

        assert isinstance(app.screen, BrowseScreen)
        assert screen._active_json_file == "storage"
        saved = json.loads((_fake_json_dir / "storage.json").read_text())
        assert saved == ["storage-rule-c"]
        # The new file is now selectable in the dropdown too.
        assert "storage" in screen._list_json_files()
        select = screen.query_one("#json_select")
        assert select.value == "storage"  # _refresh_json_dropdown kept it selected
