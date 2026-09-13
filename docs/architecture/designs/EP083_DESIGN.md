# Phase C — AI Content Platform (planning only, except EP-082 and this EP)
## EP-083 — Image Generation Provider Integration

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — Owner Decisions required before STEP 2

---

## 1. EP Identification

EP-083 — Image Generation Provider Integration

## 2. Official Name and Roadmap Evidence

Confirmed against the repository's own authoritative planning documents
(both agree):

```
docs/BACKLOG.md:3108: - **EP-083 — Image Generation Provider Integration** (MEDIUM)
```

under `## AI Content Platform (EP-082–EP-087)`, immediately after EP-082
(Text Generation Provider Integration, completed) and before EP-084
(Audio & Speech Generation Integration).

A prior planning discussion in this conversation incorrectly proposed
"Agent Harness" as EP-083's scope. That concept does not exist anywhere
in `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
`CHANGELOG.md`, or `docs/RELEASE_NOTES.md` under any EP number — it was
a misidentification, now corrected. This design proceeds exclusively
on **Image Generation Provider Integration**.

---

## 3. Scope

Integrate image-generation capability into the existing AI provider
architecture (`AIProvider`/`ProviderRegistry`/`ProviderManager`/
`ProviderRequestExecutor` — EP-014/015/069/082), following the exact
precedent EP-082 established for text: reuse, additively extend, and
never duplicate. Concretely, in scope:

- A capability-declaration mechanism so a provider can state whether
  it supports image generation (Section 8).
- New domain contracts: an image-generation request and an
  image-generation result (Sections 12–13).
- A minimal, additive generalization of `ProviderRequestExecutor` so
  it can execute an image-generation request with the same
  fallback/retry semantics EP-069 already established for text,
  without a second retry implementation (Section 9, Owner Decision 1).
- A new, standalone `ImageGenerationService`, mirroring
  `TextGenerationService`'s non-conversational shape (Section 10).
- One concrete provider implementation (recommended: `GeminiProvider`,
  the only currently-registered provider whose underlying API family
  genuinely supports image generation — Section 7, Owner Decision 2).
- An additive `image_generation:` configuration namespace and an
  additive `providers.gemini.image_model` config key.
- A dedicated `tests/EP083/` suite.

## 4. Non-Scope

- Audio/speech (EP-084), video (EP-085), presentation (EP-086)
  generation, or the combined pipeline (EP-087). EP-083 introduces no
  generic "media" abstraction that anticipates these — only what
  image generation itself requires.
- Any CLI/CommandRouter namespace. No backlog evidence requires one;
  EP-082 deferred its own CLI for the same reason, and EP-083 follows
  the same boundary.
- Image persistence (no disk-writing, no database, no draft/versioning
  storage). The result contract carries image bytes/reference
  in-memory only, exactly mirroring EP-082's own DEFERRED-persistence
  precedent for text.
- Agent execution, tool orchestration, or any workflow/checkpoint
  concept (EP-092's actual scope — Personal Data Collection Framework
  — is unrelated to EP-083 and is not touched or referenced further).
- Any change to `AIService.ask()` or `TextGenerationService`'s
  existing, audited (STEP 3 PASS WITH WARNINGS) behavior. EP-083 must
  not regress EP-082.
- A second provider registry, factory, manager, or generic
  retry/fallback implementation.
- New providers beyond extending the existing `claude`/`gemini`/
  `openai`/`ollama`/`lmstudio` identities already known to
  `ProviderFactory.KNOWN_PROVIDER_NAMES`.
- Streaming image generation, image editing/inpainting, or
  multi-turn image refinement.

---

## 5. Current Architecture Discovery

Inspected directly (not assumed) before proposing anything below:

- `src/core/ai/provider.py` — `AIProvider` ABC: `name()`, `status()`,
  `is_available()`, `configuration()`, `health()`, `ask()`, `ping()`,
  `list_models()`. `ProviderResponse(text, model, latency_ms)`. The
  `ProviderError` hierarchy, including the fallback-eligible subset
  (`ProviderUnavailableError`, `ProviderNetworkError`,
  `ProviderTimeoutError`, `ProviderRateLimitError`) and the
  non-eligible subset (`ProviderConfigurationError`,
  `ProviderAuthenticationError`). `validate_temperature()` (EP-082).
  **No capability-declaration method of any kind exists on this ABC.**
- `src/core/ai/provider_registry.py` — pure catalog (register/remove/
  get/find/list/is_registered), no capability concept, unchanged
  since before EP-082.
- `src/core/ai/provider_manager.py` — `get_current()`, `set_current()`,
  `list_providers()`, `list_fallback_candidates(exclude)` (EP-069.2
  ordering, EP-069.3 cost-aware sort), `is_enabled()`/`disable()`.
  **`list_fallback_candidates()` has no capability-filtering
  parameter and returns every registered, available provider
  regardless of what it can actually do** — correct for text (every
  known provider is treated as text-capable), not sufficient as-is
  for image generation (Section 9).
- `src/core/ai/provider_factory.py` — `KNOWN_PROVIDER_NAMES = ("claude",
  "gemini", "openai", "ollama", "lmstudio")`. Only `claude` and
  `gemini` have real `AIProvider` subclasses with working `ask()`
  implementations; `openai`/`ollama`/`lmstudio` are placeholder
  `ConfigDrivenProvider` instances whose `ask()` is the base class's,
  which always raises `ProviderUnavailableError`.
- `src/core/ai/provider_request_executor.py` (EP-082) —
  `ProviderRequestExecutor.execute(provider, prompt, *,
  fallback_enabled, max_tokens=None, temperature=None,
  system_prompt=None) -> ProviderRequestOutcome`. Internally, always
  calls `provider.ask(prompt, **kwargs)` — **hardcoded to `ask()`**,
  not generic over which provider method or payload shape to invoke.
  This is the exact seam EP-083 must extend (Section 9).
- `src/services/ai_service.py` / `src/services/text_generation_service.py`
  (EP-082) — both call `ProviderRequestExecutor.execute()` for text;
  neither is touched by this design.
- `src/core/ai/claude_provider.py` — real Anthropic Messages API
  integration (text only; Anthropic's public API has no
  image-generation endpoint as of this design).
- `src/core/ai/providers/gemini_provider.py` — real Google
  Generative Language API integration via `POST
  .../models/{model}:generateContent`. `_parse_response()` calls
  `_extract_text()`, which reads only `parts[*].text` from the first
  candidate and **silently discards any other part type** (e.g. an
  inline image part) — confirmed by direct code inspection
  (Section 7).
- `src/skills/capability_registry/skill.py` — this is **EP-056**'s
  "Capability Learning" CLI namespace over plugin skills
  (`CapabilityRegistryModule`), confirmed by its own module docstring.
  It is unrelated to any AI-provider capability concept.
- **No `src/core/capability/` package, no `CapabilityType` enum, and
  no `IMAGE_GENERATION`/`TEXT_GENERATION` capability constant of any
  kind exists anywhere in this repository's actual source tree**,
  despite `docs/BACKLOG.md`/`CHANGELOG.md`/`RELEASE_NOTES.md`
  describing EP-069.4 ("Unified Capability Abstraction") as
  **COMPLETE** and adding exactly such a package. This is a genuine
  discrepancy between the repository's documentation and the actual
  code available for this STEP 1 (Section 6, Owner Decision 3) — not
  an assumption or an oversight in this discovery.
- `config/config.yaml` — `providers.gemini` block: `enabled`,
  `api_key`, `model`, `timeout`, `temperature`, `max_tokens`,
  optional `relative_cost` (EP-069.3). No image-related key exists.
  `content_generation:` (EP-082) is the most recent additive
  top-level namespace and the direct style precedent for this EP's
  own namespace (Section 15).
- No binary/image-file handling convention exists anywhere in the
  currently-implemented parts of this repository (`src/skills/vision`,
  `src/skills/desktop` were inspected and contain no base64/image-byte/
  file-writing code) — confirming there is no existing abstraction to
  reuse for image *persistence*, which is exactly why persistence is
  explicitly out of scope (Section 4) rather than assumed away.
- `src/core/command_router.py` — `CommandModule` Protocol, unchanged;
  not used by this design (Section 17).

---

## 6. EP-069 Compatibility

Fully compatible, with zero modification to `ProviderRegistry`,
`ProviderFactory`, `ProviderManager`, or `AIProvider`'s existing
methods. EP-083's only touch point on this layer is the additive
capability method (Section 8) and, if Owner Decision 1 is approved,
an additive generalization of `ProviderRequestExecutor` (Section 9) —
in both cases, existing behavior for every existing caller
(`AIService`, `TextGenerationService`, `ReflectionModule`,
`PromptOptimizerModule`) is provably unchanged, since every extension
point defaults to reproducing current behavior when unused.

### EP-069.4 capability compatibility

**This is the one point where "reuse the existing abstraction" cannot
literally be honored, because the abstraction described as shipped
does not exist in the code made available for this STEP 1** (Section
5). Two honest paths exist, and this is Owner Decision 3 (Section 22)
rather than something silently resolved:

- Design against the *documented* EP-069.4 interface as if the code
  existed, and risk a real merge conflict/duplicate abstraction the
  moment the actual `src/core/capability/` package is synced into
  this working copy; or
- Design a minimal, self-contained capability method scoped only to
  what EP-083 itself needs right now (`AIProvider.supports_image_
  generation() -> bool`, defaulting to `False` on the base class),
  explicitly flagged as provisional and superseded the moment
  EP-069.4's real package is available, at which point a small,
  separate reconciliation EP (not EP-083 itself) migrates this one
  method onto whatever the real abstraction turns out to be.

**Recommended: the second path** (Owner Decision 3) — it is
independently useful today, blocks nothing, and duplicates nothing
that provably exists in the actual codebase.

## 7. EP-082 Compatibility

EP-082 provides, and EP-083 reuses unchanged: `AIProvider`'s existing
`ask()`-based text contract, `ProviderManager` in full, and the
general shape of `ProviderRequestExecutor`'s retry/fallback semantics
(Section 9). EP-082's own tests (`tests/EP082`, 69/0/0) and its
regression coverage of `tests/EP069`/`EP069_2`/`EP069_3` remain valid
and untouched by this design — no file EP-082 shipped is modified in
a way that changes its existing behavior (Section 9's
`execute()`-preserving approach is designed specifically to guarantee
this).

**Image generation cannot simply call the existing `ask()` contract**,
confirmed by direct inspection rather than assumption: Google's
Gemini image-generation capability is exposed through the *same*
`generateContent` endpoint `GeminiProvider.ask()` already calls, but
with an image-capable model and a response whose candidate `parts`
contain inline image data (`inlineData: {mimeType, data}`) instead of
(or alongside) `text` — and `GeminiProvider._extract_text()` silently
discards any non-text part today. `ProviderResponse(text, model,
latency_ms)` has no field capable of carrying image bytes/mime type at
all. Reusing `ask()`/`ProviderResponse` as-is for images would mean
either silently losing the generated image (current behavior) or
overloading `text` with a base64 blob, which this design rejects as
exactly the kind of "provider-specific behavior leaking into the
common abstraction" the existing architecture's conventions warn
against. A new, additive method and a new, additive response-shaped
contract are therefore necessary (Sections 8, 13) — not a redesign of
`ask()`, and not a second `ProviderResponse`-equivalent for text.

---

## 8. Proposed Architecture

```
ImageGenerationService
        |
        v
