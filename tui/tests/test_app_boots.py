"""
Headless smoke test: the app mounts and shows the login screen without
crashing, and basic form validation fires without any live network call.
Uses Textual's own Pilot/run_test() testing utilities — no live AWS calls.
"""

import pytest

from tui.app import BindingsTUI, LoginScreen


@pytest.mark.asyncio
async def test_app_boots_to_login_screen():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        assert isinstance(app.screen, LoginScreen)
        assert app.query_one("#username") is not None
        assert app.query_one("#password") is not None


@pytest.mark.asyncio
async def test_login_requires_both_fields():
    app = BindingsTUI()
    async with app.run_test() as pilot:
        # Leave both fields empty and click Sign in — should show a client-side
        # error, no network call attempted.
        await pilot.click("#signin-btn")
        await pilot.pause()
        error_text = app.query_one("#login-error").renderable
        assert "required" in str(error_text)
