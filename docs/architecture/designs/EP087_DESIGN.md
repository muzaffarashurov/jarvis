# EP-087 — Content Production Pipeline

**Status: DESIGN PROPOSED — OWNER DECISION REQUIRED**

## 1. Title

EP-087 — Content Production Pipeline.

## 2. Objective

Design the orchestration/composition layer that combines the five
already-built, independent AI content-generation capabilities (text,
image, audio/speech, video, presentation content) into a single,
coherent production request — without duplicating any of their
existing provider-selection, capability-checking, retry/fallback, or
generation logic.

## 3. Relationship to EP-086 (and EP-076) — Scope Boundary, Confirmed

This design was restarted after an initial, incorrect attempt
conflated EP-087 with `.pptx` rendering. The repository's own
authoritative scope, re-verified directly against `BACKLOG.md` in
this session, is unambiguous and is treated as final for this design:

```
- **EP-087 — Content Production Pipeline** (MEDIUM). Combine the
  above, through the EP-069 provider abstraction, into text/image/
  audio/video/presentation/combined multimedia output.
```

The three-way boundary is:

- **EP-086** generates structured presentation **content**
  (`GeneratedPresentation`: a title and slides) — already complete,
  unmodified by this design.
- **EP-076 — Universal Document Intelligence Engine** (not yet
  built) owns format-specific document/artifact **creation**,
  including turning `GeneratedPresentation` into an actual `.pptx`,
  through its own pluggable per-format backends. `BACKLOG.md`
  explicitly states this engine exists precisely so that no
  format gets its own dedicated "engine" EP — confirming a
  PPTX-rendering EP-087 would have directly contradicted the
  repository's own stated architecture philosophy.
- **EP-087** (this design) orchestrates/composes the five existing
  *content-generation* capabilities (EP-082/083/084/085/086) into a
  single request — it does not create, render, or assemble any
  artifact itself, and does not touch EP-076's territory at all.

This design does not implement, redesign, or modify EP-076 or EP-086
in any way — both are out of scope and both are treated as fixed,
external dependencies to be called through their existing, unmodified
service interfaces.

## 4. Current Repository Findings (Phase 1 investigation)

Verified directly against the current source tree, not assumed:

- **The five existing services are structurally similar but NOT
  interface-uniform.** `ImageGenerationService.generate(request:
  ImageGenerationRequest)`, `AudioGenerationService.generate(request:
  SpeechGenerationRequest)`, `VideoGenerationService.generate(request:
  VideoGenerationRequest)`, and `PresentationGenerationService.
  generate(request: PresentationGenerationRequest)` all take one
  dataclass argument and return one dataclass result. **`Text
  GenerationService.generate()` does not** — it takes plain keyword
  arguments (`prompt: str, *, max_tokens: int | None = None,
  temperature: float | None = None`), a real, pre-existing (EP-082)
  inconsistency this design must account for rather than paper over.
  Per the explicit instruction not to modify any existing service,
  this design does not change `TextGenerationService`'s signature —
  EP-087's own step-dispatch logic tolerates this heterogeneity
  directly (Section 9).
- **Every existing service already owns its own complete
  enabled/capability-check/fallback lifecycle internally** and never
  raises to its caller — each `generate()` call returns a result
  object with `success: bool`/`error: str` regardless of outcome
  (confirmed by direct reading of all five `generate()` method
  bodies). This means EP-087 needs **no** capability-filtering,
  provider-selection, or retry logic of its own: calling each
  service's `generate()` once already gets all of that for free.
  EP-069.4's Unified Capability Abstraction (`src/core/capability/`)
  is confirmed, again, to be unrelated (external/internal tool
  cataloging) and is not touched.
- **The pre-existing `WorkflowEngine`/`WorkflowDefinition`
  infrastructure (`src/core/workflow_engine/`, EP-033) is NOT a fit
  for this EP and is not reused.** Its `WorkflowRequestStep` carries a
  single free-text `request: str` string, interpreted by `Plan
  ExecutionEngine.execute_request()` — an LLM-driven natural-language
  task planner that dispatches to `CommandRouter`-registered
  capabilities. None of the five content-generation services is
  registered on `CommandRouter` (every one of EP-082-086's own
  designs explicitly deferred that), so reusing `WorkflowEngine` here
  would force premature, out-of-scope CLI/CommandRouter integration
  for all five services merely to make them reachable from a
  natural-language planner step — a materially larger, riskier change
  than this EP's actual scope justifies, and not something the
  Owner's brief for EP-087 asked for. This is a genuine architectural
  finding, not an assumption: `WorkflowRequestStep`'s own module
  docstring was read directly to confirm this shape.
