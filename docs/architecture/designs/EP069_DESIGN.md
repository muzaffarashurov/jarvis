# EP-069 — AI Provider & Tool Registry (Parent Package)
## EP-069.1 — Automatic AI Provider Fallback on Request Failure

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 0. How this scope was derived

`docs/architecture/JARVIS_ROADMAP.md` lists EP-069 only inside "Phase
A — Core Safety & Autonomy (planning only)," pointing to
`docs/BACKLOG.md` for detail. `docs/BACKLOG.md`'s "Next Engineering
Package" section is explicit: *"None yet defined... No EP-069 or
Phase 11 exists anywhere in this repository as of this release"* — and
its own "Long-Term Roadmap" section header states *"Status: PLANNING
ONLY... No EP number below has an owner, a design document, or a
STEP 1 report yet."* The one line that does exist —

> **EP-069 — AI Provider & Tool Registry** (HIGH). Provider-
> independent abstractions for AI providers, models, tools,
> capabilities, fallback providers, provider selection, and cost
> awareness, so Jarvis is never hard-coded to one AI provider.

— is a planning identifier, not a scoped requirement. The same section
explicitly invokes this repository's own splitting convention
("Engineering Package Policy," `JARVIS_ROADMAP.md`) for exactly this
situation: *"Every EP listed here still requires its own, independent
STEP 1... determining its real scope... and deciding whether it should
be... split into smaller EPs."*

### 0.1 Reconciling the one-line description against the actual codebase

Direct inspection (Section 2) shows the description bundles at least
four architecturally distinct concerns, each at a different state of
completeness:

| Backlog phrase | Actual repository state |
|---|---|
| "Provider-independent abstractions for AI providers[/]models" | **Already built.** `AIProvider` (ABC), `ProviderRegistry`, `ProviderManager`, `ProviderFactory` (EP-014), extended with real `ClaudeProvider`/`GeminiProvider` implementations (EP-015/EP-015.1). |
| "fallback providers, provider selection" | **Not built.** `ProviderManager` holds exactly one "current" provider, selected manually via `ai use <provider>`. `AIService.ask()` returns a failure the instant the current provider raises — confirmed in Section 3. |
| "tools" | **Ambiguous / conflated.** A `Tool` abstraction already exists (EP-031, `src/core/tool/`), but it is the internal Agent/Planning Engine's action-dispatch catalog (`PlanStep.subsystem`/`PlanStep.action` → `Tool.handler`) — it has no relationship to AI providers and no concept of exposing callable tools *to* a language model (LLM function/tool calling). No LLM function-calling capability exists anywhere in the provider layer (Section 2.6). |
| "capabilities... cost awareness" | **Not built**, and no cost/pricing model of any kind exists anywhere in the repository for any provider. |

Treating this single roadmap line as one EP would violate this
project's own "smallest coherent change" principle and its explicit
sub-package convention. This document therefore proceeds exactly as
directed:

- **EP-069** is retained as the **parent architectural package** —
  the roadmap identifier for the general direction ("provider- and
  tool-independent AI subsystem"). It has no design document of its
  own and produces no code.
- **EP-069.1 — Automatic AI Provider Fallback on Request Failure** is
  defined here as the **first, independently implementable slice**:
  the one item under the parent's description ("fallback providers,
  provider selection") that is concretely specifiable from the
  existing, already-built provider abstraction with no new,
  unproven architectural concept.
- "Tools," "capabilities," and "cost awareness" are explicitly
  **not** addressed by EP-069.1 (Section 6, Section 29) and are
  named as candidate future EP-069.x slices, each requiring its own
  STEP 1.

### 0.2 Why fallback (not tools or cost) is the correct first slice

- It is the only backlog phrase with a direct, unambiguous mapping to
  an existing, inspectable gap: `AIService.ask()`'s single-provider,
  fail-fast behavior (Section 3).
- It requires no new domain concept: `AIProvider`, `ProviderRegistry`,
  and the `ProviderError` hierarchy (Section 2) already model
  everything needed to decide "did this provider fail in a way that
  justifies trying another one."
- It carries no ambiguity requiring an Owner Decision about *what
  the feature even is* (unlike "tools," which conflates two
  unrelated existing concepts — Section 2.6/2.7 — and would need a
  separate STEP 1 just to define terms).
- It is bounded in size and precedented: this repository has three
  recent, structurally similar EPs (EP-064 MemoryPersistence shutdown,
  EP-066 MemoryPersistence auto-save resilience, EP-067 Telegram poll
  loop resilience) that each added a narrow reliability behavior to
  an existing component without redesigning it. EP-069.1 follows the
  same shape: a resilience addition to a request path, not a new
  subsystem.

---

## 1. Title

EP-069.1 — Automatic AI Provider Fallback on Request Failure

## 2. Status

STEP 1 complete (this document). STEP 2 (Implementation & Testing),
STEP 3 (Architecture Audit), and STEP 4 (Documentation Synchronization)
have not started. EP-069 (parent) remains a planning identifier with
no design document of its own; this document covers EP-069.1 only.

## 3. Context

Jarvis's AI subsystem (EP-014 AI Provider Manager, extended by EP-015/
EP-015.1) already supports multiple interchangeable `AIProvider`
implementations (`claude`, `gemini`, plus placeholder `openai`/
`ollama`/`lmstudio`), selected one at a time via `ai use <provider>`
and invoked through a fixed pipeline:

```
User -> Conversation Engine -> Context Engine -> Prompt Engine -> ProviderManager -> Provider
```

(`src/services/ai_service.py`, module docstring, EP-018). Today, if
the single currently-selected provider fails for any reason — an
expired API key, a network outage, an upstream 5xx, a timeout — the
request fails outright, even when a second, fully configured and
available provider (e.g. `gemini`) is registered and idle in the same
`ProviderRegistry`. There is no mechanism anywhere in the codebase
that automatically tries another registered provider before giving up.

A related, previously undocumented finding from this STEP 1: the `ai:`
configuration block already defines a `retry_count: 2` key
(`config/config.yaml` line 580) that **no code anywhere in `src/`
reads** (Section 2.5). It exists only as boilerplate carried into
dozens of unrelated tests' fixture config strings (e.g.
`tests/EP023/test_memory_manager.py`, `tests/EP061/test_scheduler_shutdown.py`,
and 28 other files) — never as a functioning setting. This is evidence
that provider-level retry/resilience was anticipated at EP-014 time
but never implemented, and is addressed directly by an Owner Decision
below (Section 28, D9) rather than silently repurposed.

## 4. Problem Statement

`AIService.ask()` (`src/services/ai_service.py:425-478`) sends a
built prompt to exactly one provider — the one `ProviderManager
.get_current()` returns — and, on any `ProviderError` from that
provider's `ask()`, immediately returns
`AskResult(success=False, ...)` to the caller (CLI, Telegram, REST,
Desktop UI, Voice Assistant — every `AIService` consumer). This is
true even when:

- the failure is transient and provider-specific (a timeout, a
  network error, an upstream 5xx classified as
  `ProviderUnavailableError`), and
