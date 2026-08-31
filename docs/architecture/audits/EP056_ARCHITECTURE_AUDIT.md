# EP-056 — Capability Registry — Architecture Audit (STEP 3)

**Verdict (after STEP 4 remediation): EP-056 STEP 3 — PASS AFTER REMEDIATION**

This audit was performed in two passes, following the same precedent
`EP052_ARCHITECTURE_AUDIT.md`/`EP055_ARCHITECTURE_AUDIT.md` already
established: the first pass (this document's original text, Sections
1-17 below, unmodified) identified one blocking finding. The owner
reviewed it, approved Owner Decision D8 (Section 17), and directed a
STEP 4 remediation. Section 18 below records that remediation and its
independent verification. Nothing in Sections 1-17 has been edited or
reworded to hide or soften the original finding — it is preserved
verbatim below, exactly as the first pass recorded it.

---

## 1. Scope of this audit

Audited against `docs/architecture/designs/EP056_DESIGN.md`,
`AI_GENERATION_STANDARD.md`, `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md`,
and the EP-054/EP-055 audit conventions (severity taxonomy, structure,
and independent-verification methodology established by
`docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md`/
`EP055_ARCHITECTURE_AUDIT.md`):

- `src/skills/capability_registry/skill.py`
- `src/bootstrap.py` (EP-056-relevant sections)
- `src/modules/test_module.py` (EP-056 test registration)
- `config/config.yaml` (`capability_registry:` block)
- `tests/EP056/__init__.py`, `tests/EP056/test_capability_registry.py`

Inspected for precedent/integration-boundary verification only (no
modification made or authorized to any of these):

- `src/core/plugins/plugin.py`, `plugin_manifest.py`,
  `plugin_registry.py`, `plugin_loader.py`, `plugin_discovery.py`
  (EP-010 Plugin system)
- `src/services/plugin_service.py`
- `src/core/ai/prompt.py`, `prompt_builder.py`, `prompt_manager.py`
  (EP-017 Prompt Engine)
- `src/core/command_router.py`
- `src/services/ai_service.py`
- `src/core/config.py`
- `src/skills/reflection/skill.py`, `src/skills/prompt_optimizer/skill.py`
- `src/core/agent/agent_engine.py`, `src/core/tool/tool.py`,
  `src/core/planning/planning_engine.py`, `src/core/scheduler/scheduler.py`

**File-scope baseline used for this audit:** `find . -newer
CHANGELOG.md` (`CHANGELOG.md`'s own last edit was the final act of
EP-055's STEP 4, strictly predating every EP-056 change) —
independently re-derived by this audit, not copied from the STEP 2
report, and confirmed to return exactly the same seven files the
STEP 2 report claimed (Section 12). **In addition**, every file in
the "DO NOT MODIFY" list above was byte-compared (`diff`) against the
original, pre-EP-056 repository archive — not merely timestamp-
checked — and every one is confirmed **byte-identical** (Section 12).
`src/skills/prompt_optimizer/skill.py` and
`docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md` (EP-055's own
STEP 4 outputs, which legitimately differ from the pristine archive)
were separately confirmed byte-identical to their EP-055-STEP-4-final
state, i.e. untouched by EP-056.

---

## 2. Owner Decisions D1–D7 verification table

| Decision | Approved requirement | Implementation evidence | Result |
|---|---|---|---|
| D1 | Candidate A: on-demand Capability Registry composing already-declared Plugin capability data plus `CommandRouter` namespace names, no new backend Protocol | `CapabilityRegistryModule` (`src/skills/capability_registry/skill.py`) composes `PluginService.running_plugins()` and a `module_names` callable directly — no `backend.py` exists under `src/skills/capability_registry/` (confirmed: `ls` shows only `skill.py`). No new data model was introduced; `Plugin.capabilities` (EP-010) is read, never modified. | **PASS on architecture; see Finding 1 for a runtime defect in the `module_names` wiring specifically** |
| D2 | Include `capability inject` in v1 | `_inject()` action exists, calls `PromptManager.build(capabilities=[...])`, returns `Prompt.rendered`. Confirmed present in `self._actions` and in `HELP_TEXT`. | **PASS on presence; see Finding 1 — the action itself crashes in real wiring** |
| D3 | No separate privacy/AI-provider gate | `config/config.yaml`'s `capability_registry:` block contains exactly one key, `enabled` — no second gate, no resource/rate-limit key (confirmed by `diff`, Section 12). `_gate()` checks only `capability_registry.enabled`. | **PASS** |
| D4 | Command namespace: `capability` | `CapabilityRegistryModule.name` returns the literal string `"capability"`; confirmed via `_test_command_router_dispatch_matches_direct_execute` (re-run) and this audit's own direct dispatch probe (Section 9). No namespace collision — `router.register()` succeeded without its own duplicate-namespace `ValueError` firing (confirmed by every successful `Bootstrap.initialize()` call in this audit's own probes). | **PASS** |
| D5 | Register at the existing `plugin_service` bootstrap location | Confirmed by `diff` (Section 12): the new registration block is inserted immediately after `router.register(PluginModule(plugin_service))`, strictly after `plugin_service`'s own construction, not alongside `ai_provider_manager`/`prompt_manager`. | **PASS** |
| D6 | Real `PromptManager` in `capability inject` integration tests | `tests/EP056/test_capability_registry.py`'s `_real_prompt_manager()` constructs an actual, unmodified `PromptManager(config=...)` — confirmed by code reading; `_test_inject_returns_rendered_prompt_containing_summary_and_text` and `_test_inject_error_translated_to_failed_command_result` both use it, the latter triggering a **real** `PromptValidationError` via a deliberately tiny `prompt.max_prompt_size`, not a mocked one. | **PASS on test-construction faithfulness; ironically, this is also why the suite could not have caught Finding 1 — see Section 8** |
| D7 | `CommandRouter`, not Tool Engine | `CapabilityRegistryModule` implements exactly the `CommandModule` Protocol (`name` property, `execute(action, arguments)`); zero import of `src.core.tool` anywhere in `src/skills/capability_registry/`. | **PASS** |

**D1–D7's literal text is implemented correctly. The blocking finding
(Section 15) is a runtime defect in how `bootstrap.py` wires one of
`CapabilityRegistryModule`'s three constructor dependencies — it does
not represent a violation of any Owner Decision's own wording, but it
does mean the feature Owner Decisions D1/D2 approved does not actually
work when exercised end-to-end.**

---

## 3. Architecture audit

- **No new backend Protocol** (D1/Section 6.2 of the design) —
  confirmed: `src/skills/capability_registry/` contains only
  `skill.py`; no `backend.py`. Correct, and consistent with
  `EP056_DESIGN.md`'s own stated reasoning (no new external I/O
  surface).
