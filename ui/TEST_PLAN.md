# Y62DB Bindings UI — Manual CRUD Test Battery

Manual QA checklist for the bindings CRUD screen (`ui/src/pages/BindingsBrowser.tsx`
+ `ui/src/components/BindingForm.tsx`) against the **live** API. Run with
`npm run dev`, sign in as `testuser` / `BeSeeingYou25!`.

Tip: keep a second terminal with `curl` + a Cognito ID token handy (same
approach used during backend verification) to independently cross-check
what DynamoDB actually stored after each UI action — this catches
UI/API payload mismatches that the UI alone wouldn't reveal.

Suggested test fixture: use a disposable rule ID like `ui-test-rule` and
group `ui-test-group` so nothing collides with real data, and delete
everything you create at the end.

## Read / Search

| # | Test | Steps | Expected result |
|---|------|-------|------------------|
| R1 | Search by rule ID, has data | Mode = "By rule ID", query = `access-keys-rotated`, Search | Results table shows known bindings, count matches |
| R2 | Search by group, has data | Mode = "By group", query = a known group, Search | Results table shows bindings for that group |
| R3 | Search, no matches | Mode = "By rule ID", query = `nonexistent-rule-xyz`, Search | "0 binding(s) found", no error shown |
| R4 | Empty query blocked | Clear the query field | Search button is disabled |
| R5 | Switch mode keeps query | Search by rule, then switch dropdown to "By group" without changing text, Search | Runs the group query against the same string, doesn't crash |

## Create

| # | Test | Steps | Expected result |
|---|------|-------|------------------|
| C1 | Happy path | Search `ui-test-rule` by rule ID (0 results) → "+ New binding" → group `ui-test-group`, binding `default`, status ACTIVE, version 1, extra `{}` → Create | Success notice, table auto-refreshes, new row appears |
| C2 | Duplicate conflict | Repeat C1's exact rule/group/binding again → Create | `409 conflict` error shown in the form, no duplicate row, original record untouched |
| C3 | Missing group | Leave "Group" blank → Create | Client-side error "Rule ID and group are both required.", no network call (check devtools Network tab — no request fires) |
| C4 | Invalid JSON extras | Extra field = `{invalid}` → Create | Client-side JSON parse error shown, no network call |
| C5 | Extras must be an object | Extra field = `[1,2,3]` → Create | Error: "must be a JSON object", no network call |
| C6 | Extras round-trip | Extra field = `{"tags":["a","b"],"nested":{"x":1}}` → Create → then Edit the same row | Edit form's extra textarea shows the exact nested structure back, unmangled |
| C7 | Cancel discards | Fill in some fields → Cancel | Form closes, no network call, table/results unchanged |
| C8 | Binding name defaults | Leave "Binding name" blank, submit | API defaults it to `"default"` per contract — confirm via the row that appears or a follow-up `GET` |

## Edit / Update

| # | Test | Steps | Expected result |
|---|------|-------|------------------|
| U1 | Happy path | Edit the C1 row → change status to INACTIVE, add extra field `{"note":"test"}` → Save | Success notice, table refreshes, new status + payload visible, version bumped by exactly 1 |
| U2 | Identity fields locked | Open Edit on any row | Rule ID / Group / Binding name inputs are disabled/greyed out |
| U3 | Version shown, not editable | Open Edit | Version field shows "(current: N, will become N+1)" and the input itself is disabled |
| U4 | Cancel discards | Open Edit, change status → Cancel | Form closes, no network call, row's data unchanged on next search |
| U5 | Stale version conflict | Open the **same** binding's Edit form in two browser tabs (A and B). Save in tab A. Then change something in tab B and Save. | Tab A: succeeds normally. Tab B: distinct message — "this binding was updated by someone else... re-search and reopen edit" (not a generic error). Re-search confirms tab B's change was **not** applied — tab A's version won. |
| U6 | Invalid JSON extras on edit | Open Edit, set extra field to malformed JSON → Save | Same client-side validation as C4, no network call |

## Delete

| # | Test | Steps | Expected result |
|---|------|-------|------------------|
| D1 | Happy path | Click Delete on a test row → confirm the browser dialog | Success notice, row disappears after auto-refresh |
| D2 | Cancel confirmation | Click Delete → click Cancel on the browser dialog | Row remains, no network call fires |
| D3 | Double-delete / already gone | Delete the same binding from two tabs in quick succession (delete in tab A, then attempt delete again in tab B before B refreshes) | Tab B's delete surfaces a `404 not_found`-style error gracefully — no crash, no blank screen |
| D4 | Post-delete search | After D1, re-run the same search | Deleted binding no longer appears in results |

## Auth / session

| # | Test | Steps | Expected result |
|---|------|-------|------------------|
| A1 | Sign out | Click "Sign out" in the header | Returns to the `<Authenticator>` sign-in screen, no residual table/data visible |
| A2 | Sign back in | Sign in again with `testuser` | Lands back on the Bindings Browser, clean state (no stale results shown) |
| A3 | Session persists across reload | While signed in, refresh the browser page (Cmd+R) | Stays signed in (no forced re-login), lands back on the browser screen |

## Resilience

| # | Test | Steps | Expected result |
|---|------|-------|------------------|
| X1 | Network failure | DevTools → Network tab → set to "Offline" → attempt a Search | Graceful error message shown (not a blank screen or unhandled exception in console) |
| X2 | Slow network / no double-submit | DevTools → throttle to "Slow 3G" → click Create/Save/Search | Button shows "Loading..."/"Saving..." and is disabled for the duration — clicking again does nothing until the first request resolves |
| X3 | Large/odd payload | Create with a large extra JSON object (10+ keys) or deeply nested object | Saves and round-trips correctly; table's raw JSON cell still renders without layout breakage |

## Cleanup

- [ ] Delete every binding created under `ui-test-rule` / `ui-test-group` (or whatever fixture you used)
- [ ] Confirm via a final search that the live table has no leftover test data — same discipline used during backend verification, so production data stays clean
