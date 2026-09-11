# ROADMAP EP-070–140 REBUILD PROPOSAL

Status: PROPOSAL (both audits below passed; canonical documents have
been synchronized — see `docs/architecture/JARVIS_ROADMAP.md` and
`docs/BACKLOG.md`).

Scope: documentation/planning only. No source code, tests,
configuration, or dependencies were touched.

---

## 0. What this continues

A prior pass produced only the *task specification* for this rebuild
(the uploaded `jarvis_ecc_roadmap_recommendations.md`) — it contains
no repository findings, no EP table, and no traceability. Nothing in
it was a design output to preserve or discard; it was the brief. This
document is the actual PASS 1 design and PASS 2 audit the brief
called for, produced by inspecting the real repository
(`github.com/muzaffarashurov/jarvis`) and the real reference repo
(`github.com/affaan-m/ECC`).

---

## 1. Repository findings

### 1.1 What already exists (Core, implemented)

The repository has 69 completed EPs (Phases 1–10, `docs/architecture/
JARVIS_ROADMAP.md`) and a real `src/core/` with, among others:
`tool`, `agent`, `planning`, `execution`, `plan_execution`,
`workflow_engine`, `workflow_scheduler`, `scheduler`, `memory`,
`long_term_memory`, `knowledge`, `rag`, `retrieval`, `embedding`,
`semantic`, `indexing`, `collaboration`, `git`, `github`,
`automation_engine`, `background_workers`. EP-069.1/.2/.3 (AI
provider fallback, fallback ordering, cost-aware selection) are
complete and documented in their own EP069*_DESIGN.md/AUDIT files.

This matters directly for scoping EP-070–140: several future items in
the existing backlog would have duplicated this Core rather than
building on it. Three concrete duplicates/overlaps were found (see
§4) and are flagged rather than silently fixed, since resolving them
fully requires a future EP's own STEP 1 with real code inspection,
which is out of scope for a documentation-only rebuild.

### 1.2 What the existing EP-070–138 roadmap actually was

`docs/BACKLOG.md`, "Long-Term Roadmap — Future Engineering Packages,"
already contained a reasonably coherent phase structure (Foundation →
Software Factory → AI Content → Social → Personal Intelligence →
Enterprise → Legal Income → Advanced Intelligence → Distributed →
Enterprise Knowledge → Education → Market → Family → Unified
Knowledge). It was not a random feature list. Its main architectural
gap, relative to the new mission brief, was structural rather than
content: it had no explicit Core/Universal-Engine/Capability
separation, and it had no answer at all for "Jarvis uses a local
GitHub project / external API / external web service / browser-only
service as a capability" (Sections 6–12 of the brief). That gap is
this rebuild's main addition.

### 1.3 ECC reference architecture

`affaan-m/ECC` is a Claude-Code-oriented agent-harness framework
(agents, skills, hooks, memory, continuous learning, a security
scanner called AgentShield) built around a `plan -> test -> implement
-> review -> verify -> remember -> improve` loop. It is a coding-agent
harness, not a general personal-assistant architecture, so most of it
is not directly transplantable — see the ECC traceability table in
§7. Its most useful transferable concepts for Jarvis are: (a) treating
verification/review as a first-class loop stage rather than an
afterthought, (b) promoting repeated successful patterns into reusable
skills, and (c) a dedicated security-scanning concern distinct from
runtime policy enforcement.

---

## 2. Old EP-070–138 disposition (per item)

Legend: **K**=Keep, **M**=Merge, **R**=Rename/generalize, **Mv**=Move,
**D**=Defer, **X**=Remove. Nothing is dropped without a placeholder —
see `docs/BACKLOG.md` for the retired-entry notices.

