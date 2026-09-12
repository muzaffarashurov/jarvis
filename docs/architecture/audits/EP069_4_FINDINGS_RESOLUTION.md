# EP-069.4 STEP 3.1 — Findings Resolution
## Unified Capability Abstraction

## Resolution Summary

STEP 3's independent audit (`docs/architecture/audits/
EP069_4_ARCHITECTURE_AUDIT.md`) reported one actionable finding
(AUDIT-001, MEDIUM) and three informational, no-action findings
(AUDIT-002, AUDIT-003, AUDIT-004). This STEP 3.1 pass:

- **Independently re-verified AUDIT-001** against the exact STEP 1
  text, the exact implementation, and this repository's own
  established `ToolError` precedent, before making any change.
- **Fixed AUDIT-001**: added a `CapabilityError(Exception)` root class
  and made `CapabilityValidationError`, `CapabilityRegistryError`,
  `CapabilityNotFoundError`, and `CapabilityBackendError` inherit from
  it, exactly mirroring `ToolError`'s documented role in
  `src/core/tool/tool_provider.py`.
- **Confirmed AUDIT-002, AUDIT-003, AUDIT-004 require no code change**
  — each was already correctly classified as informational by STEP 3,
  and this pass found no new evidence to revise that classification.
- Added 8 new, behavioral (non-tautological) regression tests directly
  targeting the fix; all pre-existing EP-069.4 tests pass unchanged.
- Re-ran the full required regression set (`EP069`, `EP069_2`,
  `EP069_3`, `EP069_4`, `EP056`) and the broadest practical suite
  reachable in this environment: **zero new regressions**, identical
  pre-existing failures/blocks to the STEP 3 baseline.

## 1. Resolution Scope

Changed only what AUDIT-001 required:

- `src/core/capability/capability.py` — added `CapabilityError`, made
  `CapabilityValidationError` inherit from it.
- `src/core/capability/capability_registry.py` — imported
  `CapabilityError`, made `CapabilityRegistryError`/
  `CapabilityNotFoundError` inherit from it.
- `src/core/capability/capability_backend.py` — imported
  `CapabilityError`, made `CapabilityBackendError` inherit from it.
- `src/core/capability/__init__.py` — exported `CapabilityError` from
  the package's public API (added to both the docstring's "Public
  API" list and `__all__`).
- `tests/EP069_4/test_unified_capability_abstraction.py` — added 5 new
  test methods (8 new assertions) exercising the fix; imported
  `CapabilityError`; updated the module docstring to describe this
  addition.

No previous EP (`EP-069`, `EP-069.1`, `EP-069.2`, `EP-069.3`,
`EP-056`) was modified. No unrelated file, comment, or existing
assertion was changed, renamed, or reformatted. `src/bootstrap.py`,
`config/config.yaml`, and `requirements.txt` remain untouched.

## 2. Source Documents Consulted

- `docs/architecture/designs/EP069_4_DESIGN.md` — specifically Section
  12.1 ("In Scope"), re-read verbatim before making any change.
- `docs/architecture/audits/EP069_4_ARCHITECTURE_AUDIT.md` — the
  original STEP 3 findings, preserved unmodified below in Section 4's
  addendum (not erased or rewritten).
- The current implementation (`src/core/capability/*.py`) and current
  tests (`tests/EP069_4/test_unified_capability_abstraction.py`), read
  fresh from disk.
- `src/core/tool/tool_provider.py` — the established `ToolError` root
  precedent.

## 3. Finding Classification (Resolution Matrix)

| AUDIT-ID | Severity | Finding | Required Action | Resolution Decision |
|---|---|---|---|---|
| AUDIT-001 | MEDIUM | `CapabilityError` root explicitly listed as In Scope (Section 12.1) but not implemented | Add the root class and wire the existing four exception types into it, or amend the design doc | **FIX** |
| AUDIT-002 | INFORMATIONAL | `test_module.py` +1 line not in STEP 1's forecast | None — already justified by established test-registration convention | **NO ACTION REQUIRED** |
| AUDIT-003 | INFORMATIONAL | `Capability`'s raw constructor bypasses validation | None — matches STEP 1's own documented trade-off | **NO ACTION REQUIRED** |
| AUDIT-004 | INFORMATIONAL | One test exercises an intentionally inert contract element | None — the strongest test possible without implementing a concrete backend | **NO ACTION REQUIRED** |

## 4. AUDIT-001 — Deep Verification (performed before any change)

Per the calling task's Section 6, the following was independently
verified rather than assumed:

1. **Was `CapabilityError` explicitly required by STEP 1?** Yes.
   `EP069_4_DESIGN.md` Section 12.1 ("In Scope") states verbatim:
   *"Error hierarchy: `CapabilityError` (root), `CapabilityRegistryError`,
   `CapabilityNotFoundError`, `CapabilityValidationError`."* This is a
   definitive "In Scope" bullet, not hedged language.
2. **Was it merely an example?** No — `grep -n "CapabilityError"
   docs/architecture/designs/EP069_4_DESIGN.md` shows exactly one
   occurrence, in the "In Scope" list itself; nowhere in the document
   is it framed as illustrative, optional, or a "candidate."
3. **Does STEP 1 define inheritance semantics?** Only implicitly, via
   the word "(root)" and the phrase "Error hierarchy" — Section 13.3's
   per-component error-handling descriptions never mention
   `CapabilityError` at all. This silence in Section 13.3 is itself
   part of why STEP 3 flagged the gap (the requirement existed in one
   place and was never carried through the rest of the same document).
4. **Does the repository establish root exception classes for similar
   domains?** Yes — `src/core/tool/tool_provider.py` defines
   `ToolError(Exception)`, documented verbatim as *"Common root for
   every exception raised by Tool Engine (EP-031). Downstream packages
   can catch this single type to handle 'anything tool-related'
   without needing to know about every specific failure mode."* This
   is the exact role Section 12.1 wanted `CapabilityError` to play.
5. **Would adding `CapabilityError` preserve the approved
   architecture?** Yes — it is a pure, behavior-free marker base class
   inserted between `Exception` and the four existing exception types.
   No existing raise site, catch site, or field changes.
6. **Would changing the STEP 1 document be more appropriate than
   changing code?** No — the fix is smaller and safer than a design
   amendment would be, directly matches an established, proven
   repository convention (`ToolError`), and preserves the ergonomic
   value ("catch one type for anything capability-related") the
   original design bullet was clearly intended to provide.
7. **Would the change break any existing API or test?** No — verified
   by execution (Section 5 below): every pre-existing
   `except CapabilityValidationError`/`except CapabilityRegistryError`/
   `except CapabilityNotFoundError`/`except CapabilityBackendError`
   catch site, in both the implementation and the test file, continues
   to match exactly as before, since subclassing does not change a
   class's own identity or its match against `except`.

**Conclusion: AUDIT-001 is a valid, actionable finding. FIX, not
DEFER or INVALID.**

### Resolution — FIXED

**What was changed:**

```python
# src/core/capability/capability.py

class CapabilityError(Exception):
    """Common root for every exception raised by the Capability package (EP-069.4).
    ...
    """


class CapabilityValidationError(CapabilityError):
    """Raised when a `Capability` or `CapabilitySchema` fails structural validation."""
```

```python
# src/core/capability/capability_registry.py
from src.core.capability.capability import Capability, CapabilityError

class CapabilityRegistryError(CapabilityError):
    ...

class CapabilityNotFoundError(CapabilityError):
    ...
```

```python
# src/core/capability/capability_backend.py
from src.core.capability.capability import Capability, CapabilityError, CapabilitySourceKind

class CapabilityBackendError(CapabilityError):
    ...
```

`CapabilityError` was placed in `capability.py` — the one module every
other module in the package already imports from — so this fix
introduces **zero new dependency edges** to the package's dependency
graph (`EP069_4_DESIGN.md` Section 16 remains accurate: `capability.py`
has no intra-package dependency; `capability_registry.py` and
`capability_backend.py` both already depended on `capability.py`
before this fix).

`CapabilityError` adds no new field, no new method, no logging, no
configuration, and no recovery behavior — a plain marker class, per
the calling task's explicit constraint.

`CapabilityError` was added to `src/core/capability/__init__.py`'s
public API (`__all__` and the module docstring's "Public API" list),
since it is now a name every consumer of this package may need to
catch — consistent with `ToolError`'s own export from
`src/core/tool/tool_provider.py`'s `__all__`.

**Verification:**

Five new, behavioral test methods (8 new assertions) were added to
`tests/EP069_4/test_unified_capability_abstraction.py`:

- `_test_validation_error_is_a_capability_error` — raises a
  `CapabilityValidationError`, catches it via `except CapabilityError`.
- `_test_registry_error_is_a_capability_error` — same pattern for
  `CapabilityRegistryError`.
- `_test_not_found_error_is_a_capability_error` — same pattern for
  `CapabilityNotFoundError`.
- `_test_backend_error_is_a_capability_error` — same pattern for
  `CapabilityBackendError`.
- `_test_specific_capability_errors_remain_distinguishable` — asserts
  (via `isinstance`) that none of the four specific exception types is
  also an instance of any of the other three, so the shared root does
  not collapse their distinguishability.

These are behavioral tests (an actual `raise`/`except` round-trip, or
an `isinstance` check against a real instance), not mere
`issubclass()`-on-the-class-object existence checks — matching the
calling task's Section 10 requirement to prefer "specific exception is
also a CapabilityError" behavioral assertions.

All five pre-existing acceptance criteria (`EP069_4_DESIGN.md` Section
19, items 1-3 concerning error behavior) were re-run unchanged and
continue to pass — none was weakened, deleted, or rewritten to
accommodate the fix.

## 5. AUDIT-002 — No Action Required (confirmed)

**Reason:** STEP 3 already confirmed the `src/modules/test_module.py`
one-line addition is required by this repository's own established
test-registration convention (every prior EP, `EP001` through
`EP069.3`, made an identical addition). This STEP 3.1 pass found no
new evidence to revise that conclusion. The registration line was
**not** removed, and no further change was made to that file.

## 6. AUDIT-003 — No Action Required (confirmed)

**Reason:** STEP 3 already confirmed `Capability`'s raw dataclass
constructor bypassing validation matches `EP069_4_DESIGN.md` Section
14.3's own explicit, documented trade-off ("a separate validating
constructor, not a permissive raw one" — implying the raw constructor
remains permissive by design), mirroring `PluginManifest`'s own
`from_dict()`-vs-bare-`__init__` precedent. `Capability`'s validation
design was **not** redesigned or changed in any way by this STEP 3.1
pass.

## 7. AUDIT-004 — No Action Required (confirmed)

**Reason:** STEP 3 already confirmed that
`_test_capability_backend_error_is_catchable` is the strongest test
possible for `CapabilityBackendError` given that Owner Decision D4
(no concrete `CapabilityBackend` implementation in this EP) remains in
force. No concrete backend was implemented merely to make this test
"more functional," per the calling task's explicit prohibition. The
test itself was left unmodified by this STEP 3.1 pass.

## 8. Tests

### EP-069.4 suite (fresh re-run after the fix)

```
TestRunner().run("EP069_4")
```

| | Before STEP 3.1 (STEP 3 baseline) | After STEP 3.1 |
|---|---|---|
| Passed | 33 | **41** |
| Failed | 0 | 0 |
| Skipped | 0 | 0 |

The 8 additional passes correspond exactly to the 8 new assertions
added for the AUDIT-001 fix (`grep -c "self\.assert_"` on the test
file returns 41, matching the reported pass count with no
discrepancy). Every one of the original 33 assertions still exists,
unmodified, and still passes.

### Required minimum regression set (fresh re-run)

| Suite | Passed | Failed | Skipped | STEP 3 baseline | Delta |
|---|---|---|---|---|---|
| EP069 | 68 | 0 | 0 | 68/0/0 | none |
| EP069_2 | 26 | 0 | 0 | 26/0/0 | none |
| EP069_3 | 80 | 0 | 0 | 80/0/0 | none |
| EP069_4 | 41 | 0 | 0 | 33/0/0 | +8 passed (the fix's own new tests) |
| EP056 | 62 | 0 | 0 | 62/0/0 | none |

### Broadest practical regression suite (fresh re-run)

All 60 registered suites were attempted individually (isolated
per-suite execution, so one suite's failure cannot mask another's):

- **58 of 60 ran to completion.** Aggregate: **7,240 passed / 3 failed
  / 1 skipped** (STEP 3 baseline: 7,232 passed / 3 failed / 1 skipped
  — the +8 delta is exactly this EP's own new assertions; every other
  suite's individual count is byte-for-byte identical to the STEP 3
  baseline).
- **2 of 60 suites still cannot run**: `EP046`, `EP048` — identical
  `AudioCaptureError`/`StreamingAudioCaptureError` ("PortAudio library
  not found"), the same pre-existing, system-level environment
  limitation identified in STEP 3. Not affected by this fix (this fix
  touches only `src/core/capability/` and this EP's own test file).
- **3 failures, unchanged, confined to `EP047` (2) and `EP049` (1
  fail, 1 skip)** — identical error messages to the STEP 3 baseline
  (`"Expected True"`, `"STT must remain available even if TTS
  construction fails"`). Already proven pre-existing and unrelated to
  EP-069.4 in STEP 3's own git-stash A/B comparison; re-confirmed here
  by exact count/message match against that baseline, with no need to
  repeat the stash experiment since nothing in this fix touches
  voice/TTS/STT code.

**No new regression introduced by this fix.** Every suite other than
`EP069_4` itself reports counts identical to the STEP 3 baseline.

## 9. Scope Verification

- Only `src/core/capability/capability.py`,
  `src/core/capability/capability_registry.py`,
  `src/core/capability/capability_backend.py`,
  `src/core/capability/__init__.py`, and
  `tests/EP069_4/test_unified_capability_abstraction.py` were modified
  by this STEP 3.1 pass.
- No previous EP (`EP-069`, `EP-069.1`, `EP-069.2`, `EP-069.3`,
  `EP-056`) was modified.
- No renaming, reorganization, reformatting, or "modernization" of any
  unrelated code occurred.
- No new feature, discovery/ranking logic, security enforcement,
  lifecycle behavior, concrete `CapabilityBackend`, bootstrap wiring,
  or CLI change was introduced — the fix is confined exactly to the
  exception hierarchy AUDIT-001 identified.
- `git diff --stat` confirms `src/modules/test_module.py` is unchanged
  since STEP 2 (still exactly `+1` line, from STEP 2, not touched
  again in STEP 3.1) — `src/core/capability/` and `tests/EP069_4/`
  remain untracked new-package additions, now with the AUDIT-001 fix
  included in their content.
- `requirements.txt`, `config/config.yaml`, `src/bootstrap.py`,
  `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md`, `VERSION`,
  `PROJECT_MANIFEST.md` — all untouched, per the calling task's
  explicit STEP 4 prohibition.

## 10. Final Review

- **Architecture**: the fix now matches `EP069_4_DESIGN.md` Section
  12.1's literal text — `CapabilityError` exists as the root of
  `CapabilityRegistryError`, `CapabilityNotFoundError`,
  `CapabilityValidationError` (and, extending the same pattern
  consistently, `CapabilityBackendError`, introduced in Section 13.3).
- **API**: `CapabilityError` is exported from
  `src/core/capability/__init__.py`'s public surface, consistent with
  `ToolError`'s own export precedent; no internal implementation
  detail was exposed.
- **Exceptions**: the hierarchy is now coherent — one root, four
  leaves, no diamond, no unrelated exception folded in.
- **Tests**: the new regression tests directly and behaviorally prove
  the fix (raise-and-catch-as-root for all four types, plus explicit
  cross-type distinguishability) — not merely a class-existence check.
- **Compatibility**: every pre-existing catch site, test, and public
  name continues to behave identically; only additive changes were
  made.
- **Scope**: nothing outside EP-069.4's own package and test file
  changed.
- **Documentation**: this document and the audit addendum (Section 11
  below) explain the change, the verification performed, and the
  reasoning, without erasing the original STEP 3 findings.

## 11. Final STEP 3.1 Verdict

**ALL REQUIRED FINDINGS FIXED**

AUDIT-001 (the only actionable finding) is resolved, verified by fresh
test execution with zero regression. AUDIT-002, AUDIT-003, and
AUDIT-004 required no code change and remain correctly closed as
informational/no-action, per STEP 3's own classification, re-confirmed
here.

---

## EP-069.4 STEP 3.1 — FINDINGS RESOLUTION COMPLETE
