"""
Headless test for the catalog-search addition to BrowseScreen: search
results should be split into (a) existing bindings shown in the main
table, and (b) unbound catalog rule IDs shown in the separate
"catalog_table", with a "Create binding for selected" action wired up.
No live network calls — the API client is monkeypatched.
"""

import pytest

from tui.api_client import Binding
from tui.app import BindingsTUI, BrowseScreen


class _FakeApi:
    """Stands in for BindingsApiClient with a small fixed dataset."""

    async def list_all_rule_ids(self):
        return [
            {"rule_id": "cloudfront-s3-origin-access-control-enabled", "has_binding": True},
            {"rule_id": "s3-bucket-public-read-prohibited", "has_binding": False},
            {"rule_id": "s3-access-point-in-vpc-only", "has_binding": False},
            {"rule_id": "sagemaker-domain-in-vpc", "has_binding": False},
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
        return []

    async def list_all_groups(self):
        return ["corp", "smoke-test"]

    async def list_bindings_for_group(self, group):
        return []

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_search_splits_bound_and_unbound_rules():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = BrowseScreen("fake-token")
        screen.api = _FakeApi()  # swap in the fake before mounting
        await app.push_screen(screen)
        await pilot.pause()

        app.query_one("#query_input").value = "s3"
        screen._run_search()
        await pilot.pause()
        await pilot.pause()  # let the @work task finish

        results_table = screen.query_one("#results_table")
        catalog_table = screen.query_one("#catalog_table")

        # One bound match (cloudfront-s3-origin-access-control-enabled).
        assert results_table.row_count == 1
        # Two unbound catalog matches (s3-bucket-public-read-prohibited,
        # s3-access-point-in-vpc-only) — sagemaker-domain-in-vpc doesn't
        # contain "s3" so it's correctly excluded.
        assert catalog_table.row_count == 2
        assert set(screen._unbound_rule_ids.keys()) == {
            "s3-bucket-public-read-prohibited",
            "s3-access-point-in-vpc-only",
        }


@pytest.mark.asyncio
async def test_search_no_catalog_matches_for_sagemaker_without_s3():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = BrowseScreen("fake-token")
        screen.api = _FakeApi()
        await app.push_screen(screen)
        await pilot.pause()

        app.query_one("#query_input").value = "sage"
        screen._run_search()
        await pilot.pause()
        await pilot.pause()

        results_table = screen.query_one("#results_table")
        catalog_table = screen.query_one("#catalog_table")

        assert results_table.row_count == 0
        # sagemaker-domain-in-vpc matches "sage" as a substring and has no binding.
        assert catalog_table.row_count == 1
        assert "sagemaker-domain-in-vpc" in screen._unbound_rule_ids


@pytest.mark.asyncio
async def test_selecting_catalog_row_enables_create_button():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        screen = BrowseScreen("fake-token")
        screen.api = _FakeApi()
        await app.push_screen(screen)
        await pilot.pause()

        app.query_one("#query_input").value = "s3"
        screen._run_search()
        await pilot.pause()
        await pilot.pause()

        create_btn = screen.query_one("#create-from-catalog-btn")
        assert create_btn.disabled is True

        catalog_table = screen.query_one("#catalog_table")
        catalog_table.move_cursor(row=0)
        catalog_table.action_select_cursor()
        await pilot.pause()

        assert create_btn.disabled is False
        assert screen.selected_catalog_rule_id in screen._unbound_rule_ids
