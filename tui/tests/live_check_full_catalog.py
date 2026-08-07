"""
Manual live-verification for the "initial view = full catalog list,
selection drives CRUD" feature. Not part of the automated pytest suite
(needs real Cognito credentials, hits the real live API). Run:

    python tui/tests/live_check_full_catalog.py <username> <password>
"""

import asyncio
import sys

sys.path.insert(0, ".")

from tui import auth
from tui.api_client import BindingsApiClient


async def main(username: str, password: str) -> None:
    print("Signing in...")
    id_token = await asyncio.to_thread(auth.sign_in, username, password)
    api = BindingsApiClient(id_token)
    rule_id, group, binding = "ui-test-rule", "ui-test-group", "tui-fullcatalog-livecheck"

    try:
        print("Loading full catalog (as the initial view does)...")
        rules = await api.list_all_rule_ids()
        print(f"  {len(rules)} rule(s) loaded.")
        assert len(rules) > 0

        # Pick a currently-unbound rule the way selecting a row would.
        unbound = [r["rule_id"] for r in rules if not r.get("has_binding") and r["rule_id"] != rule_id]
        target = unbound[0]
        print(f"Simulating row-select on unbound rule: {target}")
        bindings = await api.list_bindings_for_rule(target)
        assert bindings == []
        print("  correctly shows zero bindings -> would route to catalog table / create flow.")

        print(f"Simulating 'Create binding for selected' with prefilled rule_id={target}...")
        created = await api.create_binding(target, group, "tui-fullcatalog-livecheck", {"status": "ACTIVE", "version": 1})
        assert created is not None and created.rule_id == target
        print(f"  created: {created.key}")

        print("Confirming has_binding flips for that rule in the full list...")
        rules_after = await api.list_all_rule_ids()
        hb = {r["rule_id"]: r.get("has_binding", False) for r in rules_after}
        assert hb.get(target) is True
        print("  confirmed has_binding=True now.")

        print("Simulating row-select on the now-bound rule (loads its binding for edit/delete)...")
        loaded = await api.list_bindings_for_rule(target)
        assert len(loaded) == 1 and loaded[0].version == 1
        print(f"  loaded {len(loaded)} binding(s), version={loaded[0].version}.")

        print("Cleaning up...")
        await api.delete_binding(target, group, "tui-fullcatalog-livecheck")
        rules_final = await api.list_all_rule_ids()
        hb_final = {r["rule_id"]: r.get("has_binding", False) for r in rules_final}
        assert hb_final.get(target) is False
        print("  deleted, has_binding back to False.")

        print("\nALL LIVE CHECKS PASSED")
    finally:
        await api.aclose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python tui/tests/live_check_full_catalog.py <username> <password>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
