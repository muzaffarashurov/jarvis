# EP-069.4 Architecture Audit

STEP 3: Independent Audit

Auditor role: independent senior software architect / code reviewer /
test-audit engineer. This audit was performed against the actual
checked-out repository state, the actual implementation files, the
actual test file, and the actual approved STEP 1 design document —
not against the STEP 2 report's own claims, which are treated here as
evidence to verify, not as ground truth.

## 1. Scope

Audits EP-069.4 — Unified Capability Abstraction — STEP 2
implementation against its approved STEP 1 design
(`docs/architecture/designs/EP069_4_DESIGN.md`). Does not redesign
EP-069, EP-069.1, EP-069.2, EP-069.3, or EP-056 — those are inspected
only for compatibility, convention, and naming-collision context, per
the calling task's Section 2.4.

## 2. Documents Reviewed

- `docs/architecture/designs/EP069_4_DESIGN.md` (1,032 lines) — read
  in full, including Sections 1-28 (target selection, scope,
  architecture, data/contracts, testing strategy, acceptance criteria,
  Owner Decisions 1-7, risks, deferred decisions, consistency check).
- `docs/architecture/designs/EP069_3_DESIGN.md` — for prior-EP
  convention context (error hierarchy precedent, test-package
  convention).
- `src/core/tool/tool.py`, `tool_registry.py`, `tool_provider.py`,
  `tool_result.py` — for pattern-fidelity comparison (registry
  contract, provider/ABC contract, result/status contract, error
  hierarchy).
- `src/skills/capability_registry/skill.py` (EP-056) — for the
  naming-collision boundary review (Section 10).

## 3. Implementation Reviewed

Every file in the STEP 2 change set was opened and read in full,
directly from disk (not from the STEP 2 report):

- `src/core/capability/__init__.py` (86 lines)
- `src/core/capability/capability.py` (273 lines)
- `src/core/capability/capability_registry.py` (134 lines)
- `src/core/capability/capability_backend.py` (132 lines)
- `tests/EP069_4/__init__.py` (0 lines, empty marker)
- `tests/EP069_4/test_unified_capability_abstraction.py` (485 lines)
- `src/modules/test_module.py` (diff only: `git diff` inspected
  directly, confirmed to be a single added import line)

## 4. STEP 1 → STEP 2 Conformance

| Requirement (STEP 1 source) | Implementation | Evidence | Status |
|---|---|---|---|
| Package at `src/core/capability/`, 4 files (Section 13.1) | Exactly 4 files created at that path | `find src/core/capability -type f` returns exactly `__init__.py`, `capability.py`, `capability_registry.py`, `capability_backend.py` | PASS |
| `Capability` frozen dataclass with the 10 named fields (Section 14.1) | All 10 fields present with matching types/defaults | `capability.py` lines 186-196 | PASS |
| `CapabilitySourceKind` — exactly `INTERNAL`/`LOCAL_CLI`/`REST_API`/`BROWSER_SERVICE` (Section 12.1) | Exact 4-member enum | `capability.py` lines 39-53 | PASS |
| `CapabilityTrustLevel` — exactly 3 levels (Section 14.2, Owner Decision D6) | `TRUSTED_INTERNAL`/`TRUSTED_CONFIGURED`/`UNVERIFIED`, no numeric score | `capability.py` lines 56-74 | PASS |
| `CapabilitySchema` hand-rolled, no schema library dependency (Section 13.2, Owner Decision D3) | Plain frozen dataclasses (`CapabilitySchema`, `CapabilitySchemaField`); `requirements.txt` unmodified | `capability.py` lines 98-143; `git diff requirements.txt` empty | PASS |
| `Capability.create()` validating factory, not raw `__init__` (Section 14.3) | `Capability.create()` static method performs all validation, returns a `Capability` via its plain constructor | `capability.py` lines 198-273 | PASS |
| Validation: blank id/name/description, duplicate permission tag, duplicate schema field name (Section 14.3) | All four checks present and independently raise `CapabilityValidationError` | `capability.py` lines 247-259; verified by direct test execution (Section 14 below) | PASS |
| `CapabilityRegistry` — register/unregister/get/find/list/is_registered, mirroring `ToolRegistry` (Section 13.3) | All 6 methods present, identical semantics (thread lock, sorted `list()`, `INFO`-level log on register/unregister only) | `capability_registry.py` lines 53-134; compared line-by-line against `src/core/tool/tool_registry.py` | PASS |
| `CapabilityRegistry` does not import `ToolRegistry`/`PluginRegistry` (Section 13.3) | No such import present | `capability_registry.py` imports only `Capability`, `loguru`, `threading.Lock` | PASS |
| `CapabilityBackend` ABC, 2 abstract + 1 default method, zero concrete subclasses (Section 13.3, Owner Decision D4) | Exactly this shape; `grep` for `CapabilityBackend)` subclasses in `src/` finds none outside the test file's test-only fake | `capability_backend.py` lines 79-132; `grep -rn "CapabilityBackend)" src/` matches only the ABC's own declaration | PASS |
| `CapabilityResult`/`CapabilityStatus` mirror `ToolResult`/`ToolStatus` exactly (Section 13.3) | Field-for-field match (`capability_id`↔`tool_id`, identical `status`/`message`/`data`); `COMPLETED`/`FAILED` identical | `capability_backend.py` lines 39-72 vs. `src/core/tool/tool_result.py` | PASS |
| Error hierarchy: `CapabilityError` (root), `CapabilityRegistryError`, `CapabilityNotFoundError`, `CapabilityValidationError` (Section 12.1) | `CapabilityValidationError`, `CapabilityRegistryError`, `CapabilityNotFoundError` all exist and each directly subclass `Exception`; **no `CapabilityError` root class exists anywhere in the shipped code** | `grep -n "^class.*Error" src/core/capability/*.py` — see AUDIT-001 | **PARTIAL** |
| No bootstrap/config/CLI-namespace wiring (Section 8, Non-Goals) | `src/bootstrap.py` and `config/config.yaml` are byte-identical to the pre-STEP-2 commit | `git diff bootstrap.py config/config.yaml` empty | PASS |
| No modification to `Tool`, `Plugin`, `CapabilityRegistryModule` (Section 8/22, Protected components) | All three files untouched | `git diff src/core/tool/ src/core/plugins/ src/skills/capability_registry/` empty | PASS |
| Test package `tests/EP069_4/`, isolated, registered in `test_module.py` (Section 19/21) | Present, registered with a single-line addition matching every prior EP's own precedent | `git diff --stat` shows `src/modules/test_module.py \| 1 +` | PASS |
| Acceptance criteria 1-8 (Section 19) | All 8 independently verified — see Section 14 (Test Review) below | Direct test re-execution | PASS |

