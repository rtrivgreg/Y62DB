#!/usr/bin/env python3
"""
Y62DB HTTP Contract Exerciser

Menu choices 1-8 exercise the current REST API contract exposed by
rtrivgreg/aws-crud-rules-db.

The client supports BOTH synchronous and asynchronous HTTP execution.

Environment variables:
  Y62DB_BASE_URL      e.g. https://abc123.execute-api.us-east-1.amazonaws.com/dev
  Y62DB_BEARER_TOKEN  optional Cognito/JWT bearer token

Dependency:
  pip install httpx
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class Config:
    base_url: str
    bearer_token: str = ""
    timeout_seconds: float = 20.0

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers


def pretty(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=False, default=str))


def normalize_base_url(url: str) -> str:
    return url.strip().rstrip("/")


def read_config() -> Config:
    env_url = os.getenv("Y62DB_BASE_URL", "").strip()
    env_token = os.getenv("Y62DB_BEARER_TOKEN", "").strip()

    base_url = env_url or input("Y62DB API base URL: ").strip()
    if not base_url:
        print("A base URL is required.")
        sys.exit(2)

    if env_token:
        token = env_token
    else:
        token = input(
            "Bearer token (press Enter if endpoint does not require one): "
        ).strip()

    return Config(base_url=normalize_base_url(base_url), bearer_token=token)


def decode_response(response: httpx.Response) -> Any:
    print(f"\nHTTP {response.status_code} {response.reason_phrase}")
    print(f"URL: {response.request.url}")

    if response.status_code == 204 or not response.content:
        print("(no response body)")
        return None

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        try:
            body = response.json()
            pretty(body)
            return body
        except ValueError:
            pass

    print(response.text)
    return response.text


def sync_request(
    cfg: Config,
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> Any:
    url = f"{cfg.base_url}{path}"
    with httpx.Client(
        headers=cfg.headers,
        timeout=cfg.timeout_seconds,
        follow_redirects=True,
    ) as client:
        response = client.request(method, url, params=params, json=json_body)
        return decode_response(response)


async def async_request(
    cfg: Config,
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> Any:
    url = f"{cfg.base_url}{path}"
    async with httpx.AsyncClient(
        headers=cfg.headers,
        timeout=cfg.timeout_seconds,
        follow_redirects=True,
    ) as client:
        response = await client.request(method, url, params=params, json=json_body)
        return decode_response(response)


def choose_execution_mode() -> str:
    while True:
        mode = input("Execution mode [S]ync / [A]sync (default S): ").strip().lower()
        if mode in ("", "s", "sync"):
            return "sync"
        if mode in ("a", "async"):
            return "async"
        print("Enter S or A.")


def execute(
    cfg: Config,
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> Any:
    mode = choose_execution_mode()
    try:
        if mode == "sync":
            return sync_request(cfg, method, path, params=params, json_body=json_body)
        return asyncio.run(
            async_request(cfg, method, path, params=params, json_body=json_body)
        )
    except httpx.TimeoutException as exc:
        print(f"\nTIMEOUT: {exc}")
    except httpx.ConnectError as exc:
        print(f"\nCONNECTION ERROR: {exc}")
    except httpx.HTTPError as exc:
        print(f"\nHTTP CLIENT ERROR: {exc}")
    except KeyboardInterrupt:
        print("\nRequest cancelled.")
    return None


def ask_nonempty(label: str, default: str = "") -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print(f"{label} is required.")


def ask_int(label: str, default: Optional[int] = None) -> int:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{label}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            return int(raw)
        except ValueError:
            print("Enter an integer.")


def ask_json_object(label: str, default_obj: dict[str, Any]) -> dict[str, Any]:
    print(f"\n{label}")
    print("Press Enter to use this example:")
    pretty(default_obj)
    raw = input("JSON object: ").strip()
    if not raw:
        return default_obj
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}. Using the example instead.")
        return default_obj
    if not isinstance(obj, dict):
        print("JSON must be an object. Using the example instead.")
        return default_obj
    return obj


def option_1_rules(cfg: Config) -> None:
    """GET /rules"""
    execute(cfg, "GET", "/rules")


def option_2_groups(cfg: Config) -> None:
    """GET /groups"""
    execute(cfg, "GET", "/groups")


def option_3_catalog(cfg: Config) -> None:
    """GET /rules/{ruleId}/catalog"""
    rule_id = ask_nonempty("Rule ID", "access-keys-rotated")
    execute(cfg, "GET", f"/rules/{rule_id}/catalog")


def option_4_list_bindings(cfg: Config) -> None:
    """
    Exercise the two list-binding GET contracts:
      GET /rules/{ruleId}/bindings
      GET /groups/{group}/bindings
    """
    print("\nList bindings:")
    print("  1. By rule")
    print("  2. By group")
    sub = input("Choose 1 or 2: ").strip()

    limit = ask_int("Limit", 20)
    cursor = input("Cursor (Enter for none): ").strip()
    params: dict[str, Any] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor

    if sub == "2":
        group = ask_nonempty("Group", "corp")
        execute(cfg, "GET", f"/groups/{group}/bindings", params=params)
    else:
        rule_id = ask_nonempty("Rule ID", "access-keys-rotated")
        execute(cfg, "GET", f"/rules/{rule_id}/bindings", params=params)


def option_5_get_binding(cfg: Config) -> None:
    """GET /rules/{ruleId}/bindings/{group}/{binding}"""
    rule_id = ask_nonempty("Rule ID", "access-keys-rotated")
    group = ask_nonempty("Group", "corp")
    binding = ask_nonempty("Binding", "default")
    execute(cfg, "GET", f"/rules/{rule_id}/bindings/{group}/{binding}")


def option_6_create_binding(cfg: Config) -> None:
    """POST /rules/{ruleId}/bindings"""
    rule_id = ask_nonempty("Rule ID", "access-keys-rotated")
    group = ask_nonempty("Group", "corp")
    binding = ask_nonempty("Binding", "default")

    payload = ask_json_object(
        "Binding payload",
        {
            "status": "ACTIVE",
            "version": 1,
            "maxAccessKeyAge": 60,
        },
    )

    body = {
        "group": group,
        "binding": binding,
        "payload": payload,
    }
    execute(cfg, "POST", f"/rules/{rule_id}/bindings", json_body=body)


def option_7_update_binding(cfg: Config) -> None:
    """PUT /rules/{ruleId}/bindings/{group}/{binding}"""
    rule_id = ask_nonempty("Rule ID", "access-keys-rotated")
    group = ask_nonempty("Group", "corp")
    binding = ask_nonempty("Binding", "default")
    expected_version = ask_int("Version you last read (expected_version)", 1)

    payload = ask_json_object(
        "Replacement payload",
        {
            "status": "ACTIVE",
            "version": expected_version + 1,
            "maxAccessKeyAge": 45,
        },
    )

    body = {
        "payload": payload,
        "expected_version": expected_version,
    }
    execute(
        cfg,
        "PUT",
        f"/rules/{rule_id}/bindings/{group}/{binding}",
        json_body=body,
    )


def option_8_delete_binding(cfg: Config) -> None:
    """DELETE /rules/{ruleId}/bindings/{group}/{binding}"""
    rule_id = ask_nonempty("Rule ID", "access-keys-rotated")
    group = ask_nonempty("Group", "corp")
    binding = ask_nonempty("Binding", "default")

    print(
        f"\nWARNING: this will DELETE "
        f"{rule_id} / {group} / {binding} from the target API."
    )
    confirm = input("Type DELETE to continue: ").strip()
    if confirm != "DELETE":
        print("Delete cancelled.")
        return

    execute(cfg, "DELETE", f"/rules/{rule_id}/bindings/{group}/{binding}")


MENU = {
    "1": ("GET /rules - list rules", option_1_rules),
    "2": ("GET /groups - list groups", option_2_groups),
    "3": ("GET /rules/{ruleId}/catalog - read rule catalog", option_3_catalog),
    "4": ("GET bindings - list by rule or by group", option_4_list_bindings),
    "5": ("GET one binding", option_5_get_binding),
    "6": ("POST - create binding", option_6_create_binding),
    "7": ("PUT - replace/update binding payload", option_7_update_binding),
    "8": ("DELETE - remove binding", option_8_delete_binding),
}


def print_menu(cfg: Config) -> None:
    print("\n" + "=" * 78)
    print("Y62DB HTTP CONTRACT EXERCISER")
    print(f"Base URL: {cfg.base_url}")
    print("Authorization: " + ("Bearer token configured" if cfg.bearer_token else "none"))
    print("=" * 78)
    for number, (label, _) in MENU.items():
        print(f"{number}. {label}")
    print("Q. Quit")


def main() -> None:
    cfg = read_config()

    while True:
        print_menu(cfg)
        choice = input("\nChoice: ").strip().lower()

        if choice in ("q", "quit", "exit"):
            print("Goodbye.")
            return

        entry = MENU.get(choice)
        if entry is None:
            print("Choose 1 through 8, or Q.")
            continue

        _, handler = entry
        print()
        handler(cfg)
        input("\nPress Enter to return to the menu...")


if __name__ == "__main__":
    main()