| Old # | Old name | Disposition | New # | Reason |
|---|---|---|---|---|
| EP-069 | AI Provider & Tool Registry | K + extended | EP-069 (+.4-.7) | Remaining scope (tools/capabilities) is exactly where External Capability Integration belongs; added as sub-packages, not new top-level EPs, per this repo's own `EP-XXX.Y` convention. |
| EP-070–074 | Policy/Credentials/Autonomy Safety/Browser/PM-Orchestrator | K | EP-070–074 | Already correctly scoped and already the natural policy/credential/execution gate for the capability system. EP-074 gains sub-package EP-074.1 (Dynamic Workflow). |
| — | (none existed) | new | **EP-075, EP-076** | Universal Research & Discovery, Universal Document Intelligence — the two Level-2 engines the old roadmap never named explicitly, even though later domain EPs implicitly needed them. |
| EP-075–079 | Software Factory | K, renumbered | EP-077–081 | Sound as written; shifts +2 for the two new engines above. |
| EP-080–085 | AI Content Platform | K, renumbered | EP-082–087 | Sound; +2 shift. |
| EP-086–089 | Social Automation | K, renumbered | EP-088–091 | Sound; +2 shift. |
| EP-090–096 | Personal Intelligence/Energy/Weather | K, renumbered | EP-092–098 | Sound; +2 shift. |
| EP-097 | Work Data & Document Intake | **M** into EP-076 | EP-099 (retired placeholder) | Pure format-independent ingestion; belongs in the new Universal Document Intelligence engine, not a bespoke enterprise intake pipeline. |
| EP-098–105 | Claim/Quality/Excel/Presentation/Telegram/Web/Invoice/Orchestrator (Enterprise) | K, renumbered, REUSE notes added | EP-100–107 | Genuinely capability-level logic (defect analysis, statistics) that Universal Document Intelligence doesn't provide; kept, now explicitly reusing EP-076. |
| EP-106–110 | Legal Online Income Intelligence | K, renumbered | EP-108–112 | Sound; +2 shift. |
| EP-111–120 | Advanced Intelligence | K, renumbered, 2 overlap flags added | EP-113–122 | EP-116 (Autonomous Research Agent) and EP-119 (Multi-Agent Collaboration) flagged as overlapping EP-075 and the already-implemented `src/core/collaboration` respectively (see §4); not merged outright because their exact remaining scope needs a real STEP 1, not a documentation guess. |
| EP-121–126 | Distributed Jarvis | K, renumbered | EP-123–128 | Sound; +2 shift. |
| EP-127 | Enterprise Knowledge Base | **M** into EP-076 | EP-129 (retired placeholder) | Format-independent ingestion/indexing/provenance is exactly EP-076's job; only classification/permissions/relationships specific to enterprise documents remain, folded into EP-130. |
| EP-128 | Enterprise Document Consistency & Compliance Engine | K, renumbered, REUSE added | EP-130 | Genuine domain reasoning (contradiction detection against enterprise policy); reuses EP-076 and EP-070. |
| EP-129 | Corporate Document Style & Template Intelligence | K, renumbered | EP-131 | Sound. |
| EP-130 | Global Document Research & Benchmarking Agent | **M** into EP-075 | EP-132 (retired placeholder) | Multi-source research/credibility/synthesis is exactly EP-075's job, generalized; only the enterprise-specific gap-analysis framing remains, folded into EP-130 (new number). |
| EP-131–137 | Education / Market / Family Intelligence | K, renumbered | EP-133–139 | Sound; legitimate Level-3 capabilities per the brief's own examples (Section 5); +2 shift. |
| EP-138 | Unified Personal & Enterprise Knowledge Architecture | K, renumbered | EP-140 | Sound as the capstone; unchanged in substance. |

No EP was invented to fill a number gap, and no EP was removed
outright (**X**) — every disposition is K, M (with a retired
placeholder), R, or a renumber-only shift, all traceable above.

---

## 3. Core ≠ Universal Engines ≠ Capabilities — resulting boundary

```
LEVEL 1 — CORE (mostly already implemented, EP-001–069)
  tool/agent/planning/execution/workflow/scheduler/memory/knowledge/
  rag/retrieval/embedding/semantic/indexing/collaboration/git/github
  + new: EP-069.4-.7 (capability abstraction/discovery/security/
    lifecycle), EP-070-074 (+.1) (policy/credentials/safety/browser/
    orchestrator/dynamic-workflow)

LEVEL 2 — UNIVERSAL ENGINES (new, EP-075/076; existing Advanced
  Intelligence items re-scoped as engines: EP-122 Continuous Learning/
  Evolution, EP-113 Personal Knowledge Graph feeding EP-140)
  Universal Research & Discovery (EP-075)
  Universal Document Intelligence (EP-076)
  Dynamic Workflow (EP-074.1)
  Continuous Learning / Evolution (EP-122)
  Multi-Agent Orchestration (existing `src/core/collaboration` +
    EP-119 gap-fill)
  Model/Provider Intelligence (EP-069, already substantially done)

LEVEL 3 — CAPABILITIES (everything else: EP-082–140 domain items)
  Software Factory, AI Content, Social, Personal/Energy, Enterprise &
  Work, Legal Income, Advanced Intelligence domain agents,
  Distributed Jarvis, Enterprise Knowledge compliance/style, Education,
  Market/Innovation, Family, Unified Knowledge (capstone)
```