ProviderRequestExecutor (additive: execute_image(), Owner Decision 1)
        |
        v
ProviderManager (UNCHANGED)
        |
        v
AIProvider (additive: supports_image_generation(), generate_image())
```

Mirrors EP-082's own `TextGenerationService -> ProviderRequestExecutor
-> ProviderManager -> AIProvider` chain exactly, so the two content
types (text, image) share the same shape at every layer.

### 8.1 `AIProvider` (additive)

Two new methods, both with base-class defaults that make every
existing provider (including `openai`/`ollama`/`lmstudio` placeholders
and `ClaudeProvider`) valid without modification:

- `supports_image_generation(self) -> bool` — defaults to `False`.
- `generate_image(self, request: ImageGenerationRequest) ->
  ImageGenerationResult` — base implementation always raises
  `ProviderUnavailableError(f"Provider '{self.name()}' does not
  support image generation.")`, exactly mirroring `ask()`'s own
  base-class pattern (EP-015).

`GeminiProvider` overrides both: `supports_image_generation()` returns
`self._image_model is not None` (a new, optional constructor
parameter — Section 15); `generate_image()` performs the real HTTP
call (Owner Decision 2).

### 8.2 `ProviderRequestExecutor` (additive, Owner Decision 1)

The existing `execute()` method's public signature, behavior, and
every log line remain **completely unchanged** — this is not
negotiable per EP-082's own audited backward-compatibility
requirement. Internally, its retry/fallback control flow is factored
into a private, generic helper (`_run()`), and a new, additive public
method, `execute_image()`, calls that same helper with a
provider-agnostic request function and a capability filter:

```python
def execute_image(
    self,
    provider: AIProvider,
    request: ImageGenerationRequest,
    *,
    fallback_enabled: bool,
) -> ProviderRequestOutcome:
    ...
```

`_run()`'s only two new concerns beyond what `execute()` already does:
(a) it accepts a `request_fn: Callable[[AIProvider], T]` instead of a
hardcoded `.ask()` call, and (b) it filters `list_fallback_candidates()`
through `capability_filter` (for images:
`provider.supports_image_generation()`; for the existing `execute()`,
`capability_filter=None`, meaning "no filtering," reproducing today's
exact behavior). There is still exactly **one** retry/fallback
implementation in the repository — `_run()` — satisfying Rule 3/Rule
4 the same way EP-082's own extraction did for `AIService`/
`TextGenerationService`.

### 8.3 `ImageGenerationService` (new)

Standalone and non-conversational, mirroring `TextGenerationService`
exactly: no `ConversationManager`, `ContextManager`, `PromptManager`,
or persistence dependency of any kind. Accepts an
`ImageGenerationRequest`, resolves the current provider via
`ProviderManager.get_current()`, and delegates to
`ProviderRequestExecutor.execute_image()`.

---

## 9. Provider Selection, Execution, and Retry/Fallback

Answering Section 5's questions directly, from the discovery above:

1. **Can the existing executor execute image-generation requests
   safely?** Not as `execute()` is written today (hardcoded to
   `.ask()` and to `ProviderResponse`'s text-only shape) — but yes,
   safely and without duplication, via the additive `execute_image()`
   /`_run()` generalization in Section 8.2 (Owner Decision 1).
2. **Does its current request/response model support image-generation
   semantics?** No (Section 7) — `ImageGenerationRequest`/
   `ImageGenerationResult` are new, additive contracts (Sections
   12–13), not a repurposing of `ProviderResponse`.
3. **Does image generation require binary/image payload handling?**
   Yes — see Section 13 (base64, in-memory, no persistence).
4. **URLs, file references, base64, metadata, or another
   representation?** Base64 + mime type, in-memory only (Section 13).
5. **How should retries and provider fallback work?** Identically to
   EP-069's existing semantics (same eligible-exception set, same
   `ProviderManager` ordering), applied through the same `_run()`
   helper `execute()` itself uses (Section 8.2) — no second policy.
6. **How should providers that do not support image generation be
   excluded?** Via `capability_filter=lambda p:
   p.supports_image_generation()` passed to `_run()`, applied both to
   the initial provider (an `ImageGenerationService` caller whose
   `ProviderManager.get_current()` is not image-capable fails fast
   with a clear "current provider does not support image generation"
   result, never even reaching the executor) and to every fallback
   candidate `list_fallback_candidates()` returns.
7. **Where should capability filtering occur?** In `ImageGenerationService`
   (for the initial provider) and inside `ProviderRequestExecutor._run()`
   (for fallback candidates) — never inside `ProviderManager` itself,
   which remains capability-agnostic and unchanged (Section 5).
8. **Which layer owns image-specific validation?** `AIProvider.
   generate_image()`'s concrete implementations (mirroring how
   `validate_temperature()` is called by each concrete text provider,
   not by the ABC or the executor) — see Section 12.

