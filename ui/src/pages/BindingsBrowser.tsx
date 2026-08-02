import { useState } from "react";
import {
  Binding,
  BindingsApiError,
  listBindingsForGroup,
  listBindingsForRule,
} from "../api/bindingsApi";

/**
 * Scaffold proof-of-wiring screen: confirms a signed-in user's ID token is
 * accepted by the live API Gateway authorizer and that reads against real
 * DynamoDB data work end-to-end from the browser.
 *
 * This is intentionally read-only. Full v1 screens (create/edit/delete
 * forms for bindings, plus the RULE_PROFILE/PARAMETER_DEF browser) are the
 * next step on the roadmap (docs/BLUEPRINT.md §12.1 step 7) — not built
 * here yet.
 */
export function BindingsBrowser() {
  const [mode, setMode] = useState<"rule" | "group">("rule");
  const [query, setQuery] = useState("access-keys-rotated");
  const [results, setResults] = useState<Binding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const data =
        mode === "rule"
          ? await listBindingsForRule(query.trim())
          : await listBindingsForGroup(query.trim());
      setResults(data);
    } catch (err) {
      if (err instanceof BindingsApiError) {
        setError(`${err.code} (HTTP ${err.status}): ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>Y62DB — Rule Bindings</h1>
      <p style={{ color: "#555" }}>
        Read-only smoke test against the live CRUD API. Look up every group a
        rule is bound to, or every rule a group is bound to.
      </p>

      <form onSubmit={handleSearch} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
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
      </form>

      {error && (
        <div style={{ color: "#b00020", marginBottom: "1rem" }}>
          <strong>Error:</strong> {error}
        </div>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