- one or more other providers are registered in the same
  `ProviderRegistry`, enabled, fully configured
  (`AIProvider.is_available()` is `True`), and otherwise idle.

Jarvis's own stated long-term goal (`JARVIS_ROADMAP.md`, "Long-Term
Goal": *"a provider-independent AI Operating System... that remains
independent of any single AI provider or technology"*) is only
partially realized: providers are swappable one at a time by the
operator, but the system is still hard-dependent on whichever single
provider is currently selected surviving every request.

## 5. Goals

1. When the currently active provider's `ask()` call fails with a
   failure type judged eligible for fallback (Section 15), and at
   least one other registered provider is available, automatically
   attempt the request against that other provider before returning
   failure to the caller.
2. Preserve the existing single-provider behavior exactly when no
   eligible fallback provider exists, fallback is disabled, or the
   failure is not fallback-eligible.
3. Make the caller aware, in the successful result, that a fallback
   occurred and which provider actually served the request (`AIService`
   already reports `provider` in `AskResult`; this must reflect the
   provider that succeeded, never silently reported as the original
   one).
4. Preserve every EP-068 logging guarantee: no prompt text, no
   response text, and no raw provider-supplied error body reaches the
   log at a fallback decision point.
5. Keep provider selection, catalog storage, and provider construction
   exactly where they already live (`ProviderManager`,
   `ProviderRegistry`, `ProviderFactory` respectively) — no
   duplication of responsibility.

## 6. Non-Goals

Per the calling task's explicit instruction, EP-069.1 does **not**:

- implement cost-aware provider selection or any cost/pricing model;
- implement LLM function/tool calling, or any mechanism for exposing
  callable tools to a provider's API;
- redesign, extend, or touch the existing internal Tool Engine
  (EP-031, `src/core/tool/`) in any way;
- implement or modify any concrete provider (`ClaudeProvider`,
  `GeminiProvider`, or the `openai`/`ollama`/`lmstudio` placeholders);
- introduce retries against the *same* provider (only fallback to a
  *different*, already-registered provider is in scope — see
  Section 16, D3);
- introduce circuit breakers, health-check polling, load balancing, or
  dynamic/adaptive provider scoring of any kind;
- change how a provider is registered, constructed, or how `ai use
  <provider>` selects the "current" provider for the *next* fresh
  request (Section 14, D1);
- change `AIProvider`'s abstract contract (`name()`, `status()`,
  `is_available()`, `configuration()`, `health()`, `ask()`, `ping()`,
  `list_models()`, `validate_configured_model()`) in any way;
- perform any large-scale refactor of `src/core/ai/`.

## 7. Relationship to EP-069 Parent Package

EP-069.1 is the first of what is expected to be several EP-069.x
sub-packages under the EP-069 "AI Provider & Tool Registry" planning
identifier (Section 0). It consumes, but does not modify, the
provider-independence foundation EP-069's description refers to
(already delivered by EP-014/EP-015). It deliberately leaves "tools"
and "cost awareness" — the other two concerns bundled into the EP-069
one-liner — untouched, as separate future slices (Section 29).

## 8. Relationship to EP-068 and Previous EPs

- **No file-level overlap.** A search of every design and audit
  document from EP-064 through EP-068 (REV2) for `AIService`,
  `ProviderManager`, or `AIProvider` returned zero matches — none of
  the five most recent EPs touched, referenced, or constrained the AI
  provider subsystem in any way. EP-069.1 introduces no conflict with
  any of their Owner Decisions.
- **EP-068's logging precedent directly governs this design.**
  EP-068 (`CommandRouter.dispatch()`) established, and its Revision 2
  audit confirmed, the pattern this EP must reuse for any new log
  statement at a failure boundary: log only code-authored, closed-set
  values (module/provider name, `type(exc).__name__`) — never raw
  user input, and never a downstream component's free-form message
  when that message could carry user-supplied content. Section 19
  applies this directly to fallback logging.
- **EP-066/EP-067's precedent for "add resilience without changing
  the wrapped component" is the structural template for this EP.**
  Both added a `try`/`except` guard *around* an existing call
  (`self.save()`, `self._poll_once()`) without changing that call's
  own contract, kept the change to a single file plus a single new
  `tests/EP0NN/` package, and left every adjacent, deferred item
  explicitly untouched. EP-069.1 follows the same shape: a guard
  added around the existing `current.ask(...)` call inside
  `AIService.ask()`, with `AIProvider.ask()`'s own contract completely
  unchanged.
- **EP-064's "smallest architecturally correct scope" test** is
  applied identically in Section 0.2 above to select fallback (not
  tools, not cost) as this EP's scope.

## 9. Current Architecture

Relevant components, all under `src/core/ai/` unless noted:

- **`AIProvider`** (`provider.py`, EP-014/EP-015) — abstract base
  class every provider implements. Identity/status/health methods
  (`name()`, `status()`, `is_available()`, `configuration()`,
  `health()`) never perform network access. `ask()`, `ping()`,
  `list_models()`, `validate_configured_model()` are the EP-015
  network-capable extension points; base implementations are safe
  no-ops. Defines the shared `ProviderError` hierarchy: `ProviderError`
  (base) → `ProviderConfigurationError`, `ProviderAuthenticationError`,
  `ProviderTimeoutError`, `ProviderNetworkError`,
  `ProviderRateLimitError`, `ProviderUnavailableError`.
- **`ProviderRegistry`** (`provider_registry.py`, EP-014) — thread-safe
  catalog. `register()`, `remove()`, `get()` (raises
  `ProviderNotFoundError` if unknown), `find()` (returns `None` if
  unknown), `list()` (returns every registered provider **sorted by
  `name()`**), `is_registered()`. Owns catalog storage only; no
  selection logic.
- **`ProviderManager`** (`provider_manager.py`, EP-014) — owns exactly
  one concept of "the current provider" (`_current_name`, set via
  `set_current()`, read via `get_current()`), plus the AI subsystem's
  `enabled`/`disabled` state. Delegates catalog storage to
  `ProviderRegistry` and construction to `ProviderFactory`. Has no
  concept of an ordered fallback chain.
- **`ProviderFactory`** (`provider_factory.py`, EP-014/EP-015/
  EP-015.1) — builds one `AIProvider` per name in
  `KNOWN_PROVIDER_NAMES = ("claude", "gemini", "openai", "ollama",
  "lmstudio")` from `providers.*` configuration. `claude` → real
  `ClaudeProvider`; `gemini` → real `GeminiProvider`; the remaining
  three → `ConfigDrivenProvider`, a placeholder whose `ask()` is
  never overridden and therefore always raises the base class's
  `ProviderUnavailableError` ("does not support chat requests").
- **`ClaudeProvider`** (`claude_provider.py`, EP-015) and
  **`GeminiProvider`** (`providers/gemini_provider.py`, EP-015.1) —
  the only two providers with real network-calling `ask()`
  implementations. Both classify every failure into the shared
  `ProviderError` hierarchy identically (Section 2.4 below) and both
  already log an `ERROR`-level line on failure containing `str(exc)`
  from the underlying `requests` exception — never the prompt text
  (confirmed by direct inspection of both `ask()` bodies; `str(exc)`
  here originates from the HTTP/network library, not from
  user-supplied content).