- **No existing multimedia/content-composition abstraction exists
  anywhere in the repository** — confirmed by a targeted search
  (`grep -rli "multimedia\|content.*pipeline\|combined.*output"` across
  `src/`) turning up nothing relevant. EP-087 is new work, not a
  rename of something that already exists.
- **Configuration/bootstrap/testing conventions** are the same,
  consistent pattern established by EP-082-086: an additive top-level
  config namespace, a `Bootstrap`-wired standalone service sharing the
  existing `ai_provider_manager`/`ai_request_executor` instances
  (though, per the finding above, EP-087's own service does *not*
  need direct access to the executor/manager at all — it only needs
  the five *services*, which already encapsulate that), no
  CommandRouter registration, and a `tests/EP087/` suite following the
  same `@TestRegistry.register`/`BaseTest` convention every prior EP
  used.

## 5. Problem Statement

A caller who wants, say, "a tagline, a matching image, and narrated
audio for a product announcement" today must call three unrelated
services separately, handle three independent success/failure
outcomes themselves, and has no single place to express "these three
requests belong to one production job." EP-087 exists to provide that
single entry point, without re-implementing anything the five
services and their shared executor already do correctly.

## 6. Scope

- A new, standalone `ContentProductionPipelineService` (or an Owner-
  approved equivalent name) that accepts a single request describing
  which of the five modalities to generate and with what per-modality
  parameters, and returns one aggregate result describing each
  requested modality's independent outcome.
- Purely sequential execution in v1 (Section 12/17), in a fixed,
  documented order.
- No built-in cross-step data substitution/templating in v1 (Owner
  Decision D2, Section 25) — each step's request is fully formed by
  the caller before the pipeline runs; the pipeline does not modify
  or interpolate any request.
- At most one step per modality per pipeline request in v1 (Owner
  Decision D1).

## 7. Explicit Non-Goals

- **No artifact rendering of any kind** — no `.pptx`, no image files
  written to disk, no video downloads, no document assembly. That is
  EP-076's territory.
- No modification to `TextGenerationService`, `ImageGenerationService`,
  `AudioGenerationService`, `VideoGenerationService`,
  `PresentationGenerationService`, `ProviderManager`,
  `ProviderRequestExecutor`, or any `AIProvider`/`GeminiProvider`
  method. Every one of the five services is called exactly as it
  exists today, through its existing public `generate()` method.
- No new provider-selection, fallback, or retry mechanism — the five
  services already own this completely; EP-087 adds nothing here.
- No reuse of, or modification to, `WorkflowEngine`/
  `WorkflowDefinition` (Section 4).
- No CLI/CommandRouter exposure (matching every prior modality's own
  deferral).
- No cross-step dependency/templating engine in v1 (deferred, Owner
  Decision D2).
- No parallel/concurrent execution in v1 (deferred, Section 17).
- No cancellation mechanism in v1 (Section 17 — no evidence any
  existing service supports mid-call cancellation either).
- No EP-069.4 interaction of any kind.
- No configuration for values that should remain deterministic
  constants (Section 20).

## 8. Existing Architecture

```
TextGenerationService.generate(prompt, *, max_tokens=None, temperature=None) -> TextGenerationResult
ImageGenerationService.generate(request: ImageGenerationRequest) -> ImageGenerationResult
AudioGenerationService.generate(request: SpeechGenerationRequest) -> SpeechGenerationResult
VideoGenerationService.generate(request: VideoGenerationRequest) -> VideoGenerationResult
PresentationGenerationService.generate(request: PresentationGenerationRequest) -> PresentationGenerationResult
```

Each is independently wired in `Bootstrap._build_command_router()`
sharing one `ai_provider_manager`/`ai_request_executor` pair; each is
disabled by default via its own config namespace; none is registered
on `CommandRouter`.