No Level-3 EP requires a Core change to function; each declares which
Level-1/Level-2 systems it reuses (see the REUSE notes added
throughout `docs/BACKLOG.md`).

---

## 4. Duplicate/overlap findings (the "search for conceptual
duplicates" requirement)

1. **EP-073 (Browser Automation & Human-in-the-Loop) vs. EP-051
   (Browser Automation, Phase 8, not yet marked complete).** Same
   subsystem under two numbers, one inside the EP-069–140 range and
   one outside it (predates EP-069, so this rebuild does not touch
   EP-051 itself). Flagged in `docs/BACKLOG.md`; the recommendation is
   that EP-051's own future STEP 1 decide whether EP-073 should be
   retired in favor of finishing EP-051 with the human-in-the-loop
   requirements folded in.
2. **EP-119 (Multi-Agent Collaboration) vs. `src/core/collaboration`
   (already implemented).** The old backlog entry read as if
   multi-agent collaboration didn't exist yet. It does, at least
   partially. Flagged so a future STEP 1 inventories what's there
   (task distribution) before assuming the full scope (role matching,
   consensus, parallel isolation) is greenfield.
3. **EP-116 (Autonomous Research Agent) vs. new EP-075 (Universal
   Research & Discovery Engine).** Same core capability at two levels.
   Resolved by treating EP-116 as a thin autonomous-scheduling
   capability on top of EP-075, not a second research engine — flagged
   rather than merged outright, since EP-116 also implies proactive/
   scheduled research behavior EP-075 itself doesn't need to own.
4. **EP-097 / EP-127 / EP-130 (old numbers)** all independently
   proposed document-ingestion or research infrastructure inside
   specific domains. Merged into the two new Universal Engines (§2).

No EP-069.1/.2/.3 duplication was introduced anywhere in the new
material — every future provider/model reference in the rebuilt
sections explicitly reuses EP-069's existing fallback/cost-awareness
rather than re-describing it.

---

## 5. External Capability Integration architecture

Addresses brief Sections 6–12.

```
                 CAPABILITY DISCOVERY (EP-069.5)
                         |
       +-----------------+-----------------+
       |                 |                 |
     Local             Remote            Web
  (CLI / GitHub      (REST API)      (Browser-executed
   project)                           service, EP-073)
       |                 |                 |
       +--------- Unified Capability ------+
                  Abstraction (EP-069.4)
                         |
              Capability/Tool Registry
                  (EP-069, extended)
                         |
           Policy / Security (EP-070, EP-069.6)
                         |
              Credential Isolation (EP-071)
                         |
                  Tool Execution (EP-072)
                         |
                    Verification
                         |
              Lifecycle Mgmt (EP-069.7)
```

- **Local GitHub projects / CLI apps** (brief §6.1): discovered,
  inspected (manifest, dependencies, interface) and registered as a
  capability by EP-069.4/.5, but never executed without passing
  EP-069.6's supply-chain/permission check and EP-070's policy gate.
  The explicit forbidden pattern — "download → pip install → execute"
  unrestricted — is called out by name in EP-069.6's `docs/BACKLOG.md`
  entry.
- **External APIs** (brief §7): provider-independent by construction,
  since they're just another Capability backend behind EP-069.4;
  credentials via EP-071, execution via EP-072, no vendor hardcoded.
- **External web services / browser automation** (brief §8–9):
  execution backend is EP-073 (reused, not duplicated); official APIs
  are preferred over browser automation per the existing Global
  Security Principles in `docs/BACKLOG.md`, which this rebuild left
  unchanged because they already state the right default.
- **One abstraction, not one EP per adapter** (brief §10): local/CLI/
  GitHub-project/API/web-service/browser backends are all
  configurations of EP-069.4, not five new EPs — matching the brief's
  explicit instruction in §10 and §22.
- **Security is cross-cutting** (brief §11–12): EP-070 (policy),
  EP-069.6 (supply-chain/permission), EP-071 (credentials), and
  EP-072 (execution/verification/rollback) are each reused by name
  from every capability-consuming EP added or renumbered in this
  rebuild, rather than each domain EP inventing its own safety layer.

---