---

## 10. Component Responsibilities

| Component | Owns | Does not own | Depends on | Called by | Returns | Error propagation |
|---|---|---|---|---|---|---|
| `AIProvider.generate_image()` | Translating a validated `ImageGenerationRequest` into one concrete provider's real API call | Retry, fallback, provider selection | Nothing above it | `ProviderRequestExecutor._run()` | `ImageGenerationResult` | Raises `ProviderError` subtypes |
| `AIProvider.supports_image_generation()` | Declaring this one provider instance's own capability | Any other provider's capability, registry-wide capability tracking | Its own configuration | `ImageGenerationService`, `ProviderRequestExecutor._run()` | `bool` | Never raises |
| `ProviderRequestExecutor` | Request execution, retry/fallback orchestration, attempted-provider exclusion, capability-aware candidate filtering (image only), final outcome | Provider selection/ordering, capability *declaration*, conversation/context | `ProviderManager` (`list_fallback_candidates()` only) | `AIService`, `TextGenerationService`, `ImageGenerationService` | `ProviderRequestOutcome` | Catches `ProviderError`, never re-raises |
| `ImageGenerationService` | Standalone image-generation entry point, request/result mapping | Conversation, context, persistence, provider selection internals | `ProviderManager`, `ProviderRequestExecutor` | Future EP-087 (documented, not implemented) | `ImageGenerationResult`-derived service result | Never raises `ProviderError` to its own caller (mirrors `TextGenerationService`) |
| `ProviderManager` | Provider registry access, current-provider selection, fallback ordering, cost-aware ordering | Execution, retry, capability filtering | `ProviderRegistry` | `ProviderRequestExecutor`, services | `AIProvider` / `list[AIProvider]` | N/A (no execution) |

