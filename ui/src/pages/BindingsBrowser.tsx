import { useState } from "react";
import {
  Binding,
  BindingsApiError,
  deleteBinding,
  listAllGroups,
  listAllRuleIds,
  listBindingsForGroup,
  listBindingsForRule,
} from "../api/bindingsApi";
import { fuzzyFilter } from "../fuzzyMatch";
import { BindingForm } from "../components/BindingForm";

/**
 * Full CRUD screen for `RULE_BINDING` entities (v1 scope — see
 * docs/BLUEPRINT.md §12.1 step 7): search/list, create, edit (full payload
 * replace with optimistic locking), and delete, all against the live API.
 *
 * The RULE_PROFILE/PARAMETER_DEF read-only browser is a separate, later
 * step and isn't part of this screen.
 *
 * Search is typo-tolerant (see docs/BLUEPRINT.md §12.5 and ../fuzzyMatch):
 * it fetches every distinct rule ID / group that has at least one binding
 * (`GET /rules` or `GET /groups`), fuzzy-matches the query against that
 * list client-side, then fans out an exact-match lookup
 * (`listBindingsForRule`/`listBindingsForGroup`) per matched candidate and
 * merges everything into one results table. That fan-out is why the same
 * rule ID (or group) can appear more than once in the results — once per
 * binding under it.
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
  const [matchedCandidates, setMatchedCandidates] = useState<string[] | null>(null);
  // True when the last search matched more candidates than we're willing to
  // fan out automatically (see MAX_FANOUT below) — renders a clickable
  // picker instead of an error, so a legitimately broad query (e.g. a
  // service prefix like "ec2" or "s3" matching dozens of real rules) is
  // still browsable rather than a dead end.
  const [tooBroad, setTooBroad] = useState(false);

  // Guardrail: this table can hold hundreds of real rule IDs/groups (not
  // just test fixtures), so a broad fuzzy match could fan out to hundreds
  // of individual API calls. Rather than hammering the API, show the
  // matched candidates as a clickable picker once the match set gets
  // unreasonably large, instead of auto-fetching all of them.
  const MAX_FANOUT = 40;

  function bindingKey(b: Binding): string {
    return `${b.rule_id}#${b.group}#${b.binding}`;
  }

  /** Fetch bindings for a single candidate (from the too-broad picker) and merge into results, deduping. */
  async function fetchOneCandidate(candidate: string) {
    setLoading(true);
    setError(null);
    try {
      const data =
        mode === "rule" ? await listBindingsForRule(candidate) : await listBindingsForGroup(candidate);
      setResults((prev) => {
        const existingKeys = new Set((prev ?? []).map(bindingKey));
        const additions = data.filter((b) => !existingKeys.has(bindingKey(b)));
        return [...(prev ?? []), ...additions];
      });
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

  async function runSearch() {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setMatchedCandidates(null);
    setTooBroad(false);
    try {
      const candidates = mode === "rule" ? await listAllRuleIds() : await listAllGroups();
      const matches = fuzzyFilter(q, candidates);
      setMatchedCandidates(matches);

      if (matches.length === 0) {
        setResults([]);
        return;
      }

      if (matches.length > MAX_FANOUT) {
        setResults(null);
        setTooBroad(true);
        return;
      }

      // Fan out an exact-match lookup per fuzzy-matched candidate and merge.
      // A given rule ID / group can have several bindings, so it can
      // contribute more than one row here. Uses allSettled (not all) so a
      // single failed lookup among many concurrent ones doesn't wipe out an
      // otherwise-successful batch with a generic error — we surface
      // partial results plus a note about what failed instead.
      const outcomes = await Promise.allSettled(
        matches.map((c) => (mode === "rule" ? listBindingsForRule(c) : listBindingsForGroup(c))),
      );

      const merged: Binding[] = [];
      const failed: string[] = [];
      outcomes.forEach((outcome, i) => {
        if (outcome.status === "fulfilled") {
          merged.push(...outcome.value);
        } else {
          failed.push(matches[i]);
        }
      });

      setResults(merged);
      if (failed.length > 0) {
        setError(
          `Fetched ${merged.length} binding(s) from ${matches.length - failed.length} match(es), but ` +
            `${failed.length} lookup(s) failed (${failed.join(", ")}) — results below are partial. Try searching again.`,
        );
      }
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

      {matchedCandidates && !tooBroad && (
        <p style={{ color: "#555", fontSize: "0.9em" }}>
          Fuzzy-matched {mode === "rule" ? "rule ID(s)" : "group(s)"}:{" "}
          {matchedCandidates.length > 0 ? matchedCandidates.join(", ") : "none"}
        </p>
      )}

      {matchedCandidates && tooBroad && (
        <div style={{ marginBottom: "1rem" }}>
          <p style={{ color: "#555" }}>
            {matchedCandidates.length} {mode === "rule" ? "rule ID(s)" : "group(s)"} matched — too many
            to fetch all at once. Click one below to see its bindings (click several to build up the
            table), or narrow your search.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {matchedCandidates.map((c) => (
              <button key={c} type="button" onClick={() => fetchOneCandidate(c)} disabled={loading}>
                {c}
              </button>
            ))}
          </div>
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
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {results.map((b) => (
                <tr key={bindingKey(b)} style={{ borderBottom: "1px solid #eee" }}>
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
