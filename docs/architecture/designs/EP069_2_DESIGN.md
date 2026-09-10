# EP-069.2 — Configured Fallback Ordering / Priority

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 0. Scope Verification — Cost-Aware Selection Is NOT the Correct Next Slice

The calling task's stated candidate for EP-069.2 was **cost-aware
provider selection**, framed explicitly as "only a hypothesis" to be
independently verified. Direct inspection of this repository's own
records shows that hypothesis is incorrect, and this document departs
from it accordingly, per the calling task's own Section 12 ("If the
evidence indicates that another EP-069.x slice should come first,
document that conclusion instead of forcing the assumed scope").

**Primary evidence — `EP069_DESIGN.md` Section 29, "Deferred
EP-069.x Scope" (written and finalized during EP-069.1, the frozen
prior slice):**

> - **EP-069.2 (candidate) — Configured fallback ordering / priority.**
>   Let an operator specify an explicit provider preference order for
>   fallback, rather than reusing alphabetical registry order (Section
>   17, D6).
> - **EP-069.3 (candidate) — Cost-aware provider selection.** Requires
>   a pricing/cost model that does not exist anywhere in this
>   repository today (Section 0.1) — a substantial, separate design
>   effort, not an extension of this EP's fallback loop.

This is not an ambiguous or stale note — it is the explicit, numbered
successor plan the prior EP's own STEP 1 committed to. `docs/BACKLOG.md`
(the live backlog, updated after EP-069.1's STEP 4) restates the same
ordering in the same words, independently, in its "Next Engineering
Package" section:

> EP-069's remaining scope (configured fallback ordering, cost-aware
> provider selection, LLM function/tool calling, and expanded fallback
> eligibility) remains unscoped and planning-only; each requires its
> own future, independent STEP 1 before implementation.

Both of this repository's own source-of-truth documents — one written
at EP-069.1 design time, one updated after EP-069.1 shipped — name
**configured fallback ordering** first and **cost-aware selection**
second, in that order, with no intervening document that reorders or
supersedes this. `docs/architecture/JARVIS_ROADMAP.md`'s current
section adds nothing that contradicts this ordering (Section 0.3
below).

**Secondary evidence — architectural readiness.** Independent of the
backlog's stated order, Section 0.1 of `EP069_DESIGN.md` and direct
inspection of the current codebase (Section 9 below) confirm cost-aware
selection has a genuine, unresolved architectural prerequisite gap:
`AIProvider.ask()` returns an `AIResponse` with no token-usage or cost
field (Section 9.2), and no pricing/cost model of any kind exists
anywhere in the repository. Configured fallback ordering has no such
gap: it is a pure reordering of an already-fully-built mechanism
(`ProviderManager.list_fallback_candidates()`), requiring no new
domain concept, no contract change, and no data that does not already
exist. This independently confirms the backlog's stated order is also
the architecturally sound order, not merely a documentation artifact.

**Conclusion: EP-069.2 is retitled to "Configured Fallback Ordering /
Priority."** Cost-aware provider selection is retained as the
EP-069.3 candidate, unchanged from `EP069_DESIGN.md` Section 29, and
is explicitly out of scope for this document (Section 7).

### 0.1 What would have happened if cost-aware selection had been forced

Section 6 of the calling task's own required investigation
("Critical Architectural Question") is answered here for completeness,
since the hypothesis was explicitly named and must not be silently
dropped: cost-aware selection **cannot** be implemented cleanly with
the current provider abstraction. `AIProvider.ask()`'s return type
(`AIResponse`, `src/core/ai/message.py`) carries only `text` and
`model` (Section 9.2) — no token counts, no cost units. Meaningful
cost-aware selection needs at least one of (a) real per-request token
usage from every provider's API response, requiring a contract change
to `AIResponse`/`AIProvider.ask()` plus per-provider parsing work in
both `ClaudeProvider` and `GeminiProvider`, or (b) a purely static,
configured cost/tier number per provider with no relationship to
actual usage, which is a materially different, much weaker feature
than "cost-aware selection" implies and would need its own Owner
Decision on whether that weaker feature is even worth building. Either
path is a substantial, separate design effort — exactly matching
`EP069_DESIGN.md` Section 0.1's original assessment. Forcing it into
this slice would violate the calling task's own Non-Goals (Section 7
below) against combining multiple future EP-069.x features and against
introducing token estimation/accounting as a side effect.

### 0.2 Why fallback ordering (not tools, not eligibility expansion) is next

- It is the first-named item in both source-of-truth documents
  (Section 0), not merely "a" viable item.
- It has a direct, already-identified gap: Owner Decision D6 in
  `EP069_DESIGN.md` (Section 17) explicitly named alphabetical
  ordering as "the smallest correct choice... at the cost of no
  operator control over fallback preference," and explicitly deferred
  operator control to this EP.
- It requires no new domain concept: `ProviderManager
  .list_fallback_candidates()` (Section 9.1) already computes the
  eligible-candidate set; this EP only changes how that set is
  *ordered*, not how it is computed.
- It carries no terminology ambiguity (unlike "tools," which
  `EP069_DESIGN.md` Section 0.1 already found conflates two unrelated
  existing concepts).
- EP-069.5 (candidate — expanded fallback eligibility for
  `ProviderConfigurationError`/`ProviderAuthenticationError`,
  `EP069_DESIGN.md` Section 29) is a smaller, narrower change than
  ordering, but is listed after both ordering and cost in the
  established sequence and changes failure-classification semantics
  (a behavior change) rather than a pure ordering preference — properly
  a later, independent slice, not addressed here.

