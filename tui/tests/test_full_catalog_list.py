"""
Headless tests for the new "initial view" feature: a scrollable list of
every catalog rule with an inert (not-yet-wired) checkbox placeholder,
where selecting a row drives the existing CRUD flow exactly like a
search hit would. No live network calls — the API client is a fake.
"""

import pytest

from tui.api_client import Binding
from tui.app import BindingsTUI, BrowseScreen


class _FakeApi:
    def __init__(self):
        self.deleted = []

    async def list_all_rule_ids(self):
        return [
            {"rule_id": "cloudfront-s3-origin-access-control-enabled", "has_binding": True},
            {"rule_id": "sagemaker-domain-in-vpc", "has_binding": False},
            {"rule_id": "ui-test-rule", "has_binding": True},
        ]

    async def list_bindings_for_rule(self, rule_id):
        if rule_id == "cloudfront-s3-origin-access-control-enabled":
            return [
                Binding(
                    rule_id=rule_id,
                    group="corp",
                    binding="default",
                    payload={"status": "ACTIVE", "version": 1},
                )
            ]
        if rule_id == "ui-test-rule":
            return [
                Binding(
                    rule_id=rule_id,
                    group="ui-test-group",
                    binding="qa-d1",
                    payload={"status": "ACTIVE", "version": 1},
                )
            ]
        return []

    async def list_all_groups(self):
        return []

    async def list_bindings_for_group(self, group):
        return []

    async def delete_binding(self, rule_id, group, binding):
        self.deleted.append((rule_id, group, binding))

    async def aclose(self):
        pass


async def _mounted_screen(app):
    screen = BrowseScreen("fake-token")
    screen.api = _FakeApi()
    await app.push_screen(screen)
    return screen


@pytest.mark.asyncio
async def test_full_catalog_list_populates_on_mount():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()  # let the mount-time worker finish

        all_rules_table = screen.query_one("#all_rules_table")
        assert all_rules_table.row_count == 3
        # Placeholder checkbox glyph renders in the first column for every row.
        for row_key in ("cloudfront-s3-origin-access-control-enabled", "sagemaker-domain-in-vpc", "ui-test-rule"):
            row = all_rules_table.get_row(row_key)
            assert row[0] == screen._CHECKBOX_PLACEHOLDER


@pytest.mark.asyncio
async def test_selecting_bound_rule_in_full_list_loads_its_bindings():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        screen._load_bindings_for_rule_id("cloudfront-s3-origin-access-control-enabled")
        await pilot.pause()
        await pilot.pause()

        results_table = screen.query_one("#results_table")
        catalog_table = screen.query_one("#catalog_table")
        assert results_table.row_count == 1
        assert catalog_table.row_count == 0
        assert screen._current_rule_id == "cloudfront-s3-origin-access-control-enabled"


@pytest.mark.asyncio
async def test_selecting_unbound_rule_in_full_list_offers_create():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        screen._load_bindings_for_rule_id("sagemaker-domain-in-vpc")
        await pilot.pause()
        await pilot.pause()

        results_table = screen.query_one("#results_table")
        catalog_table = screen.query_one("#catalog_table")
        assert results_table.row_count == 0
        assert catalog_table.row_count == 1
        assert "sagemaker-domain-in-vpc" in screen._unbound_rule_ids
        assert screen._current_rule_id == "sagemaker-domain-in-vpc"


@pytest.mark.asyncio
async def test_delete_refreshes_the_rule_selected_from_full_list_not_a_stale_search():
    """Regression check: before this feature, refresh-after-delete always
    called _run_search(), which silently no-ops when the search box is
    empty — the exact state you're in right after picking a row from the
    full list instead of typing a query."""
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = await _mounted_screen(app)
        await pilot.pause()
        await pilot.pause()

        # Query box is empty — selection came from the full-catalog list.
        assert app.query_one("#query_input").value == ""

        screen._load_bindings_for_rule_id("cloudfront-s3-origin-access-control-enabled")
        await pilot.pause()
        await pilot.pause()

        binding = screen.selected_binding
        assert binding is None  # row not clicked in results_table yet
        # Simulate selecting the one result row so delete has a target.
        results_table = screen.query_one("#results_table")
        results_table.move_cursor(row=0)
        results_table.action_select_cursor()
        await pilot.pause()
        assert screen.selected_binding is not None

        screen._do_delete(screen.selected_binding)
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        assert len(screen.api.deleted) == 1
        # _refresh_current_view() must have re-run _load_bindings_for_rule_id,
        # not a no-op _run_search() against an empty query box.
        assert screen._current_rule_id == "cloudfront-s3-origin-access-control-enabled"
