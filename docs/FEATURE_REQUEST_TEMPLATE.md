# Feature Request Template

Copy this file (or paste its contents into a message) per new feature.
Filling in every section up front avoids clarifying round trips —
each unanswered question below either becomes an `ask_user_question`
back-and-forth or a wrong guess that needs rework.

Delete this instructional preamble before sending; keep the headers.

---

## 1. Objective

One sentence. The concrete deliverable, not the motivation.

> Example: "Add a Textual-based CLI TUI client that performs CRUD on
> the bindings API, mirroring the web UI's forms, with mouse support."

## 2. Scope boundary

Explicit **in** list and **out** list. If you know of a feature-adjacent
thing you do NOT want built, say so — an unstated boundary usually gets
either overbuilt (wasted work) or triggers a scope-clarifying question.

> In: search, create, edit, delete.
> Out: read-only rule-catalog "View details" drill-in; throttled/batched
> too-many-matches picker (fan out directly instead — acceptable at this
> data scale).

## 3. Source of truth

Exact files, functions, or components to mirror (or deliberately
diverge from), including where existing behavior/wording must be
copied verbatim rather than reinvented.

> `ui/src/components/BindingForm.tsx` — validation rules and conflict
> error wording must match character-for-character.
> `ui/src/fuzzyMatch.ts` — port the matching algorithm directly, don't
> redesign it.

## 4. Non-negotiable constraints

Things that must never happen, regardless of how the feature evolves.
State these even if they seem obvious to you — an unstated constraint
risks an expensive mistake, not just a question.

> Never modify or delete the legacy `config_rules`/`config_rule_parameters`
> DynamoDB tables. Always call `confirm_action` with the full diff before
> any push to the real repo.

## 5. Acceptance criteria / validation commands

The exact commands that must pass, and what "done" looks like. This
lets validation happen without a review cycle before you see it.

> `python -m py_compile` on all new modules; `pytest` run from `tui/`
> with zero failures; a live check against the real API for at least
> one create → read → update → delete round trip, self-cleaning.

## 6. Output / documentation format

Where this gets recorded and how it should be committed.

> Document as a new `docs/BLUEPRINT.md` §12.N subsection (decisions,
> architecture, validation performed). Commit message summarizes the
> change and lists files touched. Confirm before push.

## 7. Known gotchas

Anything you already know that would otherwise cost time to
rediscover — prior failed approaches, environment quirks, data-shape
surprises.

> Native browser `window.confirm()` dialogs hang browser-automation
> testing indefinitely — don't rely on it for automated QA of delete
> flows.

---

*Template origin: distilled from the Y62DB TUI feature build
(`docs/BLUEPRINT.md` §12.13), 2026-08-06.*