- **`AIService`** (`src/services/ai_service.py`, EP-014, extended by
  EP-016/EP-017/EP-018.x) — the sole entry point `AIModule` (CLI) and
  every other consumer uses. Depends only on `ProviderManager` for
  provider access (never `ProviderRegistry` or a concrete provider
  directly, per its own docstring's stated invariant). Implements no
  provider-selection or construction logic of its own.
- **Composition root** (`src/bootstrap.py:584-599`) — constructs
  `AIProviderRegistry` and `ProviderManager` from `ai.enabled`/
  `ai.default_provider` config, then `ProviderFactory(config).build_all()`
  registers all five known providers into the manager, then
  constructs a single `AIService` wired to that one `ProviderManager`.

### 9.1 Current provider construction is unconditional

`provider_factory.build_all()` always builds and registers **all
five** known provider names, regardless of each one's `enabled`
config flag — `enabled: false` only affects that provider's own
`status()`/`is_available()`/`health()` results, not whether it is
constructed and present in the registry. This means
`ProviderRegistry.list()` already reliably enumerates every
configured provider, available or not, with no change required to
discover fallback candidates (Section 12).

### 9.2 `ProviderError` hierarchy is fully shared, not per-provider

Both `ClaudeProvider` and `GeminiProvider` raise from the exact same
set of exception classes defined once in `provider.py`, imported by
both provider modules. There is no per-provider error taxonomy to
reconcile — a single, shared classification (Section 15) is sufficient
and requires no cooperation from concrete provider code.

### 9.3 `ai:` configuration (`config/config.yaml:573-581`)

```yaml
ai:
  enabled: true
  default_provider: "none"
  timeout: 120
  retry_count: 2
  max_context_messages: 20
```

`enabled` and `default_provider` are read by `bootstrap.py` when
constructing `ProviderManager`. `max_context_messages` is read by
`AIService`. `timeout` is not read by `AIService`/`ProviderManager`
(each provider has its own `providers.<name>.timeout`). `retry_count`
is read by no code at all (Section 3, Section 28 D9).

### 9.4 EP-031 Tool Engine — confirmed unrelated to this EP

`src/core/tool/tool.py`'s own docstring defines `Tool.handler` as a
callable "pre-bound... to whichever already-built subsystem service
it wraps," dispatched by `ToolExecutionProvider` for `PlanStep`
objects produced by the Planning Engine (EP-029). This is an
internal, agent-facing action-dispatch mechanism with no relationship
to an `AIProvider`, no relationship to an LLM's own function/tool-
calling API, and no code path that touches `src/core/ai/` anywhere.
No EP-031 design document exists in `docs/architecture/designs/`
(only a CHANGELOG/test-suite trail); nothing in that trail associates
Tool Engine with AI providers. EP-069.1 does not import, subclass, or
modify any `src/core/tool/*` module, and none of that directory is
listed as an in-scope file (Section 22/23).

### 9.5 EP-056 Capability Registry — confirmed adjacent but distinct

`src/skills/capability_registry/skill.py` (EP-056) implements a
read-only "capability" command namespace that summarizes already-
running plugins' capability tags and registered `CommandRouter`
namespaces, optionally injecting that summary into a prompt via
`PromptBuilder.append_capabilities()` — a seam its own docstring
already called "reserved for the future Capability Registry." This is
the closest existing concept to the word "capabilities" in EP-069's
one-line description, but it is a prompt-context feature, not a
provider-selection or fallback feature, and it composes `PluginService`/
`CommandRouter`/`PromptManager` directly with no dependency on
`ProviderManager`/`ProviderRegistry`. EP-069.1 does not modify
`src/skills/capability_registry/skill.py`, `PromptBuilder`, or
`PromptManager`.

## 10. Current Provider Selection / Request Flow

```
1. AIModule (CLI) -> AIService.ask(prompt)
2. AIService.ask():
   a. current = self._provider_manager.get_current()
      -> None if 'ai.default_provider' is "none" / never `ai use`d
   b. if current is None or subsystem disabled -> return AskResult(success=False, ...)
   c. conversation = self._begin_turn(prompt)          (EP-016)
   d. context = self._context_manager.create(...)      (EP-018)
   e. built_prompt = self._prompt_manager.build(...)    (EP-017)
   f. response = current.ask(built_prompt.rendered)     <- single provider, no alternative attempted
   g. on success: self._complete_turn(...); return AskResult(success=True, provider=current.name(), ...)
   h. on ProviderError: log; return AskResult(success=False, provider=current.name(), error=str(exc))
```

`current` is resolved exactly once (step a) and used for the entire
request; there is no loop, no alternative candidate list, and no
retry of any kind anywhere in this path today.

## 11. Current Failure Behavior

- Any `ProviderError` subtype raised by `current.ask(...)` is caught
  by a single `except ProviderError` block in `AIService.ask()`
  (lines 474-477), logged once at `ERROR` level
  (`f"AI request failed (provider='{name}'): {exc}"` — `exc` here is
  always a `ProviderError` instance whose message is a static,
  code-authored string, e.g. `"Provider 'claude' is disabled."`,
  never user-supplied content), and converted into
  `AskResult(success=False, provider=name, model="", text="",
  error=str(exc))`.
- No distinction is made between failure types for retry purposes —
  all six `ProviderError` subtypes, plus the base class itself, are
  treated identically: fail immediately.
- No other registered provider is consulted, even if
  `ProviderRegistry.list()` would show one `is_available() == True`.
- A non-`ProviderError` exception (a bug, not a modeled failure) is
  **not** caught by `AIService.ask()` at all and propagates to the
  caller — this is existing, unchanged behavior and is explicitly
  preserved (Section 16, D2).

## 12. Proposed EP-069.1 Behavior

When `AIService.ask()`'s call to the current provider's `ask()`
raises a fallback-eligible `ProviderError` (Section 15), and the
AI subsystem's fallback capability is enabled (Section 20), `AIService`
attempts the same already-built prompt against the next provider in a
deterministic candidate order (Section 17) that is registered,
`is_available() == True`, and not the one that just failed —
continuing down that ordered list until either a provider succeeds or
every eligible candidate has been tried. The conversation/context/
prompt-building steps (10.c-e) are **not** repeated per candidate —
only step (10.f), the provider call itself, is retried against a
different provider, using the identical `built_prompt.rendered`
string. The successful provider's identity is what `AskResult.provider`
reports; the conversation turn (EP-016) is completed using that
provider's response, exactly as it is today for a single-provider
success.

If every eligible candidate fails, or the failure was not
fallback-eligible, or fallback is disabled/unconfigured, or no other
candidate exists, behavior is **identical to today**: a single
`AskResult(success=False, ...)`, whose `error` reports the failure
information Section 18 defines.

## 13. Detailed Architecture

No new class is introduced. Responsibility placement, per this
project's One Responsibility Per Component rule (`AI_GENERATION_
STANDARD.md`) and matching `AIService`'s own stated invariant of
depending only on `ProviderManager`:

- **`ProviderManager`** gains one new read-only query method,
  `list_fallback_candidates(exclude: str) -> list[AIProvider]`,
  returning `ProviderRegistry.list()` filtered to
  `is_available() == True` and `name() != exclude`, in the registry's
  existing deterministic (name-sorted) order. `ProviderManager` still
  owns *which providers exist and are available* — the only state it
  already owns — and still performs no request-level orchestration.
  It does **not** gain a "current fallback chain" concept, an ordered
  preference list, or any new mutable state; ordering is derived
  fresh from the registry on every call, so it can never go stale
  relative to `register_provider()`/`remove()`.
- **`AIService.ask()`** gains the fallback control flow: on a
  fallback-eligible `ProviderError` from the current provider, it
  calls `provider_manager.list_fallback_candidates(exclude=current
  .name())`, and — only if fallback is enabled (Section 20) — tries
  `built_prompt.rendered` against each candidate in order via the
  same `try: response = candidate.ask(...); except ProviderError:
  continue` shape already used for the single-provider case, stopping
  at the first success. `AIService` owns the *policy* of when to
  fall back and how many attempts to make; `ProviderManager` owns
  only *which providers are eligible to be tried*. This mirrors the
  existing split (`AIService` = business logic/orchestration,
  `ProviderManager` = provider selection/state), not a new pattern.
- **No change to `ProviderRegistry`, `ProviderFactory`,
  `AIProvider`, `ClaudeProvider`, `GeminiProvider`, or
  `ConfigDrivenProvider`.** `is_available()` — already part of every
  provider's existing contract — is the only signal used to decide
  eligibility; no provider needs to know fallback exists.

## 14. Provider Selection / Fallback Flow

```
1. AIService.ask(prompt) — unchanged entry point/signature
2. current = provider_manager.get_current()             (unchanged, D1)
3. conversation/context/prompt-building                 (unchanged, 10.c-e)
4. attempted: list[str] = []
5. candidate = current
6. loop:
   a. attempted.append(candidate.name())
   b. try: response = candidate.ask(built_prompt.rendered); break loop on success
   c. except ProviderError as exc:
        classify(exc)                                    (Section 15)
        log fallback decision                             (Section 19)
        if not eligible(exc) or fallback disabled:
            return AskResult(success=False, ...)          (Section 18)
        remaining = provider_manager.list_fallback_candidates(exclude=<every name in attempted>)
        if remaining is empty:
            return AskResult(success=False, ...)          (Section 18, "all failed")
        candidate = remaining[0]
        continue loop (bounded — see D5)
7. on break (success): complete conversation turn using `candidate`'s response;
   return AskResult(success=True, provider=candidate.name(), ...)
```

D1: `ProviderManager.get_current()` / `ai use <provider>` semantics
are completely unchanged — fallback never changes which provider is
"current" for the *next* fresh `ask()` call. A fallback that succeeds
this request does not call `set_current()`.

## 15. Failure Classification

All six existing `ProviderError` subtypes plus the base class,
unchanged (no new exception type is introduced):

| Exception | Fallback-eligible? | Rationale |
|---|---|---|
| `ProviderUnavailableError` | **Yes** | Explicitly means "the API is unreachable or refused the request" — the canonical transient/availability failure this EP exists to route around. |
| `ProviderNetworkError` | **Yes** | Cannot reach the provider at all — the network problem is provider-specific (e.g. one API's edge, not the operator's own connectivity), so another provider may well succeed. |
| `ProviderTimeoutError` | **Yes** | Provider-specific slowness/unavailability; same rationale as the two above. |
| `ProviderRateLimitError` | **Yes** | Rate limits are per-provider/per-account; a different provider has an entirely independent quota. |
| `ProviderAuthenticationError` | **No** | A rejected credential is specific to *that* provider's configuration; retrying a *different* provider is legitimate (different credentials), but retrying is **not** what makes this non-eligible here — see D4: this project's conservative default excludes it from v1 because a bad credential is a configuration defect the operator should see immediately, not mask behind a silent fallback. |
| `ProviderConfigurationError` | **No** | Means "this provider is disabled or missing required configuration" — not a runtime failure at all; masking a configuration mistake behind automatic fallback would hide operator error, and per Non-Goals this EP does not touch configuration semantics. |
| `ProviderError` (base, uncategorized) | **No** | Only raised directly by a provider that deliberately does not implement `ask()` (the base class's own default) — e.g. a `ConfigDrivenProvider` placeholder. Falling back *away from* a placeholder is legitimate in principle, but the base class carries no information distinguishing "deliberately unimplemented" from a genuine unknown failure a future provider might raise directly; treated conservatively as non-eligible for v1 (see Section 29, deferred). |
| Any non-`ProviderError` exception | **No — unchanged existing behavior** | Not caught by `AIService.ask()` today (Section 11) and remains uncaught; fallback never converts a code bug into a silently-swallowed failure. |

This table is itself Owner Decision D4 (Section 28) — it is the
single architectural judgment call in this design that cannot be
derived mechanically from existing code, since eligibility is a
policy choice, not a fact already encoded anywhere in the repository.

## 16. Fallback Policy

- **D2 (Section 28):** Fallback attempts only ever call
  `candidate.ask(built_prompt.rendered)` — the exact same rendered
  prompt string already built once for the original provider. No
  conversation/context/prompt-engine step is re-run per candidate, and
  no candidate ever sees a different prompt than the one that would
  have been sent had it been the original selection. This preserves
  EP-018's fixed pipeline invariant ("the provider still only ever
  sees a single final prompt string") for every candidate, not only
  the first.
- **D3:** Fallback tries a *different, already-registered* provider
  only. It never retries the same provider a second time. (A
  transient failure recovering on a second attempt to the *same*
  provider is retry, not fallback, and is explicitly out of scope —
  Non-Goals.)
- **D5 (attempt bound):** The number of fallback attempts is bounded
  by construction, not by a counter: the loop in Section 14 excludes
  every already-attempted provider name from each subsequent
  `list_fallback_candidates()` call, so it can run at most once per
  currently-registered provider (today: at most 4 fallback attempts
  beyond the original, since 5 providers are always registered —
  Section 9.1) and terminates unconditionally once the candidate list
  is empty. No infinite loop is possible without a new provider being
  registered mid-request, which no code path does.

## 17. Provider Ordering / Selection Rules

Fallback order is `ProviderRegistry.list()`'s existing order —
**alphabetical by `name()`** — filtered to available candidates,
excluding every provider already attempted this request. This is
already deterministic (the registry sorts before returning, Section
9) and requires no new ordering concept, no configuration-driven
priority list, and no per-request randomness. Given today's
`KNOWN_PROVIDER_NAMES`, a `claude` failure with `gemini` available
and `openai`/`ollama`/`lmstudio` all `NOT_CONFIGURED` (their default
state) falls back to `gemini` and stops there (the placeholders are
never `is_available()`). This is Owner Decision D6 (Section 28):
reusing existing alphabetical order rather than introducing a new
configured-priority mechanism is the smallest correct choice, at the
cost of no operator control over fallback preference beyond which
providers are enabled/configured at all — accepted as a deferred
enhancement (Section 29).

## 18. Error Propagation

- **Original failure is preserved for diagnostics.** When fallback is
  attempted and ultimately exhausted, the returned `AskResult.error`
  string reports every attempted provider and its failure, not only
  the last one — e.g. `"All providers failed. claude:
  ProviderTimeoutError, gemini: ProviderUnavailableError."` (exact
  wording is an implementation detail for STEP 2; the requirement is
  that no attempted provider's failure is silently discarded). This
  directly answers "whether the original provider's failure is
  preserved for diagnostics" — yes, by design, for every attempt made.
- **A non-eligible failure (Section 15) is reported exactly as today**
  — `AskResult(success=False, provider=<original>, error=str(exc))` —
  with no mention of fallback, since none was attempted.
- **`AskResult`'s shape is unchanged** (Section 20, D8): no new field
  is added. The richer "every attempt's outcome" detail (previous
  bullet) is carried in the existing `error: str` field, formatted as
  prose, not as a new structured field — consistent with "no new
  public API surface" (Section 20, D8) and this project's Public API
  Policy discouraging speculative interface growth for a single
  consumer.

## 19. Logging and Observability

Directly governed by the EP-068 precedent (Section 8): a fallback
decision is exactly the kind of failure-boundary log site EP-068
hardened `CommandRouter.dispatch()` against, and the same discipline
applies here even though `AIService` is a different component.

- **New log lines this EP adds** (at `INFO` for a successful fallback,
  `ERROR` when a candidate fails, `ERROR` when all candidates are
  exhausted) include only: the failed provider's `name()` (a closed,
  code-authored, five-value set — Section 9.1's
  `KNOWN_PROVIDER_NAMES` — never user input), the successful
  candidate's `name()`, and `type(exc).__name__` for each failure
  (a closed set of the six `ProviderError` subclasses — never
  `str(exc)`, per the EP-068 pattern of preferring the exception's
  class name over its message at a boundary that aggregates multiple
  failures for a single log line).
