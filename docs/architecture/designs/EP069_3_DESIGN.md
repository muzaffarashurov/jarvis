# EP-069 — AI Provider & Tool Registry (Parent Package)
## EP-069.3 — Cost-Aware AI Provider Selection

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 1. Title

EP-069.3 — Cost-Aware AI Provider Selection

## 2. Status

STEP 1 (this document) only. STEP 2 (Implementation & Testing), STEP 3
(Architecture Audit), and STEP 4 (Documentation Synchronization) have
not started. No source, test, configuration, or tracked documentation
file has been modified to produce this document.

## 3. Context

EP-069 is a planning identifier only (`EP069_DESIGN.md` Section 0);
each numbered sub-package requires its own independent STEP 1. Two
sub-packages exist so far:

- **EP-069.1 — Automatic AI Provider Fallback on Request Failure.**
  Implemented and frozen. Adds `ai.fallback_enabled` (default
  `false`) and `ProviderManager.list_fallback_candidates()`, consulted
  by `AIService.ask()` when the selected provider raises a
  fallback-eligible `ProviderError`.
- **EP-069.2 — Configured Fallback Ordering / Priority.** STEP 1
  design only (`EP069_2_DESIGN.md`), **not committed to this
  repository's source tree.** Direct inspection (Section 6 below)
  confirms `src/core/ai/provider_manager.py` has no `fallback_order`
  parameter and `config/config.yaml`'s `ai:` block has no
  `fallback_order` key today. `EP069_2_DESIGN.md` is treated here
  strictly as architectural design context, per the calling task's
  instruction — not as implemented project state.

`EP069_DESIGN.md` Section 29 named cost-aware provider selection as
the EP-069.3 candidate, explicitly flagging that it "requires a
pricing/cost model that does not exist anywhere in this repository
today... a substantial, separate design effort." `EP069_2_DESIGN.md`
Section 0.1 independently reconfirmed the same gap by direct code
inspection. This document performs that design effort and verifies
both prior findings against the current source tree before proposing
anything.

## 4. Problem Statement

An operator running both `claude` and `gemini`, both configured and
available, has no way to express "prefer whichever provider is
cheaper" for provider selection. Today, the only ordering signal for
provider selection that exists in this repository is
`ProviderRegistry.list()`'s alphabetical order, consulted (via
`ProviderManager.list_fallback_candidates()`) only when EP-069.1's
fallback path is triggered. There is no cost concept anywhere in
`src/core/ai/`, `src/services/ai_service.py`, or `config/config.yaml`.

## 5. Goals

- Determine whether cost-aware provider selection can be introduced
  without changing the `AIProvider`/`ProviderResponse` contract.
- Define the smallest cost model that is architecturally honest about
  what data this system actually has available.
- Specify exactly how cost-aware selection composes with EP-069.1's
  fallback loop and with EP-069.2's (unimplemented) configured
  ordering concept, without requiring EP-069.2 to exist.
- Define deterministic, fail-safe behavior for missing/malformed
  pricing data.

## 6. Non-Goals

Per the calling task's architectural boundary, EP-069.3 does **not**:

- implement billing, accounting, an analytics platform, or a usage
  database;
- implement provider health monitoring, circuit breakers, or load
  balancing;
- implement a retry framework (unchanged from EP-069.1/EP-069.2's own
  Non-Goals: no retry against the *same* provider);
- implement model benchmarking, quality scoring, or a token
  optimization/estimation engine;
- change `AIProvider`'s or `ProviderResponse`'s abstract contract
  (Section 13 justifies this as a real finding, not an assumption);
- change which provider is "current" for the *next* fresh
  `ask()` call, or how `ai use <provider>` / `default_provider` work;
- introduce real-time/external price discovery (web/API price
  retrieval);
- require EP-069.2 (`fallback_order`) to exist in the source tree in
  order to be implemented (Section 12).

## 7. Required Architectural Investigation (Current Repository State)

Direct inspection, this STEP 1, of every component named in the
calling task:

- **`AIProvider`** (`src/core/ai/provider.py:155-288`) — abstract
  contract. `ask()` returns a `ProviderResponse` (Section 8). No
  usage/cost method exists; `configuration()` returns only a
  non-secret configuration snapshot, never runtime metrics.
- **`ProviderResponse`** (`src/core/ai/provider.py:63-75`, the actual
  successful-`ask()` return type — there is no separate `AIResponse`
  class anywhere in this repository; `EP069_2_DESIGN.md` Section 9.2
  uses "`AIResponse`" as an informal name for this same type) — fields
  are exactly `text: str`, `model: str`, `latency_ms: float`. No
  token count, no usage object, no cost field.
- **`AIService`** (`src/services/ai_service.py`) — `AskResult`
  (lines 122-141) mirrors the same shape: `success`, `provider`,
  `model`, `text`, `error`. No usage or cost data flows through it.
- **`ProviderManager`** (`src/core/ai/provider_manager.py`) — owns
  `set_current()`/`get_current()` (manual, in-memory only) and
  `list_fallback_candidates(exclude)` (lines 131-159): filters
  `ProviderRegistry.list()` to available, not-yet-attempted
  candidates. Holds no cost or pricing state.
- **`ProviderRegistry`** (`src/core/ai/provider_registry.py:102-109`)
  — `list()` returns providers sorted by `name()`, unconditionally.
  General-purpose; also used by non-fallback callers (`ai list`).