## 9. Proposed Architecture

```
ContentProductionPipelineRequest
    |
    v
ContentProductionPipelineService.generate()
    |
    +-- (if text step requested)          -> TextGenerationService.generate(...)
    +-- (if image step requested)         -> ImageGenerationService.generate(...)
    +-- (if audio/speech step requested)  -> AudioGenerationService.generate(...)
    +-- (if video step requested)         -> VideoGenerationService.generate(...)
    +-- (if presentation step requested)  -> PresentationGenerationService.generate(...)
    |
    v
ContentProductionPipelineResult (one outcome per requested step)
```

`ContentProductionPipelineService` depends on the five existing
service instances directly (constructor-injected, mirroring how every
existing service is already constructed and stored on `Bootstrap`) —
**not** on `ai_provider_manager`/`ai_request_executor` directly, and
**not** on `ProviderManager`/`ProviderRequestExecutor` at all. This is
a deliberate, evidence-based architectural choice (Section 4): since
every existing service already fully encapsulates provider selection,
capability checking, and fallback, EP-087 reaching *around* them to
call the executor directly would be a real duplication risk (two
places deciding which provider to use); depending on the services
themselves is the only way to guarantee zero duplication.

## 10. Component Responsibilities

- **`ContentProductionPipelineService`**: the sole new component.
  Owns request validation (Section 18), step ordering (Section 12),
  and result aggregation (Section 13). Owns nothing about *how* any
  individual modality is generated — it delegates every single
  generation call to the matching existing service unchanged.
- **The five existing services**: unchanged, called exactly as today.
- **`ProviderManager`/`ProviderRequestExecutor`**: unchanged, not
  directly touched by this EP at all — reached only transitively,
  through the five services.

## 11. Data Flow / Contracts

### NEW

```python
@dataclass(frozen=True)
class TextStepRequest:
    prompt: str
    max_tokens: int | None = None
    temperature: float | None = None

@dataclass(frozen=True)
class ContentProductionPipelineRequest:
    text: TextStepRequest | None = None
    image: ImageGenerationRequest | None = None
    audio: SpeechGenerationRequest | None = None
    video: VideoGenerationRequest | None = None
    presentation: PresentationGenerationRequest | None = None
```

Rationale: rather than one generic "list of typed steps" collection
(which would need its own modality-tag enum plus a runtime type check
per step, and would still have to special-case text's non-dataclass
signature underneath), the request is a single dataclass with one
optional field per modality — direct, statically typed, and trivially
extensible (a sixth modality adds one more optional field, no
enum/registry changes). `TextStepRequest` exists solely to give
text generation the same "one dataclass per step" shape as the other
four, without changing `TextGenerationService.generate()`'s own
signature — `ContentProductionPipelineService` unpacks it into the
matching keyword arguments internally.

Every field defaults to `None` ("this modality was not requested").
At least one field must be non-`None` (Section 18 validation).

```python
@dataclass(frozen=True)
class PipelineStepResult:
    modality: str  # "text" | "image" | "audio" | "video" | "presentation"
    success: bool
    error: str
    # Exactly one of the following is populated, matching `modality`,
    # when `success` is True; all are None otherwise. Kept as separate
    # optional fields rather than `Any` so callers get static typing
    # for whichever modality they actually requested.
    text_result: TextGenerationResult | None = None
    image_result: ImageGenerationResult | None = None
    audio_result: SpeechGenerationResult | None = None
    video_result: VideoGenerationResult | None = None
    presentation_result: PresentationGenerationResult | None = None

@dataclass(frozen=True)
class ContentProductionPipelineResult:
    steps: tuple[PipelineStepResult, ...]
    success: bool
```

`ContentProductionPipelineResult.success` means **the pipeline itself
ran to completion with no internal/orchestration-level error** — it
is deliberately **not** "every requested step succeeded" (Owner
Decision D3 discusses the alternative). Each `PipelineStepResult`
carries its own independent `success`/`error`, exactly mirroring how
every existing service already reports outcomes; the pipeline does
not editorialize about whether a caller's goal was "good enough" with
some steps failed.

### MODIFIED