- **Explicitly never logged:** the prompt (`built_prompt.rendered`),
  the conversation content, the response text of any candidate
  (successful or not), or any raw provider response body. None of
  these are logged today either (Section 9) — this EP does not
  introduce a new place where they could leak, and must not create
  one.
- **Distinct from existing per-provider logs.** `ClaudeProvider`/
  `GeminiProvider` already log their own `f"AI request started/
  finished/failed (provider='...', ...)"` lines per attempt
  (Section 9) — those are unchanged and continue to fire once per
  candidate tried, exactly as they already do for a single-provider
  call. This EP's new log lines are additive, at the `AIService`
  orchestration layer, to make the fallback *decision* itself visible
  in the log (which existing per-provider logs cannot show, since
  each provider has no knowledge that a fallback is occurring).

## 20. Configuration Impact

- **New, dedicated configuration is required** — this cannot be
  achieved as a purely code-level default, because "off by default"
  vs. "on by default" for a change to failure-handling behavior is
  an Owner Decision, not a fact derivable from existing code.
- **D9 (Section 28):** the existing, unused `ai.retry_count: 2`
  (Section 3, Section 9.3) is **not** silently repurposed. Its
  original intent is undocumented and ambiguous — it could equally
  have meant "retry the same provider N times" (a Non-Goal here) as
  "try N other providers." Repurposing an already-shipped,
  already-defaulted config key's meaning without an explicit renaming
  would be a silent behavior change for any operator who had already
  set it, and would contradict the Configuration Policy's expectation
  that a key's meaning stay stable once shipped. Instead, EP-069.1
  proposes one new key, `ai.fallback_enabled: false` (default
  **off**, matching this project's convention of introducing new
  optional behavior disabled by default — see `providers.*.enabled`
  defaulting `false` for every provider except `claude`/`gemini`,
  and `telegram.auto_start` defaulting `false`). The dead
  `ai.retry_count` key is left completely untouched and is flagged
  as an `ARCHITECTURE_DEBT.md` candidate for a future cleanup pass
  (Section 29) — not fixed here, since fixing stale/dead
  configuration is out of this EP's scope.