## 6. Dependency graph (validated)

```
EP-069 (+.4-.7) ──> EP-070 ──> EP-071 ──> EP-072 ──> EP-073
        │                                      │
        └──────────────> EP-074 ──> EP-074.1 ──┘
                                        │
                    EP-075 ◄── reused by ──► EP-076
                        │                        │
        ┌───────────────┼────────────────────────┼──────────────┐
        ▼               ▼                        ▼              ▼
  EP-077-081      EP-082-091 (Content/    EP-092-098      EP-100-107
  (Software        Social)                (Personal/       (Enterprise,
   Factory)                                Energy)          reuses 076)
        │
        ▼
  EP-108-112 (Legal Income) ── EP-113-122 (Advanced Intelligence,
                                 reuses 075/122's own learning loop)
        │
        ▼
  EP-123-128 (Distributed) ── EP-130-131 (Enterprise Knowledge,
                                reuses 075/076/070)
        │
        ▼
  EP-133-134 (Education) ── EP-135-137 (Market) ── EP-138-139 (Family)
        │
        ▼
  EP-140 (Unified Knowledge Architecture, capstone — depends on
          everything above that produces or classifies knowledge)
```

Checked and clean:
- **No circular dependencies**: Universal Engines (075/076) depend
  only on Core; every Level-3 EP depends downward only.
- **No Core dependency on a future domain capability**: Core (069-074)
  never references a domain EP.
- **No capability-specific Core architecture**: EP-069.4's Capability
  model has no field specific to any one domain.
- **External capabilities never bypass security**: every adapter path
  in §5 routes through EP-070/EP-069.6 before execution.
- **Verification exists where autonomy requires it**: EP-072
  (general) and EP-074.1 (dynamic-workflow-specific) both end in an
  evaluate/verify/recover step before any learning promotion (EP-122).

---

## 7. Traceability matrices

### 7.1 Existing Jarvis subsystem → new roadmap

| Existing subsystem | Future EP(s) | Status |
|---|---|---|
| `src/core/tool` | EP-069.4/.5/.7 | Extended |
| `src/core/agent`, `planning`, `execution`, `plan_execution` | EP-074.1 | Extended |
| `src/core/workflow_engine`, `workflow_scheduler`, `scheduler` | EP-074.1 | Extended |
| `src/core/memory`, `long_term_memory` | EP-114 | Extended (unchanged scope) |
| `src/core/knowledge`, `rag`, `retrieval`, `embedding`, `semantic`, `indexing` | EP-075, EP-076 | Extended, orchestration layer added |
| `src/core/collaboration` | EP-119 | Extended (overlap flagged, §4) |
| `src/core/git`, `github` | EP-077 (was EP-075) | Extended (overlap flagged, §4, with EP-069.4-.7) |
| `src/core/automation_engine` | EP-051 (pre-existing) / EP-073 | Overlap flagged, §4 |
| EP-069.1/.2/.3 (fallback) | EP-069 remainder | Preserved unchanged, reused everywhere |

### 7.2 ECC → Jarvis