## 5. Owner Decisions Verification

| Decision | Implementation evidence | Verdict |
|---|---|---|
| D1 — New Level-1 package `src/core/capability/`, not folded into `src/core/tool/` | Confirmed: separate package, separate `__init__.py` | PASS |
| D2 — `Capability` is an independent model, `Tool` left unmodified | `git diff src/core/tool/` is empty; no shared base class or field added to `Tool` | PASS |
| D3 — Hand-rolled `CapabilitySchema`, no `pydantic`/`jsonschema` | `requirements.txt` unmodified; `capability.py` imports only `dataclasses`/`enum` | PASS |
| D4 — Zero concrete `CapabilityBackend` implementations shipped | `capability_backend.py` contains only the ABC; the only concrete subclass in the entire diff is `_FakeCapabilityBackend`, defined inside the test file for test purposes only, not exported and not part of the public API (`tests/EP069_4/test_unified_capability_abstraction.py` line 50; not present in `src/core/capability/__init__.py`'s `__all__`) | PASS |
| D5 — `required_permissions` is a free-form `tuple[str, ...]`, not a typed permission object | `capability.py` line 192 | PASS |
| D6 — `CapabilityTrustLevel` has exactly 3 levels, not a numeric score | `capability.py` lines 56-74 | PASS |
| D7 — `CapabilityRegistryModule` (EP-056) not touched, renamed, or extended | `git diff src/skills/capability_registry/` is empty | PASS |

## 6. Architecture Review

- **Placement**: `src/core/capability/` sits at Core Level 1, alongside
  `src/core/tool/`, matching Section 13.1's placement rationale and the
  repository's own Level-1 examples list (which names "tool registry"
  explicitly). Confirmed correct — no Level-3 (capability-domain, in
  the unrelated sense) concept is referenced anywhere in the package.
- **Granularity**: 4 files, matching `src/core/tool/`'s own
  one-file-per-concern granularity, deliberately not
  `src/core/plugins/`'s 6-file granularity — correctly justified in
  Section 13.1 (no manifest/discovery/loader equivalent needed yet)
  and correctly followed in the implementation.
- **Reuse of established patterns**: the `*Registry` catalog shape
  (lock, register/unregister/get/find/list/is_registered, sorted
  `list()`, two `INFO` log lines) and the `*Provider`/ABC contract
  shape (identity method, one domain-action method, a defaulted
  `is_available()`) are both reused faithfully, verified by direct
  line-by-line comparison against `src/core/tool/tool_registry.py` and
  `src/core/tool/tool_provider.py`.

## 7. Capability Model Review

- **Identity**: `id: str` is the sole identity field, used as the
  `CapabilityRegistry` dict key — correctly matches `Tool.id`/
  `Plugin.id`'s own convention, no compound or derived identity.
- **Metadata**: `name`, `description`, `source`, `version` are all
  plain `str` fields with sane, documented defaults (`version` default
  `"0.0.0"`, `source` default `""`) — consistent with the design's
  intent that these are free-text provenance fields, not yet
  structured (Section 14.1, explicitly deferred to EP-069.6/.7).
- **`source_kind` semantics**: classification-only, never branched on
  anywhere in `capability.py`, `capability_registry.py`, or
  `capability_backend.py` — confirmed by inspection; no dispatch logic
  exists in this EP, matching Section 12.1's explicit constraint.
- **`trust_level` semantics**: defaults to `UNVERIFIED` both on the
  bare dataclass default (line 193) and in `Capability.create()`'s
  keyword default (line 208) — consistent, safe default, matching
  Section 14.2's stated rationale ("the safe default for any future
  automatically discovered capability").