- No `providers.*` (per-provider) configuration changes. No provider
  needs new configuration to participate in fallback — availability
  is derived entirely from each provider's own already-existing
  `is_available()`.

## 21. Backward Compatibility

- **`ai.fallback_enabled` defaults to `false`.** With no
  configuration change, `AIService.ask()`'s behavior is byte-for-byte
  identical to today: a single provider is tried, and any
  `ProviderError` fails the request exactly as it does now. This
  satisfies "existing behavior remains unchanged when fallback is not
  configured/available" (test strategy requirement) by construction,
  not by a special-cased code path.
- **`AIProvider`'s abstract contract is unchanged** — no new abstract
  or concrete method, no new required override. Every existing
  provider (including third-party or future providers not yet
  written) continues to satisfy the contract with zero changes.
- **`AskResult`'s field set is unchanged** (Section 18) — no consumer
  of `AIService.ask()` (CLI `AIModule`, and any future consumer) needs
  to change to keep working.
- **`ProviderManager.set_current()`/`get_current()`/
  `register_provider()`/`disable()` are unchanged.** The single new
  method (`list_fallback_candidates()`) is additive only.
- **No configuration file migration is required** — `ai.
  fallback_enabled` simply defaults to `false` when absent, per this
  project's established `Config.get(key, default)` pattern used
  throughout `bootstrap.py` and `AIService` already.

## 22. Components Affected

- `src/core/ai/provider_manager.py` — new `list_fallback_candidates()`
  method only. No change to any existing method.
- `src/services/ai_service.py` — `ask()`'s body gains the fallback
  loop (Section 14); its signature, return type, and docstring's
  externally-visible contract are unchanged aside from documenting
  the new behavior. `test()` (which already calls `ask()` internally
  per its own docstring) inherits fallback automatically with no
  separate change required — confirmed by inspection: `test()` is a
  thin wrapper.
- `config/config.yaml` — one new key, `ai.fallback_enabled: false`,
  added to the existing `ai:` block with an explanatory comment
  matching this file's existing per-key comment convention (Section
  9.3 shows the pattern already used for every other `ai.*`/
  `providers.*.*` key).
- `src/bootstrap.py` — reads the new `ai.fallback_enabled` key when
  constructing `AIService` (one new constructor argument), mirroring
  exactly how `ai.enabled`/`ai.default_provider` are already read at
  lines 587-588.
- New test package `tests/EP069/` (Section 25).
- `src/modules/test_module.py` — exactly one new import line,
  appended after the existing `import tests.EP068.test_command_router
  _log_redaction` line, per the established convention (Section 25).

## 23. Expected Files to Change

- `src/core/ai/provider_manager.py`
- `src/services/ai_service.py`
- `src/bootstrap.py`
- `config/config.yaml`
- `src/modules/test_module.py` (one new import line, appended)
- `tests/EP069/__init__.py` (new)
- `tests/EP069/test_ai_provider_fallback.py` (new)
- `docs/architecture/designs/EP069_DESIGN.md` (this document; already
  created during STEP 1)