| ECC concept | Jarvis equivalent | Coverage | Future EP | Adoption reason |
|---|---|---|---|---|
| plan → implement → review → verify loop | planning/execution/plan_execution (Core) | Already covered | EP-072, EP-074.1 | Same loop shape already exists; extended, not re-architected. |
| Skill promotion from repeated wins | none | Missing | EP-122 | New Continuous Learning engine adopts this idea, generalized beyond coding tasks. |
| AgentShield security scanning | none | Missing | EP-069.6 | Adopted as supply-chain/permission inspection for external capabilities specifically (not a general code-security product). |
| 68 specialized agents / skills-first surface | `src/core/agent`, `plugins` | Partially covered | EP-069.4/.5 | Jarvis's model is capability discovery over a registry, not a large fixed agent roster — concept adapted, not the roster itself. |
| Continuous learning / instincts | none | Missing | EP-122 | Adopted, renamed to fit Jarvis's Memory≠Knowledge≠Learning split (brief §14). |
| Multi-harness/IDE adapters, marketplace, npm packages, Discord community, pricing tiers | n/a | Not relevant | — | ECC's distribution/business model has no Jarvis analog; rejected as out of scope. |
| Framework-specific skills (React/Vue/etc. within ECC's 291 skills) | n/a | Not relevant | — | Explicitly excluded per brief §13 — these are content, not Jarvis Core architecture. |

### 7.3 Future capability → infrastructure

| Future capability | Infrastructure it depends on |
|---|---|
| Social Intelligence (Scenario A) | EP-075 (research), EP-088-091 (social capability layer) |
| Market/Career Intelligence (Scenario B) | EP-075, EP-135-137 |
| Personal Teacher (Scenario C) | EP-114 (memory), EP-122 (learning), EP-133-134 |
| Universal Research (Scenario D) | EP-075 directly |
| Universal Documents (Scenario E) | EP-076 directly, EP-082-087 for AI-generated slide content |
| Unknown Task (Scenario F) | EP-074.1, EP-069.5, EP-072 |
| Local GitHub Tool (Scenario G) | EP-069.4/.5/.6/.7, EP-070, EP-077 |
| External API (Scenario H) | EP-069.4/.5, EP-071, EP-072 |
| External Website (Scenario I) | EP-069.4, EP-073, Global Security Principles |
| Browser-only Service (Scenario J) | EP-073, EP-069.6, EP-070 |

---

## 8. Six-scenario validation (first pass)

| Scenario | Existing infra used | New infra required | External capabilities | Core changes required? |
|---|---|---|---|---|
| A. Social Intelligence | knowledge/rag/embedding | EP-075, EP-088-091 | Social platform APIs (via EP-069.4) | No |
| B. Market/Career Intelligence | knowledge/rag | EP-075, EP-135-137 | Market data APIs | No |
| C. Personal Teacher | memory/long_term_memory | EP-122, EP-133-134 | None required | No |
| D. Universal Research | rag/retrieval/embedding | EP-075 | Search APIs (via EP-069.4) | No |
| E. Universal Documents | knowledge/indexing | EP-076, EP-082-087 | None required | No |
| F. Unknown Task | planning/execution/workflow_engine | EP-074.1, EP-069.5 | Any, discovered at runtime | No |

No scenario required a Core rewrite — the architecture holds.

---

## 9. PASS 2 — Adversarial self-audit

Run as an independent senior-architect review of §1–8 above.

- **Existing Jarvis preserved?** Yes — no completed EP (001-069) was
  rewritten; EP-069.1/.2/.3 completion status is repeated verbatim,
  not reinterpreted. EP-051/EP-119 overlaps are flagged, not silently
  resolved by rewriting historical text.
- **Core truly universal?** Checked — EP-069.4's Capability schema was
  reviewed for domain-specific fields; it has none. Level-3 EPs each
  carry their own domain logic (claim analysis, social publishing,
  etc.) and none of it leaked into EP-069-076.
- **External capabilities unified and secured?** Checked against
  brief §27's own checklist: local GitHub projects (EP-069.4/.6),
  local CLI (same), REST APIs (EP-069.4/.5, EP-071), external web
  services (EP-069.4, EP-073), browser automation (EP-073, gated by
  EP-070) — all covered, all through one abstraction, all policy-
  gated, all versionable/revocable (EP-069.7).
- **Research and Documents genuinely domain-independent?** Checked —
  EP-075 and EP-076's `docs/BACKLOG.md` entries carry explicit
  "NO DUPLICATE" clauses forbidding domain-specific forks, and three
  old domain-specific proposals (EP-097/127/130) were folded into them
  specifically to prevent that fork from happening by omission.
- **Learning distinct from Memory/Knowledge?** Checked — EP-122
  (learning/promotion) is kept separate from EP-114 (memory, raw
  storage) and EP-075/076/113 (knowledge, structured retrieval) in
  §3's layer diagram and in the EP-122 backlog entry.
- **Agents discover capabilities dynamically? Autonomous execution
  verified?** Yes — EP-074.1 explicitly routes through EP-069.5
  (discovery) and ends in evaluate/verify/recover before learning.
- **EP-069.1 fallback duplicated anywhere?** Checked by grep across
  the rebuilt sections — zero new provider-fallback language; every
  reference reuses EP-069 by name.
- **Dependencies coherent, no artificial EPs, none too broad/narrow?**
  Checked in §6. The three MERGE dispositions (§2) were the main risk
  of either an artificially narrow retired EP or an overly broad
  merged target; both new engines carry explicit "NO DUPLICATE"
  guardrails to keep them from becoming catch-alls.

**Second validation (G–J, external capability scenarios):** confirmed
via §7.3 and §5 — discovery (EP-069.5), registration/metadata
(EP-069.4), policy (EP-070), permissions (EP-069.6), execution
(EP-072/EP-073), verification (EP-072), provenance (EP-069.4/.6), and
lifecycle/revocation (EP-069.7) each have a named owner for all four
scenarios. No gaps found requiring a design revision.

No revision to §1–8 was needed as a result of this audit; the two
overlap findings that surfaced (EP-051/EP-073, EP-119/collaboration)
were already flagged during PASS 1 and are intentionally left as
flags rather than resolved guesses.

---

## 10. Unresolved questions (for the project owner)

1. Should EP-051 (Phase 8, pre-EP-069) be completed as originally
   scoped, or should its remaining work be folded into EP-073 now,
   before either is implemented? This rebuild did not decide this — it
   is outside the EP-069–140 range this task was scoped to edit.
2. EP-069.4–.7 are scoped narrowly (abstraction, discovery, security,
   lifecycle) to avoid becoming a fifth "mega-EP" under EP-069; a
   future STEP 1 may find that EP-069.6 (security) is large enough to
   deserve its own top-level EP number rather than a sub-package —
   left as a judgment call for that STEP 1.
3. EP-116 and EP-119 are flagged as overlapping rather than merged
   outright (§4, item 2–3); a future STEP 1 with real code inspection
   should make the final call.

---

## FINAL REPORT

**A. Repository inspected**: `docs/architecture/JARVIS_ROADMAP.md`,
`docs/BACKLOG.md` (full "Long-Term Roadmap" section), `PROJECT_MANIFEST.md`
(no stale EP-070-140 references found), `src/core/*` directory
structure and file counts for tool/agent/planning/execution/workflow/
memory/knowledge/rag/retrieval/embedding/semantic/indexing/
collaboration/git/github/automation_engine, and `affaan-m/ECC`'s
README and top-level structure.

**B. Files changed**:
- `docs/BACKLOG.md`
- `docs/architecture/JARVIS_ROADMAP.md`
- `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md` (new, this file)

**C. Files intentionally unchanged**: all source code, tests,
configuration, dependencies, and runtime behavior. `PROJECT_MANIFEST.md`
was inspected and required no changes (it contains no EP-070-140
references). No other documentation file in the repository references
EP-075 through EP-138 (verified by repository-wide search), so no
further index/catalog synchronization was needed.

**D. Existing roadmap disposition**: see §2's full table — 3 items
MERGED (with retired placeholders), the rest KEPT and renumbered by a
uniform +2 shift to make room for the two new Universal Engine EPs,
plus targeted sub-package additions to EP-069 and EP-074. No item was
removed without a trace and no artificial EP was created.

**E. ECC integration**: see §7.2. Adopted (adapted): verify-before-
promote loop, skill/capability promotion from repeated success,
supply-chain security scanning (as EP-069.6). Already covered by
existing Core: the plan → execute → review loop shape. Rejected as
not relevant: ECC's distribution model, IDE/harness adapters, and
framework-specific skill content.

**F. New architecture**: Core (mostly implemented EP-001–069, plus
EP-069.4-.7 and EP-074.1) → Universal Engines (new EP-075/076, plus
existing memory/knowledge Core and EP-122 learning) → Capabilities
(EP-082–140, renumbered). See §3.

**G. External Capability Architecture**: see §5 — one Capability
abstraction (EP-069.4) behind Capability Discovery (EP-069.5), gated
by Policy (EP-070) and Supply-Chain Security (EP-069.6), executed
through the existing Tool Execution (EP-072) and Browser Automation
(EP-073), with Credential isolation (EP-071) and Lifecycle management
(EP-069.7) — covering local GitHub projects/CLI, REST APIs, external
web services, and browser-only services through the same pipeline.

**H. Universal Engines**: Universal Research & Discovery (EP-075) and
Universal Document Intelligence (EP-076) are new; Dynamic Workflow
(EP-074.1), Learning/Evolution (EP-122), Evaluation/Verification
(EP-072), Multi-Agent orchestration (existing `src/core/collaboration`
+ EP-119), and Model/Provider intelligence (EP-069, already mostly
complete) are existing or lightly-extended systems reused rather than
rebuilt. See §3, §6.

**I. Six core scenarios**: see §8 — all six validated with no required
Core change.

**J. External capability scenarios (G–J)**: see §7.3 and §9 — all four
validated with a named owner at every stage (discovery → registration
→ policy → execution → verification → provenance → lifecycle).

**K. Audit result**: **PASS**
