# JARVIS — Decision Required: Architecture Resolution

**Type:** Read-only architecture decision analysis, resolving the `DECISION REQUIRED` items from `Jarvis Master Roadmap Reconstruction`
**Nature:** Analysis only. No repository file, test, configuration, roadmap, backlog, or Git state was created, modified, or deleted.

**Epistemic labels used throughout:**
- **VERIFIED FACT** — read directly from source code, tests, or design/audit documents this session.
- **CODE-LEVEL OBSERVATION** — a specific implementation detail read directly from a file, offered as raw evidence.
- **ARCHITECTURAL INFERENCE** — a conclusion drawn from combining multiple verified facts.
- **RECOMMENDATION** — this analysis's own architectural judgment, not binding.
- **OWNER DECISION** — a choice this analysis cannot and does not make.

---

## DECISION 1 — Universal External Data Architecture

**Investigation performed this session:** read `src/core/personal_data/personal_data_source.py` (the `PersonalDataSource` ABC) in full, and re-read `EP092_DESIGN.md` §11 "FUTURE INTEGRATION" and §12 "Architectural Design" directly.

**VERIFIED FACT:** `PersonalDataSource` is a three-member `ABC` — `source_id` (property), `category` (property), `collect() -> list[PersonalDataPoint]` (method) — with an explicit, in-docstring statement that a concrete source may be "a utility API client, a solar-inverter API client, a weather API client, **a manual/CSV-style source**." The contract makes no assumption about *how* `collect()` obtains its data: synchronous HTTP call, MQTT-queue drain, or a CSV read are all equally valid implementations of the identical method signature. `collect()` is documented to return newly observed points "since the last call," and to let genuine collection failures (network error, unreachable API, malformed response) propagate — the interface was evidently designed with live, fallible transports in mind, not only static file imports.

**VERIFIED FACT:** `PersonalDataManager` is the sole caller of `collect()`, and neither `PersonalDataRegistry` nor `PersonalDataProvider` has any dependency on a source's internal transport.

**CODE-LEVEL OBSERVATION:** EP‑092's own design doc explicitly names EP‑093, EP‑094, *and* EP‑097 (Weather) as each adding "one `PersonalDataSource` implementation" — i.e., the design already anticipated an external HTTP-API-backed source (weather) using the exact same interface a manual/CSV source uses.

**DECISION: A**

Model A (`ExternalDataSource` as a specialization of `PersonalDataSource`) is not merely the smallest option — it is what the existing interface was already built to accommodate. A live-transport source (MQTT-backed, webhook-backed, polling-REST-backed) is architecturally a **new concrete class implementing the existing `PersonalDataSource` ABC**, exactly as EP‑093/094/097 already do or are expected to do. No change to `PersonalDataManager`, `PersonalDataRegistry`, or `PersonalDataProvider` is required for this.

Model B is rejected: no evidence anywhere in the repository suggests a second consumer of raw external data exists or is planned (Automation Engine, for instance, has no code path today that would consume a live sensor value directly rather than through a stored/queried `PersonalDataPoint`) — building a sibling layer today would be **exactly** the "two competing abstraction systems" both idea files and `docs/BACKLOG.md`'s own architecture principles warn against, with zero current justification.

Model C is rejected as more granularity than evidence supports today: `PersonalDataSource.collect()` already *is* the normalization boundary (a concrete source returns a `PersonalDataPoint`, already normalized) — inserting a separate, named "Normalization" layer between Transport and Source would duplicate what `collect()`'s own implementation already does internally for every existing source.

**What should be an EP:** a small number of **concrete transport-capable `PersonalDataSource` implementations** (e.g., an MQTT-subscriber source, a webhook-receiver source, a generic-polling-REST source) — each following EP‑093/094's own precedent of "one source, one EP or one EP-slice," not a new abstraction layer.

**What should NOT be an EP:** any new registry/manager/provider parallel to EP‑092's — there is no evidence justifying one.

**What belongs to an EP‑092 extension vs. a new EP:** a **shared transport helper library** (e.g., a small MQTT-connect/subscribe utility, reusable across multiple future sources) is a legitimate small, additive extension of the `personal_data` package or a lightweight sibling utility module — it is infrastructure *inside* how a source is built, not a new architectural layer *above* `PersonalDataSource`. A genuinely new EP is justified only for the first concrete live-transport source itself (to establish the pattern), with subsequent sources treated as EP‑093/094-style small additions.