No other production file is expected to change.

## 24. Explicitly Protected Files

The following must remain byte-for-byte unmodified by EP-069.1
(verified present and inspected during this STEP 1):

- `src/core/ai/provider.py` — `AIProvider` contract and the
  `ProviderError` hierarchy are consumed, never changed.
- `src/core/ai/provider_registry.py` — consumed via its existing
  `list()`/`find()` public API only.
- `src/core/ai/provider_factory.py` — provider construction is
  entirely out of scope.
- `src/core/ai/claude_provider.py`
- `src/core/ai/providers/gemini_provider.py`
- `src/core/ai/context.py`, `context_loader.py`, `context_manager.py`
  (EP-018 Context Engine)
- `src/core/ai/conversation.py`, `conversation_manager.py` (EP-016
  Conversation Engine)
- `src/core/ai/prompt.py`, `prompt_builder.py`, `prompt_manager.py`
  (EP-017 Prompt Engine) — including
  `PromptBuilder.append_capabilities()`, the EP-056 seam (Section
  9.5), which this EP does not use or touch.
- `src/core/tool/*` (all files) — EP-031 Tool Engine, confirmed
  unrelated (Section 9.4).
- `src/skills/capability_registry/skill.py` — EP-056 Capability
  Registry, confirmed adjacent but distinct (Section 9.5).
- `src/core/command_router.py` — EP-068's redaction logic (Section
  8) is reused as a *pattern*, never imported or modified.
- Every file under `tests/EP001/` through `tests/EP068/` — no
  historical EP test suite is modified, per this repository's
  established per-EP test isolation convention (confirmed identically
  stated in EP064/EP065/EP066/EP067's own Protected Files sections).
- `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
  `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `PROJECT_MANIFEST.md` — all
  four are STEP 4 (Documentation Synchronization) artifacts per this
  repository's own convention (Section 0, and confirmed by
  `CHANGELOG.md`'s existing entries, which record STEP 1 through
  STEP 4 together in a single release entry only once STEP 4
  completes — e.g. `v0.1.27-ep068`). None are modified during STEP 1
  of any prior EP inspected, and none are modified here.

## 25. Test Strategy

New, self-contained package `tests/EP069/`, following this
repository's established per-EP convention (`BaseTest`/`TestRegistry`,
no import from any other `tests/EP0NN/` package, local fixtures only
— matching `tests/EP067/test_telegram_poll_loop_resilience.py`'s
explicit "Self-contained... the local fixtures below are deliberately
... independent" pattern):

- File: `tests/EP069/test_ai_provider_fallback.py`
- Test class: `@TestRegistry.register class
  AIProviderFallbackTest(BaseTest): NAME = "EP069"`
- Registration: one new line, `import tests.EP069
  .test_ai_provider_fallback`, appended to `src/modules/test_module.py`
  after the existing EP-068 import line.

Required coverage (each item traces directly to a Goal, Non-Goal, or
Section 14-21 policy point):

1. **Primary provider succeeds → no fallback attempted.** A fake
   `AIProvider` returning a successful `ProviderResponse` is used;
   assert no second provider's `ask()` is ever called, and
   `AskResult.provider` is the primary's name — proves fallback adds
   no overhead/side-effect on the success path (Section 21).
2. **Primary fails with a fallback-eligible failure (Section 15) and
   fallback is enabled → the next available candidate is attempted
   and, on its success, its response is returned**, with
   `AskResult.provider` reporting the *fallback* provider's name, not
   the original (Section 12/18).
3. **Primary fails with a non-fallback-eligible failure (Section 15:
   `ProviderConfigurationError`, `ProviderAuthenticationError`, or the
   base `ProviderError`) → no fallback candidate is ever queried**,
   and the result is identical in shape to today's single-provider
   failure (Section 11/16).
4. **All eligible candidates fail → `AskResult(success=False, ...)`
   whose `error` names every attempted provider and its failure type**
   (Section 18) — not only the last one tried.
5. **Provider ordering is deterministic** — with three fake providers
   registered out of alphabetical construction order, assert the
   fallback attempt order matches `ProviderRegistry.list()`'s sorted
   order (Section 17), run twice to rule out any hidden
   non-determinism (e.g. dict iteration order).
6. **No unexpected infinite fallback loop** — a scenario where every
   registered provider (including a hypothetical newly-registered one
   mid-test) fails must terminate after at most
   `len(registered_providers) - 1` fallback attempts (Section 16, D5)
   — assert an explicit upper bound on `ask()` call count across all
   fakes, not merely that the test process eventually returns.
7. **Existing behavior is unchanged when `ai.fallback_enabled` is
   `False` or absent** — a primary failure with a second, available,
   otherwise-eligible candidate registered must still return
   `success=False` immediately, with the second candidate's `ask()`
   never called (Section 20/21) — this is the single most important
   regression check for backward compatibility.
8. **Sensitive information does not appear in fallback/error logs
   (EP-068 alignment)** — using `loguru`'s sink-capture mechanism
   (matching `tests/EP067/`'s own approach, item F, "No application
   data... leaked into the log"), assert that a distinctive sentinel
   value placed in the *prompt* never appears in any log line emitted
   during a multi-candidate failure/fallback sequence, and that only
   `type(exc).__name__` (never `str(exc)`) appears for each failed
   candidate's exception (Section 19).
9. **Existing provider architecture and public contracts remain
   compatible** — a test constructing every existing concrete
   provider class (`ClaudeProvider`, `GeminiProvider`,
   `ConfigDrivenProvider`) and confirming each still satisfies
   `AIProvider`'s abstract contract unchanged (i.e., this EP added no
   new abstract method they would be missing) — a cheap, high-value
   regression guard against an accidental contract change.
10. **`test()`'s existing wrapper behavior is unaffected** — `test()`
    calling `ask()` internally still returns a well-formed `AskResult`
    when fallback fires, with no separate code path to independently
    verify.

## 26. Acceptance Criteria

STEP 2 implementation of EP-069.1 is complete only when all of the
following are objectively true:

- [ ] `AIProvider`'s abstract contract, `ProviderRegistry`,
      `ProviderFactory`, `ClaudeProvider`, and `GeminiProvider` are
      byte-for-byte unmodified from their pre-EP-069.1 state.
- [ ] `ProviderManager` has exactly one new public method,
      `list_fallback_candidates(exclude: ...) -> list[AIProvider]`;
      every pre-existing public method's signature and behavior is
      unchanged.
- [ ] With `ai.fallback_enabled` absent or `False`, `AIService.ask()`'s
      observable behavior (return value, `AskResult` fields, number
      of provider `ask()` calls, log lines emitted) is identical to
      the pre-EP-069.1 implementation for every existing test
      scenario.
- [ ] With `ai.fallback_enabled: True`, a fallback-eligible primary
      failure with at least one available alternative results in the
      alternative being tried with the identical rendered prompt, and
      a success there is reported as `AskResult(success=True,
      provider=<alternative's name>, ...)`.