### 0.3 Roadmap/backlog cross-check

`docs/architecture/JARVIS_ROADMAP.md`'s "Phase A" and "Current" sections
were re-inspected directly for this STEP 1: both describe EP-069.1 as
complete and describe "the remainder of EP-069" only as "strategic
planning only" with no per-slice detail beyond what `docs/BACKLOG.md`
already states. No roadmap or backlog text contradicts, reorders, or
supersedes the Section 29 / BACKLOG.md ordering used above.

---

## 1. Title

EP-069.2 — Configured Fallback Ordering / Priority

## 2. Status

STEP 1 (this document) only. STEP 2 (Implementation & Testing), STEP 3
(Architecture Audit), and STEP 4 (Documentation Synchronization) have
not started. EP-069 (parent) remains a planning identifier with no
design document of its own.

## 3. Parent EP

EP-069 — AI Provider & Tool Registry (planning identifier only; see
`EP069_DESIGN.md` Section 0). This is the second sub-package under
that identifier; EP-069.1 (Automatic AI Provider Fallback on Request
Failure) is the first, and is treated as frozen (Section 4 of the
calling task; Section 6 below).

## 4. Context

EP-069.1 added an opt-in (`ai.fallback_enabled`, default `false`)
fallback mechanism: when the currently selected provider fails with a
fallback-eligible error, `AIService.ask()` retries the identical
already-built prompt against the next available, not-yet-attempted
provider, in an order determined entirely by
`ProviderManager.list_fallback_candidates()` — which is, in turn,
`ProviderRegistry.list()`'s existing order, **alphabetical by
`name()`**, filtered to available candidates (Section 9 below). This
was `EP069_DESIGN.md`'s Owner Decision D6, explicitly recorded as "the
smallest correct choice" for EP-069.1, with no operator-facing
mechanism to prefer one available provider over another for fallback
purposes. An operator running both `claude` and `gemini`, fully
configured and available, cannot express "prefer `gemini` as the
fallback target over `openai`'s alphabetically-earlier placeholder" —
alphabetical order is the only order that exists, and today it happens
to work only because non-`claude`/`gemini` providers are
`ConfigDrivenProvider` placeholders that are never `is_available()`.

## 5. Problem Statement

`ProviderManager.list_fallback_candidates()` (`src/core/ai/
provider_manager.py:131-159`) has no concept of operator preference: it
returns eligible candidates in whatever order `ProviderRegistry.list()`
returns them, which is fixed to alphabetical-by-name and cannot be
influenced by configuration. This is adequate only by coincidence of
today's `KNOWN_PROVIDER_NAMES` tuple and which providers happen to have
real (`ClaudeProvider`/`GeminiProvider`) versus placeholder
(`ConfigDrivenProvider`) implementations. If an operator configures a
third real provider in the future (Section 7, explicitly out of
scope to build here, but relevant to why this matters *now*), or
simply prefers `gemini` tried before `openai` for cost, latency, or
policy reasons unrelated to alphabetical accident, there is no way to
express that preference today.

## 6. EP-069.1 Boundary (Frozen)

Per the calling task's explicit instruction, this design treats
EP-069.1 as frozen and does not redesign or modify:

