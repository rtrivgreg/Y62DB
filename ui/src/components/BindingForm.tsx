import { useEffect, useState } from "react";
import {
  Binding,
  BindingPayload,
  BindingsApiError,
  createBinding,
  listAllRuleIds,
  updateBinding,
} from "../api/bindingsApi";

/**
 * Shared create/edit form for a single binding.
 *
 * - Create: `ruleId` / `group` / `binding` are free-text inputs; `payload`
 *   is built from a status select, a version number (defaults to 1), and
 *   an optional JSON textarea for any rule-specific extra keys
 *   (e.g. `maxAccessKeyAge`) — the API payload schema is open-ended beyond
 *   `status`/`version` (see repo root `api/README.md`).
 * - Edit: identity fields (`ruleId`/`group`/`binding`) are fixed — PUT is a
 *   full replace of `payload` on an existing item, not a rename. Version is
 *   auto-incremented from the value we last read and sent as
 *   `expected_version` for optimistic locking; a 409 here means someone
 *   else updated the binding since we loaded it, so we surface that
 *   distinctly and ask the caller to re-search and retry.
 */

type Props =
  | { mode: "create"; defaultRuleId?: string; onSaved: () => void; onCancel: () => void }
  | { mode: "edit"; existing: Binding; onSaved: () => void; onCancel: () => void };

const inputStyle: React.CSSProperties = { padding: "0.4rem", width: "100%" };
const labelStyle: React.CSSProperties = { display: "block", fontSize: "0.85rem", color: "#333", marginBottom: "0.25rem" };
const fieldWrapStyle: React.CSSProperties = { marginBottom: "0.75rem" };

/** Pulls the extra, rule-specific keys out of a payload (everything besides status/version). */
function extraKeysAsJson(payload: BindingPayload): string {
  const { status, version, ...rest } = payload;
  return JSON.stringify(rest, null, 2);
}