- **`ProviderFactory`** (`src/core/ai/provider_factory.py`) — builds
  one `AIProvider` per `KNOWN_PROVIDER_NAMES = ("claude", "gemini",
  "openai", "ollama", "lmstudio")`. No pricing data is read here.
- **`ClaudeProvider`** (`src/core/ai/claude_provider.py`) and
  **`GeminiProvider`** (`src/core/ai/providers/gemini_provider.py`) —
  both construct and return `ProviderResponse(text=..., model=...,
  latency_ms=...)` on success (`grep` for `usage`/`cost`/`token` in
  both files returns zero matches). Neither provider currently reads
  or discards a usage object from the underlying Anthropic/Gemini SDK
  response.
- **`ConfigDrivenProvider`** — placeholder implementation for
  `openai`/`ollama`/`lmstudio`; never `is_available()` with default
  configuration; not relevant to cost since it never actually serves
  a request today.
- **Configuration** (`config/config.yaml:573-586, 766-797`) — `ai:`
  block has `enabled`, `default_provider`, `timeout`, `retry_count`,
  `max_context_messages`, `fallback_enabled`. `providers:` block has
  one sub-block per provider (`claude`, `openai`, `gemini`, `ollama`,
  `lmstudio`), each holding provider-specific settings (`enabled`,
  `api_key`/`endpoint`, `model`, `timeout`, `max_tokens`,
  `temperature`). **No pricing, cost, or per-token rate key exists
  anywhere in either block.**
- **Exception taxonomy** (`src/core/ai/provider.py:127-153`) —
  `ProviderError` and its six subclasses; unchanged by this
  investigation, no cost-related exception exists or is implied.
- **Existing fallback implementation** — `AIService.ask()`
  (`src/services/ai_service.py:468-604`, restated in Section 10) is
  the sole caller of `list_fallback_candidates()`; `next_candidate =
  remaining[0]` (line ~589) is the single point where candidate order
  becomes "the next provider tried."
- **Tests** — `tests/EP069/test_ai_provider_fallback.py` exercises
  EP-069.1's fallback loop; no cost-related test exists anywhere in
  `tests/`.
- **Architecture documentation** — `EP069_DESIGN.md` and
  `EP069_2_DESIGN.md` (Section 3 above) both independently already
  concluded this same gap by direct inspection at their own STEP 1
  time; this investigation reconfirms it against the current tree
  rather than trusting the prior documents' claims.

### 7.1 Answer to the Critical Question

