import { useState } from "react";
import {
  Binding,
  BindingsApiError,
  deleteBinding,
  listBindingsForGroup,
  listBindingsForRule,
} from "../api/bindingsApi";
import { BindingForm } from "../components/BindingForm";

/**
 * Full CRUD screen for `RULE_BINDING` entities (v1 scope — see
 * docs/BLUEPRINT.md §12.1 step 7): search/list, create, edit (full payload
 * replace with optimistic locking), and delete, all against the live API.
 *
 * The RULE_PROFILE/PARAMETER_DEF read-only browser is a separate, later
 * step and isn't part of this screen.
 */

type FormState = { mode: "create" } | { mode: "edit"; existing: Binding } | null;

export function BindingsBrowser() {
  const [mode, setMode] = useState<"rule" | "group">("rule");
  const [query, setQuery] = useState("access-keys-rotated");
  const [results, setResults] = useState<Binding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [formState, setFormState] = useState<FormState>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function runSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data =
        mode === "rule" ? await listBindingsForRule(query.trim()) : await listBindingsForGroup(query.trim());
      setResults(data);
    } catch (err) {
      if (err instanceof BindingsApiError) {
        setError(`${err.code} (HTTP ${err.status}): ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setNotice(null);
    setFormState(null);
    await runSearch();
  }

  function handleSaved(action: "created" | "updated") {
    setFormState(null);
    setNotice(`Binding ${action}. Refreshing results...`);
    runSearch();
  }

  async function handleDelete(b: Binding) {
    const ok = window.confirm(
      `Delete binding ${b.rule_id} / ${b.group} / ${b.binding}? This cannot be undone.`,
    );
    if (!ok) return;

    setNotice(null);
    setError(null);
    try {
      await deleteBinding(b.rule_id, b.group, b.binding);
      setNotice(`Deleted ${b.rule_id} / ${b.group} / ${b.binding}. Refreshing results...`);
      await runSearch();
    } catch (err) {
      if (err instanceof BindingsApiError) {
        setError(`${err.code} (HTTP ${err.status}): ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>Y62DB — Rule Bindings</h1>
      <p style={{ color: "#555" }}>
        Full CRUD against the live API. Search bindings by rule or group, then create, edit, or
        delete them directly below.
      </p>

      <form onSubmit={handleSearch} style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        <select value={mode} onChange={(e) => setMode(e.target.value as "rule" | "group")}>
          <option value="rule">By rule ID</option>
          <option value="group">By group</option>
        </select>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={mode === "rule" ? "e.g. access-keys-rotated" : "e.g. corp"}
          style={{ flex: 1, padding: "0.4rem" }}
        />
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? "Loading..." : "Search"}
        </button>
        <button
          type="button"
          onClick={() => {
            setNotice(null);
            setFormState({ mode: "create" });
          }}
        >
          + New binding
        </button>
      </form>

      {notice && <div style={{ color: "#0a6", marginBottom: "1rem" }}>{notice}</div>}

      {error && (
        <div style={{ color: "#b00020", marginBottom: "1rem" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {formState?.mode === "create" && (
        <BindingForm
          mode="create"
          defaultRuleId={mode === "rule" ? query.trim() : ""}
          onSaved={() => handleSaved("created")}
          onCancel={() => setFormState(null)}
        />
      )}
      {formState?.mode === "edit" && (
        <BindingForm
          mode="edit"
          existing={formState.existing}
          onSaved={() => handleSaved("updated")}
          onCancel={() => setFormState(null)}
        />
      )}

      {results && (
        <div>
          <p>{results.length} binding(s) found.</p>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
                <th>Rule</th>
                <th>Group</th>
                <th>Binding</th>
                <th>Payload</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {results.map((b) => (
                <tr key={`${b.rule_id}#${b.group}#${b.binding}`} style={{ borderBottom: "1px solid #eee" }}>
                  <td>{b.rule_id}</td>
                  <td>{b.group}</td>
                  <td>{b.binding}</td>
                  <td>
                    <code>{JSON.stringify(b.payload)}</code>
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button
                      type="button"
                      onClick={() => {
                        setNotice(null);
                        setFormState({ mode: "edit", existing: b });
                      }}
                      style={{ marginRight: "0.5rem" }}
                    >
                      Edit
                    </button>
                    <button type="button" onClick={() => handleDelete(b)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
