"""
Manual live-verification script (NOT part of the automated pytest suite —
requires real Cognito credentials and hits the real live API). Exercises
the exact BindingsApiClient methods the TUI screens call: create, list,
update (optimistic lock), delete. Run manually:

    python tui/tests/live_check.py <username> <password>
"""

import asyncio
import sys

sys.path.insert(0, ".")

from tui import auth
from tui.api_client import BindingsApiClient, BindingsApiError


async def main(username: str, password: str) -> None:
    print("Signing in...")
    id_token = await asyncio.to_thread(auth.sign_in, username, password)
    print("Signed in OK.")

    api = BindingsApiClient(id_token)
    rule_id, group, binding = "ui-test-rule", "ui-test-group", "tui-livecheck"

    try:
        print("Creating binding...")
        created = await api.create_binding(rule_id, group, binding, {"status": "ACTIVE", "version": 1})
        assert created is not None and created.version == 1
        print(f"  created: {created.key} version={created.version}")

        print("Listing bindings for rule...")
        listed = await api.list_bindings_for_rule(rule_id)
        assert any(b.binding == binding for b in listed)
        print(f"  found {len(listed)} binding(s), including ours.")

        print("Updating binding (optimistic lock, version 1 -> 2)...")
        updated = await api.update_binding(rule_id, group, binding, {"status": "INACTIVE", "version": 2}, expected_version=1)
        assert updated is not None and updated.version == 2 and updated.status == "INACTIVE"
        print(f"  updated: version={updated.version} status={updated.status}")

        print("Confirming stale-version update is rejected (409 conflict)...")
        try:
            await api.update_binding(rule_id, group, binding, {"status": "ACTIVE", "version": 3}, expected_version=1)
            print("  FAIL: stale update should have raised BindingsApiError(conflict)")
        except BindingsApiError as e:
            assert e.code == "conflict", f"expected conflict, got {e.code}"
            print(f"  correctly rejected: {e.code} (HTTP {e.status})")

        print("Deleting binding...")
        await api.delete_binding(rule_id, group, binding)
        print("  deleted.")

        print("Confirming it's gone...")
        listed_after = await api.list_bindings_for_rule(rule_id)
        assert not any(b.binding == binding for b in listed_after)
        print("  confirmed gone.")

        print("\nALL LIVE CHECKS PASSED")
    finally:
        await api.aclose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python tui/tests/live_check.py <username> <password>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
