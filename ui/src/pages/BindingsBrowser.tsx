import { useRef, useState } from "react";
import {
  Binding,
  BindingsApiError,
  RuleCatalog,
  RuleWithBindingStatus,
  deleteBinding,
  getRuleCatalog,
  listAllGroups,
  listAllRuleIds,
  listBindingsForGroup,
  listBindingsForRule,
} from "../api/bindingsApi";
import { fuzzyFilter, substringFilter } from "../fuzzyMatch";
import { BindingForm } from "../components/BindingForm";

/**
 * Full CRUD screen for `RULE_BINDING` entities, plus a hybrid read-only
 * catalog-visibility layer over `RULE_PROFILE`/`PARAMETER_DEF` (v1 scope —
 * see docs/BLUEPRINT.md §12.1 step 7 and §12.11): search/list, create, edit
 * (full payload replace with optimistic locking), delete, and — for rule
 * search only — drill into a rule's full parameter-def catalog before
 * creating a binding for it.
 *
 * Group search is unchanged and stays typo-tolerant (see docs/BLUEPRINT.md
 * §12.5 and ../fuzzyMatch): it fetches every distinct group that has at
 * least one binding (`GET /groups`), fuzzy-matches the query against that
 * list client-side, then fans out an exact-match lookup
 * (`listBindingsForGroup`) per matched candidate and merges everything into
 * one results table. That fan-out is why the same group can appear more
 * than once in the results — once per binding under it.
 *
 * Rule search (see docs/BLUEPRINT.md §12.11) instead calls the merged
 * `GET /rules` endpoint, which returns EVERY seeded catalog rule tagged
 * with `has_binding`, and matches the query against `rule_id` via plain
 * SUBSTRING match (`substringFilter`) — not fuzzy — per explicit user
 * decision superseding the earlier fuzzy-matching requirement for rule
 * search specifically. Matches split into two groups:
 *   - bound rules: fanned out to `listBindingsForRule` exactly like group
 *     search, populating the same results table.
 *   - unbound rules (`has_binding: false`, no existing binding): rendered
 *     as a separate clickable list — cheap to show in full since no
 *     lookup is fired for them — offering "View details" (fetches the
 *     rule's PARAMETER_DEF catalog via `getRuleCatalog`) and "Create
 *     binding" (opens the create form pre-filled with that rule_id).
 *
 * The bound-rule fan-out is chunked (see FANOUT_BATCH_SIZE and
 * docs/BLUEPRINT.md §12.8) so a broad match doesn't fire dozens of
 * concurrent Lambda invocations at once against a possibly low
 * account-level concurrency quota. The too-broad picker gate
 * (MAX_FANOUT) only ever applies to the bound-rule / group fan-out path,
 * never to the unbound-rule list — per the user's "default to client
 * side" volume-handling decision, that list is just rendered in full.
 *
 * Searches are guarded against out-of-order async responses via
 * `searchGenerationRef` (see docs/BLUEPRINT.md §12.9) — firing a second
 * search before the first one's request settles no longer risks the
 * older response overwriting the newer one's results, and a stale
 * response can no longer clobber results a candidate-picker click just
 * fetched.
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

  // --- Group-mode search state (unchanged fuzzy-match behavior) ---
  const [groupMatches, setGroupMatches] = useState<string[] | null>(null);
  // True when the last group search matched more candidates than we're
  // willing to fan out automatically (see MAX_FANOUT below) — renders a
  // clickable picker instead of an error, so a legitimately broad query
  // (e.g. a service prefix like "corp") is still browsable rather than a
  // dead end.
  const [groupTooBroad, setGroupTooBroad] = useState(false);

  // --- Rule-mode search state (merged catalog + bindings, substring match) ---
  const [ruleMatches, setRuleMatches] = useState<{
    bound: string[];
    unbound: RuleWithBindingStatus[];
  } | null>(null);
  // Same too-broad gate as groups, but only ever counts BOUND matches —
  // the unbound list is always rendered in full (see docs/BLUEPRINT.md
  // §12.11, "default to client side" volume handling).
  const [ruleTooBroad, setRuleTooBroad] = useState(false);

  // Rule-ID to pre-fill into the create form. Set when "Create binding" is
  // clicked from the unbound-rules list; cleared for the generic
  // "+ New binding" button (which falls back to the current query text).
  const [pendingCreateRuleId, setPendingCreateRuleId] = useState<string | null>(null);

  // Drill-in panel for a single rule's PARAMETER_DEF catalog (description,
  // severity, scopes, parameters) — fetched on demand via "View details".
  const [catalogView, setCatalogView] = useState<
    | null
    | { status: "loading"; ruleId: string }
    | { status: "loaded"; ruleId: string; catalog: RuleCatalog }
    | { status: "error"; ruleId: string; message: string }
  >(null);

  // Monotonically increasing "generation" bumped once per runSearch() call.
  // GET /rules and GET /groups take no query params, so every search fires
  // an identical request and network timing alone decides which resolves
  // first — an older search can easily resolve AFTER a newer one. Each
  // async continuation below checks this ref before committing state, so
  // only the most recently *started* search's results ever win, no matter
  // what order their responses actually arrive in. fetchOneCandidate
  // deliberately snapshots (doesn't bump) this value: multiple picker
  // clicks from the same search must keep accumulating into `results`
  // together (that's the whole point of the "click several to build up
  // the table" picker UX), but a click's result is discarded if a brand
  // new search has started before it resolves.
  const searchGenerationRef = useRef(0);

  // Guardrail: this table can hold hundreds of real rule IDs/groups (not
  // just test fixtures), so a broad fuzzy match could fan out to hundreds
  // of individual API calls. Rather than hammering the API, show the
  // matched candidates as a clickable picker once the match set gets
  // unreasonably large, instead of auto-fetching all of them.
  const MAX_FANOUT = 40;

  // Even a match set within MAX_FANOUT fires one Lambda invocation per
  // candidate. Firing all of them in parallel can saturate a low
  // account-level Lambda concurrent-executions quota (see
  // docs/BLUEPRINT.md §12.8 — this happened in production), so the fan-out
  // is chunked into sequential batches of this size instead of one big
  // Promise.allSettled over everything.
  const FANOUT_BATCH_SIZE = 6;

  /**
   * Runs `fetcher` over `items` in sequential batches of FANOUT_BATCH_SIZE
   * concurrent calls, returning per-item settled outcomes in the same
   * order as `items` (so callers can still zip results back to their
   * source candidate by index).
   */
  async function fetchInBatches<T>(
    items: string[],
    fetcher: (item: string) => Promise<T>,
  ): Promise<PromiseSettledResult<T>[]> {
    const outcomes: PromiseSettledResult<T>[] = [];
    for (let i = 0; i < items.length; i += FANOUT_BATCH_SIZE) {
      const batch = items.slice(i, i + FANOUT_BATCH_SIZE);
      const batchOutcomes = await Promise.allSettled(batch.map(fetcher));
      outcomes.push(...batchOutcomes);
    }
    return outcomes;
  }

  function bindingKey(b: Binding): string {
    return `${b.rule_id}#${b.group}#${b.binding}`;
  }

  /** Fetch bindings for a single candidate (from the too-broad picker) and merge into results, deduping. */
  async function fetchOneCandidate(candidate: string) {
    const generation = searchGenerationRef.current;
    setLoading(true);
    setError(null);
    try {
      const data =
        mode === "rule" ? await listBindingsForRule(candidate) : await listBindingsForGroup(candidate);
      if (searchGenerationRef.current !== generation) return; // a newer search superseded this picker
      setResults((prev) => {
        const existingKeys = new Set((prev ?? []).map(bindingKey));
        const additions = data.filter((b) => !existingKeys.has(bindingKey(b)));
        return [...(prev ?? []), ...additions];
      });
    } catch (err) {
      if (searchGenerationRef.current !== generation) return;
      if (err instanceof BindingsApiError) {
        setError(`${err.code} (HTTP ${err.status}): ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (searchGenerationRef.current === generation) setLoading(false);
    }
  }

  /**
   * Fans out an exact-match lookup per matched candidate and merges into
   * one Binding[] (shared by both group search and the bound-rule half of
   * rule search). Sets `results` / a partial-failure `error` directly;
   * returns nothing since both callers just need the side effects.
   */
  async function fanOutAndMerge(
    matches: string[],
    fetcher: (c: string) => Promise<Binding[]>,
    generation: number,
  ) {
    const outcomes = await fetchInBatches(matches, fetcher);
    if (searchGenerationRef.current !== generation) return; // a newer search started meanwhile

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
  }

  async function runGroupSearch(q: string, generation: number) {
    const candidates = await listAllGroups();
    if (searchGenerationRef.current !== generation) return;
    const matches = fuzzyFilter(q, candidates);
    setGroupMatches(matches);

    if (matches.length === 0) {
      setResults([]);
      return;
    }
    if (matches.length > MAX_FANOUT) {
      setResults(null);
      setGroupTooBroad(true);
      return;
    }
    await fanOutAndMerge(matches, listBindingsForGroup, generation);
  }

  async function runRuleSearch(q: string, generation: number) {
    const candidates = await listAllRuleIds();
    if (searchGenerationRef.current !== generation) return;

    // Substring match against rule_id only (user decision: substring-only,
    // not fuzzy, for rule search — see docs/BLUEPRINT.md §12.11).
    const matchedRuleIds = substringFilter(
      q,
      candidates.map((c) => c.rule_id),
    );
    const byRuleId = new Map(candidates.map((c) => [c.rule_id, c]));
    const bound = matchedRuleIds.filter((id) => byRuleId.get(id)?.has_binding);
    const unbound = matchedRuleIds
      .map((id) => byRuleId.get(id))
      .filter((c): c is RuleWithBindingStatus => !!c && !c.has_binding);
    setRuleMatches({ bound, unbound });

    if (bound.length === 0) {
      setResults([]);
      return;
    }
    if (bound.length > MAX_FANOUT) {
      setResults(null);
      setRuleTooBroad(true);
      return;
    }
    await fanOutAndMerge(bound, listBindingsForRule, generation);
  }

  async function runSearch() {
    const q = query.trim();
    if (!q) return;
    const generation = ++searchGenerationRef.current;
    setLoading(true);
    setError(null);
    setGroupMatches(null);
    setGroupTooBroad(false);
    setRuleMatches(null);
    setRuleTooBroad(false);
    setCatalogView(null);
    try {
      if (mode === "rule") {
        await runRuleSearch(q, generation);
      } else {
        await runGroupSearch(q, generation);
      }
    } catch (err) {
      if (searchGenerationRef.current !== generation) return; // a newer search started meanwhile
      if (err instanceof BindingsApiError) {
        setError(`${err.code} (HTTP ${err.status}): ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
      setResults(null);
    } finally {
      if (searchGenerationRef.current === generation) setLoading(false);
    }
  }

  /** Fetches and displays a rule's full PARAMETER_DEF catalog ("View details"). */
  async function handleViewCatalog(ruleId: string) {
    setCatalogView({ status: "loading", ruleId });
    try {
      const catalog = await getRuleCatalog(ruleId);
      if (!catalog) {
        setCatalogView({ status: "error", ruleId, message: "No catalog entry found for this rule." });
        return;
      }
      setCatalogView({ status: "loaded", ruleId, catalog });
    } catch (err) {
      const message =
        err instanceof BindingsApiError
          ? `${err.code} (HTTP ${err.status}): ${err.message}`
          : err instanceof Error
            ? err.message
            : String(err);
      setCatalogView({ status: "error", ruleId, message });
    }
  }

  /** Opens the create-binding form pre-filled with a specific rule_id (from the unbound-rules list). */
  function handleCreateForRule(ruleId: string) {
    setNotice(null);
    setPendingCreateRuleId(ruleId);
    setFormState({ mode: "create" });
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setNotice(null);
    setFormState(null);
    setPendingCreateRuleId(null);
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
            setPendingCreateRuleId(null);
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
          defaultRuleId={pendingCreateRuleId ?? (mode === "rule" ? query.trim() : "")}
          onSaved={() => {
            setPendingCreateRuleId(null);
            handleSaved("created");
          }}
          onCancel={() => {
            setPendingCreateRuleId(null);
            setFormState(null);
          }}
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

      {mode === "group" && groupMatches && !groupTooBroad && (
        <p style={{ color: "#555", fontSize: "0.9em" }}>
          Fuzzy-matched group(s): {groupMatches.length > 0 ? groupMatches.join(", ") : "none"}
        </p>
      )}

      {mode === "group" && groupMatches && groupTooBroad && (
        <div style={{ marginBottom: "1rem" }}>
          <p style={{ color: "#555" }}>
            {groupMatches.length} group(s) matched — too many to fetch all at once. Click one below to
            see its bindings (click several to build up the table), or narrow your search.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {groupMatches.map((c) => (
              <button key={c} type="button" onClick={() => fetchOneCandidate(c)} disabled={loading}>
                {c}
              </button>
            ))}
          </div>
        </div>
      )}

      {mode === "rule" && ruleMatches && !ruleTooBroad && (
        <p style={{ color: "#555", fontSize: "0.9em" }}>
          Substring-matched bound rule ID(s):{" "}
          {ruleMatches.bound.length > 0 ? ruleMatches.bound.join(", ") : "none"}
        </p>
      )}

      {mode === "rule" && ruleMatches && ruleTooBroad && (
        <div style={{ marginBottom: "1rem" }}>
          <p style={{ color: "#555" }}>
            {ruleMatches.bound.length} bound rule ID(s) matched — too many to fetch all at once. Click
            one below to see its bindings (click several to build up the table), or narrow your search.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {ruleMatches.bound.map((c) => (
              <button key={c} type="button" onClick={() => fetchOneCandidate(c)} disabled={loading}>
                {c}
              </button>
            ))}
          </div>
        </div>
      )}

      {mode === "rule" && ruleMatches && ruleMatches.unbound.length > 0 && (
        <div style={{ marginBottom: "1rem" }}>
          <p style={{ color: "#555", fontSize: "0.9em" }}>
            {ruleMatches.unbound.length} matched rule(s) with no binding yet — view their catalog details
            or create a binding directly:
          </p>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
                <th>Rule ID</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {ruleMatches.unbound.map((r) => (
                <tr key={r.rule_id} style={{ borderBottom: "1px solid #eee" }}>
                  <td>{r.rule_id}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button
                      type="button"
                      onClick={() => handleViewCatalog(r.rule_id)}
                      style={{ marginRight: "0.5rem" }}
                    >
                      View details
                    </button>
                    <button type="button" onClick={() => handleCreateForRule(r.rule_id)}>
                      Create binding
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {catalogView?.status === "loading" && (
        <p style={{ color: "#555" }}>Loading catalog for {catalogView.ruleId}...</p>
      )}

      {catalogView?.status === "error" && (
        <div style={{ color: "#b00020", marginBottom: "1rem" }}>
          <strong>Could not load catalog for {catalogView.ruleId}:</strong> {catalogView.message}
        </div>
      )}

      {catalogView?.status === "loaded" && (
        <div
          style={{
            border: "1px solid #ccc",
            borderRadius: 6,
            padding: "1rem",
            marginBottom: "1.5rem",
            background: "#fafafa",
          }}
        >
          <h3 style={{ marginTop: 0 }}>Rule catalog: {catalogView.catalog.rule_id}</h3>
          <p>
            <strong>Source identifier:</strong> {catalogView.catalog.source_identifier}
            <br />
            <strong>Description:</strong> {catalogView.catalog.description}
            <br />
            <strong>Severity:</strong> {catalogView.catalog.severity}
            <br />
            <strong>Scopes:</strong> {catalogView.catalog.scopes.join(", ") || "none"}
            <br />
            <strong>Managed rule:</strong> {catalogView.catalog.managed_rule ? "yes" : "no"}
          </p>
          {catalogView.catalog.parameters.length === 0 ? (
            <p style={{ color: "#555" }}>No parameters defined for this rule.</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Required</th>
                  <th>Default</th>
                </tr>
              </thead>
              <tbody>
                {catalogView.catalog.parameters.map((p) => (
                  <tr key={p.name} style={{ borderBottom: "1px solid #eee" }}>
                    <td>{p.name}</td>
                    <td>{p.data_type}</td>
                    <td>{p.required ? "yes" : "no"}</td>
                    <td>{p.default_value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button type="button" onClick={() => setCatalogView(null)} style={{ marginTop: "0.75rem" }}>
            Close
          </button>
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
                    {mode === "rule" && (
                      <button
                        type="button"
                        onClick={() => handleViewCatalog(b.rule_id)}
                        style={{ marginRight: "0.5rem" }}
                      >
                        View details
                      </button>
                    )}
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