- **`CapabilityRegistryModule` owns command parsing, validation,
  gating, and summary composition** — confirmed by direct code
  reading: argument-shape validation, `_gate()`, `_compose_summary()`,
  and `PromptValidationError`/`PromptTemplateNotFoundError` →
  `CommandResult` translation all live exclusively in `skill.py`.
  Neither `PluginService` nor `CommandRouter` nor `PromptManager` was
  modified to add any of this logic.
- **Gate-ordering correctly applies the EP-055 STEP 4 lesson** —
  confirmed by direct code reading: in both `_list()` and `_inject()`,
  argument-shape validation (no side effects) runs first, then
  `self._gate()`, and only then any read of `PluginService`/
  `module_names`/`PromptManager`. This is the exact ordering
  `PromptOptimizerModule`'s own STEP 4 remediation (Owner Decision
  D10) established as the project's convention, and
  `CapabilityRegistryModule` applies it correctly from its first
  version — no analogous Finding 1/2-style ordering defect exists
  here (independently verified by this audit's own probes, Section 9).
- **`PluginBuilder`/`PromptManager`/EP-010 Plugin internals are never
  modified** — confirmed by import inspection of
  `src/skills/capability_registry/skill.py`: the only relevant
  imports are `PromptTemplateNotFoundError`/`PromptValidationError`
  (exception types only, reused not reimplemented, exactly matching
  `EP055_DESIGN.md` Section 10's established convention),
  `PromptManager` (type hint only), and `PluginService` (type hint
  only). No `Plugin`/`PluginManifest`/`PluginRegistry` construction or
  mutation occurs anywhere in this module.
- **Bootstrap wiring architecture (placement, dependency order)
  follows established project conventions and correctly honors the
  D5 ordering constraint** — confirmed: the registration block sits
  immediately after `plugin_service`'s own construction/registration,
  exactly as `EP056_DESIGN.md` Section 3.8/14 required, and strictly
  before `prompt_manager` would ever need to be re-referenced (it is
  already in scope from its own earlier construction). **However, one
  of the three dependency values passed at this registration site is
  itself incorrect — see Finding 1 immediately below**, which is an
  implementation defect in *what* is passed, not in *where* the
  registration is placed.
- **No duplicate registration exists** — confirmed both statically
  (exactly one `router.register(CapabilityRegistryModule(...))` call)
  and structurally (`CommandRouter.register()`'s own duplicate-
  namespace `ValueError`, confirmed unmodified, never fired in any of
  this audit's own successful `Bootstrap.initialize()` runs).
- **No unnecessary coupling** — confirmed by import inspection: zero
  references to `src.skills.desktop`, `src.skills.browser`,
  `src.skills.files`, `src.skills.vision`, `src.skills.reflection`,
  `src.skills.prompt_optimizer`, `src.core.tool`, `src.core.agent`,
  `src.core.planning`, or `src.core.scheduler` anywhere in
  `src/skills/capability_registry/skill.py`.

### Finding 1 (architecture-level root cause, detailed fully in Section 15)

`src/bootstrap.py`'s registration call passes `module_names=router.
module_names`. `CommandRouter.module_names` (`src/core/command_router.py`,
confirmed unmodified) is declared `@property`, not a plain method —
accessing `router.module_names` therefore **evaluates the property
immediately** and yields a `list[str]`, not a callable reference to
the property's getter. `CapabilityRegistryModule.__init__`'s own
constructor signature and docstring (`module_names: Callable[[],
list[str]]`, "injected as a callable rather than the router itself")
correctly document the *intended* contract, and `_compose_summary()`
correctly calls `self._module_names()` to honor that contract — but
the value `bootstrap.py` actually supplies does not satisfy it. Every
call to `_compose_summary()` (i.e. every `capability list` and every
`capability inject` call) raises `TypeError: 'list' object is not
callable`.

**Result: FAIL — this is the central finding of this audit, detailed
fully in Section 15.**

---

## 4. Command/functionality audit

| Behavior | Verified against | Result |
|---|---|---|
| `capability help` | Returns the exact `HELP_TEXT` constant; independently re-executed via both `module.execute()` and the real, enabled `CommandRouter.dispatch()` (Section 9). | PASS |
| `capability list` — valid call, feature enabled, **real Bootstrap wiring** | This audit's own direct probe (Section 9): `bootstrap.command_router.dispatch("capability list")` → `CommandResult(success=False, message="Internal error while executing 'capability list'.")`, caused by the real `TypeError` (Section 3/15). | **FAIL** |
| `capability inject <text>` — valid call, feature enabled, **real Bootstrap wiring** | Same probe: `dispatch("capability inject hi there")` → identical `TypeError`-caused "Internal error" failure. | **FAIL** |
| `capability list` — valid call, **fake collaborators (registered test suite)** | `_test_list_composes_plugin_and_namespace_summary`/`_test_list_empty_state_reports_none_without_raising` (re-run): pass, because the suite's `_FakeModuleNames` is deliberately callable, masking Finding 1 entirely. | PASS (misleadingly, given Finding 1 — see Section 8) |
| `capability inject <text>` — valid call, **fake `module_names`, real `PromptManager` (registered test suite)** | `_test_inject_returns_rendered_prompt_containing_summary_and_text`/`_test_inject_error_translated_to_failed_command_result` (re-run): pass, for the same reason. | PASS (misleadingly, given Finding 1) |
| `capability list` — extra argument | Rejected with a usage error and zero downstream calls (`_test_list_rejects_arguments`, re-run). | PASS |
| `capability inject` — missing text | Rejected with a usage error and zero downstream calls (`_test_inject_rejects_no_arguments`, re-run). | PASS |
| Unknown action | Rejected with a clear "Unknown command" message (`_test_unknown_action_returns_failure`, re-run). | PASS |
| Direct execution vs. `CommandRouter` dispatch equivalence | `_test_command_router_dispatch_matches_direct_execute` (re-run) — uses `help`, which does not reach the broken code path, so this test passes without exercising Finding 1 either. | PASS (does not exercise the defect) |

**Result: FAIL.** The two actions that constitute this EP's entire
functional purpose (`list`, `inject`) are completely non-operational
in real, production `Bootstrap` wiring, while `help` and every
argument-validation/gate path work correctly.

---

## 5. Security and capability-gate audit

| Check | Method | Result |
|---|---|---|
| `capability_registry.enabled` gate blocks `PluginService`/`module_names`/`PromptManager` access | Code reading (`_gate()` called before any dependency access in every code path) + `_test_disabled_rejects_list_with_zero_downstream_calls`/`_test_disabled_rejects_inject_with_zero_downstream_calls` (re-run) + independent mutation test (Section 8) — deleting the gate check caused 9 test failures | PASS |
| No AI-provider call exists anywhere (Owner Decision D3) | Confirmed by import inspection: no `AIProvider`/`ProviderManager` import anywhere in `skill.py` | PASS |
| No filesystem write exists anywhere | Confirmed by `grep`: zero `write_text`/`open(..., "w"/"a")` call anywhere in `skill.py` | PASS |
| Disclosure is no greater than the existing `plugin status`/`plugin info` commands (Owner Decision D3's own reasoning) | This audit compared `capability list`'s composed fields (`id`, `name`, `description`, `capabilities`) against `plugin_module.py`'s own already-existing `plugin info` output fields — confirmed identical field set, no additional disclosure | PASS |
| No shell/subprocess/code execution | Confirmed by import inspection: no `subprocess`/`os.system`/`eval`/`exec` anywhere in `skill.py` | PASS |
| Gate-ordering (post-EP-055-Finding-1/2 lesson) | Confirmed correctly applied — shape validation precedes the gate, the gate precedes every dependency read, in both `_list()` and `_inject()` (Section 3, Section 9) | PASS |

**No security defect was found.** Finding 1 (Section 15) is a
functional/reliability defect, not a security bypass or disclosure
issue — the gate itself works correctly; the code it protects is
simply broken once reached.

**Result: PASS** (security-specific scope only; see Section 4/15 for
the separate, blocking functional finding).

---

## 6. Configuration and limits audit

- `config/config.yaml`'s `capability_registry:` block contains
  exactly `enabled` (`false`) — matching Owner Decisions D1/D3
  exactly, with no extraneous key.
- The pre-existing `prompt:`/`prompt_optimizer:`/`plugins:` blocks are
  confirmed byte-identical to their pre-EP-056 state (Section 12) —
  EP-056's new block is inserted immediately after `prompt_optimizer:`,
  with a comment explicitly explaining the deliberate reuse of
  EP-010/EP-017 without modification.
- `capability_registry.enabled` is read fresh on every call via
  `self._config.get(...)`, never cached at construction — confirmed
  by code reading (`_is_enabled()` is called from `_gate()`, which is
  called from within each action handler, not from `__init__`).
- `Config.get()`'s dotted-path lookup was independently verified by
  this audit to correctly return the documented default (`False`)
  when the entire `capability_registry:` section is absent from
  config (`_test_bootstrap_config_defaults_capability_registry_disabled`,
  re-run).

**Result: PASS.**

---

## 7. Provider/Plugin/Prompt Engine integration audit

- **Plugin integration**: `PluginService.running_plugins()` is called
  and its result's `id`/`name`/`description`/`capabilities` fields are
  read directly — confirmed by code reading and by
  `_test_list_composes_plugin_and_namespace_summary`/
  `_test_list_empty_state_reports_none_without_raising` (re-run,
  against fake `PluginService` objects; no real `PluginService`
  integration test exists in the suite — see Section 8's note on why
  a fake was reasonable here but insufficient for `module_names`).
- **`CommandRouter.module_names` integration**: **broken** — see
  Finding 1 (Section 15). This is the one dependency where a fake
  collaborator's interface did not match the real component's actual
  runtime contract.
- **Prompt Engine integration (`capability inject`)**: `PromptManager.
  build(capabilities=[...])` is called with a real, unmodified
  `PromptManager` in the registered suite (Owner Decision D6,
  confirmed by code reading) — this is the one part of Candidate A
  that **is** genuinely, faithfully tested end-to-end, and this audit
  confirms it works correctly both via the registered suite (re-run)
  and via this audit's own direct `module.execute("inject", [...])`
  probe against fake `PluginService`/`module_names` collaborators
  (Section 9) — the Prompt Engine integration itself is not implicated
  in Finding 1 at all; the crash occurs in `_compose_summary()` before
  `PromptManager.build()` is ever reached.

**Result: PARTIAL FAIL** — Plugin and Prompt Engine integrations are
correct; the `CommandRouter.module_names` integration is broken
(Finding 1).

---

## 8. Test quality audit — independently re-verified, and the specific reason the suite missed Finding 1

This audit did not simply trust the STEP 2 report's "51/0/0" claim,
nor stop at re-running it.

1. **Re-ran `tests/EP056/test_capability_registry.py` from a clean
   process** (after clearing all `__pycache__` directories) —
   reproduced exactly **51 passed / 0 failed / 0 skipped**. Also
   independently re-ran the six regression suites and reproduced
   their exact figures: EP-055 64/0/0, EP-054 76/0/0, EP-053 58/0/0,
   EP-052 135/0/0, EP-051 105/0/0, EP-050 112/0/0.
2. **Performed two independent mutation tests** against isolated
   scratch copies (never touching the audited repository):
   - **Mutation 1** — disabled the `capability_registry.enabled` gate
     (`return None` unconditionally in `_gate()`). Result: **9 tests
     failed** (42 passed / 9 failed). The suite genuinely detects a
     broken gate.
   - **Mutation 2** — broke the plugin-capability-tag composition
     logic inside `_compose_summary()`. Result: **3 tests failed** (48
     passed / 3 failed). The suite genuinely detects broken summary
     logic, when reached through the fake collaborators.
3. **Went beyond the registered suite and every prior EP's own audit
   methodology** by directly exercising the real, fully-wired
   `Bootstrap` with `capability_registry.enabled: true` — something
   *no test in the registered suite does* (confirmed by exhaustive
   `grep` of every `_write_capability_registry_bootstrap_config` call
   site in the test file: every one passes
   `capability_registry_section=""`, i.e. disabled/absent; the one
   `dispatch("capability list")` call in the suite,
   `_test_bootstrap_capability_actions_report_disabled_message`,
   deliberately tests the *disabled* path, which returns before
   `_compose_summary()` is ever reached). This direct exercise is what
   surfaced Finding 1.

**Root cause of the coverage gap:** the registered suite's
`_FakeModuleNames` fixture is deliberately implemented as a callable
object (`__call__` defined) — a faithful match to
`CapabilityRegistryModule`'s own *documented* constructor contract
(`module_names: Callable[[], list[str]]`). This is not sloppy test
authorship; the fake correctly implements the intended interface. The
defect is that `src/bootstrap.py`'s actual wiring does not supply a
value satisfying that interface — `router.module_names` is a
`@property`, so accessing it as an attribute (rather than calling it,
which is impossible, or wrapping it in a callable) yields an
already-evaluated `list[str]`, not a bound method. **No unit test
using a fake collaborator could have caught this**, because a
correctly-written fake, by construction, satisfies the interface the
real code is supposed to (but does not) provide. Only a test that
constructs the *real* `CommandRouter`/`Bootstrap` and passes its real
`module_names` property through the real wiring path would surface
the mismatch — and `EP056_DESIGN.md` Section 12's own testing strategy
did not call for this specific combination (its `Bootstrap` wiring
tests test the disabled path only; its "real, non-fake" commitment,
Owner Decision D6, was scoped to `PromptManager`, not to
`module_names`).

**Conclusion: the 51 passing assertions are not hollow** — mutation
testing proves they detect real regressions in every code path they
actually exercise. But **they do not exercise the specific
integration point where the real defect lives** (`CommandRouter.
module_names`'s real type vs. the fake's type), and this is a gap in
what the design's own testing strategy asked for, not a gap in test
implementation quality.

**Result: FAIL** (test-quality assessment is otherwise PASS, but the
suite's coverage is insufficient to have caught a 100%-reproducible,
blocking functional defect — recorded as part of Finding 1, not as a
separate finding, since it is the direct cause of Finding 1 escaping
STEP 2).

---

## 9. Edge-case evidence log (for Finding 1)

- **Real, enabled `Bootstrap` probe — `capability list`:** with
  `capability_registry.enabled: true` in a real, temporary
  `config.yaml`, and a real `Bootstrap.initialize()` run to
  completion, `bootstrap.command_router.dispatch("capability list")`
  returned `CommandResult(success=False, message="Internal error
  while executing 'capability list'.")`. Calling
  `module.execute("list", [])` directly (bypassing `dispatch()`'s
  catch-all) surfaced the underlying exception:
  `TypeError: 'list' object is not callable`, raised at
  `src/skills/capability_registry/skill.py` line 309
  (`namespaces = sorted(self._module_names())`).
- **Real, enabled `Bootstrap` probe — `capability inject`:** same
  setup; `dispatch("capability inject hi there")` returned the
  identical `"Internal error"` failure, with the identical underlying
  `TypeError` at the identical line (`_compose_summary()` is shared by
  both actions).
- **Real, enabled `Bootstrap` probe — `capability help`:** returned
  `CommandResult(success=True, ...)` with the exact `HELP_TEXT`
  content — confirming `help` alone is unaffected, since it never
  calls `_compose_summary()`.
- **Root-cause confirmation:** a minimal, isolated probe
  (`CommandRouter().register(DummyModule()); type(router.module_names)`)
  confirmed `router.module_names` is of type `list`, not a bound
  method, and `callable(router.module_names)` returns `False` —
  directly confirming the property/callable type mismatch is the sole
  cause, not an unrelated `PluginService`/`PromptManager` issue.
- **Ordering-safety confirmation (no Finding-1/2-style disclosure
  issue, unlike EP-055):** this audit re-confirmed, via code reading
  and via the registered suite's own gate tests, that
  `capability_registry.enabled=false` correctly short-circuits before
  `_compose_summary()`/`PluginService`/`module_names`/`PromptManager`
  are ever reached in both `_list()` and `_inject()` — the ordering
  lesson from `EP055_DESIGN.md`'s STEP 4 remediation (Owner Decision
  D10) was correctly applied in EP-056's very first version.

---

## 10. Cross-platform audit

No OS-specific code exists anywhere in
`src/skills/capability_registry/skill.py` (confirmed by `grep` for
`platform.system`/`sys.platform`: zero matches) — consistent with
`EP056_DESIGN.md`'s own Section 11 ("none anticipated").

**Result: PASS.**

---

## 11. Backward compatibility audit

- No existing manager's method signature, return type, or behavior
  changes. `PluginService`, `CommandRouter`, `PromptManager` are all
  confirmed byte-identical (Section 12) and are used exclusively
  through their existing, unmodified public APIs.
- No existing config key's meaning or default changes.
- No existing `CommandModule` is affected — confirmed via
  `_test_bootstrap_other_modules_unaffected_when_capability_registry_absent`
  (re-run), which dispatches `system version`, `plugin help`, `reflect
  help`, and `prompt help` against a real `Bootstrap` and confirms all
  four succeed unaffected by EP-056's wiring, and via this audit's own
  additional probe (Section 9) confirming `plugin`/`reflect`/`prompt`
  all continue to function correctly alongside the broken
  `capability` actions in the same running process.
- **Finding 1 does not regress any other component** — it is fully
  contained within `CapabilityRegistryModule`'s own two actions; no
  other namespace, service, or manager is affected by the defect.

**Result: PASS** (compatibility, as distinct from the new feature's
own functionality, is fully preserved).

---

## 12. File-scope audit (final)

Independently re-derived in this audit via `find . -newer CHANGELOG.md
-type f` (after clearing all `__pycache__` directories; `CHANGELOG.md`'s
own last edit was the final act of EP-055's STEP 4, strictly predating
every EP-056 change), and additionally cross-checked by byte-comparing
(`diff`) every DO-NOT-MODIFY file against the original, pre-EP-056
repository archive:

| File | Status | Within approved EP-056 scope? |
|---|---|---|
| `config/config.yaml` | Modified (additive `capability_registry:` block only) | Yes (MODIFY) |
| `src/bootstrap.py` | Modified (one additive import, one additive registration block, confirmed by `diff` to touch nothing else) | Yes (MODIFY) |
| `src/modules/test_module.py` | Modified (one additive import line) | Yes (MODIFY) |
| `src/skills/capability_registry/skill.py` | Created | Yes (CREATE) |
| `tests/EP056/__init__.py` | Created | Yes (CREATE) |
| `tests/EP056/test_capability_registry.py` | Created | Yes (CREATE) |
| `docs/architecture/designs/EP056_DESIGN.md` | Modified (STEP 1 → STEP 2 status/approval-checklist edit only) | Yes (design-doc update, matching EP-055's own precedent) |

**No other file in the repository shows a modification timestamp
newer than `CHANGELOG.md`'s own EP-055-STEP-4-final edit.** All seven
files exactly match the approved EP-056 STEP 2 file scope; none is
unauthorized.

**DO NOT MODIFY verification**, checked by direct byte-comparison
(`diff`) against the original, pre-EP-056 repository archive:

| File | Result |
|---|---|
| `src/core/plugins/plugin.py`, `plugin_manifest.py`, `plugin_registry.py`, `plugin_loader.py`, `plugin_discovery.py` | **Byte-identical.** EP-010 Plugin system untouched. |
| `src/services/plugin_service.py` | **Byte-identical.** |
| `src/core/ai/prompt.py`, `prompt_builder.py`, `prompt_manager.py` | **Byte-identical.** EP-017 Prompt Engine untouched. |
| `src/core/command_router.py` | **Byte-identical.** `CommandModule`/`CommandResult`/`CommandRouter`/`module_names` confirmed unchanged from the interface `CapabilityRegistryModule` was designed against — the property/callable mismatch (Finding 1) is a wiring defect in `bootstrap.py`, not a `CommandRouter` regression. |
| `src/services/ai_service.py` | **Byte-identical.** Never imported by `CapabilityRegistryModule`. |
| `src/core/config.py` | **Byte-identical.** |
| `src/skills/reflection/skill.py` | **Byte-identical.** |
| `src/skills/prompt_optimizer/skill.py` | **Byte-identical to its EP-055 STEP 4 final state** (not the pristine archive, since EP-055 legitimately modified it; separately confirmed against the last known-good EP-055 output). |
| `src/core/agent/agent_engine.py`, `src/core/tool/tool.py`, `src/core/planning/planning_engine.py`, `src/core/scheduler/scheduler.py` | **Byte-identical.** Untouched, and zero reference to any of them anywhere in `src/skills/capability_registry/`. |
| `docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md` | **Byte-identical to its EP-055 STEP 4 final state.** |
| Every other prior EP's design/audit document, `JARVIS_ROADMAP.md`, `docs/BACKLOG.md`, `docs/RELEASE_NOTES.md` | **Untouched** — none appear in the modified-file list. |

`__pycache__` directories generated by this audit's own test runs and
mutation-test scratch copies were cleared before the final file-scope
check; the mutation-test scratch copies themselves were created under
separate working directories, never touching the audited repository,
and were deleted immediately after use.

**Result: PASS** (file scope itself is exactly as approved; Finding 1
is a defect *within* the approved scope, not an out-of-scope change).

---

## 13. Design ↔ implementation consistency

| Design requirement (`EP056_DESIGN.md`) | Implementation | Consistent? |
|---|---|---|
| Section 6.1/6.2 — `CapabilityRegistryModule`, no new backend Protocol | Present exactly as specified | Yes |
| Section 6.3 — `capability help`/`capability list`/`capability inject <text>` | Confirmed present, matching the approved action table | Yes |
| Section 6.4 — read-only `PluginService`/`CommandRouter` access; `PromptManager.build(capabilities=...)` for `inject` only | `PluginService`/`PromptManager` integrations confirmed correct (Section 7); `CommandRouter.module_names` integration is **not** consistent with the design's own stated intent — Section 6.4's text and the constructor's own docstring both describe a live, call-time-evaluated callable, but the actual value wired in is a construction-time-evaluated list masquerading as one (Finding 1) | **Partial — see Finding 1** |
| Section 7 — `capability_registry.enabled` gate only, no separate privacy gate (D3) | Confirmed, functionally, for the gate itself; ordering correctly applies the EP-055 lesson (Section 3/9) | Yes |
| Section 8 — exact `capability_registry:` config block | Confirmed, matches verbatim | Yes |
| Section 9 — no new dependency | Confirmed — no new import outside the standard library and already-existing project modules | Yes |
| Section 10 — reuse `PromptValidationError`/`PromptTemplateNotFoundError`, no re-implementation | Confirmed — both exception types are imported from their existing, unmodified source module and reused, never redefined | Yes |
| Section 12/D6 — real, non-fake `PromptManager` for `capability inject`'s Prompt Engine integration test | Confirmed present and genuinely exercises the real `PromptManager` (Section 7/8) | Yes |
| Section 14 — exact CREATE/MODIFY/DO NOT MODIFY file scope | Confirmed (Section 12 above) | Yes |

**No out-of-scope architecture change, no unapproved dependency, and
no violation of any Owner Decision's literal text was found.** One
implementation defect (Finding 1) causes the *behavior* Owner
Decisions D1/D2 approved to not actually function, despite every
individual design element being present and structurally correct in
isolation.

---

## 14. Critical security/behavioral questions

1. **Can `capability list`/`capability inject` reach `PluginService`/
   `module_names`/`PromptManager` while
   `capability_registry.enabled=false`?** **NO.** Confirmed via
   mutation testing (Section 8) and this audit's own probes
   (Section 9) — the gate correctly blocks all three in every
   scenario tested.
2. **Do `capability list`/`capability inject` actually work when the
   feature is enabled, in real production wiring?** **NO — see
   Finding 1.** Both raise an uncaught `TypeError`, surfaced to the
   end user only as a generic "Internal error" message with no
   indication of the real cause.
3. **Does Finding 1 expose any information, bypass any gate, or grant
   any unintended capability?** **NO.** It is a pure reliability/
   availability defect — the failure mode is "the feature does
   nothing useful," not "the feature does something unsafe."
4. **Can `capability inject` write to `paths.prompts`/`config.yaml`/
   anywhere else, or autonomously change any other component's
   behavior?** **NO.** Zero write call exists anywhere in `skill.py`
   (confirmed by `grep`); `PromptManager.build()` only registers a new
   `Prompt` object in `PromptManager`'s own, already-existing internal
   registry, exactly as every other caller's `build()` call already
   does — not a new class of side effect.
5. **Does Finding 1 affect any other EP's namespace or component?**
   **NO.** Confirmed via this audit's own probe (Section 9/11) that
   `plugin`, `reflect`, and `prompt` all continue to function
   correctly in the same running, fully-initialized process where
   `capability` is broken.
6. **Is Finding 1 intermittent, environment-specific, or data-
   dependent?** **NO — it is 100% reproducible on every single call**
   to `capability list` or `capability inject`, regardless of how many
   plugins are running or what arguments are given, because it fires
   before any plugin- or argument-dependent logic executes
   (`sorted(self._module_names())` is unconditional in
   `_compose_summary()`).

---

## 15. Findings

### Finding 1 — `capability list`/`capability inject` are completely non-functional: `bootstrap.py` passes `CommandRouter.module_names` (a property, evaluated eagerly) where a live callable was required

**Severity: HIGH — BLOCKING**

**Description:** `src/bootstrap.py`'s EP-056 registration block reads:

```python
router.register(
    CapabilityRegistryModule(
        config=config,
        plugin_service=plugin_service,
        module_names=router.module_names,
        prompt_manager=prompt_manager,
    )
)
```

`CommandRouter.module_names` (`src/core/command_router.py`, confirmed
unmodified) is declared:

```python
@property
def module_names(self) -> list[str]:
    ...
    return list(self._modules.keys())
```

Because `module_names` is a `@property`, the expression `router.
module_names` in `bootstrap.py` **evaluates the property immediately**
at the moment `CapabilityRegistryModule(...)` is constructed,
producing a plain `list[str]` — not a reference to a callable. This
`list` is stored as `self._module_names` inside
`CapabilityRegistryModule.__init__`, whose own type hint
(`module_names: Callable[[], list[str]]`) and docstring both describe
a zero-argument callable, injected specifically so the namespace list
is read fresh, live, at request time (`EP056_DESIGN.md` Section 6.4,
and the constructor's own docstring: "injected as a callable rather
than the router itself"). `_compose_summary()` correctly honors that
intended contract by calling `self._module_names()` — but since the
actual value is a `list`, this raises:

```
TypeError: 'list' object is not callable
```

`_compose_summary()` is called, unconditionally, by both `_list()` and
`_inject()` immediately after the `capability_registry.enabled` gate
passes — so **every single successful call to either action**, in
real, production `Bootstrap` wiring, raises this exception.
`CommandRouter.dispatch()`'s own, unmodified, generic exception
handler (`except Exception as exc: ... return CommandResult(success=
False, message=f"Internal error while executing '...'.")`) catches
it, so the failure does not crash the process — but it does mean the
feature Owner Decisions D1/D2 approved is **completely inoperative**,
surfaced to any caller only as an uninformative "Internal error"
message with no indication of the real cause.

**Impact:** 100% functional failure of both `capability list` and
`capability inject` — the entirety of EP-056's user-facing purpose —
whenever `capability_registry.enabled: true` is set, which is the
only way to use the feature at all. `capability help` is unaffected
(it never calls `_compose_summary()`). No other namespace, service,
manager, or Owner Decision's *gate/security* behavior is affected —
this is a pure availability defect with no security or disclosure
implication (Section 14, question 3).

**Why the registered test suite did not catch this:** see Section 8
in full. In short: the suite's `_FakeModuleNames` fixture correctly
implements the *documented* interface (a callable) — the defect is
entirely in what `bootstrap.py` actually supplies, which a
correctly-written fake, by construction, cannot reproduce. Only a
direct exercise of the real `Bootstrap`/`CommandRouter` with the
feature enabled (which this audit performed, and which
`EP056_DESIGN.md` Section 12's own testing strategy did not call for
in this specific combination) surfaces it.

**Evidence:** direct code reading of `bootstrap.py`'s registration
call and `CommandRouter.module_names`'s `@property` declaration
(Section 3); a minimal, isolated type-check probe confirming
`type(router.module_names) is list` and `callable(router.
module_names) is False`; a full, real, temporary-`Bootstrap` probe
with `capability_registry.enabled: true` reproducing the exact
end-user-facing "Internal error" message via `CommandRouter.dispatch()`
for both `capability list` and `capability inject`; and a direct
`module.execute(...)` call surfacing the underlying `TypeError` and
its exact origin line (Section 9).

**Recommendation (not performed — STEP 3 is read-only):** change the
single line in `src/bootstrap.py` from `module_names=router.
module_names` to `module_names=lambda: router.module_names` — this
preserves `CapabilityRegistryModule`'s own constructor contract
exactly as documented and designed (a zero-argument callable,
evaluated fresh at request time, which additionally means
`capability list` correctly reflects namespaces registered *after*
`CapabilityRegistryModule` itself — e.g. `scheduler`, `telegram`,
`test`, all registered later in `bootstrap.py` — once the lambda is
actually called at dispatch time rather than the property being
read once at construction time). No change to `skill.py`, `Command
Router`, or the constructor signature is needed — the fix is confined
entirely to this one call site in `bootstrap.py`. This audit
independently verified (in an isolated scratch copy, never touching
the audited repository) that this one-line fix resolves the defect:
after applying it, `dispatch("capability list")` succeeds and
correctly includes namespaces registered later in `bootstrap.py`
(e.g. `scheduler`), and `dispatch("capability inject ...")` succeeds
and returns the assembled prompt text — this fix was reverted before
the audited repository was left in its final state, since STEP 3 must
remain read-only.

**Disposition:** **BLOCKING.** This must be remediated before EP-056
can be considered complete — recorded as Owner Decision D8 (Section
17) for STEP 4, mirroring the D10 pattern EP-055's own STEP 3 audit
established for its own (lower-severity, non-blocking) findings. No
source file was modified to fix or hide this finding; the verification
fix described above was applied and reverted only in an isolated,
disposable scratch copy.

### Non-blocking observations (INFO)

- **INFO** — `PromptManager._register()` (EP-017, unmodified) stores
  every `Prompt` it composes in an unbounded, in-process dict keyed by
  `prompt_id`, for the lifetime of the process. `capability inject` is
  the first caller of `PromptManager.build()` other than `AIService.
  ask()`'s own single call site — this does not introduce a new class
  of growth (every `AIService.ask()` call already does this on every
  user message), but it is a second source of entries into the same,
  pre-existing, already-unbounded registry. Not a finding against
  EP-056 specifically (the registry's own growth characteristic is an
  EP-017 property, unmodified and out of EP-056's scope to fix), but
  recorded for completeness since `capability inject` is a genuinely
  new caller of this mechanism.
- **INFO** — Once Finding 1 is fixed (via the recommended lambda
  wrapper), `capability list`/`capability inject`'s namespace summary
  will correctly include `capability` itself (self-inclusion, since
  the property is read live, after `capability` has already
  registered) — this is harmless and arguably desirable (an accurate,
  complete picture of currently-registered namespaces), not a defect.
- **INFO** — This audit's own mutation-testing and fix-verification
  methodology (Sections 8, 15) required creating temporary, fully
  isolated scratch copies of the repository, each deleted immediately
  after use. None is, or ever was, part of the audited repository;
  disclosed here for transparency about the audit's own methodology
  only (Section 12 already independently confirms the real
  repository's scope is unaffected).

No MEDIUM or LOW severity findings were identified beyond the two INFO
observations above — the implementation is otherwise clean, minimal,
and faithful to the approved design in every respect this audit
checked.

---

## 16. Final verdict

```text
EP-056 STEP 3 — AUDIT FAILED (ONE BLOCKING FINDING)
```

Owner Decisions D1–D7 are implemented correctly against their literal
text, with zero findings against their wording. However, this audit's
direct exercise of the real, fully-wired `Bootstrap` with
`capability_registry.enabled: true` — a step beyond what the
registered test suite or the STEP 2 report's own validation performed
— found that **`capability list` and `capability inject` are
completely non-functional**: `src/bootstrap.py` passes
`CommandRouter.module_names` (a `@property`, evaluated eagerly at
construction time) where `CapabilityRegistryModule`'s own documented
constructor contract requires a live, zero-argument callable,
causing a 100%-reproducible `TypeError` on every call to either
action. The defect is confined to a single line in `src/bootstrap.py`;
`skill.py`, `CommandRouter`, `PluginService`, and `PromptManager` are
all otherwise correct and unmodified. No security, disclosure, gate-
bypass, or backward-compatibility issue was found — this is a pure,
severe availability/functionality defect.

EP-010 Plugin system, EP-017 Prompt Engine, `CommandRouter`,
`AIService`, and every other DO-NOT-MODIFY file were confirmed
byte-identical to their pre-EP-056 state. The registered EP-056 test
suite (51/0/0) and every regression suite (EP-055 64/0/0, EP-054
76/0/0, EP-053 58/0/0, EP-052 135/0/0, EP-051 105/0/0, EP-050 112/0/0)
were independently reproduced exactly from a clean process, and two
independent mutation tests confirmed the registered suite genuinely
detects a broken enabled-gate and broken summary-composition logic —
within the scope the suite actually exercises. That scope did not
include the real, enabled `Bootstrap` wiring path, which is precisely
where the blocking defect lives.

**EP-056 cannot be marked COMPLETE in its current state.** No source,
test, configuration, dependency, or Bootstrap file was modified during
this audit — STEP 3 is read-only per the repository's established
engineering workflow. STEP 4 (Finalization) requires the owner's
explicit approval of a remediation decision (Section 17) before
proceeding.

---

## 17. Owner Decision required before STEP 4

### D8 — Fix Finding 1 as part of STEP 4?

**Question:** Should STEP 4 include the one-line fix to
`src/bootstrap.py` (`module_names=router.module_names` →
`module_names=lambda: router.module_names`) that resolves Finding 1,
plus a new test that exercises the real, enabled `Bootstrap` wiring
end-to-end (closing the coverage gap Section 8 identified) — or should
EP-056 be closed with this finding outstanding?

**Options:** (a) fix in STEP 4 — a single-line, behavior-preserving
change confined to `src/bootstrap.py`, verified by this audit in an
isolated scratch copy to fully resolve the defect, plus a new,
real-`Bootstrap`, enabled-state test added to `tests/EP056/
test_capability_registry.py` specifically to prevent regression; (b)
defer — record the finding in `docs/BACKLOG.md`/
`docs/architecture/ARCHITECTURE_DEBT.md` and close EP-056 with
`capability list`/`capability inject` non-functional.

**Recommended option:** (a) — unlike EP-055's own STEP 3 findings
(both non-blocking, permitting a deliberate, considered choice to
defer), this finding means the feature Owner Decisions D1/D2 approved
does not work at all. Deferring would mean EP-056 ships a namespace
that responds successfully only to `capability help` and fails on
every other action — this is a materially different situation from
EP-054's own deferred, non-blocking findings, and this audit does not
recommend treating it the same way. The fix itself is minimal (one
line), fully verified by this audit, and introduces no new dependency,
config key, or architecture change.

**This audit does not perform this fix itself** — STEP 3 is read-only
per the repository's established engineering workflow and per the
owner's own explicit instruction for this audit (the verification fix
described in Finding 1 was applied and reverted only in an isolated,
disposable scratch copy, never left in the audited repository). This
decision is presented for the owner's approval before STEP 4 begins.

**Update — D8 APPROVED (option (a)) and implemented in STEP 4.** The
owner approved fixing Finding 1. The fix, its independent
verification, and the final resolved status are recorded in Section
18 below.

---

## 18. STEP 4 remediation — Finding 1 RESOLVED by Owner Decision D8

**The owner approved Owner Decision D8 option (a).** This section
records the STEP 4 fix and its independent verification. It is
appended, not merged into Sections 1-17 above, so the original
first-pass finding remains visible exactly as recorded.

### 18.1 What changed

`src/bootstrap.py`'s `CapabilityRegistryModule` registration call was
changed by exactly one line, plus an explanatory comment:

```diff
         router.register(
             CapabilityRegistryModule(
                 config=config,
                 plugin_service=plugin_service,
-                module_names=router.module_names,
+                module_names=lambda: router.module_names,
                 prompt_manager=prompt_manager,
             )
         )
```

`CommandRouter.module_names` (unmodified, confirmed byte-identical
before and after this fix) remains a `@property` — the fix does not
touch it, `CommandRouter`, `CapabilityRegistryModule`'s own
constructor signature, `PluginService`, or `PromptManager` in any way.
Wrapping the property access in a `lambda` defers its evaluation from
`CapabilityRegistryModule`'s construction time (when only the
namespaces registered so far exist) to each individual dispatch call
(when the full, final set of registered namespaces exists) — exactly
satisfying `CapabilityRegistryModule.__init__`'s own, already-correct,
unmodified `module_names: Callable[[], list[str]]` contract that
`EP056_DESIGN.md` Section 6.4 and STEP 2's own implementation always
intended.

No other line in `bootstrap.py` changed. `src/skills/
capability_registry/skill.py` was **not modified at all** — the
defect was confined entirely to this one call site, exactly as
Finding 1's original recommendation predicted, and no change to the
Capability Registry's own architecture, Owner Decisions D1-D7, or any
of EP-010/EP-017's files was made or needed.

### 18.2 New tests added (regression/integration guard)

Three new test methods were added to `tests/EP056/
test_capability_registry.py`, specifically constructing a **real**,
fully-initialized `Bootstrap` with `capability_registry.enabled: true`
— not a fake `module_names`/`PluginService` collaborator — closing the
exact coverage gap Section 8 identified as the reason the original 51
tests could not have caught Finding 1:

- `_test_bootstrap_enabled_capability_list_succeeds_end_to_end` —
  dispatches `"capability list"` through the real `CommandRouter` and
  asserts `success=True` with the expected summary structure.
- `_test_bootstrap_enabled_capability_inject_succeeds_end_to_end` —
  dispatches `"capability inject ..."` through the real
  `CommandRouter` and asserts `success=True`, the user's text and the
  composed summary both appear in the returned, real `Prompt.rendered`
  text.
- `_test_bootstrap_enabled_capability_list_includes_later_registered_namespaces`
  — asserts `scheduler`, `telegram`, and `test` (each registered
  *after* `capability` in `bootstrap.py`) all appear in the summary.
  This is deliberately a stronger guard than a simple crash check: it
  would also catch a *different*, silent regression (e.g. a future
  edit that replaces the lambda with an eagerly-evaluated
  `list(router.module_names)` snapshot — which would not crash, but
  would silently produce a stale, incomplete summary).

### 18.3 Independent verification that the fix is real, not merely test-shaped

This audit did not simply trust that new, green tests prove the fix.
It reverted the fix in an isolated scratch copy (`module_names=lambda:
router.module_names` → `module_names=router.module_names`, never
touching the audited repository) and re-ran the full EP-056 suite
against it:

```
Passed : 53
Failed : 9
Errors:
 - 'capability list' must succeed through the real, enabled Bootstrap
   wiring (EP056_ARCHITECTURE_AUDIT.md Finding 1 -- must not raise
   TypeError: 'list' object is not callable)
 - Expected True
 - Expected True
 - 'capability inject' must succeed through the real, enabled
   Bootstrap wiring (...)
 - Expected True
 - Expected True
 - 'scheduler' (registered after 'capability' in bootstrap.py) must
   appear in the live-evaluated summary
 - 'telegram' (registered after 'capability' in bootstrap.py) must
   appear in the live-evaluated summary
 - 'test' (registered after 'capability' in bootstrap.py) must appear
   in the live-evaluated summary
```

**Exactly the 9 assertions belonging to the 3 new test methods failed,
with the exact expected error messages — every other test (including
all 51 original assertions) continued to pass unchanged against the
reverted code.** This is direct, unambiguous proof that the new tests
would have caught the original defect, not merely passing vacuously
regardless of whether the fix is present.

### 18.4 Direct behavioral re-verification against the real, fixed code

Independent of the test suite, this audit re-ran the exact same live
probe from Section 9 against the real, fixed code — a real, temporary
`Bootstrap` with `capability_registry.enabled: true`:

| Probe | Pre-fix result (Section 9/15) | Post-fix result |
|---|---|---|
| `capability list` | `success=False`, `"Internal error while executing 'capability list'."` (underlying `TypeError: 'list' object is not callable`) | `success=True`, full composed summary returned, e.g. `"Capability Registry (EP-056):\n\nPlugins:\n- (none currently running)\n\nBuilt-in commands: agent, ai, ..., capability, ..., scheduler, ..., telegram, test, ..."` |
| `capability inject <text>` | `success=False`, identical `"Internal error"` failure | `success=True`, returned `Prompt.rendered` text contains both the given text and the composed Capability Context summary |
| `capability help` | `success=True` (unaffected either way) | `success=True` (unchanged) |
| Later-registered namespaces (`scheduler`, `telegram`, `test`) | N/A (crashed before reaching this) | All three present in the live-evaluated summary, confirming the lambda's deferred evaluation works exactly as intended, not merely "no longer crashes" |

**Finding 1 is confirmed resolved, not merely covered by new tests
that could pass regardless of the underlying behavior.**

### 18.5 Regression re-verification (behavior-preserving for everything already correct)

The full, pre-existing 51-assertion suite (Sections 4-14 of this
audit) was re-run against the fixed code and **all 51 continued to
pass unchanged** — confirming the fix is behavior-preserving for every
previously-verified scenario (argument-shape validation, the
`capability_registry.enabled` gate, fake-backed `list`/`inject`
positive paths, real-`PromptManager` error translation, `help`,
unknown-action handling, `CommandRouter` dispatch equivalence, and
every disabled-state `Bootstrap` wiring test). 11 new assertions were
added (3 new test methods), bringing the suite to **62 passed / 0
failed / 0 skipped**, independently re-run from a clean process
(cleared `__pycache__`).

The six regression suites were independently re-run again after the
STEP 4 fix and reproduced identical figures: EP-055 64/0/0, EP-054
76/0/0, EP-053 58/0/0, EP-052 135/0/0, EP-051 105/0/0, EP-050 112/0/0.

### 18.6 Scope re-verification after the STEP 4 fix

Re-running this audit's Section 12 file-scope methodology
(`find . -newer CHANGELOG.md -type f`) after the STEP 4 fix shows
exactly the same seven files already approved in STEP 2/3 — no new
file outside this already-approved set; `config/config.yaml`,
`src/modules/test_module.py`, `src/skills/capability_registry/skill.py`,
and `docs/architecture/designs/EP056_DESIGN.md` are all unchanged
since STEP 2/3 (the STEP 4 fix touched only `src/bootstrap.py` and the
test file). Byte-comparison of EP-010 Plugin system
(`plugin.py`/`plugin_manifest.py`/`plugin_registry.py`/
`plugin_loader.py`/`plugin_discovery.py`/`plugin_service.py`), EP-017
Prompt Engine (`prompt.py`/`prompt_builder.py`/`prompt_manager.py`),
`command_router.py`, and `ai_service.py` against the original
pre-EP-056 repository archive was re-run after the fix and **all
remain byte-identical**. `src/skills/capability_registry/skill.py`
itself was independently confirmed byte-identical to its STEP 2/3
state — the fix required zero change to the Capability Registry
module itself.

### 18.7 Owner Decisions D1–D8 re-verification

Re-checked after the fix: D1-D7 (Section 2) are unaffected by this
change — the fix touches only one dependency-injection call site
inside the already-approved `bootstrap.py` wiring block, introduces no
new functionality, no new config key, no new dependency, no
architecture change, and does not alter D1's Candidate A scope, D2's
`inject` action, D4's namespace name, D5's placement (the fix is
*at* the already-approved placement, not a relocation), D6's real-
`PromptManager` testing approach, or D7's `CommandRouter` integration.
**D8 (fix in STEP 4) is now implemented and verified.**

### 18.8 Status

| Finding | Original severity | Status |
|---|---|---|
| Finding 1 — `capability list`/`capability inject` completely non-functional due to `module_names` property/callable mismatch | HIGH — BLOCKING | **RESOLVED** by Owner Decision D8, verified in Sections 18.3-18.4 |

**No new finding was introduced by the fix.** The fix is minimal (one
line changed in `bootstrap.py`, plus an explanatory comment; zero
lines changed in `skill.py`; zero new dependencies; zero new config
keys; zero behavior change for anything that previously worked
correctly) and fully verified by both negative evidence (the
fix-reverted scratch copy reproduces exactly the original failure,
with exactly the 9 new-test assertions failing and nothing else) and
positive evidence (the full, unchanged 51-assertion suite plus all
regression suites still pass, and the real, fixed code now correctly
serves both `capability list` and `capability inject` end-to-end,
including correctly reflecting namespaces registered after
`capability` itself).

```text
EP-056 STEP 3 (with STEP 4 remediation) — FINAL VERDICT: PASS AFTER REMEDIATION
Owner Decisions D1-D8: all implemented and verified, zero open findings
EP-010 Plugin system: confirmed unmodified (before and after the fix)
EP-017 Prompt Engine: confirmed unmodified (before and after the fix)
CommandRouter: confirmed unmodified (before and after the fix)
src/skills/capability_registry/skill.py: confirmed unmodified by the fix
File scope: confirmed exactly matching the approved set (before and after the fix)
Tests: EP056 62/0/0 (51 original + 11 new, all independently re-verified)
Regression: EP055 64/0/0, EP054 76/0/0, EP053 58/0/0, EP052 135/0/0, EP051 105/0/0, EP050 112/0/0
```