- The `AIProvider` contract.
- `ProviderRegistry`'s catalog storage or its `list()` method's own
  alphabetical guarantee (still used as-is for `ProviderRegistry
  .list()`'s general callers, e.g. `ai list` — Section 10).
- `ProviderManager`'s `set_current()`/`get_current()`/`is_enabled()`/
  `disable()` behavior.
- The deterministic, bounded fallback *loop* in `AIService.ask()`
  (Section 16 below: this EP changes only which candidate the loop
  picks next, never the loop's termination, exception handling, or
  logging structure).
- `ai.fallback_enabled` and its default-`false` behavior.
- The `_FALLBACK_ELIGIBLE_ERRORS` failure-classification rules
  (`ProviderUnavailableError`, `ProviderNetworkError`,
  `ProviderTimeoutError`, `ProviderRateLimitError`).
- EP-068 logging/redaction guarantees (Section 15 below extends the
  same discipline to the one new log line this EP introduces, rather
  than altering any existing one).

No resolved STEP 3/3.1 finding from EP-069.1 is reopened; none of the
seven findings (`EP069_FINDINGS_RESOLUTION.md`) concern ordering, and
this design depends on none of them.

## 7. Scope

**In scope:**

- A new, optional configuration key expressing an operator-preferred
  provider order for fallback purposes only.
- A change to how `ProviderManager` (or a thin collaborator it owns)
  determines fallback-candidate order when that configuration is
  present — falling back to today's alphabetical order when it is
  absent, invalid, or incomplete (Section 11, Section 14).
- Validation of the new configuration at startup, with defined,
  non-crashing behavior for invalid entries (Section 14).
- Tests proving both the new ordering behavior and full backward
  compatibility with EP-069.1's existing behavior when the new
  configuration is absent.

**Explicitly NOT in scope** (see Section 8 for the full Non-Goals
list, which mirrors and does not weaken EP-069.1's own):

- Any change to *which* providers are eligible (that remains
  `is_available()` plus "not yet attempted," exactly as EP-069.1 left
  it).
- Any change to *whether* fallback happens at all (`ai.fallback_enabled`
  is unchanged).
- Cost-aware selection (EP-069.3 candidate — Section 0).
- LLM function/tool calling (EP-069.4 candidate).
- Expanded fallback eligibility for currently-non-eligible error types
  (EP-069.5 candidate).
- Any change to `ai use <provider>` / which provider is "current" for
  the *next* fresh request.

## 8. Non-Goals

Per the calling task's Section 7, and consistent with EP-069.1's own
Non-Goals (`EP069_DESIGN.md` Section 6), EP-069.2 does **not**:

- implement dynamic market pricing, real-time provider price
  discovery, automatic billing, budget enforcement, or user
  billing/accounting;
- implement a tokenization engine, model benchmarking, quality
  scoring, latency scoring, provider health monitoring, circuit
  breakers, or load balancing;
- implement machine-learning-based provider selection of any kind;
- implement LLM function/tool calling, or touch the internal Tool
  Engine (EP-031, `src/core/tool/*`) or the Capability Registry
  (EP-056) in any way;
- introduce retries against the *same* provider (unchanged from
  EP-069.1's own Non-Goal);
- change `AIProvider`'s abstract contract in any way;
- change `ProviderRegistry.list()`'s own general-purpose alphabetical
  guarantee (used by non-fallback callers such as `ai list` — Section
  10) — this EP adds a fallback-specific ordering concept alongside
  it, not a replacement for it;
- add any new provider implementation;
- implement cost-aware provider selection (EP-069.3 candidate,
  Section 0);
- combine any other future EP-069.x feature into this slice.

## 9. Existing Architecture

(Frozen per Section 6; restated here only as the factual basis for
Section 10-16's proposed change.)

- **`AIProvider`** (`src/core/ai/provider.py`) — abstract base class.
  `name()` returns the provider's registered string identity;
  `is_available()` reports configuration-derived readiness with no
  network access. Unchanged by this EP.
- **`ProviderRegistry`** (`src/core/ai/provider_registry.py`) —
  thread-safe catalog. `list()` (lines 102-109) returns every
  registered provider **sorted by `name()`**, unconditionally — this
  is a general-purpose guarantee other callers (e.g. `ai list`
  diagnostics) also depend on and which this EP does not alter.
- **`ProviderManager`** (`src/core/ai/provider_manager.py`) — owns
  "current provider" selection (`set_current()`/`get_current()`) and,
  since EP-069.1, `list_fallback_candidates(exclude)` (lines 131-159):
  filters `self._registry.list()` to providers not in `exclude` and
  with `is_available() == True`, returning them in whatever order
  `ProviderRegistry.list()` produced — i.e., alphabetical. Holds no
  state of its own beyond `_current_name`/`_enabled`; eligibility and
  order are both derived fresh on every call.
- **`ProviderFactory`** (`src/core/ai/provider_factory.py`) — builds
  one `AIProvider` per name in `KNOWN_PROVIDER_NAMES = ("claude",
  "gemini", "openai", "ollama", "lmstudio")`. This tuple's own order is
  never consulted for fallback purposes today (registry sorting
  discards factory-build order) and is not proposed to be consulted
  here either — Section 11.
- **`AIService.ask()`** (`src/services/ai_service.py:468-604`) — the
  fallback loop (Section 16 below restates its structure). Calls
  `self._provider_manager.list_fallback_candidates(exclude=attempted)`
  once per failed attempt and always takes `remaining[0]` as the next
  candidate (line ~589) — this single line, `next_candidate =
  remaining[0]`, is the exact point where "alphabetical" currently
  becomes "the next candidate tried," and is this EP's only call-site
  dependency inside `AIService`.

### 9.1 `list_fallback_candidates()` is the correct (and only) change point

Because `list_fallback_candidates()` already isolates "which providers
are eligible, in what order" behind one method with one call site
(`AIService.ask()`'s single `next_candidate = remaining[0]`), this EP
needs to change ordering in exactly one place — inside
`ProviderManager` — with zero changes required to `AIService.ask()`'s
control flow, exception handling, or logging structure. This
mirrors `EP069_DESIGN.md` Section 8's own precedent-following approach
(EP-066/EP-067's "add resilience without changing the wrapped
component"): here, "add a preference without changing the loop that
consumes it."

### 9.2 Cost/token data does not exist (supports Section 0.1)

`AIResponse` (`src/core/ai/message.py`) and both `ClaudeProvider.ask()`
and `GeminiProvider.ask()` (`src/core/ai/claude_provider.py`,
`src/core/ai/providers/gemini_provider.py`) return only `text` and
`model` on success. No token-count, usage, or cost field exists on any
request/response object in `src/core/ai/`, and no `providers.*.cost`
or similar configuration key exists in `config/config.yaml`. This is
restated from `EP069_DESIGN.md` Section 0.1 and independently
reconfirmed here by direct inspection, supporting Section 0's
conclusion.

## 10. Current Provider Selection Flow (Fallback Path Only)

```
1. AIService.ask(): current = provider_manager.get_current()  (unchanged)
2. On a fallback-eligible ProviderError from `candidate.ask()`:
   a. remaining = provider_manager.list_fallback_candidates(exclude=attempted)
      -> ProviderRegistry.list() (alphabetical) filtered to
         is_available() and not-yet-attempted
   b. next_candidate = remaining[0]        <-- always alphabetically-first remaining
   c. candidate = next_candidate; retry
3. Repeat until success or `remaining` is empty.
```

`ProviderRegistry.list()`'s alphabetical order is a general-purpose,
unrelated guarantee (used by `ai list` and other diagnostics) that
this EP does not change; only step (a)'s *ordering of the fallback
candidate set specifically* is proposed to change, via a new,
optional preference layered on top inside `ProviderManager` — not by
modifying `ProviderRegistry.list()` itself.

## 11. Proposed Architecture

Add one new, optional method-level concept to `ProviderManager`:
an operator-configured **fallback order** — an ordered list of
provider names — consulted only by `list_fallback_candidates()`, never
by `ProviderRegistry.list()`'s own general callers.

- `ProviderManager.__init__` gains one new optional constructor
  parameter, `fallback_order: list[str] | None`, populated by the
  composition root (`src/bootstrap.py`) from a new configuration key
  (Section 13) — mirroring exactly how `enabled`/`default_provider`
  are already passed in today (`ProviderManager.__init__`'s existing
  two parameters).
- `list_fallback_candidates(exclude)` computes the eligible-and-
  not-excluded candidate set exactly as it does today (no change to
  *which* providers qualify — Section 7), then orders that set as
  follows (Section 12 gives the precise algorithm):
  - If `fallback_order` is `None` or empty: unchanged EP-069.1
    behavior — alphabetical, i.e., today's implicit `ProviderRegistry
    .list()` order (Owner Decision D7, Section 21).
  - If `fallback_order` is present: eligible candidates whose name
    appears in `fallback_order` are returned first, in
    `fallback_order`'s sequence; any remaining eligible candidate
    whose name does *not* appear in `fallback_order` is appended
    afterward, in the existing alphabetical order among themselves
    (Owner Decision D4, Section 21 — "missing cost data" analog:
    here, "missing order data").
- No change to `ProviderRegistry`, `ProviderFactory`, `AIProvider`, or
  `AIService.ask()`'s control flow (Section 9.1). `AIService` continues
  to call `list_fallback_candidates(exclude=attempted)` and take
  `remaining[0]` exactly as it does today — this EP's entire behavior
  change is contained inside `ProviderManager`.

## 12. Provider Selection Algorithm (Fallback Ordering)

```
def list_fallback_candidates(self, exclude):
    excluded = set(exclude)
    eligible = [p for p in self._registry.list()          # alphabetical base
                if p.name() not in excluded and p.is_available()]
    if not self._fallback_order:                          # None or empty
        return eligible                                   # unchanged EP-069.1 behavior

    eligible_by_name = {p.name(): p for p in eligible}
    ordered = [eligible_by_name[name]
               for name in self._fallback_order
               if name in eligible_by_name]
    unlisted = [p for p in eligible if p.name() not in self._fallback_order]
    return ordered + unlisted                              # unlisted stays alphabetical
```

This is a pure, deterministic re-sort of an already-computed set —
`self._fallback_order` is read-only configuration state set once at
construction (Section 17, concurrency), never mutated per-request,
matching `EP069_DESIGN.md`'s own "fallback state is entirely
request-local" finding (`EP069_ARCHITECTURE_AUDIT.md` line 145) for
everything *except* this one new piece of startup-time configuration
state, which is immutable after construction (Section 17).

## 13. Configuration

One new key under the existing `ai:` block:

```yaml
ai:
  enabled: true
  default_provider: "none"
  timeout: 120
  retry_count: 2
  max_context_messages: 20
  fallback_enabled: false            # EP-069.1, unchanged
  fallback_order: []                 # EP-069.2, new — see below
```

- **Key:** `ai.fallback_order`.
- **Type:** a YAML list of strings (provider names), matching this
  project's existing convention for ordered, named sequences (e.g.
  `workflow_engine`'s `stop_on_failure`-governed step list is the
  closest structural analog for "an ordered sequence configured
  directly in `config.yaml`," though no prior AI-subsystem key uses a
  list type — this is a new but conventional YAML shape, not a new
  serialization concept).
- **Default:** `[]` (empty list), which is defined to behave
  identically to `None` in Section 11/12 — no ordering preference,
  full backward compatibility (Section 21).
- **Independent of `ai.fallback_enabled`.** Setting `fallback_order`
  has zero effect while `fallback_enabled` is `false` (the default),
  since `list_fallback_candidates()` is only ever called from inside
  the fallback-eligible branch of `AIService.ask()` (Section 9,
  Section 16) — an operator can pre-configure an order before opting
  into fallback at all.
- **Names are not required to be currently valid/registered.** A name
  in `fallback_order` that does not correspond to any registered
  provider (e.g. a typo, or a provider the operator plans to configure
  later) is simply never matched in `eligible_by_name` (Section 12)
  and has no effect — this is validated behavior (Section 14), not an
  error, matching this project's general preference for tolerant
  configuration over startup crashes for non-critical preference data
  (contrasted with, e.g., `ai.enabled` being a hard boolean gate).
- **No change to any `providers.*` per-provider configuration block.**

## 14. Error Handling

- **Invalid type for `ai.fallback_order`** (e.g. a string or a mapping
  instead of a list): treated as absent (`None`/`[]` — Owner Decision
  D8, Section 21), with a single `WARNING`-level log line at startup
  (composition root) naming only the key and the fact that its type
  was invalid — never echoing the malformed value itself, per
  EP-068's redaction discipline (Section 15). The AI subsystem
  continues to start normally; this is a preference, not a required
  setting.
- **Duplicate names in the list:** the first occurrence wins
  (Python's list-comprehension order in Section 12 naturally produces
  this); later duplicates are inert. No error raised.
- **A name in the list matching zero registered providers:** silently
  has no effect on ordering (Section 13) — this is normal, expected
  operation (e.g., a name reserved for a not-yet-configured future
  provider), not an error condition, and is not logged at all (logging
  every non-match would itself leak information about which provider
  names the operator anticimapted using, and adds no diagnostic value
  beyond what `ai providers`/`ai doctor` already report about
  availability).
- **`ai.fallback_order` present but `ai.fallback_enabled` is `false`:**
  not an error — Section 13's independence note applies; no warning is
  logged, since this is an entirely ordinary "configured but not yet
  opted in" state.
- **All eligible candidates unlisted in `fallback_order`:** falls
  through entirely to the `unlisted` branch (Section 12) — behaves
  identically to `fallback_order` being absent. Not an error.

## 15. Logging / Security

- **One new log line, at `WARNING`, only for the invalid-type case**
  (Section 14) — logs the configuration key name and
  `type(value).__name__` only, never the malformed value's contents,
  matching EP-068's "closed-set, code-authored values only" pattern
  already applied by EP-069.1 (`EP069_DESIGN.md` Section 19).
- **No new log line in `AIService.ask()`'s fallback loop.** The
  existing EP-069.1 `INFO`-level "falling back from provider='X' to
  provider='Y'" line (Section 16) already names both providers by
  `name()` regardless of *why* `Y` was chosen — whether by alphabetical
  order or by configured preference is not additional information a
  log consumer needs beyond knowing which two providers were involved,
  so this EP adds no per-request logging of its own. This keeps the
  per-request log volume introduced by fallback exactly as EP-069.1
  left it (Owner Decision D-analog, Section 21).
- **Nothing new reaches the log that could contain prompt text,
  response text, or raw provider error bodies** — this EP touches only
  ordering logic and one startup-time validation warning, neither of
  which has access to per-request content at all.

## 16. Fallback Interaction

- **The fallback loop itself (`AIService.ask()`, `EP069_DESIGN.md`
  Section 14/16) is completely unchanged**: same trigger conditions
  (`ai.fallback_enabled` and a fallback-eligible `ProviderError`), same
  termination condition (`remaining` empty), same error aggregation
  (`failure_summary`), same `AskResult` shape. This EP changes only
  what `list_fallback_candidates()` returns and in what order — never
  whether fallback happens, how many attempts are made, or how errors
  are reported.
- **The currently selected ("primary") provider is never reordered.**
  `fallback_order` only ever influences which provider is tried
  *after* the primary (`current`) provider has already failed — it has
  no effect on `ProviderManager.get_current()`/`set_current()` or on
  which provider serves the very first attempt of a request (Owner
  Decision D1 is unchanged; see Section 21, D-analog "the cheapest/
  preferred provider can never become the primary provider via this
  mechanism," directly answering the calling task's parallel question
  about cost-aware selection, restated here for the ordering case).
- **Bounded and deterministic exactly as before.** The candidate set's
  *size* is unchanged (Section 7); only its *order* changes, so the
  existing bound ("at most one attempt per eligible provider, ever" —
  `EP069_ARCHITECTURE_AUDIT.md`/`EP069_DESIGN.md` Section 16-17) is
  untouched. Given a fixed registry state and a fixed
  `fallback_order`, `list_fallback_candidates()` is a pure function of
  `exclude` — identical inputs always produce identical output order
  (Section 17).

## 17. Determinism / Concurrency / Thread Safety

- **Deterministic tie-breaking:** unlisted-in-`fallback_order`
  candidates fall back to `ProviderRegistry.list()`'s existing
  alphabetical order among themselves (Section 12) — there is never a
  case with no defined order, matching EP-069.1's own D6/D7 precedent
  of "no per-request randomness."
- **`fallback_order` is immutable after construction.** It is read
  once from configuration at composition-root time (`bootstrap.py`)
  and passed into `ProviderManager.__init__`; no runtime command
  changes it in this EP's scope (a future `ai fallback-order set ...`
  command is a natural extension — Section 26 — but is not built
  here). This means no new lock or synchronization is required beyond
  what `ProviderManager` already holds (`self._lock`, guarding only
  `_current_name`/`_enabled` — unchanged): `fallback_order`, once set
  in `__init__`, is read-only for the lifetime of the process, so
  concurrent `list_fallback_candidates()` calls reading it introduce
  no new race, exactly matching `EP069_ARCHITECTURE_AUDIT.md`'s
  existing finding (line 145) that fallback state is "entirely
  request-local" plus, now, one piece of process-lifetime-immutable
  configuration state.
- **No new shared mutable state** is introduced anywhere in
  `AIService` or `ProviderManager` beyond this one immutable
  construction-time list.

## 18. Backward Compatibility

- **Default (`ai.fallback_order` absent or `[]`): zero behavior
  change.** `list_fallback_candidates()` returns exactly what it
  returns today (Section 12's `if not self._fallback_order` branch).
  Every existing EP-069.1 test and behavior is unaffected without any
  test modification (the calling task's "DO NOT modify tests"
  instruction for STEP 1 is honored; STEP 2 will need new tests only
  for the new branch — Section 19).
- **Existing configurations remain valid without modification** —
  `ai.fallback_order` is optional; its absence is handled identically
  to an explicit empty list (Section 13).
- **`ProviderRegistry.list()`'s own general-purpose alphabetical
  contract is untouched** — any other caller of `list()` (e.g. `ai
  list` diagnostics) sees no behavior change at all, since this EP
  never modifies `ProviderRegistry`.

## 19. Test Strategy (for STEP 2 — not performed in this STEP 1)

- **New test package:** `tests/EP069_2/` (or `tests/EP069/` extended
  with a second file, per whichever the repository's own EP-069.1
  precedent and current `test_module.py` registration convention
  favors — an explicit Owner Decision, D11, Section 21, since both
  `tests/EP0NN/`-per-EP and `tests/EP0NN/test_*.py`-multi-file-per-EP
  patterns exist elsewhere in this repository and STEP 1 does not
  silently pick one).
- **Unit tests on `ProviderManager.list_fallback_candidates()`
  directly** (not through `AIService`, mirroring EP-069.1's own
  layered test approach): fake providers with controlled
  `is_available()`/`name()`, asserting:
  - No `fallback_order` configured → today's alphabetical order
    (regression test proving zero behavior change).
  - Full `fallback_order` covering all eligible candidates → exact
    configured order returned.
  - Partial `fallback_order` (covers some eligible candidates) →
    listed ones first in configured order, unlisted ones appended
    alphabetically.
  - `fallback_order` naming an unregistered/unavailable provider →
    that entry has no effect; no error.
  - Duplicate names in `fallback_order` → first occurrence position
    used, no duplicate entries in output.
  - Empty `fallback_order` (`[]`) → identical to `None`.
- **Integration test through `AIService.ask()`:** with
  `ai.fallback_enabled: true` and a two-or-three-fake-provider setup,
  confirm the actual fallback attempt order follows configured
  preference, using the same fake-provider/deterministic-`ask()`
  pattern EP-069.1 already established (no `sleep`/polling needed —
  `EP069_DESIGN.md` Section 25/30 precedent).
- **Bootstrap-level test** confirming `ai.fallback_order` from
  `config.yaml` is correctly threaded into `ProviderManager`'s
  constructor — directly addressing `EP069.1-AUDIT-002`'s
  already-identified "Bootstrap-level test... future revision or
  EP-069.x" deferral (`EP069_FINDINGS_RESOLUTION.md`), since this EP
  is a natural, in-scope place to add that missing coverage for the
  same constructor this EP itself extends.
- **Invalid-type configuration test:** a non-list `ai.fallback_order`
  value produces the one `WARNING` log line (Section 15) and
  `fallback_order` behaves as `None`, with no startup crash.
- **No existing EP-069.1 test file is modified** — new tests are
  additive only, per STEP 1's own restriction and this repository's
  per-EP test-package convention.

## 20. Acceptance Criteria (for STEP 2/3, objectively verifiable)

1. With `ai.fallback_order` absent from `config/config.yaml`,
   `ProviderManager.list_fallback_candidates()` returns candidates in
   the identical order it did before this EP, verified by a byte-for-
   byte-identical-order assertion in a regression test.
2. With `ai.fallback_order: ["gemini", "claude"]` and both providers
   eligible, `list_fallback_candidates()` returns `[gemini, claude]`,
   not `[claude, gemini]`.
3. With `ai.fallback_order: ["gemini"]` and both `gemini` and `claude`
   eligible, `list_fallback_candidates()` returns `[gemini, claude]`
   (listed-first, unlisted-appended-alphabetically).
4. With `ai.fallback_order: ["ghost-provider"]` and no provider named
   `ghost-provider` registered, `list_fallback_candidates()`'s output
   is identical to `ai.fallback_order` being absent, for the same
   eligible-candidate set.
5. With `ai.fallback_order` set to a non-list value (e.g. a string),
   exactly one `WARNING`-level log line is emitted at startup naming
   the key and the invalid type, and `list_fallback_candidates()`
   behaves as if `fallback_order` were absent.
6. No existing EP-069.1 test in `tests/EP069/test_ai_provider_fallback
   .py` fails or requires modification after this EP's changes are
   applied.
7. `AIProvider`'s abstract method signatures (`provider.py`) are
   byte-for-byte unchanged (diffable against the pre-EP-069.2
   version).
8. `ProviderRegistry.list()`'s return order for a fixed set of
   registered providers is unchanged (unit test unrelated to fallback,
   confirming no accidental modification of the general-purpose
   method).
9. `AIService.ask()`'s only changed line, if any, is the removal of no
   code and the addition of no new branch beyond what already calls
   `list_fallback_candidates()` — verified by diff inspection in STEP
   3 (this EP is designed to require zero `ai_service.py` changes at
   all; see Section 9.1).
10. `ai.fallback_order`'s absence from an operator's existing
    `config.yaml` requires no migration and produces no startup
    warning or error.

## 21. Owner Decisions

- **D1 — Exact EP-069.2 scope.** Configured fallback ordering /
  priority (Section 0), not cost-aware selection. Retitled from the
  calling task's hypothesis based on direct evidence in
  `EP069_DESIGN.md` Section 29 and `docs/BACKLOG.md`.
- **D2 — Configuration shape.** A single ordered list of provider
  names, `ai.fallback_order: []`, rather than a per-provider numeric
  priority field under `providers.*` (Section 13). Chosen because it
  requires no change to any `providers.*` block (Section 7 Non-Goal)
  and matches "one new list-shaped key" being the smallest addition
  that expresses a total order.
- **D3 — Location of ordering data.** Lives entirely in the `ai:`
  block (fallback-specific), not in `providers.*` (per-provider,
  would imply the preference is a property of the provider itself
  rather than of the fallback *feature*) and not as new state inside
  `ProviderRegistry` (which must remain the general-purpose,
  alphabetical, feature-agnostic catalog other callers depend on —
  Section 9, Section 18).
- **D4 — Behavior for names not matching any eligible provider.**
  Silently ignored, no error, no log line (Section 14) — treated as
  ordinary, not exceptional, since a forward-referencing name (a
  provider planned but not yet configured) is a normal use case, not
  an operator mistake.
- **D5 — Deterministic tie-breaking for unlisted candidates.**
  Existing alphabetical order among themselves (Section 12, Section
  17) — reuses EP-069.1's own D6/D7 precedent rather than introducing
  a second new ordering rule.
- **D6 — Interaction with EP-069.1's fallback loop.** None beyond the
  single `list_fallback_candidates()` return-order change (Section
  16) — the loop's trigger, termination, error aggregation, and
  `AskResult` shape are all explicitly unchanged.
- **D7 — Backward-compatible default.** Absent or empty
  `ai.fallback_order` is byte-for-byte identical to EP-069.1's
  pre-existing behavior (Section 11, Section 18) — chosen over any
  alternative default (e.g. defaulting to `KNOWN_PROVIDER_NAMES`'s
  factory-build order) specifically because that would be a silent
  behavior change for zero operator benefit, contradicting this
  project's Configuration Policy precedent already cited by
  `EP069_DESIGN.md` Section 20.
- **D8 — Invalid configuration behavior.** Treated as absent, with one
  `WARNING` log line naming only the key and type (Section 14, Section
  15) — never a startup crash, since this is a preference setting, not
  a subsystem-enabling gate (contrast with `ai.enabled`).
- **D9 — Whether `AIProvider` contract must change.** No. This EP
  touches only `ProviderManager` (Section 11) and, if the composition
  root requires a small parsing/validation helper, `bootstrap.py`
  (Section 22) — never `provider.py`.
- **D10 — Whether token usage/estimation is in scope.** No — this EP
  concerns ordering preference only, has nothing to do with cost, and
  explicitly excludes any token/cost concept (Section 8; the calling
  task's cost-specific investigation is answered separately in Section
  0.1 as a documented non-viability finding, not folded into this
  EP's own scope).
- **D11 — Exact test-package boundary.** Deferred to STEP 2 as an
  explicit open sub-decision (Section 19): whether new tests live in a
  new `tests/EP069_2/` package or as an additional file inside the
  existing `tests/EP069/` package. Both patterns exist elsewhere in
  this repository's test suite; STEP 1 does not silently pick one to
  avoid prejudging a convention question that has no single existing
  precedent to mirror unambiguously.
- **D12 — Whether a new CLI/command surface is needed to set
  `fallback_order` at runtime.** No, not in this EP. `ai.fallback_order`
  is configuration-file-only, read once at startup (Section 17),
  matching `ai.fallback_enabled`'s own configuration-only precedent
  from EP-069.1. A runtime `ai fallback-order set ...` command is
  named as a future extension (Section 23) but is not built here,
  since introducing a new command surface is a larger scope increase
  than this EP's stated minimal goal.

## 22. Files Expected to Change in STEP 2

- `src/core/ai/provider_manager.py` — add `fallback_order` constructor
  parameter and the new ordering branch in
  `list_fallback_candidates()` (Section 11, Section 12).
- `src/bootstrap.py` — read `ai.fallback_order` from configuration,
  validate its type (Section 14), and pass it into
  `ProviderManager.__init__` (composition-root wiring only, same site
  already wiring `enabled`/`default_provider` — `EP069_DESIGN.md`
  Section 9, lines 292-296).
- `config/config.yaml` — add the new, commented, default-`[]`
  `ai.fallback_order` key alongside the existing `ai.fallback_enabled`
  key (Section 13).
- A new test file/package per D11 (Section 21) — new tests only, no
  existing EP-069 test file modified.
- Documentation synchronization (STEP 4, not STEP 2): `docs/BACKLOG.md`
  and `docs/architecture/JARVIS_ROADMAP.md`, following the same
  post-STEP-4 update pattern EP-069.1 itself used — explicitly not
  performed in this STEP 1 (Section 24 below; the calling task's own
  Section 6 lists both as protected during STEP 1).

## 23. Future Extensions

- A runtime command (e.g. `ai fallback-order set claude,gemini`) to
  change `fallback_order` without a restart, mirroring `ai use
  <provider>`'s own in-memory-only, no-config-write precedent
  (`provider_manager.py` module docstring) — deferred per D12.
- EP-069.3 — Cost-aware provider selection (Section 0), once a
  token-usage/cost data source exists.
- EP-069.4 — LLM function/tool calling.
- EP-069.5 — Expanded fallback eligibility.
- Combining a future cost model (EP-069.3) with this EP's ordering
  concept (e.g. "prefer configured order, but cost as a tiebreak") is
  explicitly not assumed or designed for here — it would be its own,
  later Owner Decision once EP-069.3 itself exists.

## 24. Protected Files (Explicitly Not Modified in STEP 1)

Per the calling task's Section 6/13/14, this STEP 1 does not modify:

- Any file under `src/` (no production source change).
- Any file under `tests/` (no test change).
- `config/config.yaml` (no configuration change).
- `CHANGELOG.md`, `docs/RELEASE_NOTES.md` (if present), `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md`.
- `docs/architecture/designs/EP069_DESIGN.md`,
  `docs/architecture/audits/EP069_ARCHITECTURE_AUDIT.md`,
  `docs/architecture/audits/EP069_FINDINGS_RESOLUTION.md` (EP-069.1's
  frozen design/audit/findings documents).
- Any file under `src/core/tool/*`, the Capability Registry, or the
  Command Router.
- Any historical EP implementation or historical EP test file.
- Any concrete provider implementation (`ClaudeProvider`,
  `GeminiProvider`, `ConfigDrivenProvider`) — this design proves no
  provider-level change is required (Section 9, Section 11).

Only `docs/architecture/designs/EP069_2_DESIGN.md` (this file) is
created.

## 25. Risks / Trade-offs

- **A configured `fallback_order` naming a provider that later becomes
  unavailable silently degrades to "as if not configured" for that
  entry** (Section 14, D4) — accepted, since erroring on a transient
  availability change would make the feature brittle for exactly the
  scenario it exists to help with (an operator's preferred provider
  going down).
- **List-shaped YAML configuration (D2) is a new shape for this
  project's AI subsystem config**, which has so far used only scalar
  keys under `ai:` — a minor precedent-setting choice, mitigated by
  this shape being already used elsewhere in the repository for
  ordered concepts (workflow step sequences) even if not previously
  under `ai:`.
- **Test-package boundary (D11) is left open**, meaning STEP 2 makes
  one additional small decision this STEP 1 does not — accepted as
  appropriate for a genuinely convention-level choice with no single
  existing precedent, rather than STEP 1 guessing and potentially
  contradicting whatever STEP 2's implementer finds when directly
  inspecting `test_module.py`'s current registration list.
- **This design's value is bounded by today's provider landscape** —
  with only two real providers (`claude`, `gemini`) and three
  never-available placeholders, `fallback_order` has at most one
  meaningful choice to express today (which of the two real providers
  is preferred). The feature is deliberately built for the general
  case (Section 12's algorithm scales to any number of eligible
  providers) rather than only today's two-provider reality, since a
  third real provider is a plausible near-term addition this EP should
  not need to be revisited for.

## 26. Implementation Steps (for STEP 2, not performed here)

1. Add `fallback_order: list[str] | None = None` parameter to
   `ProviderManager.__init__`; store as `self._fallback_order`.
2. Implement the ordering branch in `list_fallback_candidates()`
   exactly per Section 12's algorithm.
3. Add `ai.fallback_order` to `config/config.yaml` with explanatory
   comment matching this project's existing per-key documentation
   convention (Section 13).
4. Update `bootstrap.py`'s existing `ProviderManager` construction site
   to read, validate (Section 14), and pass `ai.fallback_order`.
5. Write unit tests (Section 19) for `ProviderManager
   .list_fallback_candidates()` covering all six ordering scenarios.
6. Write one integration test through `AIService.ask()` confirming
   end-to-end ordering with `ai.fallback_enabled: true`.
7. Write the bootstrap-level wiring test addressing
   `EP069.1-AUDIT-002`'s deferred coverage (Section 19).
8. Run full regression to confirm zero existing test breakage
   (Acceptance Criterion 6).
9. Proceed to STEP 3 (Architecture Audit) only after STEP 2 review.

## 27. STEP 1 Completion Criteria

- [x] Cost-aware selection hypothesis independently verified against
      `EP069_DESIGN.md` Section 29, `docs/BACKLOG.md`, and
      `docs/architecture/JARVIS_ROADMAP.md`; found incorrect; documented
      (Section 0).
- [x] Correct next slice (configured fallback ordering) identified from
      the same evidence and independently confirmed architecturally
      ready, unlike cost-aware selection (Section 0, Section 9.2).
- [x] `AIProvider`, `ProviderRegistry`, `ProviderManager`, `AIService
      .ask()` each read directly from current source (Section 9).
- [x] EP-069.1 treated as frozen; no resolved STEP 3/3.1 finding
      reopened; no EP-069.1 document modified (Section 6, Section 24).
- [x] Exact change point identified as a single method
      (`list_fallback_candidates()`) with a single call site
      (`AIService.ask()`'s `remaining[0]`), requiring zero
      `AIService`/`AIProvider`/`ProviderRegistry` changes (Section 9.1,
      Acceptance Criteria 7-9).
- [x] Configuration approach (D2/D3) chosen and justified against at
      least one rejected alternative (per-provider numeric priority)
      (Section 21).
- [x] Every required Owner Decision (D1-D12) recorded, none silently
      resolved (Section 21).
- [x] Objectively verifiable acceptance criteria defined, avoiding
      vague language (Section 20).
- [x] Non-Goals explicitly exclude cost-aware selection, tool calling,
      and expanded eligibility (Section 8).
- [x] Protected files/boundaries enumerated and none modified during
      this STEP 1 (Section 24).
- [x] `docs/architecture/designs/EP069_2_DESIGN.md` created at the
      required path; no other file created or modified.