- [ ] A non-fallback-eligible primary failure never triggers a second
      provider's `ask()` call, regardless of `ai.fallback_enabled`.
- [ ] Exhausting every eligible candidate returns
      `AskResult(success=False, ...)` whose `error` text names every
      attempted provider and its failure type.
- [ ] No log line emitted anywhere in the fallback path contains the
      prompt text, response text, or any `str(exc)` value derived from
      a `ProviderError` raised during fallback evaluation — only
      provider names and `type(exc).__name__` values appear.
- [ ] `tests/EP069/test_ai_provider_fallback.py` exists, is registered
      in `src/modules/test_module.py`, passes in full, and does not
      import from any other `tests/EP0NN/` package.
- [ ] No file outside Section 23's list has been modified.
- [ ] Every item in Section 25's ten-point coverage list has a
      corresponding, passing assertion.

## 27. Implementation Steps for STEP 2+

(Recorded here for continuity only; STEP 2 itself is out of scope for
this document.)

1. Add `ai.fallback_enabled: false` to `config/config.yaml`'s `ai:`
   block with an explanatory comment.
2. Add `list_fallback_candidates(exclude: str) -> list[AIProvider]` to
   `ProviderManager`, implemented via
   `[p for p in self._registry.list() if p.is_available() and p.name() != exclude]`
   (extended to accept/exclude a set of names for the multi-attempt
   loop — see Section 14).
3. Introduce the fallback-eligibility classification (Section 15) as
   a small, private, pure function or a frozen set of eligible
   exception types inside `ai_service.py` — no new module.
4. Rewrite `AIService.ask()`'s existing
   `try: response = current.ask(...); except ProviderError:` block
   (lines 476-477) into the bounded loop described in Section 14,
   gated on the new `fallback_enabled: bool` constructor argument.
5. Thread `fallback_enabled` from `bootstrap.py`'s existing
   `config.get("ai.enabled", ...)`/`config.get("ai.default_provider",
   ...)` read site into `AIService`'s constructor call.
6. Write `tests/EP069/test_ai_provider_fallback.py` covering Section
   25's ten items, using local fake `AIProvider` fixtures (no network
   access, matching every existing provider test's approach).
7. Add the one new import line to `src/modules/test_module.py`.
8. Run the full existing regression suite (`tests/EP001/` through
   `tests/EP068/`, plus the new `tests/EP069/`) to confirm zero
   regressions, per this project's Testing Policy.

## 28. Architectural Decisions / Owner Decisions

**D1 — `ai use <provider>` / "current provider" semantics unchanged.**
A successful fallback within a single `ask()` call never calls
`ProviderManager.set_current()`. The "current" provider for the
*next* fresh request remains whatever `ai use` last set, even if that
provider just failed and a fallback served this request. Rationale:
conflating "which provider served the last request" with "which
provider the operator explicitly selected" would surprise an operator
who deliberately chose a provider and would silently change `ai use`'s
own documented, unchanged contract.

**D2 — Fallback reuses the single already-built prompt.** No
candidate re-runs the Conversation/Context/Prompt Engine steps
(Section 16). Rationale: those steps are provider-independent by
EP-018's own design ("ConversationManager/Conversation/ContextManager/
Context/PromptManager/PromptBuilder/Prompt all stay
provider-independent"); re-running them per candidate would be
redundant work with no behavioral benefit and would risk each
candidate seeing a subtly different prompt if context depends on
wall-clock time (e.g. "current working directory" context sources).

**D3 — Fallback is cross-provider only, never same-provider retry.**
Confirmed as a hard boundary per the calling task's explicit
instruction and Non-Goals (Section 6).

**D4 — Failure-type eligibility table (Section 15).** The single
substantive judgment call in this design. Recommended: transient/
availability-class failures (`ProviderUnavailableError`,
`ProviderNetworkError`, `ProviderTimeoutError`,
`ProviderRateLimitError`) are eligible; configuration/credential-class
failures (`ProviderConfigurationError`, `ProviderAuthenticationError`)
and the uncategorized base `ProviderError` are not. This is a
conservative default that can be revisited in a future EP-069.x
without changing this EP's structure (the eligibility check is a
single, isolated, easily-extended lookup).

**D5 — Attempt bound is structural, not a configured counter
(Section 16).** No new `ai.fallback_max_attempts`-style key is
introduced; the loop is naturally bounded by the number of currently
registered, not-yet-attempted providers. Rationale: introducing a
separate numeric limit that could be set *higher* than the number of
registered providers would add configuration surface with no possible
effect, and one set *lower* would need its own "what happens when the
limit is reached but candidates remain" sub-decision — unnecessary
complexity for a five-provider catalog.

**D6 — Fallback order reuses `ProviderRegistry`'s existing
alphabetical order (Section 17).** No configured priority list in
v1. Deferred as a candidate EP-069.x enhancement (Section 29) if
operator-controlled ordering is later requested.

**D7 — `list_fallback_candidates()` lives on `ProviderManager`, not
a new class.** Rationale: `ProviderManager` already owns "which
providers are known and selectable"; adding a filtered-listing query
is a natural extension of that existing responsibility, not a new
one, and keeps `AIService`'s stated invariant ("depend only on
ProviderManager") intact — introducing a new `FallbackPolicy`/
`ProviderSelector` class would violate that invariant for no
architectural benefit at this scope.

**D8 — No new public API surface beyond one `ProviderManager` method
and one new config key.** No new `AskResult` field, no new CLI/REST/
Telegram action, no new `AIStatus`/`AIDoctorReport` field. The richer
multi-attempt failure detail is carried in the existing `error: str`
field (Section 18).

**D9 — The dead `ai.retry_count` key is left untouched (Section 20).**
A new, unambiguously-named `ai.fallback_enabled` key is introduced
instead of repurposing it. `ai.retry_count`'s cleanup/removal is
flagged as a future `ARCHITECTURE_DEBT.md` candidate, not fixed here.

**D10 — Files allowed to change (Section 23) are exactly:**
`src/core/ai/provider_manager.py`, `src/services/ai_service.py`,
`src/bootstrap.py`, `config/config.yaml`, `src/modules/test_module.py`
(one import line), plus the new `tests/EP069/` package. No other
production file changes.

**D11 — Test placement.** A new, dedicated, self-contained
`tests/EP069/` package, per this repository's now-consistently-applied
convention (`tests/EP061/` through `tests/EP068/`). No historical EP
test file is modified.

## 29. Deferred EP-069.x Scope

Explicitly out of scope for EP-069.1, each a candidate for its own
future EP-069.x with its own STEP 1:

- **EP-069.2 (candidate) — Configured fallback ordering / priority.**
  Let an operator specify an explicit provider preference order for
  fallback, rather than reusing alphabetical registry order (Section
  17, D6).
- **EP-069.3 (candidate) — Cost-aware provider selection.** Requires
  a pricing/cost model that does not exist anywhere in this
  repository today (Section 0.1) — a substantial, separate design
  effort, not an extension of this EP's fallback loop.