**No response, request, or configuration object anywhere in this
architecture exposes input tokens, output tokens, total tokens,
cost, or pricing information.** `model` and `provider` name are the
only two identifying fields available on a completed request
(`ProviderResponse.model`, and the candidate's own `name()`). This is
not an assumption — it is the direct result of Section 7's
inspection, and it holds for both real providers (`ClaudeProvider`,
`GeminiProvider`) identically. This finding is not invented; it
matches `EP069_2_DESIGN.md` Section 9.2's independent finding exactly.

### 7.2 A related existing utility: heuristic token estimation

`src/core/context_compression/compression_provider.py`
(`DefaultCompressionProvider.estimate_tokens()`) and
`src/core/ai/context_loader.py` (`_estimate_tokens()`) both already
contain a characters-per-token heuristic estimator, used today only
for context-budget/compression decisions — never for cost, never
provider-specific, and never accurate enough to represent as a real
token count (it is a rough compression-sizing heuristic, not a
provider-calibrated tokenizer). Reusing it to approximate the cost of
a not-yet-sent prompt was considered and rejected (Section 13.2):
doing so would still leave the *output* token count — the larger,
more price-relevant share of most providers' billing — entirely
unknown before the request is sent, so any resulting "cost" figure
would be a heuristic guess dressed up as a real number. This is
exactly the kind of token-estimation/optimization surface the calling
task's architectural boundary excludes (Section 6).

## 8. EP-069.1 / EP-069.2 Interaction

- **EP-069.1 (frozen, implemented):** unchanged. `_FALLBACK_ELIGIBLE_ERRORS`,
  the retry loop's trigger/termination/`AskResult` shape, and
  `ai.fallback_enabled`'s default-`false` gate are untouched by this
  design. Cost-aware selection (Section 14) is consulted from exactly
  the same single call site EP-069.1 already established
  (`list_fallback_candidates()`), so no change to `AIService.ask()`'s
  control flow is required (mirroring `EP069_2_DESIGN.md` Section
  9.1's own precedent).
- **EP-069.2 (designed, not implemented):** this design must not
  require `fallback_order` to exist in `ProviderManager` or
  `config.yaml` to be implementable on its own (Section 6, Section
  12) — STEP 2 of this EP targets the *current* tree (EP-069.1 only).
  Section 14 specifies the composed algorithm for the case where a
  future EP-069.2 implementation lands afterward, as a forward
  compatibility note, not a dependency.

## 9. Cost Model

### 9.1 What "cost" can honestly mean here

Given Section 7.1's finding, no real per-request cost can ever be
computed by this system without a provider-contract change (Section
13). The only cost data that can exist today is **operator-declared,
static, relative pricing information** — a number the operator types
into configuration because they know their own provider/model
pricing, not a number this system measures or verifies.

### 9.2 Selected cost model: a single static per-provider cost weight

- One new optional numeric configuration value per provider,
  `providers.<name>.relative_cost` (Section 11), read once at
  startup.
- It is **not** input-token pricing, output-token pricing, or
  total-token pricing, because none of those can be computed without
  usage data this system does not have (Section 7.1). It is a single
  relative weight: lower means "prefer this provider when cost-aware
  selection is enabled," nothing more precise than that.
- **Per-provider, not per-model**, because every provider in this
  repository's current configuration (`config/config.yaml:766-797`)
  is configured with exactly one `model:` value — `providers.claude`
  configures one Claude model, `providers.gemini` configures one
  Gemini model. Provider-level granularity is model-level granularity
  today; introducing a separate per-model pricing table would add a
  data shape (a model registry) that does not exist anywhere in this
  repository and is not required to express today's actual
  configuration reality (Section 21, Owner Decision D2).
- **Per-request pricing is out of scope**: there is no per-request
  cost to compute (Section 7.1); the weight is evaluated once at
  candidate-ranking time using whatever was configured at startup.

### 9.3 Rejected: real usage-based cost

Computing actual dollar cost from real token usage was considered and
rejected for this EP (Section 13, Option A) — it requires a
provider-contract change and, more fundamentally, cannot inform
*this* request's provider choice at all, since usage for a request is
only known after that same request has already been sent to a
specific provider (Section 13.1). It is recorded as a future
extension (Section 27), not designed here.

## 10. Current Provider Selection Flow (Fallback Path Only)

Unchanged from `EP069_2_DESIGN.md` Section 10 (restated for this
document's self-containedness, since EP-069.2 is not implemented):

```
1. AIService.ask(): current = provider_manager.get_current()  (unchanged)
2. On a fallback-eligible ProviderError from `candidate.ask()`:
   a. remaining = provider_manager.list_fallback_candidates(exclude=attempted)
      -> ProviderRegistry.list() (alphabetical) filtered to
         is_available() and not-yet-attempted
   b. next_candidate = remaining[0]        <-- today: alphabetically-first remaining
   c. candidate = next_candidate; retry
3. Repeat until success or `remaining` is empty.
```

This EP proposes changing only how step (a)'s returned list is
*ordered* when cost-aware selection is enabled — identical in shape
to how `EP069_2_DESIGN.md` proposed changing that same step for
`fallback_order`.

## 11. Configuration Design

Two new, independent, optional configuration additions — no existing
key changes meaning:

```yaml
ai:
  enabled: true
  default_provider: "none"
  timeout: 120
  retry_count: 2
  max_context_messages: 20
  fallback_enabled: false            # EP-069.1, unchanged
  cost_aware_enabled: false          # EP-069.3, new — see below

providers:
  claude:
    enabled: true
    api_key: ""
    model: "claude-sonnet-4"
    timeout: 120
    max_tokens: 4096
    temperature: 0.2
    relative_cost: 3.0                # EP-069.3, new, optional
  gemini:
    enabled: true
    api_key: ""
    model: "gemini-flash-latest"
    timeout: 120
    temperature: 0.2
    max_tokens: 4096
    relative_cost: 0.5                # EP-069.3, new, optional
```

- **`ai.cost_aware_enabled`** (bool, default `false`) — master gate,
  mirroring `ai.fallback_enabled`'s own default-`false`,
  configuration-only, no-restart-required precedent. When `false`
  (the default), behavior is byte-for-byte identical to today.
- **`providers.<name>.relative_cost`** (float, optional, no default)
  — lives inside each provider's own block, matching this project's
  existing convention that provider-specific settings (`model`,
  `timeout`, `max_tokens`) live under `providers.<name>`, not under
  the feature-level `ai:` block (Section 21, D3). Absence means
  "unknown cost" for that provider (Section 15), never an error.
- **Independent of `ai.fallback_enabled`.** Exactly like
  `fallback_order` was designed to be (`EP069_2_DESIGN.md` Section
  13): `relative_cost`/`cost_aware_enabled` have zero effect while
  `fallback_enabled` is `false`, since `list_fallback_candidates()`
  is only ever consulted from inside the fallback-eligible branch of
  `AIService.ask()`.
- **No change to any existing key's meaning or default.**

## 12. Provider Contract Impact

**No change to `AIProvider`, `ProviderResponse`, or `AIService`'s
public surface.** Cost-aware selection is implemented entirely as a
new ordering step inside `ProviderManager.list_fallback_candidates()`
(Section 14) — the same single change point EP-069.2 identified for
its own, differently-sourced ordering preference
(`EP069_2_DESIGN.md` Section 9.1). This is possible only because
Section 9.2 rejected any design that would require reading per-request
usage: nothing about `relative_cost` requires `ask()` to return
anything it doesn't already return. `AIProvider.ask()`'s signature
and `ProviderResponse`'s three fields remain byte-for-byte unchanged
— directly answering the calling task's Provider Contract question:
**no**, EP-069.3 does not require changing `AIProvider`, the response
type, or `AIService`.

## 13. Architectural Options Considered

### Option A — Provider responses expose real usage metadata

Add `input_tokens: int | None`, `output_tokens: int | None` (and
derived `cost: float | None`) to `ProviderResponse`, populated by
parsing each provider's real SDK response (`ClaudeProvider`,
`GeminiProvider`) plus a per-provider/per-model price-per-token table
in configuration.

- **Correctness:** would be the only option producing an actual
  dollar-accurate figure.
- **Architectural cleanliness:** requires touching a frozen contract
  (`ProviderResponse`) and two concrete provider implementations for
  a feature whose payoff (Section 13.1) cannot be realized without
  further work.
- **Scope:** immediately expands into a token-usage/pricing table
  design — the exact "substantial, separate design effort"
  `EP069_DESIGN.md` Section 29 and `EP069_2_DESIGN.md` Section 0.1
  both already flagged, and edges toward the excluded
  "analytics/accounting platform" (Section 6).
- **Backward compatibility:** additive dataclass fields with
  defaults are technically safe, but every consumer of
  `ProviderResponse` remains unaffected only until something actually
  reads the new fields — at which point this becomes a second EP's
  worth of work (Section 27).

#### 13.1 Why Option A cannot answer this EP's question anyway

Real usage for a request is only known **after** that request has
already been sent to a specific provider. Provider *selection*
happens **before** the request is sent. Even with full usage data on
every `ProviderResponse`, there is no way to know provider X's cost
for *this* prompt without having already sent it to provider X — at
which point selection is moot. Real usage data could only inform a
different provider's *next, unrelated* request (via a rolling
average or similar), which is an accounting/analytics feature
explicitly out of scope (Section 6), not a provider-selection
mechanism. This is the deciding factor, independent of the contract
cost.

### Option B — Provider-specific cost estimation occurs outside the response contract (SELECTED)

A static, operator-declared `relative_cost` per provider (Section
9.2), consulted only during candidate ordering, exactly analogous to
how `EP069_2_DESIGN.md` designed `fallback_order` to be consulted:
no request-time data required at all.

- **Correctness:** correct for what it actually claims to be — an
  operator preference expressed as a cost weight — and makes no false
  claim of measuring real spend.
- **Architectural cleanliness:** touches only `ProviderManager` and
  the composition root (`bootstrap.py`), identical footprint to
  EP-069.2.
- **Scope:** answers "cost-aware provider selection" for the one
  question this architecture can actually answer before a request is
  sent — "which available provider did the operator say is cheaper?"
  — without expanding into billing/analytics.
- **Backward compatibility:** default `false`/absent-key behavior is
  byte-for-byte identical to today (Section 18).
- **Provider independence:** no provider implementation is touched.
- **Testability:** pure function of registry state + configuration,
  no network, no timing, no per-provider mocking of usage payloads.
- **Maintainability / future extensibility:** does not foreclose
  Option A; Section 27 documents Option A as a distinct, later
  extension if real per-request cost tracking is ever wanted for
  reasons other than selection (e.g. reporting).

### Selected Design

**Option B.** Section 13.1 is the deciding factor: Option A cannot
make *this* request's provider choice cost-aware even with a full
contract change, so paying that architectural cost now is not
justified by this EP's own stated goal.

## 14. Provider Selection Algorithm

```
def list_fallback_candidates(self, exclude):
    excluded = set(exclude)
    eligible = [p for p in self._registry.list()          # alphabetical base
                if p.name() not in excluded and p.is_available()]
    if not self._cost_aware_enabled:
        return eligible                                    # unchanged EP-069.1 behavior

    def sort_key(provider):
        cost = self._relative_cost.get(provider.name())     # None if unconfigured
        # Known cost sorts by (0, cost); unknown cost sorts after every
        # known-cost provider, tie-broken alphabetically in both groups.
        return (0, cost, provider.name()) if cost is not None else (1, 0.0, provider.name())

    return sorted(eligible, key=sort_key)
```

- `eligible` is computed **identically** to today — cost-aware
  selection changes *order only*, never *which* providers are
  candidates (same invariant `EP069_2_DESIGN.md` Section 11
  established for `fallback_order`).
- Providers with a configured `relative_cost` are ordered ascending
  by that value; a provider with no configured value is never
  excluded — it is simply ordered after every provider that does have
  one (Section 15).
- Equal `relative_cost` values, and every provider within the
  unknown-cost group, tie-break alphabetically by `name()` — reusing
  `ProviderRegistry.list()`'s existing, established tie-break rather
  than inventing a second rule (Section 19).
- **The currently selected ("primary") provider is never reordered by
  this algorithm.** `list_fallback_candidates()` is called only after
  the primary provider has already failed with a fallback-eligible
  error (Section 10); cost-aware selection has no effect on
  `ProviderManager.get_current()`/`set_current()` or on which
  provider serves the very first attempt of a request. This directly
  answers the calling task's question: cost selection does **not**
  apply only to the initial provider — it applies only to *fallback*
  candidates, never the initial one.

### 14.1 Composition with EP-069.2 (forward-compatible, not required)

If a future EP-069.2 implementation adds `fallback_order` to
`ProviderManager` after this EP ships, the two features would compose
as: names present in `fallback_order` are ordered first, in that
configured sequence (EP-069.2's own rule, unchanged); every remaining
eligible candidate — those absent from `fallback_order` — is then
ordered by `relative_cost` per Section 14's algorithm instead of by
plain alphabetical order. This directly answers "does cost override
configured fallback order": **no** — an explicit, named operator
preference (`fallback_order`) always wins for the names it lists;
cost only orders whatever `fallback_order` leaves unresolved (or
everything, when `fallback_order` is absent, as it is in the current
tree). This composition is documented here for forward compatibility
only; STEP 2 of this EP implements Section 14's algorithm standalone,
against the current tree, with no dependency on `fallback_order`
existing (Section 6, Section 8).

## 15. Unknown / Missing Data Policy

This is the mandatory policy the calling task requires, resolved for
every listed case:

1. **Provider has no pricing** (`relative_cost` absent) — treated as
   unknown cost; sorted after every known-cost provider (Section 14);
   never excluded from candidacy; no warning logged (an operator
   choosing not to configure a cost for a provider is ordinary, not a
   mistake — same reasoning `EP069_2_DESIGN.md` Section 14 applied to
   unmatched `fallback_order` names).
2. **Model has no pricing** — not a distinct case in this design
   (Section 9.2: cost is per-provider, and every provider already has
   exactly one configured model), so this collapses into case 1.
3. **Response has no token usage** — expected and permanent under the
   selected design (Section 7.1, Section 9); not an error condition,
   since this design never reads response usage at all.
4. **Provider reports incomplete usage** — not applicable; this
   design never reads provider usage (Section 12).
5. **Cost cannot be calculated** — cannot occur under this design,
   since "cost" is a single configured number, not a calculation; the
   closest analog is case 1, handled identically.
6. **Pricing configuration is malformed** (`relative_cost` present
   but not a finite, non-negative number — e.g. a string, `null`, a
   negative value, `NaN`, or `Infinity`) — treated identically to
   absent (case 1): the value is discarded and the provider is
   ordered as unknown-cost. Exactly one `WARNING`-level log line is
   emitted at startup naming the configuration key
   (`providers.<name>.relative_cost`) and `type(value).__name__` (or,
   for a negative/non-finite number, the fact that the value was
   out of range) — never echoing an arbitrary raw value verbatim
   beyond what is needed to identify the problem, matching EP-068's
   redaction discipline as EP-069.2's own D8 already applied to
   `fallback_order`.
7. **Cost calculation produces invalid values** — cannot occur; no
   calculation is performed (Section 9.2), only a direct comparison
   of configured numbers.

**The AI subsystem must never become unusable because pricing is
unavailable.** Every case above degrades to "treat this provider as
unknown-cost" and continues serving requests exactly as EP-069.1 does
today when `cost_aware_enabled` is `false` or absent.

## 16. Error Handling

- `cost_aware_enabled: true` with **zero** providers configured with
  `relative_cost`: every eligible candidate falls into the
  unknown-cost group and is ordered alphabetically among themselves —
  behaviorally identical to `cost_aware_enabled: false` for that
  configuration, and not an error.
- `relative_cost` present but `cost_aware_enabled` is `false`: not an
  error — Section 11's independence note applies; no warning logged
  (an entirely ordinary "configured but not yet opted in" state,
  matching `EP069_2_DESIGN.md` Section 14's identical case for
  `fallback_order`/`fallback_enabled`).
- A provider that is selected via cost-aware ordering and then fails:
  handled by the **existing, unchanged** EP-069.1 fallback loop
  (Section 8) — the failure-classification rules
  (`_FALLBACK_ELIGIBLE_ERRORS`), `failure_summary` aggregation, and
  `AskResult` error shape are untouched; cost-aware ordering only
  decided which candidate was tried, never what happens if it fails.
- Invalid `ai.cost_aware_enabled` type (non-boolean): treated as
  `false` (the safe default), with the same class of single startup
  `WARNING` line as Section 15 case 6, naming the key and observed
  type only.

## 17. Determinism / Tie-Breaking

- Given a fixed registry state, a fixed `relative_cost` mapping, and
  a fixed `exclude` set, `list_fallback_candidates()` is a pure
  function — identical inputs always produce identical output order
  (Section 14), matching `EP069_ARCHITECTURE_AUDIT.md`'s existing
  "fallback state is entirely request-local" finding plus one new
  piece of process-lifetime-immutable configuration state (identical
  precedent to `EP069_2_DESIGN.md` Section 17).
- **Tie-breaker for equal `relative_cost`:** alphabetical by
  `name()` — reuses `ProviderRegistry.list()`'s existing rule rather
  than inventing a second one (Section 14).
- **`relative_cost` and `cost_aware_enabled` are immutable after
  construction**, read once from configuration at composition-root
  time (`bootstrap.py`) and passed into `ProviderManager.__init__`,
  exactly like `enabled`/`default_provider` are today. No runtime
  command mutates them in this EP's scope (Section 21, D6). No new
  lock is required beyond `ProviderManager`'s existing
  `self._lock` (guarding only `_current_name`/`_enabled`, unchanged).

## 18. Backward Compatibility

- **Default (`ai.cost_aware_enabled` absent or `false`): zero
  behavior change.** `list_fallback_candidates()` returns exactly
  what it returns today (Section 14's `if not
  self._cost_aware_enabled` branch). No existing EP-069.1 test or
  behavior is affected.
- **Existing configurations remain valid without modification** —
  both new keys are optional; their absence is handled identically to
  explicit `false`/no-cost-configured (Section 11, Section 15).
- **No `providers.*` field is renamed, removed, or repurposed** —
  `relative_cost` is a pure addition to each provider's existing
  block.
- **`ProviderRegistry.list()`'s general-purpose alphabetical
  contract is untouched** — non-fallback callers (`ai list`) see no
  behavior change, since `ProviderRegistry` itself is never modified.

## 19. Security Considerations

- `relative_cost` is a plain, operator-authored number with no
  relationship to credentials, prompts, or responses — it introduces
  no new secret-leakage or prompt-leakage surface.
- No prompt text, response text, or raw provider error body is logged
  as a result of this EP — the one new log line (Section 15 case 6)
  logs only a configuration key name and a type/range description,
  reusing EP-068's existing redaction discipline exactly as
  `EP069_2_DESIGN.md` Section 15 did for its own single new log line.
- No API key, endpoint, or other `providers.<name>` secret field is
  read, logged, or otherwise touched by this design — `relative_cost`
  is read alongside those existing fields but never combined with
  them in any output.
- No network request, external price lookup, or telemetry call is
  introduced anywhere in this design (Section 9.2, explicitly
  rejecting web/API price retrieval per the calling task's
  instruction).

## 20. Test Strategy (for STEP 2 — not performed in this STEP 1)

Conceptual coverage, matching this repository's existing
`BaseTest`/`TestRegistry`/`TestRunner` conventions and EP-069.1/
EP-069.2's own layered approach (unit tests directly on
`ProviderManager`, plus one integration test through `AIService`):

- `cost_aware_enabled: false` (default) → identical order to today,
  regardless of any configured `relative_cost` (regression proving
  zero behavior change).
- `cost_aware_enabled: true`, all eligible candidates priced →
  ascending-`relative_cost` order.
- `cost_aware_enabled: true`, lower-cost provider present among
  available candidates → it is selected first.
- `cost_aware_enabled: true`, higher-cost provider present → ordered
  later, never excluded.
- Equal `relative_cost` between two candidates → alphabetical
  tie-break.
- Unknown pricing (one candidate missing `relative_cost`) → it sorts
  after every priced candidate, never excluded.
- Malformed `relative_cost` (string, negative, `NaN`) → treated as
  unknown, one `WARNING` line, no startup crash.
- Interaction with availability filtering — an unavailable provider
  never appears in the eligible set regardless of its configured
  cost (unchanged `is_available()` filter).
- Interaction with the `exclude` set — an already-attempted provider
  never reappears regardless of cost (unchanged).
- Provider failure after cost-aware selection — the existing EP-069.1
  loop continues to the next candidate exactly as today (Section 16).
- Deterministic repeated selection — same inputs, same output order,
  across repeated calls.
- Backward compatibility — an existing `config.yaml` with neither new
  key produces identical `list_fallback_candidates()` output to the
  pre-EP-069.3 implementation.
- Bootstrap-level test confirming `ai.cost_aware_enabled` and every
  configured `providers.<name>.relative_cost` are correctly threaded
  from `config.yaml` into `ProviderManager`'s constructor — the same
  class of composition-root wiring test `EP069_2_DESIGN.md` Section
  19 specified for `fallback_order`.
- No existing EP-069.1 test file (`tests/EP069/test_ai_provider_fallback.py`)
  is modified — new tests only, additive, per this repository's
  per-EP test-package convention. Exact package/file boundary
  (`tests/EP069_3/` vs. extending `tests/EP069/`) is deferred to STEP
  2 as an explicit Owner Decision (Section 21, D7), mirroring
  `EP069_2_DESIGN.md`'s own D11 rather than silently picking one.

## 21. Scope Boundaries

**In scope:** one new `ai.cost_aware_enabled` gate; one new optional
`providers.<name>.relative_cost` value; the ordering branch inside
`ProviderManager.list_fallback_candidates()`; composition-root wiring
in `bootstrap.py`; tests for all of the above.

**Explicitly out of scope** (restated from Section 6 for
completeness against the calling task's checklist): new AI providers;
Tool Engine or Capability Registry integration; unrelated `AIService`
refactoring; a new persistence layer; external billing; dashboards;
metrics infrastructure; web price scraping; automatic provider health
scoring; any contract change to `AIProvider`/`ProviderResponse`; any
change to `ai use <provider>` or initial/primary provider selection;
any dependency on EP-069.2 being implemented.

## 22. Acceptance Criteria

1. With `ai.cost_aware_enabled` absent from `config/config.yaml`,
   `ProviderManager.list_fallback_candidates()` returns candidates in
   the identical order it did before this EP (byte-for-byte order
   regression test).
2. With `ai.cost_aware_enabled: true`, `providers.gemini.relative_cost:
   0.5`, `providers.claude.relative_cost: 3.0`, and both eligible,
   `list_fallback_candidates()` returns `[gemini, claude]`.
3. With `ai.cost_aware_enabled: true` and only `gemini` priced,
   `list_fallback_candidates()` returns `[gemini, claude]`
   (priced-first, unpriced-appended-alphabetically among themselves).
4. With `providers.claude.relative_cost: "cheap"` (non-numeric),
   exactly one `WARNING`-level log line is emitted at startup naming
   the key and its type, and `claude` is treated as unpriced.
5. No existing EP-069.1 test in `tests/EP069/test_ai_provider_fallback.py`
   fails or requires modification after this EP's STEP 2 changes are
   applied.
6. `AIProvider`'s and `ProviderResponse`'s definitions
   (`provider.py`) are byte-for-byte unchanged (diffable against the
   pre-EP-069.3 version).
7. `AIService.ask()` requires zero code changes (this EP's entire
   behavior change is contained inside `ProviderManager` and
   `bootstrap.py`) — verified by diff inspection in STEP 3.
8. `ai.cost_aware_enabled`'s and `providers.*.relative_cost`'s
   absence from an operator's existing `config.yaml` requires no
   migration and produces no startup warning or error.
9. The currently selected ("current") provider for a fresh `ask()`
   call is unaffected by any `relative_cost` configuration — verified
   by a test asserting `ProviderManager.get_current()` is unchanged
   regardless of cost configuration.

## 23. Owner Decisions

- **D1 — Cost model shape.** A single static, per-provider
  `relative_cost` weight, not real usage-based cost, not per-model
  pricing (Section 9.2, Section 13). Chosen because real per-request
  cost cannot inform this request's own provider choice (Section
  13.1), and per-model granularity has no corresponding configuration
  reality to attach to today.
- **D2 — Config location.** `providers.<name>.relative_cost`
  (provider-scoped), not a new top-level `costs:`/`pricing:` block
  and not inside the `ai:` block. Chosen to match this project's
  existing convention that provider-specific settings live under
  `providers.<name>` (Section 11), the mirror image of
  `EP069_2_DESIGN.md`'s own D3 choosing the `ai:` block for a
  fallback-*feature*-scoped preference rather than a
  provider-*property*.
- **D3 — Whether cost-aware selection applies to the primary/current
  provider.** No — it applies only to `list_fallback_candidates()`
  ordering, never to `get_current()`/`set_current()` or the first
  attempt of a request (Section 14, Acceptance Criterion 9). Changing
  primary selection semantics would reopen EP-069.1's Owner Decision
  D1 and is a materially larger, unrelated change not required to
  deliver "cost-aware provider selection" for the one case this
  architecture can actually support.
- **D4 — Interaction with EP-069.2.** Documented as a forward-
  compatible composition (Section 14.1) but not a dependency — this
  EP's STEP 2 implementation must work standalone against the current
  tree, where EP-069.2 does not exist (Section 8).
- **D5 — Unknown/malformed pricing behavior.** Both degrade to
  "unknown cost, sorted last, never excluded" (Section 15) — no
  startup crash, since pricing is a preference, not a subsystem-
  enabling gate (contrast with `ai.enabled`), mirroring
  `EP069_2_DESIGN.md`'s own D8 for `fallback_order`.
- **D6 — Runtime mutability.** `relative_cost`/`cost_aware_enabled`
  are configuration-file-only, read once at startup — no new CLI
  command is introduced to change them at runtime in this EP (Section
  17, Section 27).
- **D7 — Exact test-package boundary.** Deferred to STEP 2, as an
  explicit open sub-decision (Section 20) — mirrors
  `EP069_2_DESIGN.md`'s own D11 rather than prejudging a convention
  question with no single unambiguous existing precedent.
- **D8 — Whether Option A (real usage-based cost) should ever be
  built.** Not decided here — recorded as a candidate future
  extension (Section 27) contingent on a future, separate need (e.g.
  cost *reporting*, not selection) that would justify the contract
  change Section 13.1 shows selection alone cannot justify.

## 24. Files Expected to Change in STEP 2

- `src/core/ai/provider_manager.py` — add `cost_aware_enabled` and
  `relative_cost` constructor parameters and the new ordering branch
  in `list_fallback_candidates()` (Section 14).
- `src/bootstrap.py` — read `ai.cost_aware_enabled` and each
  configured `providers.<name>.relative_cost`, validate types
  (Section 15/16), and pass them into `ProviderManager.__init__`
  (composition-root wiring only, same site already wiring
  `enabled`/`default_provider`).
- `config/config.yaml` — add the new, commented, default-`false`
  `ai.cost_aware_enabled` key and optional, commented
  `providers.<name>.relative_cost` keys (Section 11).
- A new test file/package per D7 (Section 23) — new tests only, no
  existing EP-069 test file modified.
- Documentation synchronization (STEP 4, not STEP 2): `docs/BACKLOG.md`
  and `docs/architecture/JARVIS_ROADMAP.md` — explicitly not
  performed in this STEP 1.

## 25. Protected Files (Explicitly Not Modified in STEP 1)

Per the calling task's Section "STEP 1 RULE," this STEP 1 does not
modify:

- Any file under `src/` (no production source change).
- Any file under `tests/` (no test change).
- `config/config.yaml` (no configuration change).
- `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md`, `PROJECT_MANIFEST.md`.
- `docs/architecture/designs/EP069_DESIGN.md` and
  `docs/architecture/designs/EP069_2_DESIGN.md` (both treated as
  frozen design context, not rewritten to claim EP-069.2 is
  implemented).
- `docs/architecture/audits/EP069_ARCHITECTURE_AUDIT.md`,
  `EP069_FINDINGS_RESOLUTION.md`, `EP069_2_ARCHITECTURE_AUDIT.md`,
  `EP069_2_FINDINGS_RESOLUTION.md`.
- Any concrete provider implementation (`ClaudeProvider`,
  `GeminiProvider`, `ConfigDrivenProvider`) — this design proves no
  provider-level change is required (Section 12).
- No Git operation of any kind was performed to produce this
  document.

Only `docs/architecture/designs/EP069_3_DESIGN.md` (this file) was
created.

## 26. Risks

- **A `relative_cost` value is an unverified operator claim, not a
  measured fact** — accepted, since Section 13.1 shows no measured
  alternative can inform provider selection anyway; the feature's
  honesty depends on the operator keeping the number roughly current,
  which is out of this system's control and stated plainly here
  rather than implied to be automatic.
- **This design's practical value today is bounded by the same
  two-real-provider landscape** `EP069_2_DESIGN.md` Section 25 already
  noted for `fallback_order` — with only `claude` and `gemini`
  actually available, cost-aware ordering has at most one meaningful
  choice to express until a third real provider exists. The algorithm
  (Section 14) is built for the general case regardless.
- **Combining `fallback_order` and `relative_cost` once EP-069.2
  lands (Section 14.1) is a documented intent, not a tested one** —
  STEP 2 of a future EP-069.2 implementation (or a small follow-up EP)
  would need its own test coverage for the composed behavior; this
  STEP 1 does not build or test that composition since EP-069.2 does
  not exist in this tree (Section 8).
- **Test-package boundary (D7) is left open**, an accepted,
  convention-level gap identical in kind to `EP069_2_DESIGN.md`'s own
  D11.

## 27. Future Extensions

- **Option A (Section 13)** — real usage-based cost *reporting*
  (not selection): adding usage fields to `ProviderResponse` and
  per-provider parsing, if a future need for actual spend visibility
  (distinct from provider selection) ever justifies that contract
  change on its own merits.
- A runtime command (e.g. `ai cost set claude 3.0`) to change
  `relative_cost` without a restart, mirroring `ai use <provider>`'s
  own in-memory-only precedent — deferred per D6.
- Per-model pricing, if this repository ever supports more than one
  model per provider concurrently (Section 9.2) — not needed today.
- The EP-069.2 composition described in Section 14.1, once EP-069.2
  itself is implemented.
- EP-069.4 (LLM function/tool calling) and EP-069.5 (expanded
  fallback eligibility) remain independent, unaffected candidates
  (`EP069_DESIGN.md` Section 29).

## 28. Open Questions

- Whether `relative_cost` should eventually accept a currency unit or
  remain a dimensionless weight — deferred; today's design treats it
  as dimensionless specifically to avoid implying a precision this
  system cannot verify (Section 9.1).
- Whether a future operator-facing `ai doctor`/`ai providers` report
  should surface each provider's configured `relative_cost` for
  visibility — not required for this EP's scope (Section 21) but a
  natural, low-risk STEP 2 addition if desired.
- Exact test-package boundary (D7, Section 23) — left for STEP 2.

---

## EP-069.3 STEP 1 — COMPLETE

- **Design file created:** `docs/architecture/designs/EP069_3_DESIGN.md`
  (this file) — the only file created.
- **Actual architecture examined:** `AIProvider`, `ProviderResponse`
  (there is no separate `AIResponse` class), `AIService`/`AskResult`,
  `ProviderManager`, `ProviderRegistry`, `ProviderFactory`,
  `ClaudeProvider`, `GeminiProvider`, `ConfigDrivenProvider`,
  `bootstrap.py`-driven configuration, `config/config.yaml`'s `ai:`
  and `providers:` blocks, the exception taxonomy, the existing
  EP-069.1 fallback implementation, and `tests/EP069/`.
- **Key architectural conclusion:** no component anywhere in this
  repository exposes token usage, request cost, or pricing
  information, confirming `EP069_DESIGN.md` Section 29 and
  `EP069_2_DESIGN.md` Section 9.2's prior findings by direct
  inspection. More fundamentally, real per-request usage — even if it
  existed — cannot inform *this* request's own provider choice
  (Section 13.1), which is the actual reason the selected design uses
  static, operator-declared pricing instead of any usage-derived
  figure.
- **Selected design approach:** Option B — a static
  `providers.<name>.relative_cost` weight, consulted only inside
  `ProviderManager.list_fallback_candidates()` when
  `ai.cost_aware_enabled` is `true`, ordering fallback candidates by
  ascending cost with unknown-cost providers sorted last and
  alphabetical tie-breaking throughout.
- **`AIProvider` must change:** No.
- **`ProviderResponse` (informally "`AIResponse`") must change:** No.
- **`AIService` must change:** No.
- **Pricing-data strategy:** static, optional, per-provider
  configuration value (`providers.<name>.relative_cost`); no external
  or dynamic pricing source.
- **Token-usage strategy:** none — this design deliberately does not
  read, estimate, or require token usage of any kind (Section 7.2,
  Section 9.3).
- **Interaction with EP-069.1:** none beyond reusing its existing
  single call site (`list_fallback_candidates()`); the fallback
  loop's trigger, termination, error aggregation, and `AskResult`
  shape are all unchanged.
- **Interaction with EP-069.2:** documented as a forward-compatible
  composition (Section 14.1) for if/when EP-069.2 is implemented;
  this EP's own implementation has no dependency on EP-069.2 existing
  in the source tree, which is confirmed absent today (Section 3,
  Section 7).
- **Number of Owner Decisions:** 8 (D1-D8, Section 23).
- **Major risks:** `relative_cost` is an unverified operator claim,
  not a measured fact (Section 26); practical value is bounded by
  today's two-real-provider landscape; the EP-069.2 composition is
  documented but untested until EP-069.2 itself exists.
- **Exact scope:** one new `ai.cost_aware_enabled` gate, one new
  optional `providers.<name>.relative_cost` value per provider, and
  one new ordering branch inside `ProviderManager
  .list_fallback_candidates()`, plus corresponding `bootstrap.py`
  wiring and tests (Section 21, Section 24) — nothing else.
- **Confirmation no implementation was performed:** confirmed — no
  file under `src/`, `tests/`, or `config/` was created or modified.
- **Confirmation no Git operations were performed:** confirmed — no
  `git` command of any kind was run to produce this document.

This STEP delivers only the architecture design document above.
EP-069.3 is **not** implemented.
