#!/usr/bin/env python3
"""
Y62DB NiceGUI CRUD Browser

Current scope:
- Connects only to the existing Y62DB REST/JSON contract.
- Loads all AWS Config rules from GET /rules.
- Presents them in a searchable/selectable list.
- On selection, loads GET /rules/{ruleId}/catalog.
- Also loads GET /rules/{ruleId}/bindings and shows current bindings.
- Does NOT know or use DynamoDB pk/sk/GSI details.

Environment variables:
  Y62DB_BASE_URL
  Y62DB_BEARER_TOKEN   (optional if your endpoint does not require auth)
  Y62DB_PORT           (optional; default 8080)
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

import httpx
from nicegui import ui

BASE_URL = os.getenv("Y62DB_BASE_URL", "").strip().rstrip("/")
BEARER_TOKEN = os.getenv("Y62DB_BEARER_TOKEN", "").strip()
PORT = int(os.getenv("Y62DB_PORT", "8080"))

if not BASE_URL:
    raise RuntimeError(
        "Y62DB_BASE_URL is required. Example:\n"
        "export Y62DB_BASE_URL='https://YOUR-API.execute-api.us-east-1.amazonaws.com/dev'"
    )

HEADERS = {"Accept": "application/json"}
if BEARER_TOKEN:
    HEADERS["Authorization"] = f"Bearer {BEARER_TOKEN}"


async def api_get(
    path: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """GET one Y62DB REST resource and return the decoded contract envelope."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers=HEADERS,
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        response = await client.get(path, params=params)

    if response.status_code >= 400:
        try:
            body = response.json()
            message = body.get("error", {}).get("message") or f"HTTP {response.status_code}"
        except Exception:
            message = response.text or f"HTTP {response.status_code}"
        raise RuntimeError(message)

    if response.status_code == 204:
        return {"success": True, "data": None, "error": None, "meta": {}}

    return response.json()


