# EP-055 — Prompt Optimizer — Architecture Audit (STEP 3)

**Verdict (after STEP 4 remediation): EP-055 STEP 3 — PASS AFTER REMEDIATION**

This audit was performed in two passes, following the same precedent
`EP052_ARCHITECTURE_AUDIT.md` established: the first pass (this
document's original text, Sections 1-16 below, unmodified) identified
two non-blocking findings. The owner reviewed both, approved Owner
Decision D10 (`EP055_DESIGN.md` Section 17), and directed a STEP 4
remediation. Section 18 below records that remediation and its
independent verification. Nothing in Sections 1-17 has been edited or
reworded to hide or soften the original findings — they are preserved
verbatim below, exactly as the first pass recorded them.

---

## 1. Scope of this audit

Audited against `docs/architecture/designs/EP055_DESIGN.md`,
`AI_GENERATION_STANDARD.md`, `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md`,
and the EP-050–EP-054 audit conventions (severity taxonomy, structure,
and independent-verification methodology established by
`docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md`):

- `src/skills/prompt_optimizer/skill.py`
- `src/bootstrap.py` (EP-055-relevant sections)
- `src/modules/test_module.py` (EP-055 test registration)
- `config/config.yaml` (`prompt_optimizer:` block)
- `tests/EP055/__init__.py`, `tests/EP055/test_prompt_optimizer.py`

Inspected for precedent/integration-boundary verification only (no
modification made or authorized to any of these):

- `src/core/ai/prompt.py`, `src/core/ai/prompt_builder.py`,
  `src/core/ai/prompt_manager.py` (EP-017 Prompt Engine)
- `src/core/ai/context_manager.py`, `context_loader.py`, `context.py`
  (EP-018 Context Engine)
- `src/core/command_router.py`
- `src/core/tool/`
- `src/core/ai/provider.py`, `provider_manager.py`,
  `conversation_manager.py`, `message.py`
- `src/services/ai_service.py`
- `src/core/agent/`, `src/core/planning/`, `src/core/scheduler/`
- `src/skills/reflection/`, `src/skills/desktop/`, `src/skills/browser/`,
  `src/skills/files/`, `src/skills/vision/`
- `docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md` (structural/
  severity precedent)

**File-scope baseline used for this audit:** `find . -newer
docs/architecture/designs/EP055_DESIGN.md -type f` (the design
document's own approval-edit timestamp, which strictly predates every
STEP 2 change) — independently re-derived by this audit, not copied
from the STEP 2 report, and confirmed to return exactly the same six
files the STEP 2 report claimed (Section 11). **In addition**, every
file in the "DO NOT MODIFY" list above (plus `src/core/config.py` and
`src/core/ai/message.py`) was byte-compared (`diff`) against the
original, pre-EP-055 repository archive — not merely timestamp-
checked — and every one is confirmed **byte-identical** (Section 11).

---

## 2. Owner Decisions D1–D9 verification table

| Decision | Approved requirement | Implementation evidence | Test evidence | Result |
|---|---|---|---|---|
| D1 | Candidate A: on-demand prompt/template improvement via one direct `AIProvider.ask()` call, no new backend Protocol | `PromptOptimizerModule` (`src/skills/prompt_optimizer/skill.py`) composes `ProviderManager.get_current().ask()` directly — no `backend.py`/`local_backend.py` pair exists anywhere under `src/skills/prompt_optimizer/` (confirmed: `ls` shows only `skill.py`). No import of `src.services.ai_service`/`AIService`, `PromptManager`, or `PromptBuilder` anywhere in the module (confirmed by import inspection) — the raw `AIProvider.ask()` path is used directly, avoiding both a new conversation turn and recursive re-entry into the very Prompt Engine pipeline whose template input it improves, exactly as the design's Section 6.4 required. | `_test_optimize_returns_provider_response_text`, `_test_optimize_prompt_contains_original_text` (fake-backed); this audit additionally re-ran these from a clean process (Section 8). | **PASS** |
| D2 | Command namespace: `prompt` | `PromptOptimizerModule.name` returns the literal string `"prompt"`; `config/config.yaml`'s new block is named `prompt_optimizer:`, deliberately distinct from the pre-existing `prompt:` block (EP-017), with an explicit comment explaining the separation. No namespace collision — `CommandRouter.register()`'s own duplicate-namespace `ValueError` was never triggered (confirmed by successful `Bootstrap.initialize()` in the wiring tests). | `_test_command_router_dispatch_matches_direct_execute` dispatches `"prompt help"` through a real `CommandRouter`. | **PASS** |
| D3 | Reuse `prompt_optimizer.enabled` alone; no separate AI-provider/privacy gate | `config/config.yaml`'s `prompt_optimizer:` block contains exactly `enabled`, `max_input_size`, `min_seconds_between_calls` — no second gate (e.g. `prompt_optimizer.ai_rewrite.enabled`) exists. `_gate()` in `skill.py` checks only `prompt_optimizer.enabled`. | `_test_disabled_rejects_optimize_with_zero_downstream_calls` (re-run) confirms the single gate is sufficient to block the provider call. | **PASS** |
| D4 | No `prompt save` in v1 — return-only behavior | Zero `save` action registered in `self._actions`; `_test_unknown_action_returns_failure` confirms `prompt save` is rejected as an unknown command. No file-write call (`Path.write_text`/`open(..., "w")`) exists anywhere in `skill.py` (confirmed by `grep`) — only `Path.read_text` (read-only). `config/config.yaml`'s `prompt_optimizer:` block contains no `allow_save` key. | `_test_unknown_action_returns_failure` (re-run). | **PASS** |
| D5 | No `AgentEngine.register_subsystem()` call in v1 | Zero reference to `AgentEngine`/`register_subsystem` anywhere in `src/skills/prompt_optimizer/skill.py` or the EP-055 wiring block of `src/bootstrap.py` (confirmed by `grep`; the only textual match is a docstring sentence describing the *absence* of this integration). | N/A (absence-of-code check). | **PASS** |
| D6 | Resource/rate-limit defaults: `max_input_size: 4000`, `min_seconds_between_calls: 30` | `config/config.yaml`'s `prompt_optimizer:` block contains exactly these two values; `_DEFAULT_MAX_INPUT_SIZE = 4000`/`_DEFAULT_MIN_SECONDS_BETWEEN_CALLS = 30.0` in `skill.py` match. | `_test_input_exceeding_max_size_rejected_before_provider_call`, `_test_input_at_exactly_max_size_allowed`, `_test_rate_limit_blocks_immediate_second_call` (re-run); this audit additionally reproduced both via independent mutation tests (Section 8). | **PASS** |
| D7 | `CommandRouter` dispatch, no Tool Engine change | `PromptOptimizerModule` implements exactly the `CommandModule` Protocol (`name` property, `execute(action, arguments)` method); zero import of `src.core.tool` anywhere in `src/skills/prompt_optimizer/`. | `_test_command_router_dispatch_matches_direct_execute` (re-run) instantiates a real `CommandRouter`, registers the real `PromptOptimizerModule`, and dispatches a real string. | **PASS** |
| D8 | No real-`AIProvider` integration test (non-deterministic output; fake-backed suite only) | `tests/EP055/` contains exactly `__init__.py` and `test_prompt_optimizer.py` — no `test_prompt_optimizer_ai_integration.py` or equivalent exists (confirmed by `find`/`ls`). | N/A (absence-of-file check). | **PASS** |
| D9 | Do not backfill the pre-existing EP-014…EP-017 test-registration gap | `src/modules/test_module.py`'s diff against the pre-EP-055 repository contains exactly one added line (`import tests.EP055.test_prompt_optimizer`) — no `tests.EP014`/`EP015`/`EP016`/`EP017` import was added. | N/A (absence-of-change check). | **PASS** |

**All nine Owner Decisions are implemented with zero findings against
their literal text.** One finding (Section 15) concerns an ordering
behavior the design document did not explicitly specify one way or
the other, and is recorded as a design/implementation consistency gap
rather than an Owner Decision violation.

---

## 3. Architecture audit

- **No new backend Protocol** (D1/Section 6.2 of the design) —
  confirmed: `src/skills/prompt_optimizer/` contains only `skill.py`;
  no `backend.py`, no `local_backend.py`. This is a deliberate,
  design-authorized departure from the `desktop`/`browser`/`file`/
  `vision` four-file pattern, justified because EP-055 introduces no
  new external I/O surface beyond the already-existing `AIProvider`
  call and a read of the already-configured `paths.prompts` directory
  (Section 6.2 of `EP055_DESIGN.md`) — confirmed correct by this
  audit's own review of `PromptOptimizerModule`'s dependencies (one
  already-existing, unmodified manager, plus direct `pathlib` file
  access, Section 2 above).
- **`PromptOptimizerModule` owns command parsing, validation, gating,
  rate-limiting, and result translation** — confirmed by direct code
  reading: argument-shape validation, `_resolve_input()`/
  `_load_template()`, `_gate()`, `_check_rate_limit()`, and
  `ProviderError`/`PromptTemplateNotFoundError` → `CommandResult`
  translation all live exclusively in `skill.py`. Neither
  `ProviderManager` nor `AIProvider` was modified to add any of this
  logic.
- **No improper duplication** — the `prompt_optimizer.enabled` gate,
  the `max_input_size` cap, and the `min_seconds_between_calls` rate
  limit are each enforced exactly once, in `PromptOptimizerModule`
  only (subject to Finding 2's ordering nuance, Section 15).
- **`PromptBuilder`/`PromptManager`/EP-018 Context Engine are never
  imported, constructed, or called** — confirmed by import inspection
  of `src/skills/prompt_optimizer/skill.py`: the only `src.core.ai.*`
  imports are `prompt_builder` (for the `DEFAULT_TEMPLATE_DIRECTORY`
  constant and the `PromptTemplateNotFoundError` exception type only —
  never `PromptBuilder` the class itself), `provider` (for
  `ProviderError`), and `provider_manager` (for the `ProviderManager`
  type hint). This is the central architectural constraint the design
  imposed (Section 0/14) and it holds exactly.
- **Bootstrap wiring follows established project conventions** —
  confirmed: the unconditional-registration pattern
  (`router.register(PromptOptimizerModule(...))`, gate enforced
  inside the module, not at the registration call) is structurally
  identical to `ReflectionModule`'s own wiring
  (`EP054_ARCHITECTURE_AUDIT.md` Section 3).
- **No duplicate registration exists** — confirmed both statically
  (exactly one `router.register(PromptOptimizerModule(...))` call in
  `bootstrap.py`) and structurally (`CommandRouter.register()` itself
  raises `ValueError` on any duplicate namespace — this mechanism is
  confirmed unmodified, Section 11).
- **Correct dependency ordering in `Bootstrap`** — confirmed:
  `PromptOptimizerModule` is constructed strictly after
  `ai_provider_manager` (and immediately after `ReflectionModule`,
  which depends on the same manager) is already constructed. No
  forward-reference or ordering bug exists.
- **No unnecessary coupling** — confirmed by import inspection: zero
  references to `src.skills.desktop`, `src.skills.browser`,
  `src.skills.files`, `src.skills.vision`, `src.skills.reflection`,
  `src.core.tool`, `src.core.agent`, `src.core.planning`, or
  `src.core.scheduler` anywhere in
  `src/skills/prompt_optimizer/skill.py`.
- **`AIService` and the EP-017 Prompt Engine deliberately bypassed,
  correctly** — confirmed by import inspection (zero import of
  `src.services.ai_service`, and no construction/call of
  `PromptManager`/`PromptBuilder`) and by this audit's own reasoning
  check (Section 2, D1): had `PromptOptimizerModule` used
  `AIService.ask()` or `PromptManager.build()` instead of the raw
  `AIProvider` via `ProviderManager.get_current()`, every `prompt
  optimize` call would have both appended itself as a new
  conversation turn and recursively re-entered the very Prompt Engine
  pipeline whose template input it is trying to improve — a
  correctness bug the design explicitly anticipated and the
  implementation correctly avoided.

**Result: PASS.**

---

## 4. Command/functionality audit

| Behavior | Verified against | Result |
|---|---|---|
| `prompt help` | Returns the exact `HELP_TEXT` constant; independently re-executed. | PASS |
| `prompt optimize <text>` — valid arguments, positive path | Real prompt-construction and provider-response verified (`_test_optimize_prompt_contains_original_text`, `_test_optimize_returns_provider_response_text`, `_test_optimize_joins_multiple_word_arguments`, re-run). | PASS |
| `prompt optimize` — missing text | Rejected with a usage error and zero downstream calls (`_test_optimize_rejects_no_arguments`, re-run). | PASS |
| `prompt optimize --template <name>` — wrong argument count | `["--template"]` and `["--template", "a", "b"]` both rejected with zero downstream calls (`_test_optimize_rejects_wrong_template_argument_count`, re-run). | PASS |
| `prompt optimize --template <name>` — found/not-found/empty | All three cases verified against a real, temporary `paths.prompts` fixture directory (real file I/O, not mocked) — `_test_template_loaded_and_sent_to_provider`, `_test_template_not_found_reports_failure_with_zero_provider_calls`, `_test_template_empty_reports_failure` (re-run). | PASS |
| Unknown action (including `prompt save`) | Rejected with a clear "Unknown command" message; confirmed no `save`/`optimize`-alternative action exists beyond `help`/`optimize` (`_test_unknown_action_returns_failure`, re-run). | PASS |
| Error translation | `ProviderError` is the only exception type `_optimize()` catches from the provider call, translated into a failed `CommandResult`; `PromptTemplateNotFoundError` is the only exception type `_resolve_input()` catches from `_load_template()`, likewise translated (`_test_optimize_provider_raises_error`, `_test_template_not_found_reports_failure_with_zero_provider_calls`, re-run). | PASS |
| Direct execution vs. `CommandRouter` dispatch equivalence | `_test_command_router_dispatch_matches_direct_execute` (re-run) confirms identical `success`/`message` between `module.execute(...)` and `router.dispatch("prompt help")`. | PASS |
| No active provider | Returns a clear, non-crashing failure rather than raising (`_test_optimize_no_provider_available`, re-run). | PASS |

**Result: PASS.**

---

## 5. Security and capability-gate audit

| Check | Method | Result |
|---|---|---|
| `prompt_optimizer.enabled` gate blocks the AI-provider call | Code reading (`_gate()` called before `provider.ask()` in every code path) + `_test_disabled_rejects_optimize_with_zero_downstream_calls` (re-run) + independent mutation test (Section 8) — deleting the gate check caused 4 test failures | PASS |
| `max_input_size` cap enforcement | `_test_input_exceeding_max_size_rejected_before_provider_call`/`_test_input_at_exactly_max_size_allowed` (re-run); independently reproduced via mutation test (Section 8) — deleting the cap check caused 3 test failures | PASS, functionally — see Finding 2 for an *ordering* nuance, not a bypass |
| `min_seconds_between_calls` rate limit | `_test_rate_limit_blocks_immediate_second_call`/`_test_rate_limit_allows_call_after_elapsed` (re-run); independently reproduced via mutation test (Section 8) — deleting the elapsed check caused 3 test failures | PASS |
| Zero AI-provider calls while disabled | Verified via `_FakeProviderManager.get_current_call_count` assertions in every gate test; independently reproduced by this audit's own dummy-object probe (Section 9, a `DummyProviderManager` raising `AssertionError` if called — never triggered while disabled, in every scenario probed, including the Finding 1/2 edge cases) | PASS |
| No content disclosure while disabled | This audit's own probe (Section 9) confirmed a `--template` file's actual text content is never included in any response while `prompt_optimizer.enabled=false`, even when the file is successfully read (Finding 1) | PASS |
| No `prompt save`/filesystem-write capability exists (D4) | Confirmed by `grep` — zero `write_text`/`open(..., "w"/"a")` call anywhere in `skill.py`; only `Path.read_text` (read-only) | PASS |
| No new AI-provider/network path beyond the existing, unmodified `AIProvider.ask()` | Confirmed by import inspection: no `requests`/`httpx`/`socket` import anywhere in `skill.py` | PASS |
| No shell/subprocess/code execution | Confirmed by import inspection: no `subprocess`/`os.system`/`eval`/`exec` anywhere in `skill.py` | PASS |
| Provider failure does not corrupt rate-limit state | This audit independently probed: a failing `ProviderError` call does not advance `_rate_limit_state.last_call_monotonic` (only a *successful* call does, confirmed by code reading, which sits after the `try`/`except` block) — a caller may retry immediately after a genuine failure, reasonable and intentional, not a bypass of the cost-protection the rate limit exists for | PASS (INFO-level observation, not a finding) |

**Conclusion: no bypass of the AI-provider gate, the resource-size
cap, or the rate limit was found under any probed condition, and no
template content is ever disclosed while disabled.** Findings 1 and 2
(Section 15) concern information disclosed via error-message wording
and a real (but read-only, local) filesystem access performed before
the gate — neither is a bypass of the protections those checks exist
for (provider cost, template content confidentiality).

**Result: PASS WITH TWO NON-BLOCKING FINDINGS** (Findings 1 and 2).

---

## 6. Configuration and limits audit

- `config/config.yaml`'s `prompt_optimizer:` block contains exactly
  `enabled` (`false`), `max_input_size` (`4000`),
  `min_seconds_between_calls` (`30`) — matching Owner Decisions
  D3/D4/D6 exactly, with no extraneous key (no `allow_save`, no second
  gate, consistent with D3/D4's approved recommendations).
- The pre-existing `prompt:` block (EP-017) is confirmed byte-
  identical to its pre-EP-055 state (Section 11) — EP-055's new block
  is inserted immediately after it, with a comment explicitly
  explaining the deliberate naming separation (Owner Decision D2).
- Every config value is read fresh on each call via
  `self._config.get(...)`, never cached at construction — confirmed
  by code reading (`_is_enabled()`, `_max_input_size()`,
  `_min_seconds_between_calls()` are all called from within action
  handlers, not from `__init__`).
- `Config.get()`'s dotted-path lookup was independently verified by
  this audit to correctly return the documented defaults
  (`False`/`4000`/`30.0`) when the entire `prompt_optimizer:` section
  is absent from config, not merely when it is present with an
  explicit `false` (`_test_bootstrap_config_defaults_prompt_optimizer_disabled`,
  re-run).
- `paths.prompts` (already reserved by EP-017/Section 3.2 of the
  design) is read, never written to, by `PromptOptimizerModule` — no
  new config key was introduced for the template directory itself.

**Result: PASS.**

---

## 7. Provider/template-file integration audit

- **Provider integration**: `ProviderManager.get_current()` is called,
  and its result's `.ask(prompt)` is called directly — confirmed by
  code reading and by every fake-backed test in the registered suite.
  Per Owner Decision D8, no real-`AIProvider` end-to-end test exists,
  matching the design's own recommendation and EP-054's own precedent.
- **Template-file integration**: `Path.is_file()`/`Path.read_text()`
  are the only two filesystem operations `PromptOptimizerModule`
  performs, against the already-configured `paths.prompts` directory
  — confirmed by code reading and by the registered suite's own real
  (non-fake), temporary-directory-backed tests
  (`_test_template_loaded_and_sent_to_provider`,
  `_test_template_not_found_reports_failure_with_zero_provider_calls`,
  `_test_template_empty_reports_failure`). Unlike EP-054's Finding 1
  (a design-committed real-`MemoryService` test that was missing),
  EP-055's one real I/O surface (the filesystem) **is** covered by a
  genuine, non-fake test in the registered suite — no equivalent gap
  exists here.
- **No coupling to `PromptBuilder`/`PromptManager`** — confirmed
  (Section 3): `PromptOptimizerModule` reads the same directory
  `PromptBuilder.load_template()` reads, via its own, independent
  `pathlib` calls, never by constructing or calling `PromptBuilder`
  itself.

**Result: PASS.**

---

## 8. Test quality audit — independently re-verified, not merely re-read

This audit did not simply trust the STEP 2 report's "52/0/0" claim.
It:

1. **Re-ran `tests/EP055/test_prompt_optimizer.py` from a clean
   process** (after clearing all `__pycache__` directories) —
   reproduced exactly **52 passed / 0 failed / 0 skipped**. Also
   independently re-ran the six regression suites the owner reported
   (EP-054, EP-053, EP-052, EP-051, EP-050) and reproduced their exact
   reported figures: 76/0/0, 58/0/0, 135/0/0, 105/0/0, 112/0/0
   respectively.
2. **Performed three independent mutation tests** against isolated
   scratch copies (never touching the audited repository):
   - **Mutation 1** — disabled the `prompt_optimizer.enabled` gate
     (`return None` unconditionally in `_gate()`). Result: **4 tests
     failed** (48 passed / 4 failed). The suite genuinely detects a
     broken gate.
   - **Mutation 2** — disabled the rate-limit check (`if False:`
     instead of `if elapsed < min_seconds:`). Result: **3 tests
     failed** (49 passed / 3 failed). The suite genuinely detects a
     broken rate limit.
   - **Mutation 3** — disabled the `max_input_size` cap-exceeded check
     (`if False:` instead of `if len(original) > max_size:`). Result:
     **3 tests failed** (49 passed / 3 failed). The suite genuinely
     detects a broken resource cap.
3. **Performed live edge-case probes against the real, unmutated
   code** not present in the original 52 assertions: an over-size
   input while disabled, a `--template` load (found/not-found/empty)
   while disabled, using `DummyProviderManager` objects that raise
   `AssertionError` if called — confirming zero downstream provider
   calls in every case, and producing Findings 1 and 2 (Section 15).

**Conclusion: the 52 passing assertions genuinely exercise real
behavior**, including real (non-fake) filesystem I/O for the
`--template` path. They are not hollow mock-only checks — this was
proven by demonstrating that breaking the real implementation causes
real, corresponding test failures.

**Result: PASS**, with the two ordering findings noted (Section 15).

---

## 9. Edge-case evidence log (for Findings 1 and 2)

- **Over-size-input-while-disabled probe** (Finding 2): with
  `prompt_optimizer.enabled: false` and `max_input_size: 10`, calling
  `prompt optimize <32-character text>` returned `"prompt optimize:
  input is 32 character(s), exceeding 'prompt_optimizer.max_input_size'
  (10)."` instead of the expected disabled message — confirmed via a
  `DummyProviderManager` that raises `AssertionError` if called
  (never called, confirming no functional bypass, only a
  message-content/ordering inconsistency, and matching EP-054's own
  previously-accepted Finding 2 pattern almost exactly).
- **Template-existence-while-disabled probe** (Finding 1): with
  `prompt_optimizer.enabled: false`, calling `prompt optimize
  --template <existing-name>` against a real, temporary `paths.prompts`
  fixture directory **successfully read the file's content from
  disk** (confirmed: no `PromptTemplateNotFoundError` was raised) and
  then correctly returned the standard disabled message once
  `_gate()` was reached — the file's content was never included in
  the response, confirmed by an explicit content-inclusion check.
- **Template-not-found-while-disabled probe** (Finding 1): calling
  `prompt optimize --template <nonexistent-name>` while disabled
  returned `"prompt optimize: template not found: '<name>' (expected
  '<full resolved path>')."` — disclosing both the fact that the named
  template does not exist and the exact, absolute resolved filesystem
  path, without ever reaching `_gate()`.
- **Template-empty-while-disabled probe** (Finding 1): calling
  `prompt optimize --template <name-of-an-empty-file>` while disabled
  returned `"prompt optimize: template '<name>' is empty."` — again
  disclosing a filesystem fact about the named template before
  `_gate()` was reached.
- **Provider-failure/rate-limit interaction probe**: a
  `ProviderError`-raising call does not advance the rate-limit clock
  — an intentional, reasonable behavior, not a finding.

---

## 10. Cross-platform audit

No OS-specific code exists anywhere in
`src/skills/prompt_optimizer/skill.py` (confirmed by `grep` for
`platform.system`/`sys.platform`: zero matches) — consistent with the
design's own Section 11 ("no cross-platform considerations
anticipated"). Filesystem access uses `pathlib.Path` exclusively,
matching `PromptBuilder.load_template()`'s own cross-platform-safe
convention.

**Result: PASS.**

---

## 11. File-scope audit (final)

Independently re-derived in this audit via `find . -newer
docs/architecture/designs/EP055_DESIGN.md -type f` (after clearing all
`__pycache__` directories), and additionally cross-checked by
byte-comparing (`diff`) every file against the original, pre-EP-055
repository archive:

| File | Status | Within approved EP-055 scope? |
|---|---|---|
| `config/config.yaml` | Modified (additive `prompt_optimizer:` block only, confirmed by `diff`) | Yes (MODIFY) |
| `src/bootstrap.py` | Modified (one additive import, one additive wiring block, confirmed by `diff`) | Yes (MODIFY) |
| `src/modules/test_module.py` | Modified (one additive import line, confirmed by `diff`) | Yes (MODIFY) |
| `src/skills/prompt_optimizer/skill.py` | Created | Yes (CREATE) |
| `tests/EP055/__init__.py` | Created | Yes (CREATE) |
| `tests/EP055/test_prompt_optimizer.py` | Created | Yes (CREATE) |

**No other file in the repository shows a modification timestamp
newer than `EP055_DESIGN.md`'s own approval-edit timestamp.** All six
files exactly match the approved EP-055 STEP 2 file scope; none is
unauthorized.

**DO NOT MODIFY verification**, checked by direct byte-comparison
(`diff`) against the original, pre-EP-055 repository archive — not
merely timestamp inference:

| File | Result |
|---|---|
| `src/core/ai/prompt.py` | **Byte-identical.** EP-017 Prompt Engine untouched. |
| `src/core/ai/prompt_builder.py` | **Byte-identical.** EP-017 Prompt Engine untouched. |
| `src/core/ai/prompt_manager.py` | **Byte-identical.** EP-017 Prompt Engine untouched. |
| `src/core/ai/context_manager.py`, `context_loader.py`, `context.py` | **Byte-identical.** EP-018 Context Engine untouched. |
| `src/core/command_router.py` | **Byte-identical.** `CommandModule`/`CommandResult`/`CommandRouter` confirmed unchanged from the interface `PromptOptimizerModule` was designed against. |
| `src/core/ai/provider.py`, `provider_manager.py`, `conversation_manager.py`, `message.py` | **Byte-identical.** Each confirmed used only through its existing, unmodified public API. |
| `src/services/ai_service.py` | **Byte-identical.** Never imported by `PromptOptimizerModule`. |
| `src/core/config.py` | **Byte-identical.** |
| `src/skills/reflection/`, `src/skills/desktop/`, `src/skills/browser/`, `src/skills/files/`, `src/skills/vision/` | **Untouched** — none appear in the modified-file list; zero reference to any of them anywhere in `src/skills/prompt_optimizer/`. |
| `src/core/agent/`, `src/core/planning/`, `src/core/scheduler/`, `src/core/tool/` | **Untouched** — not in the modified-file list; zero reference to any of them anywhere in `src/skills/prompt_optimizer/`. |
| Every prior EP's design/audit document | **Untouched** — none appear in the modified-file list. |

`__pycache__` directories generated by this audit's own test runs and
mutation-test scratch copies were cleared before the final file-scope
check; the mutation-test scratch copies themselves were created under
a separate working directory, never touching the audited repository,
and were deleted immediately after use.

**Result: PASS.**

---

## 12. Design ↔ implementation consistency

| Design requirement (`EP055_DESIGN.md`) | Implementation | Consistent? |
|---|---|---|
| Section 6.1/6.2 — `PromptOptimizerModule`, no new backend Protocol | Present exactly as specified | Yes |
| Section 6.3 — `prompt help`/`prompt optimize <text>`/`prompt optimize --template <name>` only, no `prompt save` (D4) | Confirmed | Yes |
| Section 6.4 — `AIProvider.ask()` via `ProviderManager` directly; `paths.prompts` read-only; no `PromptBuilder`/`PromptManager` call | Confirmed | Yes |
| Section 7 — `prompt_optimizer.enabled` gate; no second AI-provider gate (D3); resource/rate limits (D6) | Confirmed, functionally — **Finding 1/Finding 2**: neither the `--template` file-read/existence-disclosure path nor the `max_input_size` check's position relative to the gate matches the "gate first" ordering every prior EP (`desktop`/`browser`/`file`/`vision`/`reflection`) established | **Partial — see Findings 1 and 2** |
| Section 8 — exact `prompt_optimizer:` config block, no `allow_save` | Confirmed, matches verbatim | Yes |
| Section 9 — no new dependency | Confirmed — `requirements.txt` unchanged since before `EP055_DESIGN.md` existed | Yes |
| Section 10 — reuse `ProviderError` and `PromptTemplateNotFoundError`, no re-implementation | Confirmed — both exception types are imported from their existing, unmodified source modules and reused, never redefined | Yes |
| Section 14 — exact CREATE/MODIFY/DO NOT MODIFY file scope | Confirmed (Section 11 above) | Yes |
| Section 12/D8 — no real-`AIProvider` integration test; real (non-fake) filesystem test for the one real I/O surface | Confirmed — no real-provider test exists (as recommended); the `--template` path **is** covered by real, non-fake, temporary-directory-backed tests | Yes |

**No missing implementation, no implementation outside approved
scope, no incorrect dependency decision, and no unapproved
architecture change was found.** Two ordering-related
inconsistencies were found (Findings 1 and 2, Section 15) — neither
modifies any existing file's behavior, neither introduces a new
dependency or capability beyond what the design authorized, and
neither permits an AI-provider-cost bypass or template-content
disclosure; both are recorded for the owner's review without being
fixed during this audit.

---

## 13. Critical security/behavioral questions

1. **Can `prompt optimize` reach the AI provider while
   `prompt_optimizer.enabled=false`?** **NO.** `_gate()` is called
   before `provider.ask()` in every code path; confirmed via
   `_test_disabled_rejects_optimize_with_zero_downstream_calls`,
   independently re-run, and via this audit's own dummy-object probe
   (Section 9) showing zero provider calls even in the Finding 1/2
   edge cases.
2. **Can input exceeding `max_input_size` reach the provider?** **NO.**
   Rejected in every case tested, including via an independent
   mutation test confirming removing the check causes real failures.
3. **Can the rate limit be bypassed by rapid, repeated calls?** **NO.**
   Confirmed via `_test_rate_limit_blocks_immediate_second_call`
   (re-run) and an independent mutation test.
4. **Can `prompt optimize` write to `paths.prompts` or anywhere else
   (D4)?** **NO.** Zero write call (`write_text`/`open(..., "w"/"a")`)
   exists anywhere in `skill.py`; confirmed by `grep`.
5. **Can `prompt optimize` autonomously change any configuration,
   prompt, or other component's behavior?** **NO.** Zero write path
   to `Config`, `PromptManager`, `AgentEngine`, or `PlanningEngine`
   exists anywhere in `skill.py`.
6. **Can EP-055 modify or depend on `AIProvider`/`ProviderManager`/
   `PromptBuilder`/`PromptManager` behavior?** **NO.** All four are
   confirmed byte-identical to their pre-EP-055 state (Section 11)
   and used strictly through their existing, unmodified public APIs
   (Section 7) — `PromptBuilder`/`PromptManager` are, in fact, never
   called at all.
7. **Does a disabled `prompt_optimizer.enabled` flag leak any
   information to a caller?** **PARTIALLY — see Findings 1 and 2.**
   The numeric `max_input_size` value can be observed via an error
   message (Finding 2, matching EP-054's own previously-accepted
   Finding 2 pattern). More significantly, whether a given
   `--template` name exists, is empty, or is unreadable — plus its
   exact, absolute resolved filesystem path — can be observed via an
   error message while disabled, and the underlying file is actually
   read from disk in the process (Finding 1). In neither case is
   template *content*, or any data more sensitive than the operator's
   own already-visible `config.yaml`/`paths.prompts` directory
   listing, ever disclosed, and no AI-provider call ever occurs.

---

## 14. Final audit matrix

| Area | Result |
|---|---|
| Owner Decisions D1–D9 | PASS (zero findings against literal Owner Decision text) |
| Architecture | PASS |
| Commands/functional behavior | PASS |
| Security/capability gates | PASS (Findings 1 and 2) |
| Configuration/limits | PASS |
| Provider/template-file integration | PASS |
| Test quality | PASS |
| Regression (EP-050–EP-054) | PASS (all figures independently reproduced exactly) |
| File scope | PASS |
| Design↔implementation consistency | PASS (Findings 1 and 2) |
| Critical security/behavioral questions | 6/7 answered NO (safe); 1 partial (Findings 1 and 2) |

---

## 15. Findings

### Finding 1 — `prompt optimize --template <name>` reads the filesystem and discloses template existence/path before the `prompt_optimizer.enabled` gate

**Severity: MEDIUM**

**Description:** In `PromptOptimizerModule._optimize()`,
`self._resolve_input(arguments)` — which, for `--template` arguments,
calls `self._load_template(name)` and therefore performs a real
`Path.is_file()` check and `Path.read_text()` disk read against the
configured `paths.prompts` directory — executes *before*
`self._gate()` is called. This audit empirically confirmed that,
while `prompt_optimizer.enabled=false`:

- Loading an **existing** template file actually reads its content
  from disk (no exception is raised) before the disabled message is
  ultimately returned once `_gate()` is reached (content is never
  included in the response — confirmed by an explicit check).
- Loading a **non-existent** template returns `"prompt optimize:
  template not found: '<name>' (expected '<full absolute path>')."` —
  disclosing both the fact that the name does not exist and the exact
  resolved filesystem path — without `_gate()` ever being reached.
- Loading an **empty** template file returns `"prompt optimize:
  template '<name>' is empty."` — again disclosing a filesystem fact
  before `_gate()` is reached.

This is inconsistent with the "gate first, then everything else"
ordering every prior Phase 7/8/EP-054 skill
(`desktop`/`browser`/`file`/`vision`/`reflect`) established, and it is
a materially new surface (no existing, pre-EP-055 user-facing command
anywhere in the repository exposed `paths.prompts` as a
directly-queryable, name-based file-existence check — `EP055_DESIGN.md`
Section 3.2 confirmed `PromptBuilder.load_template()`'s equivalent
functionality had zero callers before EP-055).

**Impact:** No AI-provider call ever occurs in this case (confirmed
via a `DummyProviderManager` that raises `AssertionError` if called —
never triggered), so there is no provider-cost bypass. No template
*content* is ever disclosed while disabled (confirmed by explicit
probe). The practical severity is a filesystem-existence/path
disclosure limited entirely to the server's own already-configured,
non-secret `paths.prompts` directory (not an attacker-supplied path —
`name` is joined only as `<name>.txt` within that fixed directory, so
this is not a path-traversal concern by itself, though it does confirm
a template-name enumeration oracle is reachable even while the
namespace is nominally disabled). This is a genuinely new information-
disclosure surface, not merely a config-value echo (unlike EP-054's
Finding 2 / this audit's own Finding 2), which is why this audit rates
it MEDIUM rather than LOW.

**Evidence:** Direct code reading of `_optimize()`'s statement order
(Section 3); live probes against the real, unmutated code (Section 9)
confirming the exact behavior in all three cases (found/not-found/
empty) and confirming zero provider calls via an
`AssertionError`-raising dummy in every case.

**Recommendation (not performed — STEP 3 is read-only):** Move
`self._gate()` to execute immediately after argument-shape validation
and before `self._resolve_input()` is called — so
`prompt_optimizer.enabled=false` always short-circuits before any
filesystem access or config-value-dependent message is constructed,
matching the ordering `vision`/`file`/`browser`/`desktop`/`reflect`
already established. This would require moving the `max_input_size`
check (Finding 2) after the gate as well, since it currently also
precedes `_gate()` and depends on `_resolve_input()`'s result.

**Disposition:** Recorded as a non-blocking finding per the owner's
audit instructions. No source file was modified to fix or hide this
finding.

### Finding 2 — `max_input_size` cap check runs before the `prompt_optimizer.enabled` gate, leaking a config value while disabled

**Severity: LOW**

**Description:** In `PromptOptimizerModule._optimize()`, the block
that checks whether the resolved input text exceeds
`prompt_optimizer.max_input_size` executes before `self._gate()` is
called. This audit empirically confirmed that calling `prompt
optimize <text longer than max_input_size>` while
`prompt_optimizer.enabled=false` returns `"prompt optimize: input is
N character(s), exceeding 'prompt_optimizer.max_input_size' (M)."`
instead of the expected disabled message. This closely mirrors
EP-054's own previously-accepted Finding 2
(`max_message_count`/`reflection.enabled` ordering).

**Impact:** No functional or security bypass occurs — this audit
confirmed, via a `DummyProviderManager` that raises `AssertionError`
if called, that zero AI-provider call occurs in this case. The only
effect is that a caller who does not otherwise know whether Prompt
Optimizer is enabled can learn the numeric value of
`prompt_optimizer.max_input_size` (a non-secret, operator-configured
integer already visible in `config/config.yaml`) via the error
message's wording — no more sensitive than EP-054's own accepted
Finding 2.

**Evidence:** Direct code reading of `_optimize()`'s statement order
(Section 3); a live probe against the real, unmutated code (Section 9)
confirming the exact behavior and confirming zero provider calls via
an `AssertionError`-raising dummy.

**Recommendation (not performed — STEP 3 is read-only):** Addressed
by the same reordering recommended for Finding 1 — move `self._gate()`
to execute immediately after argument-shape validation, before both
`_resolve_input()` and the `max_input_size` check.

**Disposition:** Recorded as a non-blocking finding per the owner's
audit instructions. No source file was modified to fix or hide this
finding.

### Non-blocking observations (INFO)

- **INFO** — A failed provider call (`ProviderError`) does not advance
  the rate-limit clock (confirmed, Section 9) — a caller may retry
  immediately after a genuine failure. This is reasonable, intentional
  behavior (a failed call incurs no completed provider cost either),
  not a finding.
- **INFO** — This audit's own mutation-testing methodology (Section 8)
  required creating temporary, fully isolated scratch copies of the
  repository, each deleted immediately after use. None is, or ever
  was, part of the audited repository; disclosed here for transparency
  about the audit's own methodology only (Section 11 already
  independently confirms the real repository's scope is unaffected).
- **INFO** — Findings 1 and 2 share a single root cause (input
  resolution and size-checking both precede the gate) and a single
  proposed fix (Section 15's recommendation for Finding 1 resolves
  both). They are recorded as two findings, not one, because their
  impact differs materially in kind (filesystem-existence/path
  disclosure vs. a numeric config-value echo) and in severity.

No HIGH severity findings were identified.

---

## 16. Final verdict

```text
EP-055 STEP 3 — AUDIT PASSED WITH FINDINGS
```

All nine Owner Decisions (D1–D9) are implemented exactly as approved,
with zero findings against their literal text. Two related, non-
blocking ordering findings were identified through independent
probing beyond the registered test suite: Finding 1 (MEDIUM) — the
`--template` path performs a real filesystem read and discloses
template existence/path before the `prompt_optimizer.enabled` gate is
checked; Finding 2 (LOW) — the `max_input_size` cap check runs before
the same gate, allowing a non-secret config value to be observed via
an error message while the feature is disabled. In both cases, zero
AI-provider calls occur, no template content is ever disclosed, and
no resource-limit or provider-cost protection is bypassed. EP-017
Prompt Engine (`prompt.py`/`prompt_builder.py`/`prompt_manager.py`)
and every other DO-NOT-MODIFY file were confirmed byte-identical to
their pre-EP-055 state. The EP-055 test suite (52/0/0) and every
regression suite the owner reported (EP-054 76/0/0, EP-053 58/0/0,
EP-052 135/0/0, EP-051 105/0/0, EP-050 112/0/0) were independently
reproduced exactly from a clean process, and three independent
mutation tests confirmed the registered suite genuinely detects a
broken enabled-gate, a broken rate limit, and a broken resource cap.

No source, test, configuration, dependency, or Bootstrap file was
modified during this audit — STEP 3 is read-only per the repository's
established engineering workflow. STEP 4 (Finalization) requires the
owner's explicit approval before proceeding, including a decision on
whether Findings 1 and 2 should be fixed as part of STEP 4 or deferred
to a follow-up (Owner Decision, Section 17).

---

## 17. Owner Decision required before STEP 4

### D10 — Fix Findings 1/2's gate-ordering issue as part of STEP 4, or defer?

**Question:** Should STEP 4 (Finalization) include moving
`self._gate()` to execute before `_resolve_input()`/the
`max_input_size` check in `_optimize()` (resolving both Finding 1 and
Finding 2 with a single, minimal reordering), or should this be
deferred to a separate, later fix — mirroring how EP-054's own,
structurally identical Finding 2 was left unresolved through that
EP's STEP 4?

**Options:** (a) fix the ordering in STEP 4 — a small, behavior-
preserving reordering of already-existing checks within
`_optimize()`, changing no public interface, config key, or test
expectation other than the affected disabled-state error-message
paths; (b) defer — record both findings in `docs/BACKLOG.md`/
`docs/architecture/ARCHITECTURE_DEBT.md` (per
`AI_DEVELOPMENT_PLAYBOOK.md`'s Architecture Debt Workflow) and close
EP-055 with the findings outstanding, exactly as EP-054's own Finding
2 was closed.

**Recommended option:** (a) — unlike EP-054's Finding 2 (a single,
low-severity numeric-value echo), this EP's Finding 1 is a genuinely
new, previously-nonexistent, name-based filesystem-existence oracle
reachable even while the namespace is nominally disabled; the fix is
small (reordering two already-written blocks, no new logic) and
removes a MEDIUM-severity finding at negligible risk, whereas EP-054
elected to defer only a LOW-severity finding.

**This audit does not perform this fix itself** — STEP 3 is read-only
per the repository's established engineering workflow and per the
owner's own explicit instruction for this audit. This decision is
presented for the owner's approval before STEP 4 begins.

---

## 18. STEP 4 remediation — Findings 1 and 2 RESOLVED by Owner Decision D10

**The owner approved Owner Decision D10 option (a).** This section
records the STEP 4 fix and its independent verification. It is
appended, not merged into Sections 1-17 above, so the original
first-pass findings remain visible exactly as recorded.

### 18.1 What changed

`src/skills/prompt_optimizer/skill.py`'s `_optimize()` method was
reordered, and its input-resolution logic was split into two methods:

- **`_validate_optimize_arguments(arguments)`** (new) — performs only
  argument-shape validation (missing text, wrong `--template` argument
  count, or an all-whitespace free-text join). Zero filesystem access,
  zero config-value-dependent messaging. Safe to run before the gate,
  exactly like every other `CommandModule`'s own usage-error checks.
- **`_resolve_input(arguments)`** (narrowed) — now assumes the shape
  has already been validated, and performs the one side-effecting
  step: reading a template file from disk for `--template` arguments
  (via the unchanged `_load_template()`), or joining free-text
  arguments (no side effect).

`_optimize()`'s new order is: `_validate_optimize_arguments()` →
`self._gate()` → `self._check_rate_limit()` → `self._resolve_input()`
→ the `max_input_size` check → the provider call. Previously it was:
`_resolve_input()` (with inline shape validation) → the
`max_input_size` check → `self._gate()` → `self._check_rate_limit()`
→ the provider call. **The gate now runs before any filesystem access
or config-value-dependent message is produced**, resolving both
findings with their shared root cause and shared fix.

No other method changed. `_load_template()`, `_gate()`,
`_check_rate_limit()`, the config keys, the `HELP_TEXT`, the action
registry, and every constant are byte-for-byte unchanged. The file
grew from 410 to 465 lines (well under the 500-line hard limit) —
the increase is entirely the extracted `_validate_optimize_arguments()`
method and its docstring, plus expanded docstrings on `_optimize()`
and `_resolve_input()` explaining the new ordering rationale for future
maintainers.

### 18.2 Independent verification that the fix is real, not merely test-shaped

This audit did not simply trust that new, green tests prove the fix.
It constructed an isolated scratch copy with the **exact pre-fix
ordering restored** (never touching the real, audited repository) and
confirmed the new tests **genuinely fail** against it:

- Restoring the pre-fix `_optimize()`/`_resolve_input()` and re-running
  `_test_disabled_rejects_existing_template_without_reading_file`
  against it produced a real, uncaught `AssertionError:
  _load_template() must not be called while prompt_optimizer is
  disabled` — proving the test would have caught the original bug,
  not merely passing vacuously.
- Isolating `_test_disabled_rejects_oversized_input_without_leaking_max_input_size`'s
  core assertion against the same restored pre-fix code showed
  `result.message` was the size-exceeded message
  (`"prompt optimize: input is 32 character(s), exceeding
  'prompt_optimizer.max_input_size' (10)."`), not `_DISABLED_MESSAGE`
  — confirming that assertion, too, would have failed against the
  original bug.

This is the same "prove the test bites" methodology this audit's
Section 8 already applied to the original 52 assertions via mutation
testing — applied here to the 4 new test methods (12 additional
assertions) specifically written to close Findings 1 and 2.

### 18.3 Direct behavioral re-verification against the real, fixed code

Independent of the test suite, this audit re-ran the same three live
probes from Section 9 against the real, fixed code:

| Probe | Pre-fix result (Section 9) | Post-fix result |
|---|---|---|
| Over-size input while disabled | Leaked `max_input_size` value via error message | Returns `_DISABLED_MESSAGE` verbatim; `"max_input_size"` does not appear in the message |
| Existing `--template` while disabled | File was read from disk (no exception); disabled message returned afterward | `_load_template()` is never reached — verified via a poisoned subclass that raises if it is called; `_DISABLED_MESSAGE` returned |
| Not-found `--template` while disabled | Disclosed `"template not found: '<name>' (expected '<path>')"` | Returns `_DISABLED_MESSAGE` verbatim; `"not found"` does not appear in the message |
| Empty `--template` while disabled | Disclosed `"template '<name>' is empty."` | Returns `_DISABLED_MESSAGE` verbatim; `"empty"` does not appear in the message |

**Both findings are confirmed resolved, not merely covered by new
tests that could pass regardless of the underlying behavior.**

### 18.4 Regression re-verification (behavior-preserving while enabled)

The full, pre-existing 52-assertion suite (Sections 4-14 of this
audit) was re-run against the fixed code and **all 52 continued to
pass unchanged** — confirming the reorder is behavior-preserving for
every previously-verified enabled-path scenario (positive-path
generation, template loading, rate limiting, resource capping,
provider-error handling, `CommandRouter` dispatch, `Bootstrap`
wiring). 12 new assertions were added (4 new test methods), bringing
the suite to **64 passed / 0 failed / 0 skipped**, independently
re-run from a clean process (cleared `__pycache__`).

The six regression suites the owner reported before STEP 3 began were
independently re-run again after the STEP 4 fix and reproduced
identical figures: EP-054 76/0/0, EP-053 58/0/0, EP-052 135/0/0,
EP-051 105/0/0, EP-050 112/0/0.

### 18.5 Scope re-verification after the STEP 4 fix

Re-running this audit's Section 11 file-scope methodology
(`find . -newer docs/architecture/designs/EP055_DESIGN.md -type f`)
after the STEP 4 fix shows exactly: `config/config.yaml`,
`src/bootstrap.py`, `src/modules/test_module.py`,
`src/skills/prompt_optimizer/skill.py`,
`docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md`,
`tests/EP055/__init__.py`, `tests/EP055/test_prompt_optimizer.py` — no
new file outside this already-approved set. `config/config.yaml`,
`src/bootstrap.py`, and `src/modules/test_module.py` are unchanged
since STEP 2/3 (the STEP 4 fix touched only `skill.py` and the test
file). Byte-comparison of EP-017 Prompt Engine
(`prompt.py`/`prompt_builder.py`/`prompt_manager.py`) and every other
DO-NOT-MODIFY file against the original, pre-EP-055 repository
archive was re-run after the fix and **all remain byte-identical**.

### 18.6 Owner Decisions D1–D10 re-verification

Re-checked after the fix: D1-D9 (Section 2) are unaffected by this
change — the fix touches only internal method ordering within the
already-approved `PromptOptimizerModule`, introduces no new
functionality, no new config key, no new dependency, no new namespace,
and does not alter D1's Candidate A scope, D4's return-only behavior,
or any other Owner Decision's substance. **D10 (fix in STEP 4) is now
implemented and verified.**

### 18.7 Status

| Finding | Original severity | Status |
|---|---|---|
| Finding 1 — `--template` filesystem read/existence disclosure before the gate | MEDIUM | **RESOLVED** by Owner Decision D10, verified in Sections 18.2-18.3 |
| Finding 2 — `max_input_size` value leak before the gate | LOW | **RESOLVED** by Owner Decision D10, verified in Sections 18.2-18.3 |

**No new finding was introduced by the fix.** The fix is minimal
(one method split, one reordering, zero new dependencies, zero new
config keys, zero behavior change while enabled) and fully verified
by both negative evidence (the fix-reverted scratch copy genuinely
fails the new tests / reproduces the original leaks) and positive
evidence (the full, unchanged 52-assertion suite plus all reported
regression suites still pass).

```text
EP-055 STEP 3 (with STEP 4 remediation) — FINAL VERDICT: PASS AFTER REMEDIATION
Owner Decisions D1-D10: all implemented and verified, zero open findings
EP-017 Prompt Engine: confirmed unmodified (before and after the fix)
File scope: confirmed exactly matching the approved set (before and after the fix)
Tests: EP055 64/0/0 (52 original + 12 new, all independently re-verified)
Regression: EP054 76/0/0, EP053 58/0/0, EP052 135/0/0, EP051 105/0/0, EP050 112/0/0
```