- **`CapabilityFieldKind` semantics**: six flat primitive kinds
  (`str`/`int`/`float`/`bool`/`list`/`dict`), deliberately no
  nested/recursive kind — matches Section 13.2/25's explicit,
  documented deferral.
- **Schema representation**: `CapabilitySchema.fields` is a `tuple`
  (immutable), not a `list` — correctly avoids a mutable-collection
  field on a `frozen=True` dataclass. `CapabilitySchemaField` is itself
  `frozen=True`.
- **Validation behavior**: `Capability.create()` checks id/name/
  description non-blank, duplicate permission tags, and delegates
  schema-field-uniqueness checking to `CapabilitySchema.validate()`
  for both `input_schema` and `output_schema` independently (lines
  256-259) — matches the four failure modes enumerated in Section
  14.3 exactly, verified functionally in Section 14 below.
- **Invalid states**: a `Capability` instance can still in principle
  be constructed by calling the bare dataclass constructor directly
  (bypassing `Capability.create()`'s validation), since `frozen=True`
  dataclasses do not enforce `__post_init__` validation by default and
  none was added. This is an accepted, explicitly documented trade-off
  in the approved design (Section 14.3: "a separate validating
  constructor, not a permissive raw one" — implying the raw
  constructor remains permissive by design, mirroring
  `PluginManifest.from_dict()` vs. `PluginManifest.__init__`'s own
  precedent in this repository). Not a defect; recorded as
  AUDIT-003 (Informational) for completeness.

**Checked for and not found**: mutable-state leaks (no mutable
collection field exists on any of the four frozen dataclasses;
`required_permissions` and `CapabilitySchema.fields` are both
`tuple`); accidental coupling (no import of `Tool`/`Plugin`/anything
outside the `capability` package or the standard library); ambiguous
defaults (`trust_level` defaults consistently to `UNVERIFIED`
everywhere it can be set); incorrect equality/hash semantics (all four
dataclasses are `frozen=True` with only hashable field types — tuples
of frozen dataclasses/strings, enums — so the auto-generated
`__eq__`/`__hash__` pair is well-formed; confirmed by direct test:
`_test_registry_register_and_get` asserts `retrieved == capability`,
which passed); unsafe validation (validation raises a specific,
documented exception type in every checked path, no bare `except`,
no swallowed exception); inappropriate inheritance (no inheritance
relationship exists among `Capability`/`CapabilitySchema`/
`CapabilitySchemaField` — all are independent dataclasses, as designed).

## 8. Capability Registry Review

- **Registration semantics**: `register()` raises
  `CapabilityRegistryError` on a duplicate id under lock, otherwise
  inserts and logs — verified functionally.
- **Lookup semantics**: `get()` raises `CapabilityNotFoundError` for
  an unknown id; `find()` returns `None` for the same case without
  raising — a clear, intentional two-method split matching
  `ToolRegistry`'s own convention exactly (confirmed by inspecting
  `src/core/tool/tool_registry.py`).
- **Duplicate handling**: covered above; verified functionally (see
  Section 14).
- **Missing-capability behavior**: `unregister()` also raises
  `CapabilityNotFoundError` for an unknown id, consistent with `get()`.
- **Ordering guarantees**: `list()` explicitly sorts by `id` (line
  122) — matches the one ordering guarantee Section 13.3 specifies;
  verified functionally with a two-entry, reverse-insertion-order test
  (`_test_registry_list_sorted_by_id`).
- **Mutation behavior**: `list()` returns a new `list` object each
  call (via `sorted(...)`), not a live view into the internal dict —
  callers cannot corrupt the registry's internal state by mutating the
  returned list. The internal `dict` itself (`self._capabilities`) is
  a private, single-underscore-prefixed attribute, never returned by
  reference from any public method.
- **Encapsulation**: `_capabilities` and `_lock` are both
  underscore-prefixed and never exposed; every mutation goes through
  `register()`/`unregister()`, both of which acquire the lock.