- **EP-069.4 (candidate) — LLM function/tool calling.** Exposing
  callable tools to a provider's own API (distinct from the existing,
  unrelated EP-031 Tool Engine — Section 9.4). Requires its own Owner
  Decision on whether/how it should relate to `Tool`/`ToolRegistry`
  (EP-031) at all, which this document deliberately does not
  prejudge.
- **EP-069.5 (candidate) — Fallback eligibility for
  `ProviderConfigurationError`/`ProviderAuthenticationError`.** If a
  future need arises to fall back even on a misconfigured/rejected
  provider (e.g. for a fully automated, unattended deployment), this
  would revisit D4 (Section 28) specifically, without touching the
  rest of this EP's structure.
- **`ai.retry_count` cleanup** (Section 20, D9) — removing or
  properly documenting the existing dead configuration key. Suitable
  for `ARCHITECTURE_DEBT.md` or a documentation-only future pass, not
  introduced as a side effect of EP-069.1.
- **Same-provider retry** (Section 6, Section 28 D3) — retrying the
  identical provider on a transient failure before considering
  fallback at all. A legitimate, separate future enhancement that
  this EP's structure does not preclude but does not implement.

## 30. Risks and Trade-offs

- **A fallback provider may have a materially different model/
  behavior than the one the operator selected.** Accepted: `AskResult
  .provider`/`.model` already correctly report whichever provider
  actually served the request (Section 12), so the caller is never
  misled about which provider produced the response; the trade-off
  (a `gemini` reply when `claude` was configured) is the entire point
  of the feature and is opt-in via `ai.fallback_enabled` (Section 20).
- **A `ConfigDrivenProvider` placeholder is never a useful fallback
  target.** Its `ask()` always raises the base class's
  `ProviderUnavailableError`, so `is_available()` still gates it out
  today only via its own `enabled`/configured check — a placeholder
  that reports itself `is_available() == True` (misconfigured to look
  configured, e.g. a non-empty but bogus `api_key`) would be
  attempted and immediately fail, adding one wasted attempt before
  moving to the next real candidate. Bounded by D5 (Section 28) — this
  can add at most one extra failed attempt, never an infinite loop or
  a silent success being skipped.
- **Ordering by name (D6) may not reflect operator preference** (e.g.
  `gemini` alphabetically precedes `lmstudio`/`ollama`/`openai` but a
  configured, working `ollama` might be a stronger candidate than an
  unconfigured `gemini` in some deployments). Mitigated in practice by
  the `is_available()` filter (unconfigured providers are never
  attempted regardless of order); explicitly deferred as EP-069.2
  (Section 29) if this proves insufficient.
- **Test flakiness risk is low** — unlike EP-066/EP-067 (real
  background threads with timing-sensitive assertions), fallback is
  entirely synchronous within a single `ask()` call; tests need no
  `sleep`/polling loops, only fake providers with deterministic
  `ask()` behavior.
- **Silent masking of a real outage.** A fully successful fallback
  means an operator relying only on `ask()`'s return value would never
  see that the primary provider is degraded. Mitigated by the new
  `INFO`-level fallback log line (Section 19) and by
  `AskResult.provider` truthfully reporting the fallback provider's
  name rather than the originally-selected one — an attentive
  operator or a future `ai doctor`-style surface (unchanged by this
  EP) can observe the mismatch.

## 31. STEP 1 Completion Criteria

- [x] `docs/BACKLOG.md` and `docs/architecture/JARVIS_ROADMAP.md`
      re-opened and inspected specifically for EP-069's definition
      (Section 0), confirming it is a planning identifier only.
- [x] `AIProvider`, `ProviderRegistry`, `ProviderManager`,
      `ProviderFactory`, `AIService`, `ClaudeProvider`,
      `GeminiProvider`, `ConfigDrivenProvider`, and the
      `bootstrap.py` provider-registration site were each read
      directly from source (Sections 9, 9.1-9.3).
- [x] EP-064 through EP-068 (REV2) design and audit documents searched
      for any reference to the AI provider subsystem — none found
      (Section 8) — and their structural/logging precedents (broad
      guard placement, EP-068 redaction discipline, Owner Decision
      format) applied directly (Sections 8, 13, 19).
- [x] No EP-014/EP-015 design document exists in
      `docs/architecture/designs/`; their intent and constraints were
      instead recovered from source docstrings, which explicitly
      self-identify as EP-014/EP-015/EP-015.1/EP-015.2/EP-015.3
      artifacts (Section 9).
- [x] EP-031 (Tool Engine) inspected directly via
      `src/core/tool/tool.py`'s own docstring and confirmed
      architecturally unrelated to AI providers or LLM tool-calling
      (Section 9.4).
- [x] EP-056 (Capability Registry) inspected directly via
      `src/skills/capability_registry/skill.py` and its own design
      document, confirmed adjacent-but-distinct (Section 9.5).
- [x] Existing test conventions (`BaseTest`/`TestRegistry`,
      per-EP self-contained packages, `test_module.py` sequential
      import registration) verified directly against
      `tests/EP067/test_telegram_poll_loop_resilience.py` and
      `src/modules/test_module.py` (Section 25).
- [x] Owner Decision format verified directly against
      `EP066_DESIGN.md`'s Section 11 and mirrored exactly (Section
      28).
- [x] Verified that no project manifest/index file
      (`PROJECT_MANIFEST.md`, `CHANGELOG.md`, `docs/RELEASE_NOTES.md`,
      `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`) is
      conventionally updated during STEP 1 — confirmed by inspecting
      how EP-068's STEP 1-through-4 lifecycle is recorded in
      `CHANGELOG.md` as a single post-STEP-4 entry, and that
      `PROJECT_MANIFEST.md` does not enumerate individual EP design
      documents at all (Section 24). None of these five files is
      modified by this document.
- [x] The critical design question (fallback semantics) was answered
      point-by-point, not assumed: ownership of selection vs. policy
      (Section 13), registration/availability representation (Section
      9.1, 13), failure classification and eligibility (Section 15),
      attempt bound and determinism (Sections 16-17), diagnostic
      preservation (Section 18), exhaustion behavior (Section 12,
      18), logging/EP-068 alignment (Section 19), public-API impact
      (Section 18, 20, D8), configuration requirement (Section 20),
      and backward compatibility (Section 21) are each addressed
      explicitly and separately.
- [x] Confirmed conservative: no retries, circuit breakers, health
      checks, load balancing, cost optimization, or dynamic scoring
      are introduced (Section 6, Section 29).
- [x] Every file named in Sections 22-24 was confirmed to exist (or,
      for new files, confirmed not to already exist) by direct
      repository inspection during this STEP 1.
- [x] Protected files enumerated (Section 24), including explicit
      confirmation that EP-031 and EP-056 files are excluded from
      this EP's scope.
- [x] Acceptance criteria (Section 26) are each independently
      verifiable by inspection or test, with no vague language.
- [x] `docs/architecture/designs/EP069_DESIGN.md` created at the
      required path.
- [x] No production source file modified. No test file created. No
      other documentation file modified. STEP 2 not started.