export function BindingForm(props: Props) {
  const isEdit = props.mode === "edit";
  const existing = isEdit ? props.existing : null;

  const [ruleId, setRuleId] = useState(existing?.rule_id ?? (props as { defaultRuleId?: string }).defaultRuleId ?? "");
  const [group, setGroup] = useState(existing?.group ?? "");
  const [binding, setBinding] = useState(existing?.binding ?? "default");
  const [status, setStatus] = useState<"ACTIVE" | "INACTIVE">(existing?.payload.status ?? "ACTIVE");
  const [version, setVersion] = useState<number>(existing?.payload.version ?? 1);
  const [extraJson, setExtraJson] = useState(existing ? extraKeysAsJson(existing.payload) : "{}");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create-mode rule picker: suggestions sourced from the same merged
  // catalog + bindings list (`GET /rules`, see docs/BLUEPRINT.md §12.11)
  // that powers the BindingsBrowser rule search, so typing here offers
  // every known rule_id — bound or not — not just previously-bound ones.
  // Fetched once on mount; edit mode doesn't need it since the rule ID
  // field is fixed there.
  const [ruleIdOptions, setRuleIdOptions] = useState<string[]>([]);
  useEffect(() => {
    if (isEdit) return;
    let cancelled = false;
    listAllRuleIds()
      .then((rules) => {
        if (!cancelled) setRuleIdOptions(rules.map((r) => r.rule_id));
      })
      .catch(() => {
        // Best-effort suggestions only — a failure here shouldn't block
        // manually typing a rule_id, so it's silently ignored.
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    let extra: Record<string, unknown>;
    try {
      const parsed = JSON.parse(extraJson || "{}");
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("must be a JSON object");
      }
      extra = parsed as Record<string, unknown>;
    } catch (err) {
      setError(`Extra payload fields must be valid JSON (an object): ${err instanceof Error ? err.message : String(err)}`);
      return;
    }

    if (!ruleId.trim() || !group.trim()) {
      setError("Rule ID and group are both required.");
      return;
    }

    setSubmitting(true);
    try {
      if (isEdit && existing) {
        const nextVersion = existing.payload.version + 1;
        const payload: BindingPayload = { status, version: nextVersion, ...extra };
        await updateBinding(ruleId.trim(), group.trim(), binding.trim(), payload, existing.payload.version);
      } else {
        const payload: BindingPayload = { status, version, ...extra };
        await createBinding(ruleId.trim(), group.trim(), binding.trim() || undefined, payload);
      }
      props.onSaved();
    } catch (err) {
      if (err instanceof BindingsApiError) {
        if (err.code === "conflict" && isEdit) {
          setError(
            `Conflict (409): this binding was updated by someone else since you loaded it. ` +
              `Re-search and reopen edit to get the latest version before retrying.`,
          );
        } else if (err.code === "conflict") {
          setError(`Conflict (409): a binding already exists for this rule + group + binding name.`);
        } else {
          setError(`${err.code} (HTTP ${err.status}): ${err.message}`);
        }
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        border: "1px solid #ccc",
        borderRadius: 6,
        padding: "1rem",
        marginBottom: "1.5rem",
        background: "#fafafa",
      }}
    >
      <h3 style={{ marginTop: 0 }}>{isEdit ? "Edit binding" : "New binding"}</h3>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
        <div style={fieldWrapStyle}>
          <label style={labelStyle}>Rule ID</label>
          <input
            style={inputStyle}
            value={ruleId}
            onChange={(e) => setRuleId(e.target.value)}
            disabled={isEdit}
            placeholder="e.g. access-keys-rotated"
            list={isEdit ? undefined : "rule-id-options"}
          />
          {!isEdit && (
            <datalist id="rule-id-options">
              {ruleIdOptions.map((id) => (
                <option key={id} value={id} />
              ))}
            </datalist>
          )}
        </div>
        <div style={fieldWrapStyle}>
          <label style={labelStyle}>Group</label>
          <input
            style={inputStyle}
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            disabled={isEdit}
            placeholder="e.g. corp"
          />
        </div>
        <div style={fieldWrapStyle}>
          <label style={labelStyle}>Binding name</label>
          <input
            style={inputStyle}
            value={binding}
            onChange={(e) => setBinding(e.target.value)}
            disabled={isEdit}
            placeholder="default"
          />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
        <div style={fieldWrapStyle}>
          <label style={labelStyle}>Status</label>
          <select style={inputStyle} value={status} onChange={(e) => setStatus(e.target.value as "ACTIVE" | "INACTIVE")}>
            <option value="ACTIVE">ACTIVE</option>
            <option value="INACTIVE">INACTIVE</option>
          </select>
        </div>
        <div style={fieldWrapStyle}>
          <label style={labelStyle}>
            Version {isEdit && existing ? `(current: ${existing.payload.version}, will become ${existing.payload.version + 1})` : ""}
          </label>
          <input
            style={inputStyle}
            type="number"
            value={isEdit && existing ? existing.payload.version + 1 : version}
            onChange={(e) => setVersion(Number(e.target.value))}
            disabled={isEdit}
          />
        </div>
      </div>

      <div style={fieldWrapStyle}>
        <label style={labelStyle}>
          Extra payload fields (JSON object, optional — e.g. rule-specific keys like <code>maxAccessKeyAge</code>)
        </label>
        <textarea
          style={{ ...inputStyle, fontFamily: "monospace", minHeight: "80px" }}
          value={extraJson}
          onChange={(e) => setExtraJson(e.target.value)}
        />
      </div>

      {error && (
        <div style={{ color: "#b00020", marginBottom: "0.75rem" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="submit" disabled={submitting}>
          {submitting ? "Saving..." : isEdit ? "Save changes" : "Create binding"}
        </button>
        <button type="button" onClick={props.onCancel} disabled={submitting}>
          Cancel
        </button>
      </div>
    </form>
  );
}