None. This is the first EP since EP-082 that requires zero changes to
`src/core/ai/provider.py`, `provider_request_executor.py`,
`provider_factory.py`, or any `GeminiProvider` file — because it does
not add a new AI-provider capability, it composes existing ones.

### EXISTING (fully reused, unmodified)

`TextGenerationService`, `ImageGenerationService`,
`AudioGenerationService`, `VideoGenerationService`,
`PresentationGenerationService`, and every type each already returns.

## 12. Execution Model — Sequential, Fixed Order

Steps execute **sequentially**, in a fixed, documented order: text,
then image, then audio, then video, then presentation. This order is
chosen because it is the platform's own founding chronological order
(EP-082 through EP-086) and because it places the fastest, cheapest
steps first and the slowest (video, potentially 10 minutes) last —
so a caller who only cares about the fast steps and doesn't request
video never pays video's cost, and a caller who requests everything
sees their fast results are not held up waiting behind a slow one
that comes later in the same call. No parallelism is introduced
(Section 17) — running independent HTTP calls concurrently would be a
real, if modest, new concurrency surface with no existing precedent
anywhere in this AI-provider subsystem (every one of EP-082-086's own
audits confirmed their single provider call is safe precisely because
it is not run concurrently with itself), and no evidence in the
Owner's brief demands parallel execution for v1.

## 13. Partial Failure Handling

Steps are independent in v1 (no built-in dependency wiring, Owner
Decision D2) — a failure in one step (e.g. image generation disabled)
does not prevent any other *independently requested* step from
running. Each step's `PipelineStepResult` reports its own outcome.
`ContentProductionPipelineResult.success` is `False` only if the
pipeline itself hit an internal error before completing its intended
steps (e.g. an unexpected exception escaping a step dispatch — see
Section 19) — never merely because one requested modality's own
`generate()` call reported `success=False`, since that is itself a
normal, already-handled outcome for every existing service, not a
pipeline-level failure.

## 14. Provider Abstraction Usage (EP-069)

EP-087 uses the EP-069 provider abstraction **only transitively**,
through the five existing services — it holds no direct reference to
`ProviderManager` or `ProviderRequestExecutor` (Section 9). This is
the cleanest possible answer to "how does EP-087 use the existing
provider abstraction without duplicating provider-selection logic":
by not touching it directly at all.

## 15. Capability Discovery / Filtering

Not EP-087's concern (Section 4) — each service already performs its
own `supports_<modality>_generation()` check before ever reaching the
executor. EP-087 adds no capability-checking logic of its own.

## 16. Limits

- **At most one step per modality per request** (Owner Decision D1) —
  v1 does not support, e.g., requesting two images in one pipeline
  call. A caller wanting multiple instances of the same modality
  calls the pipeline (or the underlying service) more than once.
- **At least one step must be requested** — an all-`None` request is
  rejected (Section 18) as a caller error, not run as a silent no-op.