**What must wait for EP‑071 (Credentials/Secrets):** any source requiring an API key, OAuth token, or MQTT broker credential (Home Assistant, most smart-meter/inverter cloud APIs, any authenticated webhook). Unauthenticated or locally-trusted sources (a local MQTT broker with no auth, a local serial/USB device, Open‑Meteo's documented no-API-key-required non-commercial tier) do **not** need to wait — see Decision 3.

---

## DECISION 2 — Capability Governance Wiring

**Investigation performed this session:** grepped `src/core/command_router.py`, `src/core/tool/*.py`, `src/core/scheduler/*.py`, `src/core/execution/*.py`, and `src/core/ai/provider_request_executor.py` for any reference to `capability`, `policy`, `security_engine`, or `lifecycle`; also grepped `src/skills/capability_registry/*.py` (the EP‑056 skill most likely to reference the EP‑069.x stack) and `src/bootstrap.py`.

**VERIFIED FACT:** Zero matches were found in `command_router.py`, `tool/*.py`, `scheduler/*.py`, or `execution/*.py`. `bootstrap.py` constructs no `CapabilitySecurityEngine`, `PolicyEngine`, or `CapabilityLifecycleRegistry` instance anywhere (confirmed by a prior-session full-file search returning zero references). `src/skills/capability_registry/skill.py` (EP‑056, "reserved for the future Capability Registry" per its own docstring lineage) also contains **zero** references to any of EP‑069.5/.6/.7/070 — it composes only `PluginService` and `CommandRouter.module_names`, predating and unaware of the later EP‑069.x stack.

**CODE-LEVEL OBSERVATION:** `provider_request_executor.py` does contain the word "capability" repeatedly, but exclusively in the sense of `AIProvider.supports_image_generation()`-style per-provider modality flags — a completely different, unrelated concept from the `Capability` domain model (EP‑069.4). This is worth flagging explicitly because a naive text search could mistake this for wiring; it is not.

**ARCHITECTURAL INFERENCE:** No execution path in the current codebase — CLI dispatch, Tool Engine, Scheduler, or AI provider execution — consults capability authorization, security assessment, policy decision, or lifecycle status before acting. Every one of the ten sub-questions posed reduces to the same answer: **no**, none of them is currently true.

1. Is `CapabilityRegistry` connected to the other four packages? **No** — `capability_discovery`/`capability_security`/`capability_policy`/`capability_lifecycle` each independently import only `Capability` (the frozen dataclass), never `CapabilityRegistry`, by explicit Owner Decision in each of their own design docs (re-confirmed this session by reading each engine's module docstring: "never queries `CapabilityRegistry`," "zero dependency on `CapabilityRegistry`").
2. Does `bootstrap.py` connect them? **No.**
3. Does `CommandRouter` use them? **No.**
4. Does Tool Engine use them? **No.**
5. Does Scheduler/`ExecutionEngine` use them? **No.**
6. Does AI/provider execution use them? **No** (confirmed this session — `ProviderRequestExecutor`'s "capability" references are unrelated, as above).
7. Do security decisions affect actual execution? **No** — `CapabilitySecurityEngine`'s own docstring: "performs no assessment logic of its own... not wired into `src/bootstrap.py`, `config/config.yaml`, or any CLI surface."
8. Do policy decisions affect actual execution? **No** — `PolicyEngine`'s own docstring: "not connected to `ToolEngine`/`ToolExecutionProvider` or any execution path... performs no enforcement of any kind."
9. Does lifecycle state affect actual availability? **No** — `CapabilityLifecycleRegistry`'s own docstring: `disable()`/`revoke()` "never modify the live capability catalog in any way."
10. Are discovery results used by runtime components? **No** — `CapabilityDiscoveryEngine` is directly constructible and independently usable, per its own Owner Decision, with no bootstrap/config/CLI wiring of any kind.

**RECOMMENDATION — minimum viable integration architecture:**

```
Capability (registered in CapabilityRegistry)
        │
        ▼
CapabilityDiscoveryEngine.discover(task) → ranked candidates
        │
        ▼
CapabilitySecurityEngine.assess(candidate) → CapabilitySecurityAssessment
        │
        ▼
PolicyEngine.decide(capability, assessment) → PolicyDecision (OBSERVE..REQUIRE_APPROVAL)
        │
        ▼
[enforcement point, e.g. CommandRouter.dispatch() or a new ToolEngine gate]
        │
        ▼
CapabilityLifecycleRegistry.record_event(...) ← audit trail, both success and denial
```

This is a straight sequential wiring of the *existing* five packages in their own already-implied dependency order (`PolicyEngine.decide()` already accepts a `CapabilitySecurityAssessment` as an argument, per its own imports — confirmed this session in `capability_policy_engine.py`'s import list — meaning the Security→Policy handoff is already type-compatible and simply unused). No new authorization framework is proposed or needed.

1. **Where should capability authorization happen?** At the single existing chokepoint every interface already shares — `CommandRouter.dispatch()` — for CLI-reachable actions; a second, `ToolEngine`-level gate is needed only if/when Tool Engine gains parameterized handlers (still blocked by its own disclosed zero-argument-handler limitation, unrelated to this decision).
2. **Where should policy decisions happen?** Immediately after security assessment, before the actual action executes — i.e., inside the same enforcement point, not distributed across each skill/module individually (distributing it would risk exactly the inconsistent-enforcement problem EP‑068's disclosed logging gap already demonstrates for a different concern).
3. **Where should security validation happen?** Immediately before policy, using `CapabilitySecurityEngine.assess()` unchanged.
4. **Where should lifecycle state be checked?** As a fast pre-check before discovery/security run at all (a `DISABLED`/`REVOKED` capability should short-circuit before spending effort assessing it) — this is an ordering refinement the current five packages don't structurally prevent but also don't currently implement.
5. **Should enforcement be centralized or distributed?** **Centralized**, at `CommandRouter.dispatch()`, mirroring this project's own established pattern of one shared dispatch chokepoint for every interface.
6. **Which existing component should own orchestration?** None yet — this is precisely the gap. A new, thin orchestration point (not a new engine — a coordinator that calls the four existing engines in sequence) is required. **This coordinator, not any of the five underlying packages, is the actual missing piece.**
7. **How can this be done without a second authorization framework?** By building only the coordinator described above and wiring it into `CommandRouter.dispatch()` and `bootstrap.py` — zero new domain logic, since all decision logic already exists inside the four engines.
8. **Does EP‑070 need modification, or only integration?** **Integration only** — `PolicyEngine.decide()`'s signature already accepts what it needs; nothing in its implementation needs to change for it to be called from a real caller instead of zero callers.
9. **Does EP‑069.6 remain advisory, or become enforcement-capable?** It **remains advisory** in the sense that it still only *assesses* and returns a result — "enforcement" is what the *coordinator* does with that result (via `PolicyEngine`), not something `CapabilitySecurityEngine` itself needs to gain. No change to EP‑069.6's own code is implied.
10. **One EP or multiple?** **One EP** — this is a single, bounded integration task across five already-complete packages, not five separate integration efforts; splitting it would fragment a chain that only has value once fully connected end-to-end.

---

## DECISION 3 — EP‑071 Credentials/Secrets Dependency

**Investigation performed this session:** confirmed no credential-management package exists anywhere in `src/core/`; re-read `.env.example`'s role as cited in `EP093_DESIGN.md` evidence item E18 ("any real credential a concrete `PersonalDataSource` needs belongs in `.env`, read through `Config`, never hardcoded or placed in `config.yaml`").

**VERIFIED FACT:** The project already has a *minimal* credential convention today — `.env` + `Config` — used by existing AI providers (`ClaudeProvider`/`GeminiProvider` read API keys this way, per the established pattern EP‑093's own design doc cites as precedent). There is no dedicated secret-*management* subsystem (rotation, scoped access, audit-on-read, redaction-on-log beyond the disclosed-but-unresolved `CommandRouter` gap) — only this baseline convention.

1. **Does Universal External Data require EP‑071 first?** **No, not universally** — only for sources that are themselves authenticated. Unauthenticated/local sources do not.
2. **Can transport architecture be implemented before credentials?** **Yes** — Decision 1's Model A requires no credential-management subsystem to exist; the *first* concrete live-transport source EP should deliberately be chosen from the unauthenticated category (see below) precisely to avoid this dependency.
3. **Which external sources can work without EP‑071?** A local MQTT broker with no authentication configured; a local serial/USB sensor; Open‑Meteo's non-commercial tier (idea file #1 itself notes "API бесплатен... и не требует API key" — this is the one idea-file claim this session did not independently re-verify against Open‑Meteo's live documentation, so it is flagged `ARCHITECTURAL INFERENCE` from the idea file's own text, not independently confirmed).
4. **What should be explicitly blocked until EP‑071?** Any smart-meter/solar-inverter cloud vendor API (virtually all require an API key or OAuth), Home Assistant's own REST/WebSocket API (requires a long-lived access token), and any webhook source requiring signature verification with a shared secret.
5. **Should credentials be a generic infrastructure service?** **RECOMMENDATION:** yes, eventually — but the existing `.env`+`Config` convention is sufficient for a first authenticated source if EP‑071 is not yet ready; a dedicated EP‑071 becomes necessary once more than one or two authenticated sources exist and rotation/scoping/audit become real operational needs, not before.
6. **Should `PersonalDataSource` know anything about secrets?** **No** — per the existing convention (and consistent with every existing `*Provider` abstraction in the codebase, none of which embeds secret-handling logic itself, per this project's own established pattern), a concrete source reads its credential through `Config` exactly as `ClaudeProvider` does; `PersonalDataSource`'s own ABC contract needs no change.

**Dependency rule (supported by evidence):**

```
External Data Architecture (Decision 1, Model A)
        │
        ├── Unauthenticated/local sources ──▶ proceed immediately, no EP-071 dependency
        │
        └── Authenticated sources ──▶ EP-071 required first (or, as an interim,
                the existing .env/Config convention, accepted as a disclosed,
                temporary gap until EP-071 exists)
```

---

## DECISION 4 — Diagnostics vs. Observability

**Investigation performed this session:** re-confirmed `RuntimeService.status()` (EP‑059) as the only cross-subsystem status aggregation in the codebase; re-confirmed via prior-session search that no metrics/tracing library or `/metrics`-style endpoint exists; `loguru` is used pervasively for per-event logging (already implemented, unrelated to either gap).

1. **What diagnostic functionality already exists?** `RuntimeService.status()` (REST/Background-Worker/Scheduler/Shell presence, PID, uptime) and each subsystem's own `status()` action reachable via CLI (`worker status`, `runtime status`, etc.) — but nothing that traces a single capability/provider through multiple steps and reports *where* it failed.
2. **What logging already exists?** Pervasive `loguru`-based per-event logging, including the EP‑068-established sensitive-argument redaction convention (imperfectly applied — one disclosed HIGH finding remains open per EP‑051's audit).
3. **What telemetry already exists?** None (VERIFIED, per repeated searches this and the prior session).
4. **Is there already a partial observability system?** **No** — `RuntimeService.status()` is a diagnostics precedent (one-shot, human-triggered snapshot), not an observability precedent (continuous, time-series telemetry) — this session's code reading reconfirms the distinction drawn in the prior report rather than finding evidence to merge them.
5. **Should diagnostics be implemented before observability?** **RECOMMENDATION: yes** — Diagnostics can be built entirely on data structures that already exist (`RuntimeStatus`, `CapabilityLifecycleRecord`, `Capability` catalog membership) with zero new data-collection code, making it strictly cheaper to build first; Observability requires new instrumentation throughout the codebase and has no existing precedent to build from.
6. **Should they share a common health/status interface?** **RECOMMENDATION: yes, loosely** — Diagnostics' output shape (a per-subsystem PASS/WARN/FAIL line) is a natural superset of what `RuntimeStatus` already returns; a shared `HealthCheck`-style small interface both could implement is reasonable, but this is a design detail for a future STEP 1, not resolved here.
7. **Should they be separate EPs?** **RECOMMENDATION: yes, two EPs** — they have different implementation costs (near-zero new instrumentation for Diagnostics vs. pervasive new instrumentation for Observability) and different consumers (human operator vs. machine/future self-healing), which argues for independent scoping and independent STEP 1s rather than one combined EP that would force them to ship together.
8. **Could diagnostics simply consume observability data?** Only partially, and only once Observability exists — Diagnostics' first version does not need to wait for Observability, since most of what it reports (capability/provider/lifecycle/runtime status) already exists without any telemetry layer.
9. **Minimum useful architecture?** A thin `doctor` CLI module reading `RuntimeService.status()`, `CapabilityDiscoveryEngine`'s catalog, and `CapabilityLifecycleRegistry`'s records — zero new instrumentation required for v1.

**DECISION: Two EPs, Diagnostics first.**

---

## DECISION 5 — Resource & Cost Governance

**Investigation performed this session:** read `ProviderResponse` (EP‑015) in full — its only fields are `text: str`, `model: str`, `latency_ms: float`. No `usage`, `tokens_used`, `prompt_tokens`, `completion_tokens`, or `cost` field exists anywhere in `provider.py`. Re-confirmed `config/config.yaml` contains only static per-provider `max_tokens: 4096` values and no `budget`/`rate_limit`/`concurrency` keys anywhere in the file.

**VERIFIED FACT:** Jarvis currently has **zero actual usage tracking** at the provider-response level. `max_tokens` is a *request-shaping* parameter (an upper bound on how long a single generation may be), not a governance mechanism — it does not aggregate, does not persist, and does not inform any future decision. EP‑069.3's `relative_cost` is a **static, operator-declared** number used only to *order* fallback candidates; it is never compared against any actual measured spend, because — per EP‑069.3's own STEP 1 finding, re-confirmed this session — "real per-request usage could not inform that same request's own provider choice even if it existed, since usage is only known after a request has already been sent."

1. **What is missing?** Everything downstream of provider *selection*: no response includes token/cost usage at all, so there is nothing to aggregate into a budget even in principle without first changing `ProviderResponse`.
2. **What belongs inside `ProviderRequestExecutor`?** The natural place to *capture* usage, since it is already the single shared chokepoint for every content-generation call across all five modalities (text/image/audio/video/presentation) — but capturing requires `AIProvider.ask()`/`generate_image()`/etc. to first *return* usage data, which `ClaudeProvider`/`GeminiProvider` do not currently surface in `ProviderResponse` at all (an upstream, currently-unaddressed prerequisite this session's evidence newly surfaces).
3. **What belongs in Policy (EP‑070)?** The *decision* of what to do when a budget is exceeded (deny, warn, require approval) — natural fit for `PolicyEngine`'s existing `PolicyLevel` model, once wired (Decision 2).
4. **What belongs in Observability?** The *reporting/trending* of usage over time — a natural Observability metric once that layer exists (Decision 4), but not a prerequisite for basic budget *enforcement*.
5. **Global vs. provider-specific?** **RECOMMENDATION:** both are needed — a global daily/task ceiling and a per-provider ceiling (since EP‑069.3 already models providers as having different relative costs, a global-only budget would not reflect that a call to a more expensive provider should count more against the ceiling).
6. **Is a new EP justified?** **Yes** — this is not a small addition to any single existing file; it requires (a) a `ProviderResponse` schema change to surface usage (touching every provider), (b) new accounting state, and (c) a new enforcement decision point. This exceeds what "extend EP‑069.3" or "extend EP‑070" alone could cleanly absorb.
7. **Could this be an extension of EP‑069.3/EP‑070 instead?** **Partially, but not cleanly** — EP‑069.3 was explicitly, deliberately scoped *not* to include real usage tracking (its own STEP 1 finding, re-confirmed above); reopening that scope inside EP‑069.3 itself would contradict that EP's own, already-audited design decision. A new EP that *consumes* EP‑069.3's cost data and EP‑070's policy model (without modifying either) is the cleaner boundary.
8. **Is resource governance required before self-development/autonomous execution?** **Yes, as a safety precondition** (consistent with both idea files' and this project's own conservative posture), though it is a **softer** dependency than Decision 2's governance-wiring gap — self-development could theoretically proceed without it at higher risk, but should not by this project's own stated principles (least privilege, bounded risk).

**DECISION: New EP justified. Must first extend `ProviderResponse` (a small, additive schema change) before any accounting logic can exist — this is a previously-undisclosed prerequisite this session's evidence surfaces.**

---

## DECISION 6 — Time-Series Storage

**Investigation performed this session:** read `EP093_DESIGN.md`'s own evidence trail in full, including its documented ingestion pattern: `Job(command="scripts/collect_personal_data.py", schedule=Schedule(INTERVAL, ...))`, run via the Scheduler on a configured interval, wrapping calls to `PersonalDataService.collect(source_id)` for each registered source.

**VERIFIED FACT:** The actual, real ingestion pattern already established by EP‑093 is **interval-based batch collection** (a periodic scheduled job calling `collect()` once per interval across all sources), not continuous streaming. **CODE-LEVEL OBSERVATION:** `EP092_DESIGN.md` §11 confirms EP‑095/096 both "read through `PersonalDataManager.query()` / `PersonalDataService`, never through the persistence layer directly" — meaning both future EPs are already insulated from the storage backend choice by the existing `PersonalDataProvider` abstraction and can be implemented against whatever backend is active without knowing which one it is.

1. **Expected ingestion frequency?** Interval-based (hourly/daily-scale, matching the Scheduler-job precedent), not sub-second sensor streaming — at least for every source that exists today or is concretely planned (EP‑093/094/097, all manual/CSV or single-poll-per-interval in nature).
2. **What queries will EP‑095 (Visualization) need?** `UNKNOWN — requires EP‑095's own future STEP 1`; not specified anywhere in the repository today beyond "reads through `PersonalDataManager.query()`."
3. **What queries will EP‑096 (Forecast/Anomaly) need?** Same `UNKNOWN` — likely time-windowed aggregates (daily/weekly totals, moving averages) based on the idea file's own description, but not evidenced in the repository.
4. **Does `PersonalDataProvider` already permit storage replacement?** **Yes** (VERIFIED, per its own docstring: "a second implementation could be added later without touching `PersonalDataManager` or anything above it").
5. **Can JSONL remain the default?** **Yes, for the foreseeable, evidenced workload** — nothing in EP‑093/094/097's actual or anticipated scope requires high-frequency writes or indexed range queries beyond what a category-scoped JSONL file plus in-process filtering in `query()` can handle at interval-based ingestion rates.
6. **At what threshold should a database backend become necessary?** **RECOMMENDATION, not evidenced:** once a source ingests at sub-minute frequency *or* once `query()` is observed (via EP‑095/096's own future STEP 1 investigation, not this analysis) to need indexed time-range scans across a full year or more of data at interactive latency — neither condition exists today.
7. **Should time-series storage be a separate EP now or later?** **Later.** No evidenced need exists now; introducing it now would be speculative complexity against `docs/architecture/NON_GOALS.md`'s own stated principle to avoid it.

**DECISION RULE: Stay on JSONL by default. Revisit only when a specific future source (live-transport, per Decision 1) is scoped at sub-minute ingestion frequency, or when EP‑095/096's own future STEP 1 concretely identifies a query pattern JSONL cannot serve at acceptable latency — whichever comes first. Do not build a time-series storage EP speculatively.**

---

## DECISION 7 — EP‑095–098 Relationship to External Data

**Investigation performed this session:** `EP092_DESIGN.md` §11 (re-read in full, quoted above) is direct, load-bearing evidence for this decision.

1. **Can EP‑095 (Visualization) start before live external data exists?** **Yes** — it reads through `PersonalDataManager.query()` against whatever data is already stored, including EP‑093/094's existing manual/CSV-sourced historical data. No dependency on Decision 1's live-transport work exists.
2. **Can EP‑096 (Forecast/Anomaly) work on existing EP‑093/094 historical data?** **Yes**, for the same reason — though its *forecast quality* would obviously improve with denser, more frequent data, its architectural dependency is on `PersonalDataManager.query()`, already satisfied.
3. **Does EP‑097 (Weather) require the Universal External Data EP first?** **No** — EP‑097 is explicitly scoped (per `EP092_DESIGN.md` §11) as its own `PersonalDataSource` implementation, following the exact same pattern EP‑093/094 already established; it does not need Decision 1's live-transport abstraction to exist first, since a weather API poll is architecturally identical in shape to EP‑093/094's own acquisition pattern (a scheduled interval poll), just against a live HTTP endpoint instead of manual/CSV input. It may, however, need EP‑071 or the interim `.env` convention if its chosen provider requires an API key (Open‑Meteo's free tier reportedly does not, per idea file #1, un-reverified this session).
4. **Does EP‑098 (Recommendation) depend on EP‑096 and EP‑097?** **Yes** — `EP092_DESIGN.md` §11 explicitly names EP‑098 as "the first consumer expected to query across multiple categories at once," implying it needs at minimum EP‑096 (Forecast/Anomaly) and EP‑097 (Weather) producing queryable data, consistent with `docs/BACKLOG.md`'s own stated sequencing.
5. **Should EP‑095–098 remain separate?** **Yes** — no evidence suggests merging any of them; each has a distinct, already-recorded scope in `docs/BACKLOG.md`.
6. **Does any of them need renumbering?** **No** — they are already-reserved, implemented-adjacent (EP‑093/094 already consume the same numbering phase) roadmap numbers; renumbering would violate Phase 14's Rule 2/7 for no evidenced benefit.
7. **Does idea-file EP numbering conflict matter here?** **Yes, directly** — Idea File #2's proposed EP‑095–102 would collide with these four already-reserved, partially-implemented-context numbers; this decision reconfirms that collision remains live and unresolved (see the Master Roadmap Reconstruction §21, unchanged by this session's further investigation).
8. **Which EP can proceed independently?** EP‑095 and EP‑096 can both start immediately, independent of each other and of Decision 1's external-data work, since both are gated only on EP‑092/093/094 (already complete). EP‑097 can also start immediately if a no-credential weather provider is used; otherwise it waits on Decision 3's credential resolution. EP‑098 is the one genuinely blocked item, waiting on EP‑096 and EP‑097.

**DECISION: EP‑095 and EP‑096 are unblocked today. EP‑097 is unblocked today if a credential-free weather provider is chosen, otherwise blocked on Decision 3. EP‑098 is blocked on EP‑096/097. None require renumbering. Universal External Data (Decision 1) is NOT a prerequisite for any of EP‑095–098 — this corrects an implied dependency in the Master Roadmap Reconstruction's own §17 sequencing, which listed External Data before EP‑095–098; repository evidence shows they are independent.**

---

## DECISION 8 — Workflow Engine vs. Task DAG

**Investigation performed this session:** read `workflow_definition.py` and `workflow_engine.py` (EP‑033) and `collaboration_engine.py` (EP‑032) directly, in full for the former two, and the module docstring/class structure for the latter.

**VERIFIED FACT (Workflow Engine):** `WorkflowDefinition.steps` is a plain `tuple[WorkflowRequestStep, ...]` — a strictly **linear, ordered sequence**. `WorkflowEngine` "walks each `WorkflowRequestStep` in order" and halts remaining steps (marking them `SKIPPED`) on failure if `stop_on_failure` is enabled. There is **no dependency graph, no branching, no parallel execution, and no concept of one step's output feeding a specific later step** — each `WorkflowRequestStep` is only a `name` plus a flat `request: str` string forwarded to Planning. This directly answers sub-questions 1–3: **no DAG support, no dependencies, no typed outputs** — all three are absent by design, not merely undocumented.

**VERIFIED FACT (Collaboration Engine):** `CollaborationEngine.collaborate()` "distribute[s] the request across every registered agent" — a **fan-out broadcast** of one request to all agents, coordinating only *which* agents receive it, never *how* they depend on each other or exchange results. This directly answers sub-question 5: Collaboration Engine solves **task distribution**, not task **dependency/sequencing** — a materially different problem than Task DAG's own premise (Idea File #2's own example: Task A → {Task B, Task C} → Task D → Task E, with data flowing along the edges).

4. **Does it support artifact passing?** **No** — confirmed by the same reading: a `WorkflowRequestStep` carries only a plain-text `request`; nothing in `WorkflowRunResult`/`WorkflowStepOutcome` (per their import in `workflow_engine.py`) suggests a typed payload is carried between steps, only a `WorkflowStepOutcomeStatus`.
6. **Does Task DAG require a new EP?** **Yes** — the linear, no-dependency-graph nature of `WorkflowEngine` is a structural property, not a gap that a small extension could close without materially redesigning its core data model (`WorkflowDefinition.steps` would need to become a graph, not a tuple).
7. **Could Task DAG simply be an extension of EP‑033?** **No, not "simply"** — extending `WorkflowDefinition` from a tuple to a dependency graph is a genuine breaking-shape change to its core domain model, which this project's own Engineering Principles ("preserve backward compatibility") would require handling as a new, additive capability alongside the existing linear model, not a silent redesign of it. This is architecturally closer to "a new EP that may reuse `WorkflowEngine`'s dispatch-to-`PlanExecutionEngine` pattern" than "extend EP‑033 in place."
8. **Are typed artifacts a separate architectural concern?** **Yes** — confirmed independently of the DAG-scheduling question: even a purely linear pipeline could benefit from typed inter-step payloads, and DAG scheduling could exist without them (untyped dict handoff). They are orthogonal and should be designed/scoped separately, consistent with the prior report's own recommendation, now confirmed rather than merely inferred.
9. **Is asynchronous execution already present?** Background Workers (EP‑036) and Scheduler (EP‑034) provide asynchronous/background *job* execution, but neither is wired to Workflow Engine or Planning for a DAG-style dependency-aware execution model — this session found no evidence of that integration existing.
10. **What is genuinely missing?** A dependency-graph-capable execution model (Task DAG) and a typed inter-step data contract (Typed Artifacts) — both **confirmed genuinely absent**, not merely undocumented, by direct code reading this session.

**DECISION: Task DAG is NOT sufficiently covered by existing Workflow Engine or Collaboration Engine. A new EP is justified for Task DAG. Typed Artifacts is confirmed as a separate, orthogonal concern that should be scoped independently (see Decision 9).**

---

## DECISION 9 — Typed Artifact Contract

**Investigation performed this session:** the Decision 8 code reading directly answers this — `WorkflowRequestStep.request: str` and (by extension, consistent with every other cross-component boundary examined this and the prior session: `CommandResult`, `PlanExecutionEngine.execute_request()`, `AgentProvider.execute()`) every inter-component handoff examined in this codebase uses either a plain string, a project-specific untyped result dataclass (`CommandResult`), or a raw file path — never a declared, versioned, cross-subsystem artifact schema.

**Is a typed artifact contract actually necessary?** **RECOMMENDATION, not a repository-evidenced requirement today** — no current subsystem is observed *failing* or *working around* the absence of one; the need is anticipatory, tied to Task DAG (Decision 8) and to future multi-step content-production or research workflows, not to any documented present-day pain point. This should be treated as a **enabling** investment for Task DAG, not an independently urgent gap.

**If pursued, where does it belong?**
- **Should it be part of Workflow Engine?** **RECOMMENDATION: no** — per Decision 8's own conclusion that Task DAG itself should not simply extend EP‑033 in place, a typed-artifact contract is more fundamental than either Workflow Engine or a future Task DAG EP specifically; it is a **shared data-contract concern** multiple orchestration mechanisms (Workflow Engine, a future Task DAG, Collaboration) could all use.
- **Does it deserve its own EP?** **RECOMMENDATION: only as a small, foundational sub-package of the Task DAG EP**, not a fully independent EP on its own — the two are tightly coupled in practice (a DAG's edges are exactly where typed artifacts flow), and Idea File #2's own text explicitly proposes bundling them ("Typed Artifact Handoff... can be made part of EP‑099" in its own numbering, i.e., made part of its Task DAG proposal, not separate).
- **How would it interact with files?** A typed artifact should be able to *reference* a file (path + declared type/schema) without necessarily embedding file bytes — consistent with how `CommandResult` and existing skills (`files`, `vision`) already pass paths rather than raw content.
- **How does it remain Windows-safe?** No special Windows risk was identified for a pure in-memory/JSON-serializable data-contract design — the Windows risk surface for this project concentrates in process/file-handle/subprocess concerns (per §17 of the prior report), not data-schema design; this item carries essentially zero Windows risk.
- **How does it avoid becoming an enterprise-scale type system?** **RECOMMENDATION:** keep the schema minimal and evolve it only as concrete producer/consumer pairs are actually built (mirroring this project's own "Unknown API Policy" discipline of never inventing speculative infrastructure ahead of a real consumer) — do not attempt a comprehensive upfront artifact taxonomy.

**DECISION: Typed Artifact Contract should be a sub-scope of the same future Task DAG EP, not a separate EP, and not an urgent standalone gap.**

---

## DECISION 10 — Self-Development / Autonomous Coding

**Investigation performed this session:** builds directly on Decision 2's code-level confirmation that capability governance is fully disconnected, plus a fresh check this session confirming zero Windows-specific process-replacement handling anywhere in `src/core/` (no `os.replace`/module-reload/subprocess-restart pattern was found associated with any "canary" or self-modification concept in the codebase — none exists to find, since EP‑074 has no code at all).

| Prerequisite | Status | Evidence |
|---|---|---|
| Governance *model* (security assessment, policy decision, lifecycle tracking) | **EXISTS** | EP‑069.6/070/069.7, all audited PASS/PASS‑WITH‑WARNINGS |
| Governance *enforcement* (the model actually gating a real action) | **MISSING** | Decision 2 — zero wiring found anywhere |
| Isolated workspace / branch / snapshot mechanism | **MISSING** | `src/core/git/`/`src/core/github/` (EP‑038/039) provide general git operations, but no canary-specific branch/snapshot workflow was found |
| Build/test/health-check/rollback pipeline (automatable) | **MISSING (as automation)** | Only the human-driven STEP 1‑4 lifecycle exists; no evidence of any automated equivalent |
| Windows file-lock/process-replacement handling | **MISSING** | Confirmed absent this session; a hard, unaddressed technical risk specific to this feature |
| Resource budget (bounding what a self-modifying agent could spend/attempt) | **MISSING** | Decision 5 |
| Failure recovery (automated) | **MISSING** | No automated-rollback mechanism found; only human-driven STEP 3.1 remediation |
| Test execution / regression testing infrastructure | **EXISTS, reusable** | `BaseTest`/`TestRegistry`/`TestRunner`, already used by every EP — directly reusable by a future canary pipeline without modification |
| Approval boundary | **EXISTS as a model, not enforced** | EP‑070's `PolicyLevel` including `REQUIRE_APPROVAL`, unwired (Decision 2) |
| Artifact verification | **MISSING** | Depends on Decision 9's typed artifact contract, itself not yet built |

1. **Which prerequisites already exist?** The governance *model* and the test-execution infrastructure — both directly reusable.
2. **Which are missing?** Enforcement wiring, isolated workspace/snapshot, automated build/test/rollback pipeline, Windows process-replacement handling, resource budgets, automated failure recovery, artifact verification — a substantial majority of the full prerequisite list.
3. **Which existing EP can provide each prerequisite?** Governance enforcement → Decision 2's proposed wiring EP. Resource budgets → Decision 5's proposed EP. Test execution → already provided by `BaseTest`/`TestRegistry`/`TestRunner`, no new EP needed. Everything else (workspace/snapshot, automated pipeline, Windows process handling, automated rollback, artifact verification) has **no existing EP or package that provides it today** — these are net-new, EP‑074/074.1's own responsibility to design.
4. **Should EP‑074 remain blocked?** **Yes.**
5. **Minimum architecture required before autonomous code modification is allowed:** (a) Decision 2's governance-wiring EP complete and actually enforcing at least one real action type; (b) Decision 5's resource-governance EP complete; (c) an explicit, EP‑074-owned design for Windows-safe process replacement (not currently addressed by any existing EP and not solvable by reusing something that already exists); (d) an automated build/test/rollback pipeline, which may reuse `BaseTest`/`TestRegistry`/`TestRunner` for its test-execution step but still requires new orchestration code around it.

**DECISION: EP‑074/074.1 remains blocked. The gap is larger than "wire the governance stack" alone — it additionally requires net-new workspace/snapshot, automated pipeline, and Windows process-management design that no existing or currently-proposed EP provides. This confirms and sharpens the prior report's caution rather than resolving it further.**

---

## DECISION 11 — MCP

**Investigation performed this session:** re-confirmed `CapabilitySourceKind` (EP‑069.4) already includes `REST_API` and `BROWSER_SERVICE` enum members; re-confirmed zero MCP-client code exists anywhere in `src/core/` or `requirements.txt`.

**ARCHITECTURAL INFERENCE:** An MCP server's exposed tools/resources map naturally onto the existing `Capability` model — each tool becomes one `Capability` instance with an appropriate `source_kind`. This requires **one new concrete `CapabilityBackend` implementation** (the piece EP‑069.4 explicitly shipped zero of, by its own Owner Decision) for the MCP protocol specifically, not a new domain model.

**DECISION:** MCP should be **a Capability backend integration, built after Decision 2's governance-wiring EP**, not a new independent subsystem. Building it before governance wiring would mean MCP-exposed tools execute with the same zero enforcement every other capability currently has — acceptable only for deliberately low-risk, read-only MCP sources, and only with an explicit Owner Decision accepting that gap (consistent with the prior report's own conditional framing, now confirmed rather than softened). MCP is **not automatically required** — no evidence in the repository or either idea file names a concrete MCP server Jarvis actually needs to connect to; this remains speculative until an Owner names a real target.

---

## DECISION 12 — Observability / Resource Governance / Diagnostics Relationship

Synthesizing Decisions 4 and 5's own findings into one cross-cutting shape:

```
Execution (CommandRouter, ProviderRequestExecutor, Scheduler jobs, capability actions)
        │
        ├──▶ Usage/Event Capture ──▶ Observability (continuous, machine-consumable)
        │                                    │
        │                                    ▼
        │                          Resource/Cost Governance
        │                          (accounting against budgets,
        │                           decision via Policy Engine)
        │
        └──▶ On-demand status query ──▶ Diagnostics ("doctor")
                     (reads current state: RuntimeStatus, Capability
                      catalog, Lifecycle records, and — once it exists —
                      recent Observability data as one more input)
```

This avoids a circular dependency because Diagnostics is defined as a **read-only consumer** of whatever Observability/Lifecycle/Runtime state already exists at query time — it never writes back into Resource Governance or Observability, and Resource Governance never depends on Diagnostics. Observability and Resource Governance share the same **Usage/Event Capture** point (naturally `ProviderRequestExecutor`, per Decision 5) but remain separable: Observability is optional for Resource Governance to function minimally (a simple counter/ledger suffices without a full telemetry system), while a full Observability system provides richer trending on top of the same captured events.

---

## DECISION 13 — Candidate EP Disposition

| Candidate (from prior report) | Disposition | Reason |
|---|---|---|
| 1. Capability Governance Integration/Wiring | **KEEP AS NEW EP** | Confirmed, code-level, as the single most consequential missing integration; no existing EP can absorb it without contradicting its own already-audited scope |
| 2. Capability & System Diagnostics ("Doctor") | **KEEP AS NEW EP**, small | Zero new instrumentation required; cheap, high-value, genuinely new reporting layer |
| 3. System Observability/Telemetry | **KEEP AS NEW EP**, deferred behind Diagnostics | Genuinely new instrumentation work; larger than Diagnostics |
| 4. Resource & Cost Budget Governance | **KEEP AS NEW EP** | Confirmed to require a `ProviderResponse` schema change EP‑069.3/070 cannot cleanly absorb — not an extension, a real new boundary |
| 5. External Data Transport & Live Source Abstraction | **EXTEND EXISTING (EP‑092 pattern), not a new abstraction layer; KEEP AS NEW EP only for the first concrete transport-capable source** | Decision 1 confirms Model A requires no new subsystem — only new concrete `PersonalDataSource` implementations, following the EP‑093/094 precedent |
| 6. Time-Series Storage Backend | **DEFER** | Decision 6 — no evidenced need at current/anticipated ingestion frequency; speculative if built now |
| 7. Typed Artifact Contract | **MERGE into Task DAG EP** | Decision 9 — orthogonal but tightly coupled; not independently urgent |
| (New, this session) Task DAG | **KEEP AS NEW EP** | Decision 8 — confirmed, code-level, that Workflow Engine and Collaboration Engine do not provide this |
| (New, this session) `ProviderResponse` usage-field extension | **EXTEND EXISTING (EP‑015's `ProviderResponse`)** | A small, additive schema change, prerequisite to Resource Governance, not itself EP-sized |

---

## DECISION 14 — Actual Next EP

**Evaluation of candidates against dependency, safety, and value:**

- Task DAG, Typed Artifacts, Observability, and MCP are all either dependent on Governance Wiring (MCP) or independently valuable but non-blocking for anything else critical (Task DAG, Observability).
- EP‑074 Self-Development is explicitly, multiply blocked (Decision 10) and should not be next.
- EP‑071 Credentials is a real dependency for *some* future work (authenticated external sources, MCP with authenticated servers) but nothing in the currently-implemented/audited state is blocked *waiting* on it today — Decision 7 confirms EP‑095/096 and a credential-free EP‑097 can all proceed without it.
- EP‑095/096 (Visualization, Forecast/Anomaly) are unblocked today (Decision 7) and represent direct, already-reserved roadmap progress with zero new architectural risk — but they are **domain capability** work, not **foundation** work, and building capability on top of a still-disconnected governance/accounting substrate is architecturally riskier than closing that substrate first (consistent with the general "foundations before features" principle both idea files and this project's own architecture already lean on).
- Governance Wiring (Decision 2's proposed EP) uniquely: (a) requires zero new architectural invention — it is pure integration of five already-audited, already-correct packages; (b) directly unblocks the largest number of stated future ambitions in both idea files and `docs/BACKLOG.md` (self-development, MCP, any future policy-gated capability); (c) closes a real, currently-live risk — every capability in the system today executes with **zero security assessment and zero policy enforcement**, which is a meaningfully different risk posture than "not yet built," since the components exist and could create a false impression of governance if not clearly disclosed as disconnected.

```text
RECOMMENDED NEXT EP: EP-NEW-CANDIDATE-1 — Capability Governance Integration (Wiring)
```

**Why it should be next:** it is the only candidate that is simultaneously (a) zero new architectural risk (pure integration of already-audited code), (b) a real, currently-live gap (not speculative), and (c) a hard or soft prerequisite for the largest number of other named future ambitions (EP‑074, MCP, EP‑073 browser HITL, any future policy-gated capability).

**What it must accomplish:** wire `CapabilityDiscoveryEngine` → `CapabilitySecurityEngine` → `PolicyEngine` → `CapabilityLifecycleRegistry` into one real, bootstrap-constructed coordinator, and connect that coordinator to at least one genuine execution path (`CommandRouter.dispatch()` is the strongest, most evidence-supported candidate, being the single shared chokepoint every interface already uses).

**What it must NOT attempt:** redesigning any of the five underlying packages' own internal logic (all already audited PASS/PASS‑WITH‑WARNINGS); building any new concrete `CapabilityBackend` (MCP, REST, browser — those remain separate, later EPs per Decision 11); building Resource Governance, Diagnostics, or Observability in the same EP (each is its own bounded scope per Decisions 4/5); attempting Task DAG or Typed Artifacts (unrelated concern, Decision 8/9).

**What it unlocks:** a real basis for EP‑073/EP‑074 to eventually build on; a real enforcement point for any future MCP backend (Decision 11); a real target for Resource Governance's policy-side "budget exceeded" response (Decision 5) once that EP exists.

**What it depends on:** nothing beyond what already exists — EP‑069.4/.5/.6/.7/070 are all complete and require no changes themselves.

**Which future EPs remain blocked pending it:** EP‑074/074.1 (fully, per Decision 10, though not solely on this), any MCP integration intended to enforce security/policy (Decision 11), any future browser/desktop-automation EP intended to route through real policy approval (EP‑073's own eventual future STEP 1).

---

## DECISION MATRIX

| Decision | Current Evidence | Decision | EP Impact | Dependency |
|---|---|---|---|---|
| External Data Model | `PersonalDataSource` ABC already transport-agnostic; EP‑092 design doc names EP‑097 as a future HTTP-API source under the same interface | **Model A** | New concrete sources only, following EP‑093/094 precedent; no new abstraction EP | EP‑092 (satisfied) |
| Capability Governance | Five packages complete/audited; zero wiring anywhere (`bootstrap.py`, `CommandRouter`, `ToolEngine` all searched, zero matches) | **Wire via new coordinator EP** | New EP (integration only, no new domain logic) | EP‑069.4/.5/.6/.7, EP‑070 (all satisfied) |
| EP‑071 Credentials | No credential-management subsystem exists; `.env`/`Config` is the only current convention | **Required only for authenticated sources; not a blanket blocker** | Gates specific future sources/backends, not External Data architecture itself | None currently blocked by it |
| Diagnostics vs Observability | `RuntimeService.status()` is the only precedent; zero telemetry exists | **Two EPs, Diagnostics first** | Two small-to-medium new EPs | Diagnostics: none. Observability: none, but larger scope |
| Resource/Cost Governance | `ProviderResponse` has no usage/cost fields at all (VERIFIED this session) | **New EP required; must extend `ProviderResponse` first** | New EP, plus a prerequisite small schema change | `ProviderRequestExecutor` (EP‑082, satisfied); EP‑069.3/EP‑070 consumed, not modified |
| Time-Series Storage | Ingestion is interval-based batch (per EP‑093's own scheduler-job design); `PersonalDataProvider` already swappable | **Defer** | No EP now | Revisit only if a sub-minute live source is scoped |
| EP‑095–098 | EP‑092 design doc directly confirms both EP‑095/096 read only through existing `query()` | **EP‑095/096 unblocked now; EP‑097 unblocked if credential-free; EP‑098 blocked on EP‑096/097** | No renumbering | EP‑092/093/094 (satisfied) |
| Workflow vs Task DAG | `WorkflowDefinition.steps` confirmed linear tuple, no dependency graph, no typed outputs (VERIFIED, code read) | **Task DAG is a genuine new EP; not a Workflow Engine extension** | New EP | EP‑029/030/032/033 (reused, not modified) |
| Typed Artifacts | No typed cross-component contract found anywhere examined | **Merge into Task DAG EP, not independent** | Sub-scope of Task DAG EP | Task DAG EP |
| Self-Development | Governance model exists but disconnected; workspace/pipeline/Windows-process-handling entirely missing | **Remains blocked; larger gap than governance wiring alone** | EP‑074/074.1 unchanged, still blocked | Governance Wiring EP + Resource Governance EP + net-new Windows/pipeline design |
| MCP | `CapabilitySourceKind` already models `REST_API`/`BROWSER_SERVICE`; zero MCP client code exists | **Capability backend extension, after Governance Wiring; not independently required** | New, small `CapabilityBackend` implementation, deferred | Governance Wiring EP (recommended precondition) |

---

## REQUIRED DEPENDENCY GRAPH

```
Existing Audited Foundations
(EP-001-068, EP-069.1-.7, EP-070, EP-082-087, EP-092-094)
                │
    ┌───────────┼─────────────────────────────┬───────────────────┐
    ▼           ▼                             ▼                   ▼
Governance   EP-095 Visualization        EP-096 Forecast/    ProviderResponse
Wiring EP    (unblocked now)             Anomaly (unblocked  usage-field
(NEXT EP)         │                       now)                extension
    │             └───────────┬───────────────┘                  │
    │                         ▼                                  ▼
    │                   EP-097 Weather              Resource & Cost Governance EP
    │              (unblocked if credential-free            │
    │               source chosen; else waits                │
    │               on EP-071 / interim .env)                │
    │                         │                                │
    │                         ▼                                │
    │                   EP-098 Recommendation                  │
    │                   (blocked on EP-096 + EP-097)            │
    │                                                          │
    ├──────────────┬─────────────────────┬────────────────────┘
    ▼              ▼                     ▼
MCP Backend    EP-074/074.1        Diagnostics ("Doctor") EP
Integration    Self-Development         │
(after         (blocked: also needs     ▼
Governance     net-new workspace/    Observability EP (can follow
Wiring)        pipeline/Windows      Diagnostics, feeds both
               process design)       Diagnostics and Resource Gov.)

Task DAG EP (independent of the above; depends only on
already-complete EP-029/030/032/033) ── includes Typed Artifact
Contract as a sub-scope

External Data Transport (Decision 1, Model A) ── independent of
Governance Wiring and of EP-095-098; gated per-source on EP-071
only when a specific source is authenticated
```

---

## DO NOT BUILD

Concrete list, each supported by this and the prior session's investigation:

- **A second Capability Registry, Discovery engine, Security engine, Policy engine, or Lifecycle registry** — all five already exist, are already audited, and need only wiring (Decision 2), not replacement.
- **A second Personal Data framework, registry, manager, or provider** — `PersonalDataSource`'s ABC is already transport-agnostic (Decision 1); a live-transport source is a new *implementation* of the existing contract, never a new framework.
- **A second Workflow Engine** — Task DAG (Decision 8) should reuse `WorkflowEngine`'s dispatch-to-`PlanExecutionEngine` pattern where applicable, not duplicate it; only its core scheduling *model* needs to be new, not the whole engine concept.
- **A second Memory system** — Structured Memory (typed relations/provenance, carried over unresolved from the prior report) should extend EP‑025/026/057, not replace them; not further investigated this session beyond confirming no contradicting evidence emerged.
- **A vector database** — no vector-store backend exists to replace, and no evidenced query-volume/latency problem justifies introducing one; remains deferred (unchanged from the prior report, reconfirmed by finding nothing new this session).
- **A time-series database** — Decision 6, deferred; JSONL is sufficient for the evidenced interval-based ingestion pattern.
- **A standalone MCP subsystem/architecture** — Decision 11; MCP is a `CapabilityBackend` extension of what already exists, not a new architecture.
- **A duplicate browser automation layer** — EP‑051 (implemented) already covers this; any new browser-security work belongs in resolving the EP‑051/EP‑073 self-flagged duplication `docs/BACKLOG.md` already names, not a third implementation.
- **A duplicate AI provider abstraction** — EP‑014/015/069.x already fully cover this; `ProviderResponse`'s needed usage-field extension (Decision 5) is an additive change to the existing model, not a new one.
- **A new, second authorization/security framework** — Decision 2's own critical requirement; the existing five-package chain is architecturally sufficient once wired.
- **A speculative "Universal External Data Layer" (Model B)** — Decision 1 explicitly rejects this; no second consumer of raw external data was found to justify it.
- **A credential-management system built ad hoc inside a Universal External Data EP** — Decision 3; this belongs to EP‑071 specifically, and should not be invented piecemeal inside an unrelated EP.

---

## 1. RESOLVED DECISIONS

1. **External Data Model:** Model A — `PersonalDataSource` extension; confirmed by the ABC's own transport-agnostic design and EP‑092's own documented expectation of an HTTP-API-backed weather source under the identical interface.
2. **Capability Governance Wiring:** required, as a single new integration EP connecting five already-correct, currently-disconnected packages; no redesign of any of them needed.
3. **EP‑071 Credentials:** required only for authenticated sources; unauthenticated/local sources may proceed without it, using the existing `.env`/`Config` convention as an interim measure for a first authenticated source if EP‑071 is not yet built.
4. **Diagnostics vs. Observability:** two separate EPs, Diagnostics first (cheaper, builds on existing `RuntimeService.status()` and Capability/Lifecycle data with zero new instrumentation).
5. **Resource & Cost Governance:** a new EP is justified; it has a previously-undisclosed prerequisite this session surfaces — `ProviderResponse` (EP‑015) currently has no usage/cost fields at all and must be extended first.
6. **Time-Series Storage:** defer; JSONL is sufficient for the confirmed interval-based, batch-scheduled ingestion pattern EP‑093 already established as this project's real precedent.
7. **EP‑095–098:** EP‑095/096 unblocked today; EP‑097 unblocked today if a credential-free weather provider is chosen; EP‑098 blocked on EP‑096/097; none require renumbering; Universal External Data is not a prerequisite for any of them (a correction to the prior report's own sequencing).
8. **Workflow Engine vs. Task DAG:** confirmed, by direct code reading, that Workflow Engine (`WorkflowDefinition.steps` is a plain linear tuple) and Collaboration Engine (a fan-out broadcast, not dependency-aware) do not provide DAG-style execution; Task DAG is a genuine new EP.
9. **Typed Artifact Contract:** genuinely absent everywhere examined; should be a sub-scope of the Task DAG EP, not independently urgent or independently numbered.
10. **Self-Development/Autonomous Coding:** remains blocked; the gap is larger than governance wiring alone — workspace/snapshot, automated build/test/rollback pipeline, and Windows-specific process-replacement handling are all entirely missing and not provided by any existing or currently-proposed EP.
11. **MCP:** should be implemented as a new `CapabilityBackend` for the existing Capability model, after Governance Wiring, not as an independent subsystem; not currently required absent a named target server.
12. **Observability/Resource Governance/Diagnostics relationship:** a shared Usage/Event Capture point (at `ProviderRequestExecutor`) feeds both Observability and Resource Governance; Diagnostics is a read-only consumer of Runtime/Capability/Lifecycle state (and, later, Observability data) with no circular dependency.
13. **Candidate EP disposition:** see the table in Decision 13.
14. **Actual next EP:** Capability Governance Integration/Wiring (EP-NEW-CANDIDATE-1).

## 2. REMAINING OWNER DECISIONS

- Whether the interim `.env`/`Config` convention is acceptable for a first authenticated external-data source, or whether EP‑071 must exist first regardless (Decision 3).
- The exact enforcement default (`PolicyLevel`) new capabilities should receive once Governance Wiring exists — permissive-by-default (OBSERVE) vs. restrictive-by-default (REQUIRE_APPROVAL) is a genuine, unresolved policy choice this analysis cannot make.
- Whether Resource Governance's global vs. per-provider budget split (Decision 5, point 5) should be user-configurable from day one or fixed initially.
- The precise threshold (ingestion frequency or query-latency symptom) at which Time-Series Storage should actually be revisited (Decision 6) — this analysis proposes a rule of thumb, not a binding number.
- Whether EP‑074/074.1 remains an active project goal on any particular timeline, given the now-clarified size of its remaining prerequisite gap (Decision 10).
- Whether a specific MCP server is actually wanted as a real integration target (Decision 11) — nothing in the repository or either idea file names one.
- How and when to formally correct `JARVIS_ROADMAP.md`'s stale phase annotations (carried over, unchanged, from the prior report).

## 3. CANDIDATE EP DISPOSITION

See the table under **DECISION 13** above (reproduced in full there; not duplicated here to avoid redundant restatement of the same evidence).

## 4. RECOMMENDED NEXT EP

```text
RECOMMENDED NEXT EP: EP-NEW-CANDIDATE-1 — Capability Governance Integration (Wiring)
```
(Full justification under **DECISION 14** above.)

## 5. DEPENDENCY GRAPH

See **REQUIRED DEPENDENCY GRAPH** above.

## 6. DO NOT BUILD

See **DO NOT BUILD** above.

## 7. ROADMAP CORRECTIONS REQUIRED

(Carried forward from the prior report, re-confirmed by this session's deeper investigation, plus two new items this session's code reading surfaces.)

- `JARVIS_ROADMAP.md`'s Phase A/C/E annotations should be updated to reflect EP‑069.6, EP‑069.7, EP‑070, EP‑084–087, EP‑093, EP‑094 as complete (unchanged from the prior report).
- **New this session:** the roadmap/backlog should explicitly record that EP‑069.6/.7/070, while individually audited PASS, are **not wired to any execution path** — a first read of "COMPLETE" could otherwise wrongly imply active enforcement exists, which this session's code-level search confirms it does not.
- **New this session:** `EP092_DESIGN.md`'s own §11 "FUTURE INTEGRATION" note, and this session's confirmation that EP‑095/096 do not depend on a not-yet-built Universal External Data layer, should be reflected in `docs/BACKLOG.md`'s Phase E description if that document currently implies (as its narrative ordering suggests) that EP‑095–098 wait on a broader external-data foundation.
- `docs/BACKLOG.md`'s own self-flagged EP‑051/EP‑073 and EP‑075/EP‑116 duplications remain unresolved (carried over, unchanged).
- Any future roadmap update should record `EP-NEW-CANDIDATE-1` through `-4` (or their eventual reconciled numbers) only once an Owner has approved them — this analysis does not assign final numbers, per Phase 14's Rule 6.

---

*End of report. No files, code, tests, configuration, or roadmap documents in the repository were created, modified, or deleted in the course of this review.*
