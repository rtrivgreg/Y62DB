/**
 * Thin client for the Y62DB Bindings CRUD API (`RULE_BINDING` entities
 * only — see repo root `api/README.md` for the full contract this file
 * implements against).
 *
 * Deliberately plain `fetch()`, not Amplify's `API` (REST) category: this
 * API was hand-built outside Amplify and its `COGNITO_USER_POOLS`
 * authorizer expects the raw Cognito ID token in the `Authorization`
 * header, not IAM SigV4 signing. `fetchAuthSession()` gives us that token
 * directly from the current Authenticator session — no extra category
 * config needed for a REST API this simple.
 */
import { fetchAuthSession } from "aws-amplify/auth";
import { API_BASE_URL } from "../amplify-config";

export interface BindingPayload {
  status: "ACTIVE" | "INACTIVE";
  version: number;
  // Any other rule-specific keys (e.g. maxAccessKeyAge) pass through as-is.
  [key: string]: unknown;
}

export interface Binding {
  rule_id: string;
  group: string;
  binding: string;
  payload: BindingPayload;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: ApiError | null;
  meta: {
    request_id: string;
    timestamp: string;
    count?: number;
    next_cursor?: string | null;
  };
}

/** Thrown for both transport failures and API-reported errors (4xx/5xx). */
export class BindingsApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(message: string, code: string, status: number, details?: Record<string, unknown>) {
    super(message);
    this.name = "BindingsApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const session = await fetchAuthSession();
  const idToken = session.tokens?.idToken?.toString();
  if (!idToken) {
    throw new BindingsApiError(
      "No signed-in session — sign in before calling the API.",
      "no_session",
      401,
    );
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      Authorization: idToken,
      ...init.headers,
    },
  });
}

async function parseEnvelope<T>(response: Response): Promise<T | null> {
  // DELETE returns 204 with no body.
  if (response.status === 204) return null;

  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || !envelope.success) {
    const err = envelope.error;
    throw new BindingsApiError(
      err?.message ?? `Request failed with status ${response.status}`,
      err?.code ?? "unknown_error",
      response.status,
      err?.details,
    );
  }
  return envelope.data;
}

/** GET /rules/{ruleId}/bindings — every group a rule is bound to. */
export async function listBindingsForRule(ruleId: string): Promise<Binding[]> {
  const res = await authorizedFetch(`/rules/${encodeURIComponent(ruleId)}/bindings`);
  return (await parseEnvelope<Binding[]>(res)) ?? [];
}

/** GET /groups/{group}/bindings — every rule bound to a group. */
export async function listBindingsForGroup(group: string): Promise<Binding[]> {
  const res = await authorizedFetch(`/groups/${encodeURIComponent(group)}/bindings`);
  return (await parseEnvelope<Binding[]>(res)) ?? [];
}

/** GET /rules/{ruleId}/bindings/{group}/{binding} — a single binding. */
export async function getBinding(
  ruleId: string,
  group: string,
  binding: string,
): Promise<Binding | null> {
  const res = await authorizedFetch(
    `/rules/${encodeURIComponent(ruleId)}/bindings/${encodeURIComponent(group)}/${encodeURIComponent(binding)}`,
  );
  return parseEnvelope<Binding>(res);
}

/** POST /rules/{ruleId}/bindings — create. 409 if it already exists. */
export async function createBinding(
  ruleId: string,
  group: string,
  binding: string | undefined,
  payload: BindingPayload,
): Promise<Binding | null> {
  const res = await authorizedFetch(`/rules/${encodeURIComponent(ruleId)}/bindings`, {
    method: "POST",
    body: JSON.stringify({ group, binding, payload }),
  });
  return parseEnvelope<Binding>(res);
}

/**
 * PUT /rules/{ruleId}/bindings/{group}/{binding} — full replace of
 * `payload`, guarded by optimistic locking. `expectedVersion` must be the
 * `payload.version` you last read; a stale value returns 409.
 */
export async function updateBinding(
  ruleId: string,
  group: string,
  binding: string,
  payload: BindingPayload,
  expectedVersion: number,
): Promise<Binding | null> {
  const res = await authorizedFetch(
    `/rules/${encodeURIComponent(ruleId)}/bindings/${encodeURIComponent(group)}/${encodeURIComponent(binding)}`,
    {
      method: "PUT",
      body: JSON.stringify({ payload, expected_version: expectedVersion }),
    },
  );
  return parseEnvelope<Binding>(res);
}

/** DELETE /rules/{ruleId}/bindings/{group}/{binding} — 204 on success. */
export async function deleteBinding(
  ruleId: string,
  group: string,
  binding: string,
): Promise<void> {
  const res = await authorizedFetch(
    `/rules/${encodeURIComponent(ruleId)}/bindings/${encodeURIComponent(group)}/${encodeURIComponent(binding)}`,
    { method: "DELETE" },
  );
  await parseEnvelope<null>(res);
}

/**
 * GET /rules — every distinct rule ID that has at least one binding.
 * Candidate list for client-side fuzzy rule-ID search (see `../fuzzyMatch`).
 */
export async function listAllRuleIds(): Promise<string[]> {
  const res = await authorizedFetch("/rules");
  return (await parseEnvelope<string[]>(res)) ?? [];
}

/**
 * GET /groups — every distinct group that has at least one binding.
 * Candidate list for client-side fuzzy group search.
 */
export async function listAllGroups(): Promise<string[]> {
  const res = await authorizedFetch("/groups");
  return (await parseEnvelope<string[]>(res)) ?? [];
}