No component in this table becomes a "god object": each row has exactly one execution-layer concern, matching EP-082's own audited boundary discipline.

---

## 11. Execution Lifecycle

```
ImageGenerationService.generate(request)
  -> check enabled (config)
  -> get_current() provider
  -> if provider is None -> fail: "No AI provider is currently selected."
  -> if not provider.supports_image_generation()
       -> fail: "<provider> does not support image generation."
       (no executor call at all -- this is a configuration/selection
        problem, not a transient failure, so it is never retried)
  -> ProviderRequestExecutor.execute_image(provider, request, fallback_enabled=...)
       -> attempt provider.generate_image(request)
       -> on fallback-eligible ProviderError (and fallback_enabled=True):
            -> list_fallback_candidates(exclude=attempted)
            -> filter to provider.supports_image_generation()
            -> retry next capable candidate, else exhausted-failure
       -> on non-eligible ProviderError: fail immediately
  -> map ProviderRequestOutcome -> ImageGenerationResult-derived service result
```

No agentic loop, no multi-step iteration, no tool invocation, no
workflow state, and no cancellation semantics are introduced — a
single image-generation request is a single provider call (with
fallback), exactly like `TextGenerationService.generate()` is a
single text call. There is no "termination condition" beyond
"succeeded, or every eligible candidate failed," because there is no
loop.

---

## 12. Data Contracts — Request