- No new numeric limit is introduced for any individual modality's own
  parameters (e.g. `slide_count`, `duration_seconds`) — those remain
  entirely each modality's own existing, already-enforced concern
  (EP-086's 30-slide bound, etc.); EP-087 does not re-validate or
  duplicate any of them.

## 17. Cancellation / Timeouts / Concurrency — Documented as a Risk, Not Solved

No new cancellation or pipeline-level timeout mechanism is introduced.
This is an explicit, evidence-based non-goal (Section 7), not an
oversight: no existing service supports mid-call cancellation, and
inventing one here — for a feature no existing modality has — would
be scope creep with no concrete requirement behind it. The genuine
consequence, documented here as a risk rather than silently accepted
(Section 26): a pipeline request that includes the video step can
take up to `video_generation.max_wait_seconds` (600s by default) on
top of every other requested step's own latency, entirely blocking
the calling thread for the whole duration — the same blocking-call
trade-off `VideoGenerationService` itself already accepted (EP-085
Section 21), now simply inherited by whatever calls the pipeline. No
new synchronization/thread-safety mechanism is needed: each service
call remains a single, independent, sequential call with no shared
mutable state between steps (each service already owns none, per
every one of EP-082-086's own concurrency audits).

## 18. Validation

- Reject a request with zero non-`None` step fields
  (`ContentProductionPipelineError`-style message, or reuse an
  existing convention — see Section 19) before calling any service.
- Perform no other new validation — each individual step's own
  request dataclass validates itself exactly as it already does
  inside its own service/provider (e.g. `PresentationGenerationRequest`'s
  `slide_count` bound is still enforced exactly where it is today,
  inside `GeminiProvider.generate_presentation()`; EP-087 does not
  re-check it).

## 19. Error Handling

No new `ProviderError` subtype is needed, since EP-087 never talks to
a provider directly. Two failure categories exist:

- **Per-step failure** (a service's own `generate()` returned
  `success=False`): captured verbatim into that step's
  `PipelineStepResult` — not an exception, not a pipeline-level error.
- **Pipeline-level/internal failure** (something EP-087's own
  dispatch logic gets wrong — e.g. an unexpected exception from a
  service call that isn't the service's own normal `success=False`
  contract, which every existing service's own tests already confirm
  should not happen but which defensive code should not assume):
  caught per-step, converted into that step's own `PipelineStepResult
  (success=False, error=...)` rather than allowed to abort the whole
  pipeline and silently skip every subsequent step — one step's
  unexpected internal error should not prevent an unrelated, later
  step from still being attempted.

## 20. Security / Resource Safety

No new attack surface: EP-087 never touches a filesystem path, a URI,
a binary payload, or user-controlled configuration value beyond what
each existing service/request already validates. Prompt/content
values are never logged by EP-087 itself — it delegates every actual
generation call (and therefore every logging decision about that
call's content) to the existing, already-audited service.

## 21. Configuration

**None is proposed.** Per Section 11 of the STEP 1 brief ("avoid
configuration for values that should remain deterministic
constants"): the fixed step order (Section 12), the "at most one step
per modality" limit (Section 16), and the "reject empty request"
validation (Section 18) are all deterministic architectural constants
with no plausible reason to be tunable per-deployment — this
repository's own established convention only introduces a config
namespace for actually-variable operational knobs (enabled flags,
model names, timeouts), none of which this EP needs, since it
introduces no provider call and no timeout of its own. If STEP 2
discovers a genuine need (e.g. an `enabled` flag matching every prior
service's own precedent, for consistency), that is a small, easily
justified addition at that time — not assumed here without evidence.

## 22. Bootstrap / Service Integration

`ContentProductionPipelineService` would be constructed in
`Bootstrap._build_command_router()` (mirroring every prior service's
placement) with the five existing service instances passed in
directly — no new shared state, no new executor/manager reference.
No `CommandRouter` registration (Section 7).

## 23. Dependency Analysis

No new external dependency of any kind — this EP is pure composition
over existing, already-dependency-satisfied services.

## 24. Testing Strategy (for STEP 2)

Mirrors the established `tests/EP0NN/` convention (`@TestRegistry.
register`, `BaseTest`), with fakes standing in for the five services
(not for `ProviderManager`/`GeminiProvider`, since EP-087 never
touches those layers directly — a cleaner, shallower fake surface
than any prior EP needed):

- **Contract tests**: `ContentProductionPipelineRequest`/
  `PipelineStepResult`/`ContentProductionPipelineResult` construction/
  immutability; empty-request rejection.
- **Service tests**: single-modality request calls exactly that one
  service and none of the other four; multi-modality request calls
  every requested service exactly once, in the documented order
  (text, image, audio, video, presentation) — verified via a fake
  service that records call order; a step's own `success=False`
  result is passed through verbatim into that step's
  `PipelineStepResult`, without the pipeline treating it as an
  exception; an unexpected exception raised by one fake service
  is caught and converted into that step's own failed
  `PipelineStepResult` without preventing a later, independent step
  from still running.
- **Ordering test**: explicitly assert step execution order is
  text → image → audio → video → presentation regardless of the
  order fields are set on the request object (dataclass field order
  must not silently become execution order by accident — the
  dispatch order must be hard-coded in the service, not derived from
  `dataclasses.fields()`).
- **Aggregate-result tests**: `ContentProductionPipelineResult.success`
  is `True` when every requested step completes (regardless of each
  step's own individual success/failure) and `False` only on a
  genuine internal/dispatch error.
- **Regression**: `tests/EP086`, `tests/EP085`, `tests/EP084`,
  `tests/EP083`, `tests/EP082`, `tests/EP069`, `tests/EP069_3`,
  `tests/EP069_4` must remain fully green and untouched — this EP
  changes none of their files.

Because EP-087 makes no HTTP calls, no polling, and no filesystem
access of its own, this is the first EP in the platform whose test
suite needs **no** `unittest.mock.patch` of `requests`/`time` at
all — every test can run against simple fake service objects.

## 25. Alternatives Considered

### Alternative A — Sequential, fixed-order composition (RECOMMENDED)

As designed above. **Advantages**: minimal, no new dependency, zero
duplication risk (never touches `ProviderManager`/executor directly),
trivially testable (pure fakes, no HTTP mocking), easy to extend
(one new optional field per future modality), directly matches the
Owner's brief's explicit "do not introduce unnecessary abstraction"
guidance. **Disadvantages**: no parallelism (a multi-step request
pays the sum of every requested step's latency, worst case ~10+
minutes if video is included); no cross-step data dependencies in v1
(a caller wanting "generate a tagline, then use it as the image
prompt" must currently do that themselves across two separate calls,
or the pipeline needs Owner Decision D2's opt-in extension later).

### Alternative B — Generic DAG/workflow-definition executor

Model the pipeline as a directed acyclic graph of typed steps with
data-flow edges (step B's request can reference step A's result),
executed via topological sort with independent branches run in
parallel — either by extending the existing `WorkflowEngine`
(Section 4) to support typed, non-natural-language steps, or by
building an entirely new, generic executor. **Advantages**: solves
cross-step dependencies and parallelism in one general mechanism;
extensible to arbitrarily complex future pipelines. **Disadvantages**:
significantly higher complexity (a topological sort, a dependency-
resolution/substitution engine, and genuine concurrency-safety
analysis this codebase's AI-provider layer has never needed before);
extending `WorkflowEngine` would mean either forcing CommandRouter
registration on all five services (a real, unplanned scope expansion
of EP-082-086 themselves) or building a second, parallel workflow
concept solely for this EP (the exact "second implementation of
existing functionality" this codebase's own conventions repeatedly
warn against); testing complexity is substantially higher (concurrent
execution, partial-graph-failure semantics); no concrete evidence in
`BACKLOG.md`, `EP086_DESIGN.md`, or the Owner's brief demonstrates
this complexity is actually needed for v1's stated combinations
("text/image/audio/video/presentation/combined multimedia output").
**Rejected for v1**, recorded here as the natural evolution path if a
future EP genuinely needs branching, parallelism, or in-pipeline data
dependencies — Alternative A's request/result shape does not preclude
adding this later (Owner Decision D2 discusses the minimal version of
this exact extension).

## 26. Risks and Mitigations

- **Risk**: a pipeline request including the video step can block its
  caller for up to ~10 minutes plus every other requested step's own
  latency. **Mitigation**: none introduced in v1 (Section 17) — this
  is the same, already-accepted trade-off `VideoGenerationService`
  itself carries; documented here so a future caller/consumer of
  EP-087 is not surprised by it.
- **Risk**: `TextGenerationService`'s non-dataclass `generate()`
  signature is a real, pre-existing interface inconsistency this EP
  must bridge (Section 4/11). **Mitigation**: `TextStepRequest`
  isolates this bridging to one small, well-documented unpacking step
  inside `ContentProductionPipelineService`, with zero change to
  `TextGenerationService` itself.
- **Risk**: a future EP-076 (document assembly) or a future caller
  might expect EP-087 to also hand back an assembled artifact.
  **Mitigation**: this design states the boundary explicitly and
  repeatedly (Sections 2, 3, 7) precisely to prevent that
  misunderstanding from recurring, the same way it recurred once
  already in this EP's own STEP 1 history.

## 27. Owner Decisions Required

- **D1 — Multi-instance-per-modality in v1.** Recommended: **no** —
  at most one step per modality per request (Section 16). Alternative:
  allow a list of steps per modality (e.g. two images). **Consequence**:
  the recommended option keeps `ContentProductionPipelineRequest` a
  flat, single-instance-per-field dataclass; the alternative would
  require each field to become a tuple/list and would meaningfully
  complicate the result-aggregation shape for comparatively little
  demonstrated value at this stage.
- **D2 — Cross-step data dependencies in v1.** Recommended: **none** —
  every step's request is fully caller-supplied; the pipeline performs
  no substitution/templating (Section 6/13/25). Alternative: a
  minimal, single-hop substitution (e.g. an optional placeholder token
  in a later step's text field, replaced with an earlier step's
  result at run time) — deferred, not rejected forever; Alternative
  A's request shape does not block adding this later. **Consequence**:
  the recommended option keeps v1 genuinely minimal and matches the
  explicit "do not introduce unnecessary abstraction" guidance; the
  alternative directly enables the most obviously useful combined
  workflow ("tagline then a matching image") but introduces a real,
  if small, new templating concept with its own edge cases (what
  happens if the referenced earlier step failed or was not requested).
- **D3 — Aggregate `success` semantics.** Recommended: `success` means
  "the pipeline completed its dispatch without an internal error",
  independent of each step's own success/failure (Section 11/13).
  Alternative: `success` means "every requested step individually
  succeeded". **Consequence**: the recommended option avoids the
  pipeline making a subjective judgment call about what counts as a
  "good enough" partial result, leaving that entirely to the caller
  inspecting `steps`; the alternative is simpler for a caller who only
  wants a single boolean but silently discards useful partial-success
  information a caller might actually want (e.g. "I got the text and
  audio, only the image failed").
- **D4 — Fixed step order.** Recommended: text, image, audio, video,
  presentation (Section 12), matching the platform's own founding
  order and putting the slowest step last. Alternative: any other
  fixed order, or an Owner-specified configurable order (rejected per
  Section 21's "no configuration for deterministic constants"
  reasoning, unless the Owner disagrees that this is a fully
  deterministic choice). **Consequence**: low — this is the one
  Owner Decision whose alternative selection would require no
  structural design change, only reordering the dispatch sequence.

## 28. STEP 2 Implementation Boundaries

STEP 2 MUST:

1. Resolve Owner Decisions D1-D4 before writing implementation code.
2. Implement `ContentProductionPipelineService` depending only on the
   five existing service instances — never `ProviderManager`/
   `ProviderRequestExecutor`/`AIProvider`/`GeminiProvider` directly.
3. Introduce zero changes to `TextGenerationService`,
   `ImageGenerationService`, `AudioGenerationService`,
   `VideoGenerationService`, `PresentationGenerationService`,
   `ProviderManager`, `ProviderRequestExecutor`, `AIProvider`, or any
   `GeminiProvider` file.
4. Introduce zero new configuration unless the Owner's D1-D4
   resolution or STEP 2's own investigation surfaces a genuine,
   justified need (Section 21).
5. Not implement Alternative B (Section 25) unless the Owner
   explicitly overrides D2 to require cross-step dependencies beyond
   the minimal single-hop substitution described there.
6. Not touch EP-076 or EP-086 in any way.

## 29. Acceptance Criteria

- `ContentProductionPipelineService.generate()` correctly dispatches
  to exactly the requested subset of the five services, in the fixed
  order (Section 12/24), and to none of the non-requested ones.
- Each step's independent outcome is preserved verbatim in the
  aggregate result; no step's failure prevents an independent,
  later-ordered step from still being attempted.
- Zero changes to any of the five existing services or to the shared
  provider/executor infrastructure.
- Full regression: `tests/EP082`-`tests/EP086`, `tests/EP069`,
  `tests/EP069_3`, `tests/EP069_4` remain green and unmodified.
- No new dependency, no new HTTP/filesystem access, no new
  configuration beyond what STEP 2 genuinely justifies.

## 30. Final Recommendation

The scope is now confirmed correctly (Content Production Pipeline,
not a PPTX renderer) and resolves cleanly to a minimal, low-risk
composition layer over five already-complete, well-tested services —
requiring zero changes to any of them or to the shared provider
architecture. Four small, genuinely open choices (D1-D4) remain for
the Owner; none of them changes the fundamental architecture.

```
DESIGN PROPOSED — OWNER DECISION REQUIRED
```
