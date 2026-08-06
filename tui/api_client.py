"""
Thin async client for the Y62DB Bindings CRUD API (`RULE_BINDING` entities
only — see repo root `api/README.md` for the full contract). Direct
Python counterpart of `ui/src/api/bindingsApi.ts` — same endpoints, same
envelope-unwrapping, same error semantics, so the TUI's behavior matches
the web UI's.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .config import API_BASE_URL


def _enc(s: str) -> str:
    return quote(s, safe="")


class BindingsApiError(Exception):
    """Thrown for both transport failures and API-reported errors (4xx/5xx)."""

    def __init__(self, message: str, code: str, status: int, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details


@dataclass
class Binding:
    rule_id: str
    group: str
    binding: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def status(self) -> str:
        return str(self.payload.get("status", ""))

    @property
    def version(self) -> int:
        return int(self.payload.get("version", 0))

    @property
    def key(self) -> str:
        return f"{self.rule_id}#{self.group}#{self.binding}"

    @classmethod
    def from_json(cls, d: dict) -> "Binding":
        return cls(
            rule_id=d["rule_id"],
            group=d["group"],
            binding=d["binding"],
            payload=d.get("payload") or {},
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )


class BindingsApiClient:
    """One instance per signed-in session — holds the bearer token and an httpx client."""

    def __init__(self, id_token: str, base_url: str = API_BASE_URL):
        self._id_token = id_token
        self._client = httpx.AsyncClient(base_url=base_url, timeout=15.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self, has_body: bool) -> dict[str, str]:
        headers = {"Authorization": self._id_token}
        if has_body:
            headers["Content-Type"] = "application/json"
        return headers

    async def _request(
        self, method: str, path: str, json_body: Optional[dict] = None
    ) -> Any:
        resp = await self._client.request(
            method, path, json=json_body, headers=self._headers(json_body is not None)
        )
        # DELETE returns 204 with no body.
        if resp.status_code == 204:
            return None

        envelope = resp.json()
        if not resp.is_success or not envelope.get("success"):
            err = envelope.get("error") or {}
            raise BindingsApiError(
                err.get("message") or f"Request failed with status {resp.status_code}",
                err.get("code") or "unknown_error",
                resp.status_code,
                err.get("details"),
            )
        return envelope.get("data")

    # --- GET /rules/{ruleId}/bindings — every group a rule is bound to. ---
    async def list_bindings_for_rule(self, rule_id: str) -> list[Binding]:
        data = await self._request("GET", f"/rules/{_enc(rule_id)}/bindings") or []
        return [Binding.from_json(b) for b in data]

    # --- GET /groups/{group}/bindings — every rule bound to a group. ---
    async def list_bindings_for_group(self, group: str) -> list[Binding]:
        data = await self._request("GET", f"/groups/{_enc(group)}/bindings") or []
        return [Binding.from_json(b) for b in data]

    # --- GET /rules/{ruleId}/bindings/{group}/{binding} — a single binding. ---
    async def get_binding(self, rule_id: str, group: str, binding: str) -> Optional[Binding]:
        data = await self._request(
            "GET", f"/rules/{_enc(rule_id)}/bindings/{_enc(group)}/{_enc(binding)}"
        )
        return Binding.from_json(data) if data else None

    # --- POST /rules/{ruleId}/bindings — create. 409 if it already exists. ---
    async def create_binding(
        self,
        rule_id: str,
        group: str,
        binding: Optional[str],
        payload: dict[str, Any],
    ) -> Optional[Binding]:
        body = {"group": group, "binding": binding, "payload": payload}
        data = await self._request("POST", f"/rules/{_enc(rule_id)}/bindings", body)
        return Binding.from_json(data) if data else None

    # --- PUT .../{group}/{binding} — full replace, guarded by optimistic locking. ---
    async def update_binding(
        self,
        rule_id: str,
        group: str,
        binding: str,
        payload: dict[str, Any],
        expected_version: int,
    ) -> Optional[Binding]:
        body = {"payload": payload, "expected_version": expected_version}
        data = await self._request(
            "PUT", f"/rules/{_enc(rule_id)}/bindings/{_enc(group)}/{_enc(binding)}", body
        )
        return Binding.from_json(data) if data else None

    # --- DELETE .../{group}/{binding} — 204 on success. ---
    async def delete_binding(self, rule_id: str, group: str, binding: str) -> None:
        await self._request(
            "DELETE", f"/rules/{_enc(rule_id)}/bindings/{_enc(group)}/{_enc(binding)}"
        )

    # --- GET /rules — merged catalog + bindings view; each entry tagged with has_binding. ---
    async def list_all_rule_ids(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/rules") or []

    # --- GET /groups — every distinct group with at least one binding. ---
    async def list_all_groups(self) -> list[str]:
        return await self._request("GET", "/groups") or []