```python
@dataclass(frozen=True)
class ImageGenerationRequest:
    """A provider-independent request to generate one or more images (EP-083).

    Attributes:
        prompt: The image description. Required, non-empty.
        negative_prompt: What to avoid in the generated image. None
            means no negative prompt is supplied.
        size: Requested output dimensions as "WIDTHxHEIGHT" (e.g.
            "1024x1024"), or None to use the provider's own default.
            EP-083 does not enumerate a fixed set of valid sizes --
            each concrete provider validates and translates this to
            its own accepted values, raising ProviderConfigurationError
            for a value it cannot honor.
        number_of_images: How many images to generate. Defaults to 1.
            Must be a positive integer; a concrete provider that
            cannot honor a value greater than its own maximum raises
            ProviderConfigurationError.
        seed: Optional deterministic seed. None means no seed
            requested (provider default randomness).
    """
    prompt: str
    negative_prompt: str | None = None
    size: str | None = None
    number_of_images: int = 1
    seed: int | None = None
```

**Provider-independent, by design.** Fields present here are only
those with a plausible, common meaning across image-generation APIs
in general (prompt, negative prompt, size, count, seed) — not every
parameter a specific provider happens to expose. Provider-specific
options (e.g. a Gemini-only "style preset" or an aspect-ratio enum
that doesn't map cleanly to "WIDTHxHEIGHT") are explicitly NOT added
to this common contract; a concrete provider that needs one reads it
from its own `providers.<name>.*` configuration instead (mirroring
how `temperature`'s *default* lives in provider config while the
*override* lives in the common `ask()` contract — Section 15).

**Validation ownership:** `ImageGenerationRequest` itself performs no
validation beyond what a frozen dataclass gives for free (immutability).
Each concrete `generate_image()` implementation validates the fields
it can actually honor and raises `ProviderConfigurationError` for
anything it cannot — the same layering EP-082 already established for
`validate_temperature()` (single rule, applied at the point closest to
the actual API call, not centralized in the ABC).

## 13. Data Contracts — Result

```python
@dataclass(frozen=True)
class GeneratedImage:
    """One generated image (EP-083).

    Attributes:
        data_base64: The image's raw bytes, base64-encoded. In-memory
            only -- EP-083 introduces no file persistence (Section 4).
        mime_type: The image's MIME type (e.g. "image/png").
    """
    data_base64: str
    mime_type: str


@dataclass(frozen=True)
class ImageGenerationResult:
    """Result of `AIProvider.generate_image()` (EP-083).

    Attributes:
        images: The generated image(s). Always non-empty on success.
        model: The model identifier that produced `images`.
        latency_ms: Wall-clock time the request took, in milliseconds.
    """
    images: tuple[GeneratedImage, ...]
    model: str
    latency_ms: float
```

Mirrors `ProviderResponse`'s existing shape (`model`, `latency_ms`)
exactly, replacing its single `text: str` with `images: tuple[
GeneratedImage, ...]` — the smallest change that fits the same
pattern rather than a structurally different result type. `images` is
a tuple (immutable, matching the frozen-dataclass style already used
throughout `provider.py`), never empty when `success` (a provider
returning zero images is treated as `ProviderUnavailableError`,
handled at the same layer `_extract_text()`'s empty-string case would
be, per Section 7's discovery).

`ImageGenerationService.generate()` wraps this into a service-level
result (`ImageGenerationServiceResult`, exact naming left to STEP 2 as
a non-architectural detail) that never raises `ProviderError` to its
own caller — identical failure-reporting convention to
`TextGenerationResult` (EP-082 Section 14): every failure becomes
`success=False` with a user-friendly `error` string, never a raised
exception.

---

## 14. Error Model

No new exception type is introduced. Every image-generation failure
is one of the `ProviderError` subtypes EP-069.1 already defined,
classified identically to text:

| Failure | Exception | Fallback-eligible |
|---|---|---|
| Provider unreachable / doesn't support image generation | `ProviderUnavailableError` | Yes (same as today) |
| Network failure | `ProviderNetworkError` | Yes |
| Timeout | `ProviderTimeoutError` | Yes |
| Rate limit | `ProviderRateLimitError` | Yes |
| Invalid request (bad size, unhonorable seed/count) | `ProviderConfigurationError` | No |
| Bad/missing API key | `ProviderAuthenticationError` | No |
| Malformed provider response (e.g. no image part where one was expected) | `ProviderUnavailableError` (mirrors `GeminiProvider`'s existing "invalid response body" precedent) | Yes |

One nuance specific to images, not present for text: a provider that
is reachable, authenticated, and configured correctly, but simply
**does not support image generation at all**, is excluded *before*
any request is attempted at all (Section 9, point 6/7) — this is a
capability mismatch, not a `ProviderUnavailableError` from a real call,
and is reported by `ImageGenerationService` as a plain, non-exception
failure result, never even reaching `ProviderRequestExecutor`. This
keeps "provider doesn't support X" cleanly distinct from "provider
tried and failed," which the fallback-eligibility table above would
otherwise conflate if capability filtering were left to the executor
alone for the *initial* provider.

---

## 15. Configuration

Two small, additive changes, following `content_generation:`'s exact
precedent (EP-082):

```yaml
image_generation:
  # EP-083 Image Generation Provider Integration. Additive namespace;
  # does not alter 'ai:', 'providers:', or 'content_generation:'
  # semantics. Governs standalone image-generation requests only.
  enabled: false
  fallback_enabled: false
```

And, inside the existing `providers.gemini` block only (the one
concrete provider this design recommends implementing — Owner
Decision 2):

```yaml
  gemini:
    ...
    # EP-083. The image-capable Gemini model identifier. Absent/empty
    # means this provider does not support image generation
    # (supports_image_generation() returns False). Distinct from
    # 'model' above, which remains the text model EP-082 already uses.
    # image_model: "gemini-3-flash-image"
```

No `default_temperature`-equivalent is proposed for images (no
common, cross-provider "creativity" dial for image generation is
established by this discovery; a future EP can add one additively if
a real need emerges). `enabled`/`fallback_enabled` follow
`content_generation:`'s exact naming and off-by-default convention.

---

## 16. Security / Safety

- API keys: reuses `providers.gemini.api_key` unchanged; no new
  secret introduced or logged (identical to EP-082's own posture).
- Generated image bytes are never logged (mirrors "never log secrets/
  full responses" precedent); only provider name, model, and
  exception class appear in any log line, matching
  `ProviderRequestExecutor`'s existing redaction discipline.
- No new network/filesystem access beyond the same already-configured,
  already-network-capable `GeminiProvider` HTTP client.
- No content-policy/moderation layer is introduced by EP-083 — a
  provider that rejects a prompt for its own content-policy reasons
  surfaces that as whatever `ProviderError` its own response mapping
  already produces (e.g. `ProviderConfigurationError` for a 4xx
  content-policy rejection, consistent with how `GeminiProvider`
  already classifies non-2xx statuses); EP-083 adds no separate
  moderation/filtering system of its own.

---

## 17. CLI Scope

Out of scope, explicitly. No backlog evidence requires a CLI/
CommandRouter namespace for EP-083, and no EP-092 functionality
(irrelevant here regardless, given Section 2's correction) is
introduced. `ImageGenerationService` is an internal, injectable
component only, exactly mirroring EP-082's own CLI deferral and
Owner Decision precedent.

---

## 18. Testing Strategy

`tests/EP083/`, following the exact `tests/EP082/` convention
(single `NAME = "EP083"` suite, `BaseTest`/`TestRegistry`, fakes
mirroring `_FakeAIProvider`/`_FakeProviderManager`). Coverage:

- `AIProvider.supports_image_generation()` default `False`; overridden
  `True` only when a fake/real provider is configured with an image
  model.
- `ProviderRequestExecutor.execute_image()`: primary success, fallback
  disabled, fallback-eligible retry (skipping non-capable candidates),
  non-eligible immediate failure, exhausted fallback — mirroring
  `tests/EP082`'s own `_test_executor_*` structure exactly, so the
  two suites are directly comparable.
- `execute()` (existing, text) **regression**: `tests/EP082`'s full
  suite must still pass unmodified after the `_run()` factoring —
  this is a required acceptance gate for STEP 2, exactly as EP-082's
  own extraction required `tests/EP069`/`EP069_2`/`EP069_3` to keep
  passing.
- `ImageGenerationService`: success path, disabled config, no provider
  selected, current provider lacks capability (fails fast, zero
  executor/provider calls), fallback success, never touches
  conversation/context (structural introspection test, mirroring
  EP-082's own `_test_service_never_receives_conversation_or_
  context_dependency`).
- `GeminiProvider.generate_image()`: additive-parameter/contract
  tests via mocked HTTP (`unittest.mock.patch`, the precedent
  `tests/EP082` already established for `requests.post`/
  `requests.request`), covering successful image extraction, a
  malformed/empty-image response, and `supports_image_generation()`
  toggling correctly based on `image_model` presence.
- `ClaudeProvider`/placeholder providers: `supports_image_generation()`
  returns `False` and `generate_image()` raises
  `ProviderUnavailableError` — regression-style assertions confirming
  the base-class default is never silently overridden.

---

## 19. Parallel Development Risks

- `src/bootstrap.py` — every skill/service-adding EP touches this;
  EP-084–EP-087 sibling work, if concurrent, will also add
  registration lines here — additive, low structural conflict risk,
  same as EP-082's own note.
- `config/config.yaml` — new `image_generation:` top-level key plus
  one new field inside the existing `providers.gemini` block; low
  risk, same additive pattern as `content_generation:`.
- `src/core/ai/provider.py`, `provider_request_executor.py` — touched
  by this EP's additive extensions; if EP-069.4's real
  `src/core/capability/` package is synced into this working copy
  before STEP 2 begins, `supports_image_generation()`'s eventual
  migration onto that package (Section 6, Owner Decision 3) becomes
  the coordination point to watch, not a conflict in the meantime.
- `src/core/ai/providers/gemini_provider.py` — touched by this EP's
  concrete implementation (Owner Decision 2); no other currently
  known EP touches this file.

---

## 20. Future EP Boundaries

- EP-084 (Audio & Speech), EP-085 (Video), EP-086 (Presentation) are
  expected to follow the same pattern this design establishes for
  images (their own additive `AIProvider` method, their own request/
  result contracts, their own `execute_<modality>()` addition to
  `ProviderRequestExecutor`'s shared `_run()`) — not to reuse
  `ImageGenerationRequest`/`ImageGenerationResult` directly, since
  audio/video/presentation payloads are not images.
- EP-087 (Content Production Pipeline) is the expected future
  consumer that composes `TextGenerationService`,
  `ImageGenerationService`, and its siblings together — out of scope
  here, noted only.
- EP-092 (Personal Data Collection Framework) has no architectural
  relationship to EP-083 at all (Section 2) — no boundary needs
  defining beyond this correction.

---

## 21. Owner Decisions

```text
OWNER DECISION REQUIRED

Decision: How does ProviderRequestExecutor gain image-generation
execution without a second retry/fallback implementation or a
breaking change to its existing, audited execute()?

Option A (recommended): Factor execute()'s existing retry/fallback
control flow into a new private _run() helper. execute()'s own
public signature and behavior are completely unchanged (calls _run()
with an .ask()-wrapping request_fn and capability_filter=None). Add a
new, additive public execute_image() that calls the same _run() with
a .generate_image()-wrapping request_fn and a capability filter.

Option B: Leave execute() untouched and give ImageGenerationService
its own, separate, image-specific retry/fallback loop.

Reason: Option A produces exactly one retry/fallback implementation
in the repository, matching this project's Rule 3/Rule 4 and EP-082's
own precedent. Option B is simpler to review in isolation but
directly duplicates EP-069/EP-082's fallback logic -- exactly what
this task's own instructions forbid.

Impact: Option A requires an internal (non-public-signature-changing)
refactor of a shipped, audited file (provider_request_executor.py)
and requires STEP 2 to prove tests/EP082's full suite still passes
unmodified afterward -- a real but bounded regression-testing
obligation, identical in kind to what EP-082's own STEP 2 already
did to ai_service.py. Option B has zero refactor risk to
provider_request_executor.py but leaves two fallback
implementations in the codebase permanently.
```

```text
OWNER DECISION REQUIRED

Decision: Does STEP 2 ship a real, working image-generation provider
now, or architecture only (all providers reporting
supports_image_generation() = False)?

Option A (recommended): Implement GeminiProvider.generate_image()
for real, calling the same generateContent endpoint
GeminiProvider.ask() already uses, with an image-capable model
(configured via the new providers.gemini.image_model key) and
extended response parsing to extract inline image parts. This is the
only currently-registered provider whose underlying API family
genuinely supports image generation (confirmed by web research during
this STEP 1, not assumed) -- Anthropic's Claude API has no public
image-generation endpoint.

Option B: Ship only the AIProvider/ProviderRequestExecutor/
ImageGenerationService architecture, with zero concrete providers
capable of image generation, deferring the first real integration to
a narrowly-scoped EP-083.1 (mirroring how EP-069 was split into
EP-069.1-.4).

Reason: EP-082's own precedent integrated real, already-network-capable
providers additively rather than shipping architecture-only. Option A
follows that precedent and delivers a genuinely usable capability at
the end of STEP 2, at the cost of STEP 2 needing to verify Gemini's
exact current image-generation request/response schema against
Google's live API documentation at implementation time (this design
confirms the endpoint and general shape, not the exact JSON field
names for the image-output request, since that is an implementation
detail, not an architectural one).

Impact: Option A means STEP 2 includes one real, external
API-integration risk (schema drift/verification) in addition to the
architecture work. Option B is architecturally complete but produces
no usable image-generation capability until a future sub-package
ships -- mirroring EP-069's own multi-step delivery, which this
repository's conventions already accept as normal.
```

```text
OWNER DECISION REQUIRED

Decision: How does EP-083 handle the discovery that EP-069.4's
documented "Unified Capability Abstraction" (src/core/capability/)
does not exist in the actual repository made available for this
STEP 1, despite being described as COMPLETE in
docs/BACKLOG.md/CHANGELOG.md/RELEASE_NOTES.md?

Option A (recommended): EP-083 defines its own minimal,
self-contained AIProvider.supports_image_generation() method now
(Section 8.1), explicitly documented as provisional pending
EP-069.4's real package becoming available, at which point a small,
separate reconciliation step (not part of EP-083) migrates it.

Option B: Pause EP-083's capability-related design until EP-069.4's
actual code is synced into this working copy, so EP-083 can build on
the real abstraction directly instead of a provisional stand-in.

Reason: Option A unblocks EP-083 today and adds a single boolean
method that is trivially reconcilable later; Option B blocks all of
Phase C indefinitely on a documentation/code synchronization gap this
STEP 1 did not create and cannot resolve on its own.

Impact: Option A carries a small, explicitly-flagged technical-debt
item (one method that may be renamed/relocated once EP-069.4's real
package exists) in exchange for unblocking EP-083 now. Option B
carries no such debt but stops this EP entirely pending an
out-of-band repository sync.
```

---

## 22. Acceptance Criteria

STEP 2 is complete when:

- `AIProvider.supports_image_generation()` and `generate_image()`
  exist with the base-class defaults specified in Section 8.1, and
  every existing provider (`ClaudeProvider`, the three
  `ConfigDrivenProvider` placeholders) remains valid without
  modification beyond inheriting these defaults.
- `ProviderRequestExecutor.execute()`'s existing public signature,
  behavior, and every log line are provably unchanged (regression:
  `tests/EP082` 69/69, `tests/EP069` 68/68 unmodified pass).
- `ProviderRequestExecutor.execute_image()` exists, sharing the same
  `_run()` control flow, with capability-aware fallback filtering.
- `ImageGenerationService` exists, is non-conversational (structural
  test per Section 18), and is wired in `src/bootstrap.py` with no
  CommandRouter registration.
- If Owner Decision 2 = Option A: `GeminiProvider.generate_image()`
  performs a real, successfully-mocked-in-tests HTTP call and extracts
  at least one `GeneratedImage` from a representative response.
- `image_generation:` config namespace and `providers.gemini.
  image_model` exist, additive, with `ai:`/`providers:`/
  `content_generation:` semantics unchanged.
- `tests/EP083/` exists and passes in full.
- No CLI/CommandRouter functionality was added.
- No Agent Harness, workflow-gate, or checkpoint functionality was
  introduced anywhere.

---

## 23. STEP 2 Implementation Contract

**Create:**
- `src/services/image_generation_service.py` — `ImageGenerationService`,
  `ImageGenerationRequest` re-export or local definition (placement
  detail for STEP 2), service-level result type.
- `tests/EP083/__init__.py`, `tests/EP083/test_image_generation_
  provider_integration.py`.

**Modify (additive only, exact scope per Owner Decisions above):**
- `src/core/ai/provider.py` — add `ImageGenerationRequest`,
  `GeneratedImage`, `ImageGenerationResult` dataclasses;
  `AIProvider.supports_image_generation()` and `generate_image()`
  with base-class defaults.
- `src/core/ai/provider_request_executor.py` — factor `execute()`'s
  body into a private `_run()`; add `execute_image()` (Owner Decision
  1). `execute()`'s public signature and `ProviderRequestOutcome`
  contract do not change.
- `src/core/ai/providers/gemini_provider.py` — add `image_model`
  constructor parameter, `supports_image_generation()` override,
  `generate_image()` implementation, extended response parsing for
  inline image parts (Owner Decision 2, Option A only).
- `src/bootstrap.py` — construct and wire `ImageGenerationService`
  using the same shared `ProviderRequestExecutor` instance EP-082
  already wired for `ai_service`/`text_generation_service`; add
  `image_model` to `ProviderFactory`'s Gemini construction; parse
  `image_generation.*` config (mirroring `_parse_content_generation_
  default_temperature()`'s composition-root pattern). No
  CommandRouter change.
- `config/config.yaml` — additive `image_generation:` section;
  additive `providers.gemini.image_model` key.

**Do not modify:** `src/core/ai/provider_manager.py`,
`src/core/ai/provider_registry.py`, `src/core/ai/provider_factory.py`
(beyond the one additive Gemini constructor argument),
`src/core/ai/claude_provider.py`, `src/services/ai_service.py`,
`src/services/text_generation_service.py`, any `tests/EP069*` or
`tests/EP082` file, `src/core/command_router.py`.

**Dependency direction:** unchanged from Section 8's diagram —
`ImageGenerationService` depends downward on `ProviderRequestExecutor`
and `ProviderManager`; nothing depends upward on
`ImageGenerationService` except a future EP-087 (not implemented now).

**Backward-compatibility requirement:** `tests/EP082`'s full suite
(69/69) and `tests/EP069`'s full suite (68/68) must pass unmodified
after STEP 2; this is the acceptance gate for the `_run()` extraction,
identical in spirit to EP-082's own STEP 2/3 obligation toward
`tests/EP069`/`EP069_2`/`EP069_3`.

**Prohibited scope:** anything listed in Section 4 (Non-Scope);
implementing EP-069.4's real capability package (Owner Decision 3
explicitly defers this); any CLI surface; any change to
`ProviderManager`'s public method set.
