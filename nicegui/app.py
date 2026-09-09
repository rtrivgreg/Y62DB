#!/usr/bin/env python3
"""Y62DB NiceGUI CRUD Browser."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional
from urllib.parse import quote

import httpx
from nicegui import ui

BASE_URL = os.getenv("Y62DB_BASE_URL", "").strip().rstrip("/")
BEARER_TOKEN = os.getenv("Y62DB_BEARER_TOKEN", "").strip()
PORT = int(os.getenv("Y62DB_PORT", "8080"))

if not BASE_URL:
    raise RuntimeError("Y62DB_BASE_URL is required")

HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
if BEARER_TOKEN:
    HEADERS["Authorization"] = f"Bearer {BEARER_TOKEN}"


async def api_request(
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers=HEADERS,
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        response = await client.request(method, path, params=params, json=json_body)

    if response.status_code >= 400:
        try:
            body = response.json()
            error = body.get("error") or {}
            message = error.get("message") or f"HTTP {response.status_code}"
            details = error.get("details") or {}
            if details:
                message = f"{message}\n{json.dumps(details, indent=2, default=str)}"
        except Exception:
            message = response.text or f"HTTP {response.status_code}"
        raise RuntimeError(message)

    if response.status_code == 204 or not response.content:
        return {"success": True, "data": None, "error": None, "meta": {}}
    return response.json()


async def api_get(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return await api_request("GET", path, params=params)


def parse_payload(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Payload is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Payload must be a JSON object.")
    return value


def binding_path(rule_id: str, group: str, binding: str) -> str:
    return (
        f"/rules/{quote(rule_id, safe='')}/bindings/"
        f"{quote(group, safe='')}/{quote(binding, safe='')}"
    )


@ui.page("/")
def main_page() -> None:
    state: dict[str, Any] = {"rules": [], "selected_rule": None}

    ui.label("Y62DB AWS Config Rule Browser").classes("text-2xl font-bold")
    ui.label("REST/JSON contract client — UI → API Gateway/Lambda → DynamoDB").classes(
        "text-sm text-gray-500"
    )

    with ui.row().classes("w-full items-start gap-6"):
        with ui.card().classes("w-1/3 min-w-[360px]"):
            ui.label("AWS Config Rules").classes("text-lg font-semibold")
            search = ui.input("Filter rules", placeholder="Type part of a rule ID...").props(
                "clearable"
            ).classes("w-full")
            rule_select = ui.select(
                options=[], label="Select a Config rule", with_input=True
            ).props('use-input input-debounce="0" behavior="menu"').classes("w-full")
            with ui.row().classes("gap-2"):
                refresh_button = ui.button("Refresh Rules", icon="refresh")
                count_label = ui.label("0 rules").classes("text-sm text-gray-500")
            rules_status = ui.label("").classes("text-sm")

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
                    selection="single",
                ).classes("w-full")
                with ui.row().classes("gap-2"):
                    create_button = ui.button("Create Binding", icon="add")
                    edit_button = ui.button("Edit Selected", icon="edit")
                    delete_button = ui.button("Delete Selected", icon="delete")
                    refresh_bindings_button = ui.button("Refresh Bindings", icon="refresh")
                ui.label("Select one binding row before Edit or Delete.").classes(
                    "text-xs text-gray-500"
                )

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
        bindings_table.selected = []
        bindings_table.update()

    def selected_binding() -> Optional[dict[str, Any]]:
        selected = bindings_table.selected or []
        return selected[0] if selected else None

    def filtered_rule_ids() -> list[str]:
        needle = (search.value or "").strip().lower()
        all_ids = [r["rule_id"] for r in state["rules"]]
        return all_ids if not needle else [rid for rid in all_ids if needle in rid.lower()]

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
            envelope = await api_get(f"/rules/{quote(rule_id, safe='')}/catalog")
            if not envelope.get("success", False):
                raise RuntimeError((envelope.get("error") or {}).get("message", "API returned success=false"))
            data = envelope.get("data") or {}
            rule_id_label.set_text(data.get("rule_id", rule_id))
            source_id_label.set_text(f"Source identifier: {data.get('source_identifier', '') or '(none)'}")
            severity_label.set_text(f"Severity: {data.get('severity', '') or '(not supplied)'}")
            description_label.set_text(f"Description:\n{data.get('description', '') or '(not supplied)'}")
            scopes = data.get("scopes") or []
            scopes_label.set_text("Scopes:\n" + ("\n".join(f"• {s}" for s in scopes) if scopes else "(none)"))
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
            detail_status.set_text(f"Catalog loaded: {len(parameter_table.rows)} parameter(s).")
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
                    f"/rules/{quote(rule_id, safe='')}/bindings", params=params
                )
                if not envelope.get("success", False):
                    raise RuntimeError((envelope.get("error") or {}).get("message", "API returned success=false"))
                page = envelope.get("data") or []
                items.extend(i for i in page if isinstance(i, dict))
                cursor = (envelope.get("meta") or {}).get("next_cursor")
                if not cursor:
                    break

            rows = []
            for item in items:
                payload = item.get("payload") or {}
                remaining_payload = {k: v for k, v in payload.items() if k not in {"status", "version"}}
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
                        "payload": json.dumps(remaining_payload, sort_keys=True, default=str) if remaining_payload else "",
                        "_payload": payload,
                    }
                )
            bindings_table.rows = rows
            bindings_table.selected = []
            bindings_table.update()
            bindings_status.set_text(
                f"{len(rows)} binding(s) loaded." if rows else "No current bindings for this rule."
            )
        except Exception as exc:
            bindings_status.set_text(f"Error: {exc}")
            ui.notify(f"Unable to load bindings for {rule_id}: {exc}", type="negative")

    async def load_selected_rule(rule_id: str | None) -> None:
        await asyncio.gather(load_catalog(rule_id), load_bindings(rule_id))

    async def load_rules() -> None:
        refresh_button.disable()
        rules_status.set_text("Loading rules...")
        clear_detail()
        clear_bindings()
        try:
            envelope = await api_get("/rules")
            if not envelope.get("success", False):
                raise RuntimeError((envelope.get("error") or {}).get("message", "API returned success=false"))
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

    async def load_rules_preserve_selection(rule_id: str) -> None:
        try:
            envelope = await api_get("/rules")
            if not envelope.get("success", False):
                return
            rows = envelope.get("data") or []
            state["rules"] = sorted(
                [r for r in rows if isinstance(r, dict) and r.get("rule_id")],
                key=lambda r: r["rule_id"].lower(),
            )
            rule_select.options = [r["rule_id"] for r in state["rules"]]
            rule_select.value = rule_id if rule_id in rule_select.options else None
            rule_select.update()
            count_label.set_text(f'{len(state["rules"])} rules')
        except Exception:
            pass

    async def create_binding() -> None:
        rule_id = state.get("selected_rule")
        if not rule_id:
            ui.notify("Select a rule first.", type="warning")
            return
        with ui.dialog() as dialog, ui.card().classes("w-[700px] max-w-full"):
            ui.label(f"Create Binding — {rule_id}").classes("text-lg font-semibold")
            group_input = ui.input("Group").classes("w-full")
            binding_input = ui.input("Binding", value="default").classes("w-full")
            payload_input = ui.textarea(
                "Payload JSON",
                value=json.dumps({"status": "ACTIVE", "version": 1}, indent=2),
            ).classes("w-full").props("rows=10")

            async def submit() -> None:
                try:
                    group = (group_input.value or "").strip()
                    binding = (binding_input.value or "default").strip()
                    if not group:
                        raise ValueError("Group is required.")
                    payload = parse_payload(payload_input.value or "{}")
                    await api_request(
                        "POST",
                        f"/rules/{quote(rule_id, safe='')}/bindings",
                        json_body={"group": group, "binding": binding, "payload": payload},
                    )
                    dialog.close()
                    ui.notify("Binding created.", type="positive")
                    await load_bindings(rule_id)
                    await load_rules_preserve_selection(rule_id)
                except Exception as exc:
                    ui.notify(f"Create failed: {exc}", type="negative", multi_line=True)

            with ui.row().classes("justify-end w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Create", on_click=submit, icon="add")
        dialog.open()

    async def edit_binding() -> None:
        rule_id = state.get("selected_rule")
        row = selected_binding()
        if not rule_id:
            ui.notify("Select a rule first.", type="warning")
            return
        if not row:
            ui.notify("Select one binding row first.", type="warning")
            return
        group = row["group"]
        binding = row["binding"]
        current_payload = dict(row.get("_payload") or {})
        expected_version = current_payload.get("version")

        with ui.dialog() as dialog, ui.card().classes("w-[700px] max-w-full"):
            ui.label(f"Edit Binding — {rule_id} / {group} / {binding}").classes("text-lg font-semibold")
            ui.label(f"Current version: {expected_version}").classes("text-sm text-gray-500")
            payload_input = ui.textarea(
                "Replacement Payload JSON",
                value=json.dumps(current_payload, indent=2, default=str),
            ).classes("w-full").props("rows=14")

            async def submit() -> None:
                try:
                    if expected_version is None:
                        raise ValueError("Selected binding has no payload.version.")
                    payload = parse_payload(payload_input.value or "{}")
                    if "version" not in payload:
                        raise ValueError("Replacement payload must contain version.")
                    await api_request(
                        "PUT",
                        binding_path(rule_id, group, binding),
                        json_body={"payload": payload, "expected_version": expected_version},
                    )
                    dialog.close()
                    ui.notify("Binding updated.", type="positive")
                    await load_bindings(rule_id)
                except Exception as exc:
                    ui.notify(f"Update failed: {exc}", type="negative", multi_line=True)

            with ui.row().classes("justify-end w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Update", on_click=submit, icon="save")
        dialog.open()

    async def delete_binding() -> None:
        rule_id = state.get("selected_rule")
        row = selected_binding()
        if not rule_id:
            ui.notify("Select a rule first.", type="warning")
            return
        if not row:
            ui.notify("Select one binding row first.", type="warning")
            return
        group = row["group"]
        binding = row["binding"]

        with ui.dialog() as dialog, ui.card():
            ui.label("Delete Binding").classes("text-lg font-semibold")
            ui.label(f"Delete {rule_id} / {group} / {binding}?")
            ui.label("This operation removes the binding from the API-backed catalog.").classes(
                "text-sm text-red-600"
            )

            async def confirm_delete() -> None:
                try:
                    await api_request("DELETE", binding_path(rule_id, group, binding))
                    dialog.close()
                    ui.notify("Binding deleted.", type="positive")
                    await load_bindings(rule_id)
                    await load_rules_preserve_selection(rule_id)
                except Exception as exc:
                    ui.notify(f"Delete failed: {exc}", type="negative", multi_line=True)

            with ui.row().classes("justify-end w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Delete", on_click=confirm_delete, icon="delete").props("color=negative")
        dialog.open()

    search.on("update:model-value", lambda _: apply_filter())
    rule_select.on_value_change(lambda event: ui.run_async(load_selected_rule(event.value)))
    refresh_button.on("click", lambda: ui.run_async(load_rules()))
    refresh_bindings_button.on("click", lambda: ui.run_async(load_bindings(state.get("selected_rule"))))
    create_button.on("click", lambda: ui.run_async(create_binding()))
    edit_button.on("click", lambda: ui.run_async(edit_binding()))
    delete_button.on("click", lambda: ui.run_async(delete_binding()))

    ui.timer(0.1, load_rules, once=True)


ui.run(
    title="Y62DB Config Rule Browser",
    host="127.0.0.1",
    port=PORT,
    reload=False,
)