@ui.page("/")
def main_page() -> None:
    state = {
        "rules": [],
        "selected_rule": None,
    }

    ui.label("Y62DB AWS Config Rule Browser").classes("text-2xl font-bold")
    ui.label(
        "REST/JSON contract client — UI → API Gateway/Lambda → DynamoDB"
    ).classes("text-sm text-gray-500")

    with ui.row().classes("w-full items-start gap-6"):
        # Left side: rules
        with ui.card().classes("w-1/3 min-w-[360px]"):
            ui.label("AWS Config Rules").classes("text-lg font-semibold")

            search = ui.input(
                "Filter rules",
                placeholder="Type part of a rule ID...",
            ).props("clearable").classes("w-full")

            rule_select = ui.select(
                options=[],
                label="Select a Config rule",
                with_input=True,
            ).props(
                'use-input input-debounce="0" behavior="menu"'
            ).classes("w-full")

            with ui.row().classes("gap-2"):
                refresh_button = ui.button("Refresh Rules", icon="refresh")
                count_label = ui.label("0 rules").classes("text-sm text-gray-500")

            rules_status = ui.label("").classes("text-sm")

        # Right side: catalog detail + current bindings
        with ui.column().classes("flex-1 gap-4"):
            with ui.card().classes("w-full"):
                ui.label("Rule Catalog Detail").classes("text-lg font-semibold")
                detail_status = ui.label(
                    "Select a rule to load its catalog metadata."
                ).classes("text-sm text-gray-500")

                rule_id_label = ui.label("").classes("text-xl font-semibold")
                source_id_label = ui.label("")
                severity_label = ui.label("")
                description_label = ui.label("").classes("whitespace-pre-wrap")
                scopes_label = ui.label("").classes("whitespace-pre-wrap")

                ui.separator()
                ui.label("Parameters").classes("text-md font-semibold")

                parameter_table = ui.table(
                    columns=[
                        {"name": "name", "label": "Name", "field": "name", "align": "left"},
                        {"name": "data_type", "label": "Type", "field": "data_type", "align": "left"},
                        {"name": "required", "label": "Required", "field": "required", "align": "left"},
                        {"name": "default_value", "label": "Default", "field": "default_value", "align": "left"},
                    ],
                    rows=[],
                    row_key="name",
                ).classes("w-full")

            with ui.card().classes("w-full"):
                ui.label("Current Bindings").classes("text-lg font-semibold")
                bindings_status = ui.label(
                    "Select a rule to load its current bindings."
                ).classes("text-sm text-gray-500")

                bindings_table = ui.table(
                    columns=[
                        {"name": "group", "label": "Group", "field": "group", "align": "left"},
                        {"name": "binding", "label": "Binding", "field": "binding", "align": "left"},
                        {"name": "status", "label": "Status", "field": "status", "align": "left"},
                        {"name": "version", "label": "Version", "field": "version", "align": "left"},
                        {"name": "updated_at", "label": "Updated", "field": "updated_at", "align": "left"},
                        {"name": "payload", "label": "Other Payload", "field": "payload", "align": "left"},
                    ],
                    rows=[],
                    row_key="row_key",
                ).classes("w-full")

    def clear_detail() -> None:
        rule_id_label.set_text("")
        source_id_label.set_text("")
        severity_label.set_text("")
        description_label.set_text("")
        scopes_label.set_text("")
        parameter_table.rows = []
        parameter_table.update()

    def clear_bindings() -> None:
        bindings_table.rows = []
        bindings_table.update()

    def filtered_rule_ids() -> list[str]:
        needle = (search.value or "").strip().lower()
        all_ids = [r["rule_id"] for r in state["rules"]]
        if not needle:
            return all_ids
        return [rid for rid in all_ids if needle in rid.lower()]

    def apply_filter() -> None:
        rule_select.options = filtered_rule_ids()
        rule_select.update()

    async def load_catalog(rule_id: str | None) -> None:
        if not rule_id:
            clear_detail()
            detail_status.set_text("Select a rule to load its catalog metadata.")
            return

        state["selected_rule"] = rule_id
        clear_detail()
        rule_id_label.set_text(rule_id)
        detail_status.set_text("Loading catalog metadata...")

        try:
            envelope = await api_get(f"/rules/{rule_id}/catalog")
            if not envelope.get("success", False):
                err = envelope.get("error") or {}
                raise RuntimeError(err.get("message", "API returned success=false"))

            data = envelope.get("data") or {}

            rule_id_label.set_text(data.get("rule_id", rule_id))
            source_id_label.set_text(
                f"Source identifier: {data.get('source_identifier', '') or '(none)'}"
            )
            severity_label.set_text(
                f"Severity: {data.get('severity', '') or '(not supplied)'}"
            )
            description_label.set_text(
                f"Description:\n{data.get('description', '') or '(not supplied)'}"
            )

            scopes = data.get("scopes") or []
            scopes_label.set_text(
                "Scopes:\n" + ("\n".join(f"• {s}" for s in scopes) if scopes else "(none)")
            )

            params = data.get("parameters") or []
            parameter_table.rows = [
                {
                    "name": p.get("name", ""),
                    "data_type": p.get("data_type", ""),
                    "required": "Yes" if p.get("required") else "No",
                    "default_value": p.get("default_value", ""),
                }
                for p in params
            ]
            parameter_table.update()

            detail_status.set_text(
                f"Catalog loaded: {len(parameter_table.rows)} parameter(s)."
            )
        except Exception as exc:
            detail_status.set_text(f"Error: {exc}")
            ui.notify(f"Unable to load catalog for {rule_id}: {exc}", type="negative")

    async def load_bindings(rule_id: str | None) -> None:
        if not rule_id:
            clear_bindings()
            bindings_status.set_text("Select a rule to load its current bindings.")
            return

        clear_bindings()
        bindings_status.set_text("Loading current bindings...")

        try:
            items: list[dict[str, Any]] = []
            cursor: str | None = None

            while True:
                params: dict[str, Any] = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                envelope = await api_get(
                    f"/rules/{rule_id}/bindings",
                    params=params,
                )
                if not envelope.get("success", False):
                    err = envelope.get("error") or {}
                    raise RuntimeError(err.get("message", "API returned success=false"))

                page = envelope.get("data") or []
                items.extend(i for i in page if isinstance(i, dict))

                meta = envelope.get("meta") or {}
                cursor = meta.get("next_cursor")
                if not cursor:
                    break

            rows = []
            for item in items:
                payload = item.get("payload") or {}
                remaining_payload = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"status", "version"}
                }
                group = item.get("group", "")
                binding = item.get("binding", "")
                rows.append(
                    {
                        "row_key": f"{group}::{binding}",
                        "group": group,
                        "binding": binding,
                        "status": payload.get("status", ""),
                        "version": payload.get("version", ""),
                        "updated_at": item.get("updated_at", "") or "",
                        "payload": (
                            json.dumps(remaining_payload, sort_keys=True, default=str)
                            if remaining_payload
                            else ""
                        ),
                    }
                )

            bindings_table.rows = rows
            bindings_table.update()

            if rows:
                bindings_status.set_text(f"{len(rows)} binding(s) loaded.")
            else:
                bindings_status.set_text("No current bindings for this rule.")
        except Exception as exc:
            bindings_status.set_text(f"Error: {exc}")
            ui.notify(
                f"Unable to load bindings for {rule_id}: {exc}",
                type="negative",
            )

    async def load_selected_rule(rule_id: str | None) -> None:
        await asyncio.gather(
            load_catalog(rule_id),
            load_bindings(rule_id),
        )

    async def load_rules() -> None:
        refresh_button.disable()
        rules_status.set_text("Loading rules...")
        clear_detail()
        clear_bindings()
        try:
            envelope = await api_get("/rules")
            if not envelope.get("success", False):
                err = envelope.get("error") or {}
                raise RuntimeError(err.get("message", "API returned success=false"))

            rows = envelope.get("data") or []
            state["rules"] = sorted(
                [r for r in rows if isinstance(r, dict) and r.get("rule_id")],
                key=lambda r: r["rule_id"].lower(),
            )

            rule_select.options = [r["rule_id"] for r in state["rules"]]
            first_rule = rule_select.options[0] if rule_select.options else None
            rule_select.value = first_rule
            rule_select.update()

            count_label.set_text(f'{len(state["rules"])} rules')
            rules_status.set_text("Rules loaded successfully.")

            if first_rule:
                await load_selected_rule(first_rule)
            else:
                detail_status.set_text("No rules are available.")
                bindings_status.set_text("No rules are available.")
        except Exception as exc:
            state["rules"] = []
            rule_select.options = []
            rule_select.update()
            count_label.set_text("0 rules")
            rules_status.set_text(f"Error: {exc}")
            ui.notify(f"Unable to load rules: {exc}", type="negative")
        finally:
            refresh_button.enable()

    search.on("update:model-value", lambda _: apply_filter())
    rule_select.on_value_change(
        lambda event: ui.run_async(load_selected_rule(event.value))
    )
    refresh_button.on("click", lambda: ui.run_async(load_rules()))

    ui.timer(0.1, load_rules, once=True)


ui.run(
    title="Y62DB Config Rule Browser",
    host="127.0.0.1",
    port=PORT,
    reload=False,
)