- **Error hierarchy**: `CapabilityRegistryError`/`CapabilityNotFoundError`
  both directly subclass `Exception`, exactly mirroring the real
  `ToolRegistryError`/`ToolNotFoundError` (verified: both of those also
  directly subclass `Exception`, not a shared `ToolError` root, despite
  `ToolError` existing elsewhere in the same package for a different
  file's classes) — this specific pairing is therefore faithfully
  reproduced. See AUDIT-001 for the separate, package-wide
  `CapabilityError` root gap.
- **Public API**: exactly the 6 methods Section 13.3 specifies, no
  more.
- **Dependency direction**: imports only `Capability` (same package)
  plus `threading`/`loguru` — no import of `ToolRegistry`/
  `PluginRegistry`, confirmed by direct inspection of the import block.

**Confirmed the registry has NOT silently become**: a discovery
engine (no ranking, scoring, or task-matching method exists — `find`/
`get`/`list` are the only read methods, all exact-id or full-catalog);
a ranking engine (no sort key other than `id`); a lifecycle manager (no
versioning, enable/disable, update, or revocation method — only
register/unregister exist, matching the minimal baseline Section 8
explicitly permits); a backend factory (no method returns or
constructs a `CapabilityBackend`); a policy engine or security/trust
enforcement system (no method reads `required_permissions` or
`trust_level` for any decision — those fields pass through
`CapabilityRegistry` inertly, exactly as designed).

## 9. Capability Backend Review

- **ABC/contract correctness**: `CapabilityBackend(ABC)` with
  `@abstractmethod` on both `backend_kind()` and `invoke()`; attempting
  direct instantiation raises `TypeError` (Python's standard ABC
  enforcement) — verified functionally
  (`_test_backend_cannot_be_instantiated_directly`, passed).
- **Abstract methods**: exactly the two Section 13.3 specifies; no
  extra abstract method was added.
- **Return contract**: `invoke()` is typed to return `CapabilityResult`
  in the abstract signature; the concrete test-only fake honors this.
- **Status semantics**: `CapabilityStatus.COMPLETED`/`FAILED` exactly
  mirror `ToolStatus`.
- **Error semantics**: `CapabilityBackendError(Exception)` exists as a
  base class "for every exception raised by a `CapabilityBackend`"
  (docstring) — since zero concrete backends ship in this EP, nothing
  in the shipped code actually raises it yet; this is consistent with
  Section 13.3 ("Error handling: `CapabilityBackendError` base class")
  and is not a defect (an unused-but-defined contract element for a
  contract with no concrete implementer yet is expected here).
- **Dependency direction**: imports `Capability`/`CapabilitySourceKind`
  from the same package only; no import of `ToolProvider`/`ToolEngine`
  or anything outside `src/core/capability/`.
- **Extensibility**: the two-abstract-plus-one-default shape is
  minimal and directly modeled on the already-proven `ToolProvider`
  shape (verified by direct comparison), rather than speculatively
  enumerating methods for backend kinds this EP does not implement.

**Confirmed STEP 2 did not prematurely implement a concrete backend**:
`grep -rn "(CapabilityBackend)" src/` (excluding the ABC's own
declaration) returns no match anywhere under `src/`. The only concrete
subclass in the entire STEP 2 diff, `_FakeCapabilityBackend`, is
defined and used exclusively inside
`tests/EP069_4/test_unified_capability_abstraction.py`, is not
exported from the package's `__init__.py`, and is not referenced by
any production code path — it exists solely to exercise the ABC's
contract (`is_available()`'s default, `invoke()`'s return shape) in a
test, which is the same technique this repository's own
`ToolProvider` tests would need for an ABC with no concrete production
implementation. This matches Owner Decision D4 exactly.

**Confirmed the abstraction is not over-engineered**: three methods
total (two abstract, one defaulted), no manager, no factory, no
registration mechanism for backends, no configuration hook — the
minimum shape needed to prove the contract is implementable, nothing
more.

## 10. EP056 Boundary Review

- **Actual naming collision**: yes, at the word level only —
  `Capability` (this EP's new class) and `CapabilityRegistryModule`
  (EP-056's existing, unmodified `CommandModule`) share the word
  "capability," and both live under paths containing the word
  "capability" (`src/core/capability/` vs.
  `src/skills/capability_registry/`).
- **Two competing abstractions?** No. `CapabilityRegistryModule`
  defines no domain model of its own (confirmed by direct inspection
  of `src/skills/capability_registry/skill.py`, unchanged by this
  diff) — it composes a text summary from `PluginService`/
  `CommandRouter` accessors. There is nothing for the new `Capability`
  class to compete with or duplicate.
- **Clear package-boundary distinction?** Yes — `src/core/capability/`
  (Core Level 1, new) vs. `src/skills/capability_registry/` (a Level-3
  skill, EP-056, untouched). Different directories, different
  packages, different consumers (a future discovery/security substrate
  vs. an existing prompt-context CLI command).
- **Did EP-069.4 accidentally duplicate or replace EP-056?** No —
  `git diff src/skills/capability_registry/` is empty; no file under
  that path was read for implementation purposes beyond the STEP 1
  investigation, and none was modified.
- **Will future integration be clear?** The new package's `__init__.py`
  docstring explicitly states "This package must NOT be confused with
  `src/skills/capability_registry/skill.py`'s `CapabilityRegistryModule`
  (EP-056)" and each of the four new source files' module docstrings
  repeats this disambiguation — directly fulfilling the STEP 1 Risk
  mitigation in Section 24 ("Mitigation: this document's explicit
  Section 11 analysis, referenced by class docstrings in STEP 2").
  Confirmed present in all four files by direct inspection.
- **Did STEP 1 explicitly accept the coexistence?** Yes — Section 11's
  full dedicated overlap analysis and Owner Decision D7 both explicitly
  decide not to touch, rename, or extend `CapabilityRegistryModule`,
  and Section 24 records the residual naming-confusion risk with an
  explicit, followed-through mitigation.

No architectural concern is raised here beyond the pre-existing,
already-documented naming risk, which was disclosed, accepted, and
mitigated as designed.

## 11. API Review

- **`__init__.py` exports**: 14 symbols in `__all__`, each one
  traceable to a symbol actually defined in one of the three
  implementation files — no undocumented or accidental export.
  Cross-checked: every name in `__all__` is imported at the top of
  `__init__.py` from exactly one of `capability.py`/
  `capability_backend.py`/`capability_registry.py`, and every public
  class/enum/exception defined in those three files appears in
  `__all__` (i.e., no unintentionally-hidden public symbol and no
  export of an undefined name).
- **Naming consistency**: every public name is prefixed `Capability`,
  consistent with the package's own subject and avoiding collision
  with `Tool`/`Plugin`/`ToolResult`/`ToolStatus`'s own names.
- **Import cycles**: `capability.py` has no intra-package import;
  `capability_registry.py` imports only from `capability.py`;
  `capability_backend.py` imports only from `capability.py`;
  `__init__.py` imports from all three. This is a strict DAG (root →
  two independent branches → aggregator) with no cycle, confirmed both
  by static inspection and by the fact that `import src.core.capability`
  succeeds without error.
- **Package boundaries**: no import crosses into `src/core/tool/`,
  `src/core/plugins/`, `src/skills/`, `src/bootstrap.py`, or
  `config/`.
- **Documentation**: every public class has a docstring describing
  responsibility, attributes, and (where relevant) an explicit
  cross-reference to `EP069_4_DESIGN.md` and to the EP-056
  disambiguation.
- **Exception exposure**: `CapabilityValidationError`,
  `CapabilityRegistryError`, `CapabilityNotFoundError`,
  `CapabilityBackendError` are all present in `__all__` and all
  importable directly from the package root
  (`from src.core.capability import CapabilityValidationError`, etc.)
  — consistent exposure, no exception type left un-exported.

**Accidental API commitments**: none identified beyond the one
findings-worthy gap in Section 16 below (the absent `CapabilityError`
root, which is a scope gap, not an accidental over-commitment).

## 12. Dependency Review

- **Circular dependencies**: none. Verified both by static
  import-graph inspection (Section 11) and by successful runtime
  import of the full package.
- **Higher-level → lower-level imports into Core**: none — nothing
  under `src/services/`, `src/modules/`, or `src/skills/` (other than
  the untouched EP-056 module, which imports nothing new) imports
  `src.core.capability`. The one production-code touch point,
  `src/modules/test_module.py`, imports the *test* module
  (`tests.EP069_4.test_unified_capability_abstraction`) for
  registration purposes only, exactly mirroring every prior EP's own
  identical pattern — it does not import `src.core.capability`
  directly, and this is test-registration wiring, not application
  wiring.
- **Unnecessary dependencies**: none — the only imports in the three
  implementation files are `dataclasses`, `enum`, `abc`, `threading`,
  and `loguru` (already a project-wide dependency, used identically to
  `ToolRegistry`'s own `loguru` usage).
- **Hidden coupling to existing provider code**: none — confirmed no
  import of `src.core.tool.*` or `src.core.plugins.*` anywhere in
  `src/core/capability/`.
- **Coupling to CLI/bootstrap/configuration**: none — confirmed by
  empty diffs on `src/bootstrap.py` and `config/config.yaml`, and by
  the absence of any `CommandModule`/`CommandRouter` import in the new
  package.
- **Coupling to concrete implementations**: none — `CapabilityBackend`
  depends only on the abstract `Capability`/`CapabilitySourceKind`/
  `CapabilityResult` types, never on a concrete backend (there are
  none to depend on).

The new Core abstraction is fully independent, as the approved design
required.

## 13. Error Handling Review

- **Exception hierarchy**: as identified in Section 4/16, three of the
  four errors named in Section 12.1's "In Scope" list
  (`CapabilityRegistryError`, `CapabilityNotFoundError`,
  `CapabilityValidationError`) are implemented and correctly used, but
  the fourth named item, a root `CapabilityError`, does not exist —
  see AUDIT-001.
- **Exception specificity**: every `raise` site in the implementation
  raises a specific, purpose-named exception (never a bare `Exception`
  or a generic `ValueError`/`RuntimeError`) — `CapabilityValidationError`
  for all four `Capability.create()`/`CapabilitySchema.validate()`
  failure modes, `CapabilityRegistryError` for duplicate registration,
  `CapabilityNotFoundError` for unknown-id lookups.
- **Consistent behavior**: `get()` and `unregister()` both raise
  `CapabilityNotFoundError` for the same "unknown id" condition,
  consistent with each other and with `find()`'s deliberate
  non-raising counterpart.
- **Accidental exception swallowing**: none found — no `except` clause
  exists anywhere in the four implementation files' non-test code
  except `CapabilitySchema.validate()`'s own internal duplicate-name
  check (which does not swallow anything; it raises).
- **Inappropriate generic exceptions**: none.
- **Error messages**: every raised exception includes the offending
  id/field name in its message (e.g. `f"Capability already registered:
  '{capability.id}'."`), consistent with `ToolRegistryError`'s own
  message style.
- **Validation boundaries**: validation happens exactly once, at
  `Capability.create()`/`CapabilitySchema.validate()` construction
  time — no redundant or duplicated validation elsewhere.

No unnecessary defensive programming beyond what Section 14.3
required was found or expected.

## 14. Test Review

Executed directly (not merely trusted from the STEP 2 report), fresh,
via this repository's own `TestRunner`:

```
TestRunner().run("EP069_4")
```
Result: **Passed: 33, Failed: 0, Skipped: 0** (re-run independently
during this audit; matches the STEP 2 report's own claim).

**Positive cases confirmed present and exercised**: normal
`Capability.create()` construction (three separate tests — the
`memory_recall` worked example, a fully-populated REST example with a
two-field schema, and a defaults-only construction); valid
registration/lookup/list/is_registered on `CapabilityRegistry`; valid
`CapabilityBackend` contract behavior via the test-only fake
(`is_available()`'s inherited default, `invoke()`'s return shape,
`backend_kind()`).

**Negative cases confirmed present and exercised**: blank `id`, blank
`name`, blank `description` (three separate tests, not combined);
duplicate `required_permissions` tag; duplicate field name in
`input_schema`; duplicate field name in `output_schema` (tested
separately from `input_schema`, not merely assumed symmetric);
duplicate `CapabilityRegistry` registration; `get()`/`unregister()` on
an unknown id (tested separately, not conflated); `CapabilityBackend`
direct instantiation (`TypeError`).

**Boundary cases confirmed present**: an empty `CapabilitySchema`
(zero fields) validated directly; an empty `required_permissions`
tuple accepted; registry `list()` ordering verified with
reverse-insertion-order input (`zeta` registered before `alpha`,
`list()` still returns `["alpha", "zeta"]`) rather than an
already-sorted input that would not actually exercise the sort.

**Test quality — no tautologies found**: every test constructs a real
object or performs a real operation and asserts on a concrete,
specific outcome (an exact id, an exact tuple value, an exact boolean,
or an exact exception type caught via `try`/`except`) — none merely
asserts that a constructor did not raise with no further check, and
none re-asserts a value the test itself just set without exercising
any actual logic.
`assert_equal(len(capability.input_schema.fields), 2, ...)` and
similar counts are meaningful (they exercise `Capability.create()`'s
pass-through of a multi-field schema), not restatements of a literal.
One test, `_test_capability_backend_error_is_catchable`, is
comparatively weak (it only confirms `CapabilityBackendError` is a
well-formed, catchable `Exception` subclass, since no concrete backend
exists yet to raise it in practice) — this is not a defect (nothing
stronger could be tested against an intentionally unimplemented
contract), but is noted as AUDIT-004 (Informational).

**Assertion-count reconciliation**: `grep -c "self\.assert_"` on the
test file returns exactly 33, matching the reported 33 passes with no
discrepancy — the pass count is not inflated by any loop or
parametrization that would make "33" appear larger than the number of
actual distinct checks.

**Regression** (relevant previous EPs): see Section 15.

## 15. Regression Results

Executed directly via `src.testing.runner.TestRunner`, this
repository's own test framework — no alternative framework was
invented for this audit, per Section 18's requirement.

### Minimum required suite set (re-run fresh during this audit)

| Suite | Passed | Failed | Skipped | Time |
|---|---|---|---|---|
| EP069 | 68 | 0 | 0 | 0.009s |
| EP069_2 | 26 | 0 | 0 | 0.203s |
| EP069_3 | 80 | 0 | 0 | 0.043s |
| EP069_4 | 33 | 0 | 0 | 0.000s |
| EP056 | 62 | 0 | 0 | 0.375s |

All five pass with zero failures, independently confirming the STEP 2
report's own claim rather than merely trusting it.

### Broadest practical regression suite in this environment

All 60 suites registered in `src/modules/test_module.py` were
attempted individually (each in its own isolated call, so one suite's
failure could not mask or block another's execution):

- **58 of 60 suites ran to completion.** Aggregate across those 58:
  **7,232 passed / 3 failed / 1 skipped.**
- **2 of 60 suites could not run at all**: `EP046` and `EP048`, both
  raising `AudioCaptureError`/`StreamingAudioCaptureError`: *"The
  'sounddevice' package is not usable (missing package or missing
  PortAudio runtime library)."* This is a missing **system-level**
  audio library (PortAudio), not installable via `pip` in this
  sandbox, and unrelated to any Python dependency this EP could add.
- **3 failures occurred, all confined to `EP047` (2 failures) and
  `EP049` (1 failure, 1 skip)** — both voice/TTS-STT suites. Exact
  failure messages: `"Expected True"` and `"STT must remain available
  even if TTS construction fails"`.

**Pre-existing vs. introduced by this EP — verified, not assumed.**
This audit did not merely infer that the EP047/EP049 failures were
pre-existing; it confirmed it directly:

```
git stash --include-untracked   # removes every EP-069.4 STEP 2 file
TestRunner().run("EP047")       # → 47 passed / 2 failed, identical error messages
TestRunner().run("EP049")       # → 86 passed / 1 failed / 1 skipped, identical error message
git stash pop                   # restores STEP 2 changes exactly
```

With every EP-069.4 file (source, tests, and the `test_module.py`
registration line) completely removed from the working tree, EP047
and EP049 fail identically, with the same counts and the same error
strings. This proves conclusively that these 3 failures are
**pre-existing and environment-caused** (the same missing audio
runtime affecting `EP046`/`EP048`, manifesting as partial rather than
total failure in these two suites depending on how defensively each
test handles the missing hardware), not a regression introduced by
this EP. `git status --short` after the `stash pop` confirmed the
working tree was restored to the exact pre-audit state (Section 27).

**Distinguishing the three categories, per Section 18's requirement:**
- *Implementation failure (caused by this EP)*: none found.
- *Environment limitation*: `EP046`, `EP048` (cannot run at all —
  missing PortAudio system library).
- *Pre-existing failure (unrelated to this EP, confirmed via
  git-stash A/B comparison)*: `EP047` (2), `EP049` (1 fail + 1 skip).

No environment modification was made to force these suites to pass,
per Section 18's explicit instruction.

## 16. Findings

### AUDIT-001

**Severity:** MEDIUM

**Category:** Architecture / Correctness

**Title:** Approved "Error hierarchy" scope item (`CapabilityError` root) was not implemented

**Evidence:** `EP069_4_DESIGN.md` Section 12.1 ("In Scope") states
verbatim: *"Error hierarchy: `CapabilityError` (root),
`CapabilityRegistryError`, `CapabilityNotFoundError`,
`CapabilityValidationError`."* A repository-wide search
(`grep -rn "class CapabilityError" src/`) finds no such class anywhere
in the implementation. `CapabilityValidationError`
(`capability.py:94`), `CapabilityRegistryError`
(`capability_registry.py:23`), and `CapabilityNotFoundError`
(`capability_registry.py:27`) each directly subclass `Exception`, with
no shared `Capability`-package root between them (and
`CapabilityBackendError`, introduced separately in Section 13.3 but
not listed in Section 12.1, is likewise a direct `Exception`
subclass). The word "`CapabilityError`" appears exactly once in the
entire 1,032-line design document (Section 12.1) and nowhere else —
not in Section 13.3's per-component error-handling descriptions, not
in Section 14 (Data/contracts), not in the Section 19 acceptance
criteria, and not in the Section 20 STEP 2 file/implementation
forecast.

**Expected:** Per Section 12.1's explicit "In Scope" list, a
`CapabilityError` class should exist as the common root of this
package's exception hierarchy — directly analogous to the real,
already-established `ToolError` in `src/core/tool/tool_provider.py`
("Common root for every exception raised by Tool Engine (EP-031)...
Downstream packages can catch this single type to handle 'anything
tool-related' without needing to know about every specific failure
mode"). This project convention is proven to exist and be intentional
in this exact codebase, not a hypothetical best practice.

**Actual:** No `CapabilityError` class exists. A caller cannot catch
"any capability-package error" with one `except` clause; it must catch
`CapabilityValidationError`, `CapabilityRegistryError`,
`CapabilityNotFoundError`, and `CapabilityBackendError` individually
(or fall back to bare `Exception`).

**Impact:** Low practical impact today, since this EP ships no
consumer of these exceptions outside its own test suite. However, it
is a genuine, literal deviation from the Owner-approved STEP 1
scope's explicit text, and every future EP that catches
capability-related errors (EP-069.5/.6/.7, and any future
`CapabilityBackend` implementer) will either need this root added
later (a small but real backward-compatible-only-if-done-now change:
inserting a root class after subclasses already exist without
re-declaring inheritance would not be a breaking change, but adding it
now is simpler than retrofitting it once external catch-sites exist)
or will need to catch each specific exception type individually
forever.

**Recommendation:** Either (a) add a `CapabilityError(Exception)` root
class to `capability.py` (or a shared location) and make
`CapabilityValidationError`, `CapabilityRegistryError`,
`CapabilityNotFoundError`, and `CapabilityBackendError` inherit from
it, mirroring `ToolError`'s exact role; or (b) if the project owner
judges the flat hierarchy (matching `ToolRegistryError`/
`ToolNotFoundError`'s own precedent, which also do not inherit from
`ToolError`) to be the actually-intended design, amend
`EP069_4_DESIGN.md` Section 12.1 to remove the `CapabilityError (root)`
bullet so the approved document accurately reflects the accepted
architecture. Either resolution is a small, low-risk change suitable
for STEP 3.1 (Findings Resolution), not a re-architecture.

**Status:** OPEN

### AUDIT-002

**Severity:** INFORMATIONAL

**Category:** Testing

**Title:** `src/modules/test_module.py` was modified despite not appearing in the STEP 1/STEP 2 forecasted file list

**Evidence:** `git diff --stat` shows `src/modules/test_module.py | 1
+`. Neither `EP069_4_DESIGN.md` Section 21 ("Files expected to change
in STEP 2") nor the STEP 2 report's own original file forecast
included this file.

**Expected:** Per the calling task's Section 3 ("Implementation
Principles... Follow existing repository conventions for... test
structure"), every prior EP (EP001 through EP069.3, confirmed via
`git log --oneline -- src/modules/test_module.py`) made an identical
one-line addition to register its own test suite for the CLI `test`
command.

**Actual:** The change is present, is a single line, is purely
additive (an `import` statement), and does not alter any existing
line, comment, or behavior. `git diff` confirms no other part of the
file changed.

**Impact:** None — this is the expected, repository-mandated
mechanism for making a new EP's tests reachable via the standard `test`
CLI command, and its absence would itself have been a deviation from
established test-structure convention. This finding exists only to
record, for the audit trail, that the file list diverged from STEP 1's
own forecast and why that divergence is correct rather than scope
creep. The STEP 2 report itself already disclosed this exact
deviation with the same justification.

**Recommendation:** None required. No action needed.

**Status:** OPEN (informational — no resolution required before STEP 4)

### AUDIT-003

**Severity:** INFORMATIONAL

**Category:** Correctness / API

**Title:** `Capability`'s raw dataclass constructor remains unvalidated; only `Capability.create()` validates

**Evidence:** `Capability` is a plain `@dataclass(frozen=True)` with no
`__post_init__`. Calling `Capability(id="", name="", description="",
source_kind=..., input_schema=..., output_schema=...)` directly (not
via `Capability.create()`) would succeed and produce an instance with
a blank `id`, bypassing every validation check in
`Capability.create()`.

**Expected:** Per Section 14.3, `Capability.create()` is explicitly
described as *"a separate validating constructor, not a permissive raw
one"* — the phrasing itself acknowledges that the raw constructor
remains unvalidated by design, mirroring `PluginManifest`'s own
`from_dict()`-vs-bare-`__init__` precedent in this same repository.

**Actual:** Matches the documented, accepted design exactly — this is
not a deviation, only an observation worth recording so a future
reader does not mistake the raw constructor's permissiveness for an
oversight.

**Impact:** None under this EP's own scope (nothing in this EP or its
tests constructs a `Capability` via the raw constructor with invalid
data). Would only become a real risk if a future EP (e.g. EP-069.5's
discovery engine deserializing capabilities from an external source)
bypassed `Capability.create()` — recorded here so that future EP's own
STEP 1 is aware of the expectation.

**Recommendation:** None required for this EP. Future EPs that
construct `Capability` instances from untrusted or external data
should be reminded (e.g. in this class's own docstring, which already
partially covers this) to go through `Capability.create()`, not the
raw constructor.

**Status:** OPEN (informational — no resolution required before STEP 4)

### AUDIT-004

**Severity:** INFORMATIONAL

**Category:** Testing

**Title:** One test (`_test_capability_backend_error_is_catchable`) exercises a currently-inert contract element

**Evidence:** `tests/EP069_4/test_unified_capability_abstraction.py`
lines 473-485 test only that `CapabilityBackendError` is a catchable
`Exception` subclass, since no concrete `CapabilityBackend` exists yet
to raise it in a real code path.

**Expected:** N/A — this is the strongest test possible for an
intentionally-unimplemented contract element (Owner Decision D4); no
stronger test could exist without prematurely implementing a concrete
backend, which Section 8 explicitly forbids.

**Actual:** Matches expectations exactly.

**Impact:** None. Recorded only so this test is not mistaken for an
oversight or a weak/tautological test during a future review pass —
it is appropriately scoped to what is actually implemented.

**Recommendation:** None required.

**Status:** OPEN (informational — no resolution required before STEP 4)

## 17. Scope Verification

- **No hidden scope expansion**: confirmed. No discovery, ranking,
  automatic backend selection, security policy, trust enforcement,
  lifecycle management, persistence, configuration loading, bootstrap
  integration, CLI behavior change, provider migration, or unrelated
  refactoring was found anywhere in the diff. `git diff --stat` shows
  exactly one modified existing file (`src/modules/test_module.py`,
  +1 line, test-registration only) plus new, additive files.
- **No unrelated files modified**: confirmed via `git status --short`
  and `git diff --stat` — the full change set is exactly: 4 new files
  under `src/core/capability/`, 2 new files under `tests/EP069_4/`, 1
  new design document (from STEP 1, already present before STEP 2
  began), and the single-line `test_module.py` addition.
- **No debug artifacts, temporary files, or generated files**:
  confirmed — `find src/core/capability tests/EP069_4 -type f` lists
  exactly the 6 expected source/test files; all `__pycache__`
  directories under these paths are `.gitignore`-excluded (`git status
  --short --ignored` shows them as `!!`, not `??` or `M`), so none is
  part of the tracked change set.
- **No accidental configuration changes**: confirmed —
  `git diff config/config.yaml` is empty.
- **No Git operations performed by this audit**: confirmed (Section
  27).

## 18. Final Verdict

**PASS WITH WARNINGS**

Rationale: the STEP 2 implementation conforms to the approved STEP 1
design in every architecturally material respect — package placement,
component shapes, ABC/registry contracts, dependency direction,
Owner Decisions D1-D7, the EP-056 boundary, and scope discipline are
all verified correct by direct, independent inspection and test
execution, not merely by trusting the STEP 2 report. Regression is
clean (5 directly-relevant suites and the broadest practical
environment-reachable suite set all pass, with the 3 observed
failures independently proven pre-existing via a git-stash A/B
comparison). The one MEDIUM finding (AUDIT-001, a literal gap against
one explicit "In Scope" bullet in the approved design text) does not
represent an architectural, correctness, or regression defect — it is
a small, well-understood, easily resolved documentation/implementation
reconciliation that can be handled in STEP 3.1 without revisiting any
other part of the design or implementation. No CRITICAL or HIGH
finding exists.

---

## EP-069.4 STEP 3 — AUDIT COMPLETE
