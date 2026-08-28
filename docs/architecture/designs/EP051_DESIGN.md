# EP-051 — Browser Automation — Design Specification (STEP 1)

Status: STEP 1 (Architecture Discovery, Technology Evaluation & Design) — DESIGN ONLY. No implementation performed. Owner Decisions D1–D12 (Section 21) are **APPROVED** (see each decision's sign-off line). STEP 2 (Implementation) has NOT begun.

---

## 1. Executive Summary

EP-051 gives Jarvis controlled, deterministic browser interaction —
launch a browser, navigate it, read its state, and drive simple DOM
interactions (click/type/select an element) — through the same
`CommandRouter` namespace-module pattern EP-050 (Computer Use) just
established for OS-level input.

The repository already reserves this territory: `src/skills/browser/`
exists but contains two empty files (`selenium_driver.py`,
`skill.py`), and `requirements.txt` pre-declares an unpinned,
unused `selenium` dependency. Both are placeholders only — nothing is
implemented, nothing imports Selenium anywhere in the project, and no
`tests/EP051/` directory exists yet (Section 2/6).

**Recommendation, in one sentence:** build a new `BrowserModule`
(`"browser"` `CommandRouter` namespace) behind a `BrowserBackend`
Protocol, implemented with **Playwright's synchronous API** (not the
pre-provisioned Selenium), gated by a single `browser.enabled` config
flag (default `false`), covering a deliberately small v1 action set
(lifecycle, navigation, one-element observation/interaction, single
key press, screenshot), reusing EP-050's `CommandModule` /
Protocol-backend / fake-backend-testing / config-gate / opaque-
screenshot patterns exactly, and explicitly deferring tabs, dropdown
`select`, general keyboard/hotkey interaction, an explicit `wait`
action, JavaScript execution, downloads, and uploads.

This document performs Architecture Discovery, Technology Evaluation,
and Design only. No source file, test file, configuration file, or
dependency file has been created or modified. The only artifact
produced by STEP 1 is this document.

---

## 2. Current Repository State

Confirmed by direct inspection (not assumed from documentation alone):

- `src/skills/browser/selenium_driver.py` — **0 bytes**.
- `src/skills/browser/skill.py` — **0 bytes**.
- No `BrowserModule`, `BrowserBackend`, or any browser abstraction
  exists anywhere in `src/`.
- `grep -rn "selenium" --include="*.py" .` across the entire
  repository returns **zero matches** — Selenium is not imported,
  referenced, or used by any Python file in the project.
- `requirements.txt` line 40 declares a bare `selenium` (no version
  pin) with no accompanying comment/justification — unlike every
  other recently-added dependency in the same file (e.g.
  `openwakeword==0.6.0`, pinned and commented per EP-048's Owner
  Decision D1 precedent, Section 6.4/24 below).
- No `tests/EP051/` directory exists.
- `docs/architecture/JARVIS_ROADMAP.md` and `docs/BACKLOG.md` both
  independently confirm: *"EP-051 Browser Automation — NOT STARTED.
  No design, research, or implementation work has begun,"* and both
  explicitly record `src/skills/browser/` as *"still empty, confirmed
  reserved for EP-051"* — stated at EP-050 completion time, i.e. this
  is not new information EP-051 STEP 1 is discovering for the first
  time, but a pre-existing, already-disclosed reservation.
- `src/bootstrap.py` contains no import of, or reference to,
  anything under `src/skills/browser/`.

**Conclusion:** `src/skills/browser/` is a pure placeholder directory
and `selenium` is a pure placeholder dependency. EP-051 STEP 1 starts
from a clean, empty slate with no existing abstraction, test, or
convention to preserve inside `src/skills/browser/` itself — only the
*surrounding* architecture (`CommandRouter`, `Config`, `Bootstrap`,
the `ComputerUseBackend`/`DesktopModule` precedent) is fixed and must
be reused, per Section 13 below.

---

## 3. Existing Browser Capability

There is none. Both files under `src/skills/browser/` are empty; no
Selenium abstraction, no test, no configuration key, and no
`CommandRouter` registration exists. `EP050_DESIGN.md` Section 24
already reached the same conclusion when it briefly evaluated
Selenium's relevance to EP-050 and confirmed it "irrelevant... a
browser-automation library, squarely EP-051's territory... EP-050
does not import it." EP-051 STEP 1 confirms this remains true and
that nothing has changed since.

### Selenium Requirement Analysis (explicit answers)

1. **Is Selenium actually used anywhere?** No — zero imports anywhere
   in the repository.
2. **Is `src/skills/browser/` implemented or only a placeholder?**
   Only a placeholder — both files are 0 bytes.
3. **Are there existing Selenium abstractions?** None.
4. **Are there existing Selenium tests?** None — `tests/EP051/` does
   not exist.
5. **Is the current dependency version appropriate?** No — it is
   entirely unpinned, inconsistent with every other recently-declared
   dependency's pinning convention (Section 2), and therefore not
   "appropriate" regardless of which library STEP 2 ultimately uses.
6. **Would continuing with Selenium minimize architectural churn?**
   No. "Minimizing churn" only has force when something is already
   built on top of the incumbent choice. Nothing is — no code, no
   test, no abstraction depends on Selenium today, so keeping it
   avoids zero real migration cost. The usual argument for staying
   with an already-integrated dependency does not apply here.
7. **Is there a compelling reason to replace it with Playwright?**
   Yes — see Section 7/8's full technology evaluation. Given (6),
   this is a from-scratch technology choice, not a migration.

---

## 4. EP-050 Relationship

EP-050 (Computer Use) introduced OS-level input — mouse, keyboard,
clipboard, screenshots, active-window focus — entirely outside any
browser's DOM. `EP050_DESIGN.md` Section 26 already drew the
authoritative EP-050/EP-051 boundary line at design time:

| Capability | EP-050 | EP-051 |
|---|---:|---:|
| Mouse control | **Yes** | — |
| Keyboard control | **Yes** | — |
| Clipboard (text) | **Yes** | — |
| Screenshot capture (raw) | **Yes** | — |
| Window focus/activation (by title) | **Yes**, minimal | — |
| Browser navigation | — | **Yes** |
| Browser DOM interaction | — | **Yes** |

EP-051 does not reopen this boundary; it fills the "EP-051" column.

**Concretely:**

- EP-050's `desktop type`/`desktop click` operate on raw screen
  coordinates and OS-level keyboard focus, with zero knowledge of
  what application (if any) is focused, let alone DOM structure.
- EP-051's `browser click`/`browser type` operate on **DOM elements
  resolved by selector**, inside a browser process EP-051 itself
  launches and owns — a fundamentally different addressing model
  (selector-based, not coordinate-based) that Playwright/Selenium
  both provide natively and PyAutoGUI does not (Section 7).
- EP-051 **does not** reuse `ComputerUseBackend`'s mouse/keyboard
  primitives to drive the browser (e.g. moving the OS cursor to a
  computed pixel position and sending a raw click). Per Section 13
  below, EP-050's raw-input infrastructure is explicitly not
  duplicated or borrowed for DOM interaction — the browser automation
  library's own selector-based interaction API is used instead, kept
  entirely inside `src/skills/browser/`, at the browser abstraction
  layer, never touching `src/skills/desktop/`.
- EP-051's `browser screenshot` action exists independently of
  EP-050's `desktop screenshot` — they capture different things
  (one page's rendered content vs. the whole physical screen) via
  different libraries, with no shared code path. Both follow the same
  *design pattern* (raw, uninterpreted bytes only, Section 12/17
  below), by convention, not by code reuse.

**What EP-051 reuses from EP-050 (design pattern, not code):**
`CommandModule` implementation shape, Protocol-based
backend/`*BackendError` pairing, constructor-injected backend
(`Bootstrap` builds it, the module never imports the concrete
implementation), config-gate-rechecked-per-dispatch safety model,
fake-backend deterministic testing convention, and the "screenshot
bytes are opaque, never logged, never interpreted" privacy rule.
These are architectural precedents worth repeating exactly, not
literal imports from `src/skills/desktop/`.

---

## 5. Goals

- Provide Jarvis a `"browser"` `CommandRouter` namespace capable of:
  launching and closing a real, controllable browser; navigating to a
  URL and through history (back/forward/reload); observing basic page
  state (title, URL, page text); locating a single DOM element by
  selector; clicking, typing into, and clearing that element; sending
  one keypress to it (e.g. `Enter` to submit a search box); and
  capturing a raw, uninterpreted screenshot of the current page.
- Fit the existing architecture with zero new architectural layers:
  reuse `CommandRouter`, `Config`, and `Bootstrap`'s existing
  extension points exactly as `DesktopModule` does.
- Keep the v1 surface small, reliable, and conservative rather than a
  complete browser agent (Section 19).
- Establish (not necessarily fully build) the security/trust
  boundary between Jarvis's own instructions and untrusted webpage
  content extracted via `browser page-text` (Section 13).
- Leave the module safely off by default (`browser.enabled: false`),
  matching every prior risky-capability EP's precedent
  (`voice.wake.enabled`, `voice.wake.assist.enabled`,
  `desktop.enabled`).

---

## 6. Non-Goals

Explicitly out of scope for EP-051 v1, regardless of what the chosen
browser library technically supports:

- **Visual reasoning / OCR** on page screenshots — screenshots remain
  raw, uninterpreted bytes (Section 17), exactly mirroring
  `EP050_DESIGN.md` Section 18's rule for `desktop screenshot`. This
  capability belongs to EP-053 Vision Integration (Section 20).
- **Autonomous browsing loops** — EP-051 exposes single, explicit,
  synchronous actions dispatched one at a time through
  `CommandRouter.dispatch()`, identical to EP-050's model (Section
  10/22's State Machine). There is no "browse until X is found" loop,
  no multi-step planning, and no self-directed re-dispatch.
- **Arbitrary JavaScript execution** — no `browser eval`/`execute-
  script` action exists in v1 (Section 6/D8). This is the browser
  analogue of EP-050's "no shell/code execution of any kind" rule
  (`EP050_DESIGN.md` Section 15) and closes off the single largest
  realistic remote-code-style risk a browser automation library could
  otherwise introduce.
- **Browser-based shell execution** — not applicable to a browser
  library at all; stated for completeness per the task's checklist.
- **Credential harvesting** — EP-051 does not read, store, export, or
  transmit saved passwords, autofill data, or session tokens beyond
  what a normal, single interactive browser session naturally holds
  in memory during its own lifetime; there is no dedicated
  credential-access action.
- **CAPTCHA bypass / anti-bot bypass** — not implemented, not a goal;
  if a target site presents a CAPTCHA or blocks automation, EP-051
  surfaces this as an ordinary navigation/interaction failure
  (Section 16), never attempts to defeat it.
- **Unrestricted downloads / unrestricted uploads** — v1 implements
  neither a download action nor a file-upload action at all (Section
  6/D7); this is a hard exclusion, not merely "unrestricted vs.
  restricted."
- **Autonomous purchases / autonomous account changes** — EP-051 v1
  provides only the generic primitives (`click`, `type`); it contains
  no purchase-specific, checkout-specific, or account-management-
  specific logic, and (per Section 14) ships with no human-approval
  mechanism finer than the single category gate — any consumer that
  chains `browser` actions into a purchase flow does so entirely
  outside EP-051's own knowledge or control, and the Human Approval
  gap (Section 14) applies with full force to that use case.
- **Tab/window management, dropdown `select`, general keyboard/hotkey
  interaction, and an explicit `wait` action** are deferred from v1
  for conservatism (Section 19), not because the underlying library
  lacks them.

---

## 7. Technology Evaluation

Three candidate approaches were evaluated, per the task's explicit
list, against the actual repository (a single narrow backend behind
a Protocol, Section 9 below) and the realistic target (a Windows
workstation, matching EP-050's own target, though — unlike EP-050 —
nothing about this evaluation depends on staying Windows-only;
Section 8/D11):

| Criterion | Selenium | Playwright | pyautogui-based browser interaction |
|---|---|---|---|
| Already in `requirements.txt` | **Yes** (unpinned, unused, Section 2) | No | Yes (`pyautogui`, already used by EP-050 for OS input) |
| Actually used anywhere today | No | No | No (as browser automation; EP-050 uses it for OS input only) |
| Browser lifecycle management | Yes (`webdriver.Chrome()` etc., requires a separately-managed driver binary unless using Selenium Manager) | Yes (bundles/manages browser binaries via `playwright install`, no separate driver-binary management) | None natively — would require manually launching the browser as an OS process and driving it via raw screen coordinates |
| DOM interaction / selectors | Yes (CSS/XPath, explicit waits required) | Yes (CSS/XPath/text/role selectors, **auto-waiting built in** — actions wait for the element to be actionable before proceeding) | None — no DOM/selector concept at all; would require pixel-coordinate guessing, entirely defeating the purpose of "browser automation" as opposed to "OS input aimed at a browser window" |
| Reliability / flakiness | Moderate — explicit `WebDriverWait`/`expected_conditions` boilerplate needed to avoid race conditions | High — auto-waiting is a first-class design feature, substantially reducing flaky-test/flaky-action patterns compared to Selenium | Very low — brittle against window position, screen resolution, DPI scaling, and any UI change |
| Waits | Manual (`WebDriverWait`) | Automatic (actionability checks before every interaction) plus explicit wait APIs available | Manual, coordinate/time-based only |
| Error handling | Exception hierarchy is broad and driver-specific (`NoSuchElementException`, `TimeoutException`, `WebDriverException`, ...) | Narrower, more consistent exception surface (`TimeoutError`, `Error`) | No structured errors — failures are silent (wrong pixel clicked) rather than raised |
| Screenshots | Yes (page or element) | Yes (page or element), including full-page capture | Yes, but of the whole OS screen, not the page/DOM (duplicates EP-050's `desktop screenshot`, not a fit) |
| Multiple tabs/windows | Yes | Yes (`BrowserContext`/`Page` model maps cleanly to tabs) | No concept of tabs at all |
| Authentication/session handling | Yes (cookies, storage state) | Yes (cookies, `storage_state` import/export) | No — sessions live only in whatever the human visually sees |
| Headless support | Yes | Yes, mature and fast | N/A (interacts with a real, visible window only) |
| Testability (fake-backend-friendly) | Yes — can be hidden behind a Protocol like any other library | Yes — same | Poor — no natural seam to fake; testing would require a real display |
| Installation complexity | Requires a matching driver binary per browser/version (mitigated somewhat by Selenium Manager in recent versions) or an already-provisioned one | One extra step: `playwright install` downloads managed browser binaries after `pip install playwright` — a known, documented, one-time setup cost | Nothing extra beyond `pyautogui` (already present), but see reliability row |
| Dependency footprint | Moderate (`selenium` package plus a driver binary) | Moderate (`playwright` package plus its own bundled browser binaries) | None (reuses EP-050's existing dependency) |
| Sync API available (fits `CommandRouter.dispatch()`'s synchronous, single-threaded model) | Yes (Selenium is sync-only) | Yes (`playwright.sync_api`, used identically to the async API but without `asyncio`) | Yes (trivially, since it's just `pyautogui` calls) |
| Future extensibility | Good | Good — actively developed, modern web platform feature coverage (Chromium/Firefox/WebKit engines) kept current by the maintainer | Poor — fundamentally the wrong abstraction level for DOM automation |
| Maintenance activity | Mature, long-established, large community, slower release cadence | Actively maintained by Microsoft, frequent releases, strong current adoption for new automation projects | N/A |
| Compatibility with EP-050 | No overlap either way | No overlap either way | Would create direct, undesirable overlap with `ComputerUseBackend` (Section 4) |

**Conclusion:** `pyautogui`-based browser interaction is rejected
outright — it has no selector/DOM concept, would duplicate EP-050's
screenshot capability incorrectly (screen, not page), and is the
"raw coordinate targeting when a DOM selector is available" case the
task's own EP-050 boundary section explicitly names as *not*
reusable (`EP050_DESIGN.md`-style Section 13 reasoning, mirrored
above in Section 4). The real choice is between Selenium and
Playwright — see Section 8.

---

## 8. Recommended Technology

**Recommendation: Playwright, using its synchronous API
(`playwright.sync_api`).**

Reasons:

1. **Auto-waiting materially reduces flakiness.** Playwright's click/
   type/fill actions wait for an element to be visible, stable, and
   receiving-events before acting, without hand-written
   `WebDriverWait` boilerplate. This directly serves EP-051's own
   Goals (Section 5: "reliable... foundation") more than Selenium
   does out of the box.
2. **Cleaner lifecycle and installation model.** `playwright install`
   downloads and manages its own browser binaries; there is no
   separate driver-binary version-matching problem (a common source
   of Selenium setup friction, especially across browser upgrades).
3. **A narrower, more consistent error surface** (Section 16) — fewer
   distinct exception types to normalize behind `BrowserBackendError`
   than Selenium's broader, driver-specific hierarchy.
4. **Zero migration cost (Section 2/6).** Because nothing in the
   repository is built on Selenium today, "Selenium is already in
   `requirements.txt`" carries no real weight — the Existing
   Dependencies Policy's concern ("never introduce a new third-party
   dependency unless explicitly requested... always reuse existing
   libraries already used by the project") is about avoiding
   *redundant* dependencies for a problem an existing, working
   dependency already solves. Selenium does not currently solve
   anything in this project; it is an unused placeholder. Choosing
   Playwright is a from-scratch technology decision, not a
   replacement of working infrastructure — but it is still a genuine
   new dependency addition requiring justification (this section) and
   an explicit Owner Decision (D1), which this document provides
   rather than silently assuming.
5. **A single sync API fits `CommandRouter.dispatch()`'s synchronous,
   single-threaded dispatch model exactly** (Section 10/22), with no
   `asyncio` event-loop integration required anywhere in
   `BrowserModule` or `Bootstrap`.

**Trade-off accepted:** Playwright adds a genuinely new third-party
dependency (and a one-time `playwright install` post-install step)
rather than reusing an already-declared one — a real cost, honestly
stated per the Existing Dependencies Policy, and one that requires
Owner Decision D1's explicit sign-off rather than being assumed.
Unlike EP-050's PyAutoGUI choice (which needed no new dependency at
all), EP-051 cannot avoid this cost under any of the three evaluated
options that actually provide DOM automation, since Selenium is
"already present" in name only.

**Version pinning (STEP 2 requirement, not performed now):** the
exact `playwright==` version to pin should be determined at STEP 2
implementation time by checking the latest stable PyPI release,
mirroring `EP048_DESIGN.md` Owner Decision D1's precedent for
`openwakeword==0.6.0` ("pin the current latest release... a model-
format-sensitive dependency") — `requirements.txt`'s existing bare,
unpinned `selenium` line is itself the anti-pattern (Section 2) this
project's own dependency convention argues against repeating.

---

## 9. Architecture

Mirrors `EP050_DESIGN.md` Section 9's shape exactly, substituting the
browser domain for the OS-input domain:

```
CommandRouter.dispatch("browser <action> [args...]")
    -> BrowserModule                      (src/skills/browser/skill.py)
        -> BrowserBackend                 (src/skills/browser/backend.py, Protocol)
            -> PlaywrightBrowserBackend    (real, STEP 2)
               _FakeBrowserBackend         (test-only, tests/EP051/test_browser.py)
                -> real browser process (Chromium, via Playwright)
```

- **`BrowserBackend`** (`src/skills/browser/backend.py`): a
  `runtime_checkable` `Protocol`, exactly mirroring
  `ComputerUseBackend`'s role — the *only* interface `BrowserModule`
  depends on. `BrowserModule` never imports Playwright itself,
  keeping the module fully decoupled from Playwright's own import-
  time/browser-binary requirements, matching `DesktopModule`'s
  identical decoupling from `pyautogui`.
- **`PlaywrightBrowserBackend`** (`src/skills/browser/
  playwright_backend.py`, STEP 2): the real implementation,
  constructed by `Bootstrap` and injected into `BrowserModule`,
  mirroring `WindowsComputerUseBackend`'s construction/injection
  pattern in `Bootstrap` exactly.
- **`BrowserModule`** (`src/skills/browser/skill.py`): implements
  `CommandModule` (`name == "browser"`), following
  `DesktopModule`/`SystemModule`'s reference shape — parses/validates
  `CommandRouter` arguments, enforces the `browser.enabled` safety
  gate (re-checked per dispatch, not only at registration, Section
  14), and translates a `BrowserBackend` call/exception into a
  `CommandResult`. Contains no browser-driving logic itself.
- **No `BrowserProvider`, `BrowserManager`, or `BrowserEngine` layer**
  is introduced. Per the task's own instruction ("do not create
  unnecessary Manager/Provider/Engine layers") and matching
  `DesktopModule`'s own precedent of a two-layer design (`Module` +
  `Backend` Protocol, nothing between them), a third layer would add
  indirection with no current consumer needing it. `Bootstrap` plays
  the same "composition root" role it already plays for every other
  module.
- **Session/page abstraction lives inside `PlaywrightBrowserBackend`
  itself, not as a separate public type.** `BrowserModule` never
  handles a raw Playwright `Page`/`BrowserContext` object directly;
  it only ever calls named `BrowserBackend` methods (`launch()`,
  `goto(url)`, `click(selector)`, ...) and receives plain, backend-
  agnostic return values (`str`, `bool`, a small `PageState`/
  `Screenshot`-style dataclass), exactly matching `ComputerUseBackend`
  method shapes (`Screenshot`, `CursorPosition`, `ScreenSize`
  dataclasses in `backend.py`).

---

## 10. Browser State Model

Browser automation is inherently stateful in a way EP-050's raw input
primitives are not (EP-050's actions are each a single, self-
contained, synchronous OS call with no session concept at all,
`EP050_DESIGN.md` Section 20). EP-051 must own a genuine session
lifecycle across separate `CommandRouter` dispatches.

**Minimum v1 state model:**

- **One browser session per running Jarvis process, lazily created.**
  `browser launch` starts a real browser instance and one page/tab;
  `PlaywrightBrowserBackend` holds the live `Browser`/`Page` objects
  as its own private instance state between dispatches (this is safe
  and consistent with the existing architecture: `Bootstrap`
  constructs `BrowserModule`/`PlaywrightBrowserBackend` once, at
  startup, as a long-lived singleton registered into `CommandRouter`
  — the same lifetime every other module, including `DesktopModule`,
  already has; EP-051 is simply the first module whose backend
  *meaningfully uses* that lifetime to hold open, cross-dispatch
  state, rather than being stateless between calls).
- **No concurrent/multiple named sessions in v1** (Owner Decision
  D5) — a second `browser launch` while a session is already open
  either fails cleanly (*"a browser session is already open; run
  'browser close' first"*) or is a no-op returning the existing
  session's state; the exact choice is a STEP 2 implementation detail
  that does not affect this architecture.
- **Single active tab/page only in v1** (Section 19) — no tab index,
  no "switch to tab N." Deferred, not built.
- **Cookies / authentication state** live inside the browser process
  itself for the session's lifetime, exactly as they would in a
  normal, manually-driven browser. EP-051 v1 introduces no explicit
  cookie-export, cookie-import, or persisted-session-across-restarts
  capability (`storage_state` load/save) — every session starts
  clean on `browser launch` and every credential/cookie is discarded
  on `browser close` or process exit. This is a deliberate v1
  simplification, not a Playwright limitation.
- **Navigation history** is whatever the underlying browser process
  itself tracks; `browser back`/`browser forward` simply delegate to
  it. EP-051 does not maintain its own parallel history list.
- **Session lifetime:** created by `browser launch`, destroyed by
  `browser close` (releases the browser process) or implicitly by
  Jarvis process shutdown (mirroring how `desktop`'s backend has no
  explicit "shutdown" call either — process exit is sufficient
  cleanup for both).
- **Accessing state without an open session:** any action other than
  `launch` dispatched while no session exists fails cleanly with a
  `CommandResult(success=False, message="no active browser session;
  run 'browser launch' first")`, performing no backend call — the
  browser-automation analogue of EP-050's `GATE_CHECK` state (Section
  15).

---

## 11. CommandRouter / Tool Engine Decision

Evaluated the same four options `EP050_DESIGN.md` Section 11/32
already evaluated for Computer Use, reapplied to Browser Automation:

**A. Direct CommandRouter integration** (as designed above).
**B. Extending Tool Engine for parameterized tools.**
**C. A browser-specific execution abstraction.**
**D. Another architecture.**

| Criterion | A: CommandRouter | B: Extend Tool Engine | C: Browser-specific abstraction |
|---|---|---|---|
| Consistency with EP-050 | **Identical pattern**, zero new precedent needed | Would require Tool Engine's parameter-handling gap (Section 6.3/28 of `EP050_DESIGN.md`) to be closed *first*, for both EPs' sake — not something EP-051 can do unilaterally, same conclusion EP-050 already reached | Introduces a second dispatch mechanism alongside `CommandRouter`, contradicting `AI_DEVELOPMENT_PLAYBOOK.md`'s "no new architectural layers without necessity" rule |
| Parameter handling | `CommandRouter.dispatch()` already passes a full `list[str]` of arguments to every `CommandModule.execute()` call — sufficient for every v1 `browser` action (a URL, a selector, text, a key name) | `Tool.handler` is zero-argument-only for **every** action currently registered project-wide (confirmed unchanged since EP-050, Section 2) — `browser goto <url>`/`browser click <selector>` cannot be expressed at all without first widening this signature | Would need to invent its own parameter-passing convention from scratch |
| Stateful browser sessions | `BrowserModule`/`PlaywrightBrowserBackend` hold session state as ordinary instance attributes across dispatches (Section 10) — no special support needed from `CommandRouter` itself, which is already stateless/pass-through | Tool Engine's existing built-in tools are bound, one-shot closures over a `Service` method (`src/core/tool/__init__.py`'s own docstring) — no existing precedent for a Tool that holds open, cross-invocation session state | Would need bespoke session-lifetime management the abstraction doesn't yet define |
| Security | Same posture as EP-050: whichever surface can already reach `CommandRouter.dispatch()` can reach `browser` actions (Section 14) | Same, if it were viable | Same, if it were viable |
| Testability | Identical to `DesktopModule`'s already-proven fake-backend pattern (Section 18) | N/A — not viable without the parameter-handling change | Would need its own, new testing convention |
| Future EP compatibility | Matches the shape any future stateful, parameterized skill (e.g. EP-052 File Automation) will likely also need | Blocked on the same pre-existing, cross-cutting limitation | Sets a second precedent future EPs would have to choose between |
| Architectural debt | None introduced — reuses an already-proven pattern | Would either introduce the Tool Engine widening as *this* EP's unilateral scope (forbidden — "never redesign architecture" applies to EP-051 exactly as it did to EP-050) or remain blocked | Introduces a new, EP-051-only abstraction with no other consumer, i.e. exactly the kind of "unnecessary... layer" the task instructs against |
| Implementation complexity | Lowest — an established, once-repeated pattern | Highest — requires cross-cutting Tool Engine work outside EP-051's own scope, as a prerequisite | Moderate, but for a self-inflicted problem A already avoids |

**Recommendation: A — direct `CommandRouter` integration**, for
reasons identical to `EP050_DESIGN.md` Section 32's own conclusion,
now reinforced by a second, independent EP reaching the same result:
Tool Engine's zero-argument limitation is not an EP-050-specific
accident — it blocks *any* project skill needing parameters, and
EP-051 is a second, independent confirmation of exactly the same
pre-existing architectural gap. Per Section 21/D4 below, this is
recorded as a second data point for the still-unscheduled "future,
dedicated parameterized Tool support" item `EP050_DESIGN.md` Section
28 already flagged — EP-051 does not re-propose fixing it itself, and
does not modify `src/core/tool/` in any way.

---

## 12. Security Model

The realistic threat model mirrors `EP050_DESIGN.md` Section 15's own
framing, extended to browser-specific risks: *any dispatch surface
that can reach `CommandRouter.dispatch()` (interactive shell,
Telegram, the REST API, voice) can trigger a browser action* —
including navigating to an arbitrary URL, reading whatever a loaded
page's DOM/session contains, and driving simple form interactions on
it.

**What EP-051 v1 implements itself (no Owner Decision needed):**

- **No JavaScript execution capability of any kind** (Section 6/D8)
  — the browser-automation analogue of EP-050's "no shell/code
  execution" rule, closing off the single largest realistic risk
  (arbitrary script execution against whatever page/session is
  loaded, including any authenticated session cookies present).
- **No download or upload actions at all** (Section 6/D7) — not
  merely restricted, entirely absent from the v1 action set, closing
  off both "silently exfiltrate a file via download" and "silently
  read/attach a local file via upload" as concerns EP-051 v1 need not
  reason about further.
- **Structured, auditable logging of every action** (Section 17),
  following EP-050's identical never-log-sensitive-content rule.
- **No hidden/background/daemon invocation path** — every action is
  a single, explicit, synchronous dispatch through the same
  `CommandRouter.dispatch()` every other module already uses; there
  is no autonomous loop (Section 6) that could chain actions without
  an explicit caller.
- **Selector-based interaction only** — `browser click <selector>`
  acts only on the single element a selector resolves to; there is no
  raw-coordinate click fallback that could hit unintended page
  content.

**Browser-specific risks considered and their v1 disposition:**

| Risk | v1 disposition |
|---|---|
| Arbitrary URL navigation | Allowed once `browser.enabled` is true; no allow-list in v1 (Owner Decision D6) |
| External websites | Same as above — no distinction from "trusted" sites in v1 |
| Login sessions / cookies | Live only inside the browser process for the session's lifetime (Section 10); no export/import capability |
| Credentials | Never read, stored, or logged by EP-051 itself; whatever a human or a filled form types is only ever passed through as ordinary `type` text |
| Clipboard | Out of scope for EP-051 entirely — clipboard remains EP-050's territory (Section 4); `browser type` sends literal text supplied as a `CommandRouter` argument, never reads the OS clipboard |
| Downloads | Not implemented at all in v1 (Section 6/D7) |
| File uploads | Not implemented at all in v1 (Section 6/D7) |
| JavaScript execution | Not implemented at all in v1 (Section 6/D8) |
| Browser extensions | Not installed, configured, or supported by v1's launch action — a plain, extension-free browser context only |
| Popups | Playwright's default popup handling applies (new popups become ordinary new pages); v1 exposes no explicit popup-management action — an opened popup is simply not automatically switched to, since v1 has no multi-tab concept (Section 10/19) |
| Redirects | Followed transparently by the underlying browser, exactly as a human's browser would; `browser current-url` always reports the post-redirect URL |
| Malicious pages | No sandboxing beyond what the browser engine itself provides; EP-051 adds no additional isolation layer in v1 |
| Prompt injection from web content | See Section 13 — a dedicated trust-boundary analysis |
| Sensitive page content | `browser page-text` may return arbitrarily sensitive text (e.g. a logged-in banking page); it is returned to the caller like any other command output, never persisted or logged by EP-051 itself beyond its length (Section 17, mirroring EP-050's clipboard/typed-text logging rule) |
| Screenshots | Raw, uninterpreted bytes only, same privacy model as `EP050_DESIGN.md` Section 19 (Section 17 below) |
| Logging | Section 17 |
| Browser history | Not read or exported by EP-051 beyond `back`/`forward` delegating to the live session (Section 10) |

**Owner Decision required:** Section 21, Decision D2, resolves the
overall confirmation/gating model, mirroring `EP050_DESIGN.md`'s D2
exactly (Section 14 below).

---

## 13. Prompt Injection / Trust Boundary

This is new territory relative to EP-050 — EP-050 never reads
content whose *origin* is an untrusted third party (a screenshot's
pixels are not "read" as text at all, Section 4). `browser page-text`
is the first EP-051 v1 capability whose return value is
**textual content authored by an arbitrary, untrusted website**, not
by Jarvis, the user, or any of Jarvis's own configuration/prompts.

**The trust boundary, stated explicitly:**

- **Jarvis instructions** — text originating from the user, from
  Jarvis's own configuration, or from Jarvis's own prompt
  construction — are the only content that may ever be treated as
  something to *act on* (dispatch a command, change behavior, alter a
  plan).
- **Untrusted webpage content** — anything returned by `browser page-
  text`, `browser title`, or any future text-observation action — is
  **data**, in exactly the same category as a file's contents or an
  email body a future EP might read. It must never be treated as an
  instruction, regardless of what it contains, including if the page
  text itself contains phrases like "ignore previous instructions" or
  attempts to imitate a system/user message.

**What this means concretely for EP-051 v1's own design:**

- `BrowserModule`/`BrowserBackend` never feed a `page-text` (or any
  other observation) result back into `CommandRouter.dispatch()`,
  into any AI provider prompt, or into any Agent/Planning decision
  point, themselves. EP-051 v1 has no such feedback loop at all — it
  is a pure request/response primitive: a caller asks for the page
  text, EP-051 returns it as an inert string, and EP-051's own
  responsibility ends there.
- The trust boundary therefore has **no live enforcement code to
  write in EP-051 v1** — there is no consumer inside this
  Engineering Package's own scope that could conflate the two
  categories, because EP-051 introduces no autonomous consumer of its
  own observation output. Confirmed by inspection: `src/core/agent/`,
  `src/core/planning/`, and `src/core/plan_execution/` do not call
  `CommandRouter.dispatch()` with content derived from a prior
  dispatch's own result anywhere in the current codebase.
- **This boundary becomes load-bearing, not merely documented, the
  moment any future EP** (a hypothetical browsing-aware Agent/
  Planning extension, or a future workflow step) **consumes
  `browser page-text`'s output and feeds it toward another dispatch
  or another AI call.** This document records that requirement now,
  for that future consumer, rather than waiting until it exists: any
  such future design must treat `page-text` output as untrusted data
  requiring the same handling discipline applied to any other
  external, unauthenticated input source (Section 5 lists this as an
  explicit Goal — "establish... the security/trust boundary," not
  "build a runtime filter for it").
- **No implementation is required or proposed in EP-051 v1** beyond
  this documented rule — per the task's own instruction ("Do not
  implement a security framework during STEP 1... Document the
  required safety boundary"), and because, as shown above, there is
  currently no code path in the repository where the violation could
  actually occur yet.

---

## 14. Human Approval Model

`JARVIS_ARCHITECTURE_VISION.md`'s Human Approval principle ("Jarvis
never performs irreversible actions automatically... require user
confirmation unless explicitly configured otherwise") applies here
exactly as `EP050_DESIGN.md` Section 16 already analyzed for Computer
Use, and reaches the same structural conclusion:

**Are browser actions "irreversible"?** Mixed, and content-dependent
in a way EP-051 cannot judge without the DOM/vision interpretation
this document explicitly keeps out of scope:

- `browser title`, `browser current-url`, `browser page-text`,
  `browser exists`, `browser screenshot` — fully reversible,
  read-only, no side effect.
- `browser launch`, `browser close`, `browser goto`, `browser back`/
  `forward`/`reload`, `browser click`, `browser type`, `browser
  clear`, `browser press` — side-effecting, but EP-051 has no way to
  know in general whether a given `click` merely expands a menu or
  submits an irreversible purchase, since it does not interpret page
  content (Section 6) any more than EP-050 interprets screen content.

**Design decision for v1 (recommended, Owner Decision D2):**
treat the entire `browser` namespace as one safety category, gated by
a single config flag (`browser.enabled`, default `false`), exactly
mirroring EP-050's own D2 "Option C" resolution: a category-level
gate today, with a genuine per-call confirmation prompt explicitly
named as a future, cross-cutting `CommandRouter`/dispatch-surface
extension — not something EP-051 can build unilaterally (identical
reasoning to `EP050_DESIGN.md` Section 15's own conclusion: no
synchronous request/response channel back to the calling surface
exists in `CommandRouter.dispatch()` today, for any module). Building
one exclusively for `browser` would repeat EP-050's own rejected
Option B and create a second, inconsistent precedent.

**Higher-risk actions named by the task** (navigation to arbitrary
URLs, login, form submission, downloads, uploads, external side
effects, purchases, account changes): v1's resolution is **not** to
build per-action tiering inside `browser.enabled` (which would
require the same content-interpretation this document keeps out of
scope to classify correctly), but to structurally remove two of the
listed categories from v1 entirely — downloads and uploads (Section
6/D7) — and to explicitly flag that "login," "form submission,"
"purchases," and "account changes" are not distinct EP-051 actions at
all; they are simply *what a target website does* in response to
ordinary `browser click`/`browser type` sequences EP-051 cannot
distinguish from any other click/type sequence. This gap is
documented here, per Owner Decision D2, not silently accepted.

---

## 15. Observation vs Action

| Category | v1 actions |
|---|---|
| **Observation** (read-only, no side effect) | `browser title`, `browser current-url`, `browser page-text`, `browser exists <selector>`, `browser screenshot <path>` |
| **Action** (side-effecting) | `browser launch`, `browser close`, `browser goto <url>`, `browser back`, `browser forward`, `browser reload`, `browser click <selector>`, `browser type <selector> <text>`, `browser clear <selector>`, `browser press <selector> <key>` |

**Do these categories need different safety treatment?**
Recommendation: **no, not in v1** — mirroring `EP050_DESIGN.md`
Section 16's identical conclusion for Computer Use. A finer-grained
model (e.g. "observation always allowed, even while `browser.enabled`
is otherwise false, since it's read-only") is possible in principle,
but even `browser title`/`browser page-text` require an already-open
browser session (Section 10), which itself can only exist if
`browser launch` — an action — already succeeded under the gate.
Splitting the gate would therefore only matter for a hypothetical
future capability that observes an *externally* (non-Jarvis-launched)
running browser, which is explicitly not part of this design. Kept as
one uniform gate for the same reasons EP-050 gave: no new
architecture required, consistent with the "one flag" precedent, and
a single, obvious switch for the owner.

---

## 16. Configuration

Following `config.yaml`'s existing per-subsystem block convention
(same as `desktop:`, Section 22 of `EP050_DESIGN.md`) exactly:

| Key | Type | Default | Purpose | Security implication |
|---|---|---|---|---|
| `browser.enabled` | bool | `false` | Master gate for the entire `browser` namespace (Section 14) | The single safety switch; off by default, matching `desktop.enabled`/`voice.wake.enabled` precedent |
| `browser.headless` | bool | `false` (Owner Decision D10) | Whether the launched browser window is visible or headless | A visible browser is a lightweight, incidental observability aid for a new, ungated-per-action capability (Section 14) — not a security control by itself |
| `browser.browser_type` | string | `"chromium"` | Which Playwright-supported engine `PlaywrightBrowserBackend` launches (`chromium`/`firefox`/`webkit` are all valid Playwright values; only `chromium` is exercised/verified in v1) | None directly; exists so a future engine choice needs no code change to `Bootstrap`'s construction call, mirroring `desktop.backend`'s identical single-supported-value-today precedent (`EP050_DESIGN.md` Section 22) |
| `browser.default_timeout_ms` | int | a sane bound (e.g. `30000`) | Caps how long any single navigation/interaction waits before failing, preventing an indefinitely hung dispatch | Bounds resource/time usage only, not a security control |

No other keys are added "for the future." Explicitly **not** added
in v1: `browser.allowed_domains` (Owner Decision D6 — deferred, not
built), any per-action enable/disable key (Section 15's single-gate
conclusion), and any download-directory or upload-source
configuration (Section 6/D7 — the capabilities themselves do not
exist in v1, so no configuration for them is needed either).

---

## 17. Error Model

Reuses the project's existing two-state result convention
(`CommandResult.success: bool` / `.message: str`), exactly matching
`EP050_DESIGN.md` Section 21's own reasoning for not inventing a new,
richer taxonomy that exists nowhere else in the codebase:

| Condition | `message` prefix (example) |
|---|---|
| `browser.enabled: false` | `"Browser Automation is disabled (browser.enabled=false)."` |
| No active session for a non-`launch` action | `"no active browser session; run 'browser launch' first"` |
| `browser launch` while a session is already open | `"a browser session is already open; run 'browser close' first"` |
| Navigation failure (DNS, connection refused, etc.) | `"browser goto: navigation failed: <underlying reason>"` |
| Timeout (navigation or element interaction exceeding `browser.default_timeout_ms`) | `"browser <action>: timed out waiting for <selector/navigation>"` |
| Element not found for a given selector | `"browser <action>: no element matches selector '<selector>'"` |
| Invalid selector syntax | `"browser <action>: invalid selector '<selector>'"` |
| Unsupported/unrecognized action name | `"browser: unrecognized action '<action>'"` |
| Browser process closed unexpectedly / crashed | `"browser <action>: browser session is no longer available; run 'browser launch' again"` |
| Malformed arguments (wrong count/type) | `"browser <action>: invalid arguments, expected ..."` |

`BrowserBackendError` is the single exception type
`PlaywrightBrowserBackend` (and `_FakeBrowserBackend`) may raise,
mirroring `ComputerUseBackendError`'s identical role — every
Playwright-specific exception (`TimeoutError`, `Error`, etc.) is
caught inside `PlaywrightBrowserBackend` and re-raised as
`BrowserBackendError` with a normalized message, so `BrowserModule`
has exactly one exception type to catch, and no Playwright-specific
type or message format leaks through the public `CommandResult`
surface, per the task's own instruction ("Do not expose Selenium/
Playwright-specific implementation details unnecessarily").

---

## 18. Testing Strategy

Follows `tests/EP050/test_desktop.py`'s fake-backend precedent
exactly, itself following `tests/EP046/test_voice.py`'s original
fake-class convention:

### Automated tests (`tests/EP051/test_browser.py`, run in every CI/sandbox environment, no real browser)

- `_FakeBrowserBackend` — a plain class implementing `BrowserBackend`
  in full, holding simple in-memory state (a fake "current URL,"
  "current title," a small fixed page-text string, a fixed set of
  selectors considered "present") and recording every call made to
  it, so tests can assert *what* was called without launching a real
  browser.
- `BrowserModule` behavior against the fake:
  - argument parsing/validation for every action (missing URL,
    missing selector, wrong argument count).
  - `browser.enabled: false` blocks every action, with zero backend
    calls (mirroring `EP050_DESIGN.md` Section 25's identical
    `GATE_CHECK` assertion for `desktop.enabled`).
  - session-state errors: dispatching a non-`launch` action before
    `browser launch`, and dispatching `browser launch` twice without
    an intervening `browser close`, both fail cleanly per Section 17,
    without a real browser.
  - successful dispatch calls the correct backend method with the
    correct arguments exactly once, for every v1 action.
  - a `BrowserBackendError` raised by the fake is translated into a
    failed `CommandResult`, never propagated raw through
    `CommandRouter` — including a simulated navigation-timeout
    scenario, demonstrating the error model's generality.
  - logging never includes page-text content, typed text content, or
    screenshot bytes (Section 17) — asserted by capturing log output
    and checking the fixture's sensitive value is absent, only its
    length appears.
  - `CommandRouter` string-dispatch (`"browser <action> <args>"`)
    produces results identical to direct `BrowserModule.execute()`
    calls, mirroring `EP050_DESIGN.md`'s identical dispatch-equality
    assertion.

None of the above requires installing Playwright's browser binaries,
launching a real Chromium process, or any network access — fully
deterministic, satisfying the same hard constraint EP-050's suite
already satisfies for OS-level hardware.

### Optional real-browser integration tests (not part of the default suite)

A small, separately-invoked test module (e.g. `tests/EP051/
test_browser_integration.py`, skipped by default / run only with an
explicit flag or on a machine with `playwright install` already
completed) that exercises `PlaywrightBrowserBackend` against a real,
local, static test page (not a live third-party website, to keep the
test hermetic and avoid flakiness from external site changes): launch
a real Chromium instance, navigate to a `file://` fixture page,
click/type into a known element, and verify the resulting page state
— mirroring `tests/EP050/test_desktop_windows_integration.py`'s own
"separate, unregistered, real-environment" precedent exactly.

### Manual verification (owner performs, real machine, real network)

- `browser launch` against a real target site, confirmed visually
  (non-headless per Owner Decision D10's default).
- `browser goto`/`back`/`forward`/`reload` against a real multi-page
  site.
- `browser click`/`browser type`/`browser press` driving a real login
  or search form end to end.
- `browser screenshot` produces a visually correct capture of the
  real, rendered page.
- `browser.enabled: false` genuinely blocks every `browser` action on
  the real machine, not just against the fake backend.

This three-tier split (automated / optional integration / manual)
mirrors `EP050_DESIGN.md` Section 25's own precedent exactly.

---

## 19. EP-051 V1 Scope

| Capability | EP-051 v1 | Deferred | Reason |
|---|---|---|---|
| Browser launch | **Yes** | | Required lifecycle entry point (Section 10) |
| Browser close | **Yes** | | Required lifecycle exit point |
| Navigation (goto URL) | **Yes** | | Core capability; the reason this EP exists |
| Back | **Yes** | | Cheap, directly delegates to the browser's own history (Section 10) |
| Forward | **Yes** | | Same as Back |
| Reload | **Yes** | | Same as Back |
| Page title | **Yes** | | Basic, cheap observation |
| Current URL | **Yes** | | Basic, cheap observation; also reports post-redirect URLs (Section 12) |
| Page text | **Yes** | | Minimum useful "what's on this page" observation without OCR/vision (Section 6) |
| Element lookup (`exists <selector>`) | **Yes** | | Needed as its own observation and to support reliable pre-checks before `click`/`type` |
| Click | **Yes** | | Core interaction primitive |
| Type | **Yes** | | Core interaction primitive |
| Clear | **Yes** | | Cheap, commonly paired with `type` for re-filling a field |
| Select (dropdown) | | **Deferred** | Not essential for a minimal v1; click/type cover most form interaction; adding it later is a small, low-risk, backward-compatible extension |
| Keyboard interaction (general hotkeys) | | **Deferred** | Only a single, element-scoped keypress (`press <selector> <key>`, e.g. `Enter`) ships in v1 for the common "submit a search box with no visible button" case; general hotkey/modifier-combination support is deferred as unnecessary for v1's scope |
| Keyboard interaction (single key on an element) | **Yes** (`browser press <selector> <key>`) | | Narrow, common, low-risk addition covering the realistic "submit via Enter" case without the general hotkey surface above |
| Screenshot | **Yes** | | Mirrors EP-050's raw-capture precedent (Section 17); useful for basic verification/debugging even without vision interpretation |
| Wait (explicit wait-for-selector/timeout action) | | **Deferred** | Playwright's own auto-waiting (Section 8) already covers the realistic need for every v1 action; a standalone `wait` action adds surface area for a need not yet demonstrated |
| Tab management (new/switch/close/list tabs) | | **Deferred** | Adds real state-model complexity (Section 10 would need a tab-index concept) for a capability not required by any v1 goal; single-tab sessions are sufficient for v1's scope |
| JavaScript execution | | **Deferred (Non-Goal)** | Section 6/D8 — largest realistic risk surface; permanently excluded pending a dedicated future security review, not merely "not yet built" |
| Downloads | | **Deferred (Non-Goal)** | Section 6/D7 — belongs conceptually nearer EP-052 File Automation's territory (Section 20) |
| Uploads | | **Deferred (Non-Goal)** | Section 6/D7 — same reasoning as Downloads |

The objective, per the task's own framing, is a small, reliable
Browser Automation foundation — fifteen actions total
(launch, close, goto, back, forward, reload, title, current-url,
page-text, exists, click, type, clear, press, screenshot) — not a
complete browser agent.

---

## 20. EP-050 / EP-052 / EP-053 Boundaries

| Capability | EP-050 | EP-051 | EP-052 | EP-053 |
|---|---:|---:|---:|---:|
| Mouse / keyboard / clipboard (OS-level) | **Yes** | — | — | — |
| Screenshot capture (screen, raw) | **Yes** | — | — | — |
| Browser lifecycle (launch/close) | — | **Yes** | — | — |
| Browser navigation | — | **Yes** | — | — |
| Browser DOM interaction (click/type/clear/press) | — | **Yes** | — | — |
| Browser page observation (title/URL/text/screenshot) | — | **Yes** | — | — |
| File download handling | — | — | **Yes** (future) | — |
| File upload handling | — | — | **Yes** (future) | — |
| General file management (organize/move/rename) | — | — | **Yes** | — |
| OCR | — | — | — | **Yes** |
| Visual/scene understanding (screenshots or page images) | — | — | — | **Yes** |
| Vision model invocation | — | — | — | **Yes** |

**EP-051 / EP-052 boundary (File Automation):** EP-051 downloads and
uploads are Non-Goals (Section 6/D7), not merely restricted — a
browser-triggered file download or a file-picker upload dialog is
conceptually adjacent to general file management, which is EP-052's
territory. EP-051 v1 does not silently grow into "browser downloads
manage themselves through a general file system," per the task's
explicit instruction. If a future EP-051.x or EP-052 revision adds
download/upload support, the browser-triggering half (clicking a
download link, selecting a file in an upload dialog) and the file-
management half (where downloaded files live, how uploads are
sourced) should be designed together, deliberately, not assumed by
extension of either EP alone.

**EP-051 / EP-053 boundary (Vision Integration):** `browser
screenshot` returns raw, uninterpreted image bytes (Section 6/17),
exactly as EP-050's `desktop screenshot` does. EP-051 performs no
visual reasoning, OCR, or "what does this page look like" analysis
of its own screenshots — that capability belongs entirely to EP-053,
which may consume EP-051's screenshot output as one of its inputs
(alongside EP-050's), without EP-051 reaching into EP-053's
territory itself. `browser page-text` is a DOM-text-based
observation, not a Vision capability, and remains distinct from
whatever EP-053 eventually does with rendered pixels.

---

## 21. Owner Decisions

Per the task's explicit instruction, only genuine questions the
existing architecture and repository cannot answer are listed here,
mirroring `EP050_DESIGN.md` Section 30's own format.

**Approval status: D1–D12 are all APPROVED** (owner sign-off recorded
inline under each decision below). No decision remains open. This
approval authorizes STEP 2 to *begin design-conformant
implementation once separately requested*; per
`AI_DEVELOPMENT_PLAYBOOK.md`'s Prompt Strategy, STEP 1 approval and a
STEP 2 request are still two separate prompts — this document's
approval alone does not itself start STEP 2 (Section 22/24).

---

### D1

**Question:** Which browser automation technology should
`PlaywrightBrowserBackend`... (or, if rejected, a differently-named
backend)... actually use (Section 7/8)?

**Options:**
A. Playwright (sync API), as recommended — a genuinely new
   dependency, replacing the unused, unpinned `selenium` placeholder.
B. Selenium — reuse the already-declared (but unused, unpinned)
   dependency as-is.
C. Selenium, but re-pinned to a specific current version before use.

**Recommended:** A.

**Reason:** Section 7/8 in full — auto-waiting, a narrower error
surface, no separate driver-binary management, and (per Section 2/6)
zero real migration cost since nothing is built on Selenium today.
"Already in `requirements.txt`" does not, by itself, justify keeping
an unused, unpinned, unjustified dependency over a technically
stronger, actively-maintained alternative when no code depends on the
incumbent.

**Owner sign-off: APPROVED — Option A.** Playwright (sync API) is
confirmed as the v1 browser automation technology. STEP 2 will remove
the unpinned `selenium` line from `requirements.txt` and add a pinned
`playwright==<version>` line (Section 22).

**Impact if rejected (i.e. owner picks B or C):** Section 7's
technology-evaluation table, Section 8's recommendation text, and
Section 22's proposed `requirements.txt` change (remove `selenium`,
add `playwright`) would instead become: pin `selenium` to a current
version and proceed with `SeleniumBrowserBackend` implementing the
identical `BrowserBackend` Protocol (Section 9's architecture is
technology-agnostic and needs no change either way) — `WebDriverWait`/
`expected_conditions` boilerplate would then need to be built inside
the backend itself to approximate Playwright's built-in auto-waiting
(Section 7), a real, non-trivial STEP 2 cost this recommendation
avoids.

---

### D2

**Question:** What safety/confirmation model (Human Approval,
Section 14) should EP-051 v1 ship with?

**Options:**
A. Single category-level config gate only (`browser.enabled`,
   default `false`) — no per-action confirmation, no domain
   restriction, no distinction between "safe" observation actions and
   side-effecting ones. Buildable entirely within EP-051's own files.
B. Category gate (A) plus a genuine per-call confirmation prompt for
   every `browser` action, requiring the same new synchronous
   request/response channel `EP050_DESIGN.md` Section 15/30 (D2)
   already identified as a cross-cutting `CommandRouter`/dispatch-
   surface extension EP-050 explicitly declined to build unilaterally.
C. Category gate (A) now; explicitly flag per-call confirmation (B)
   as a fast-follow once a concrete confirmation-channel design
   exists for `CommandRouter` in general — the same resolution
   `EP050_DESIGN.md` Section 30 (D2) already reached for Computer
   Use.

**Recommended:** C.

**Reason:** Identical to `EP050_DESIGN.md` Section 30 (D2)'s own
reasoning, restated for Browser Automation: Option B is
architecturally the most complete reading of the Human Approval
principle, but requires a cross-cutting change this task's own rules
forbid EP-051 from making unilaterally. Option A alone under-delivers
on a real, named principle without saying so. Option C ships a safe,
off-by-default posture today while explicitly naming the gap —
consistent with, and reinforcing, EP-050's own precedent rather than
introducing a second, different resolution for a structurally
identical problem.

**Impact if rejected (i.e. owner picks A or B):** A: Section 14's
design stands as written with no explicit follow-up commitment. B:
STEP 1 is not actually complete for EP-051 either — a second design
pass covering the general `CommandRouter` confirmation-channel
extension itself would be a prerequisite for both EP-050 and EP-051
before STEP 2 could begin, and would need to be scoped as its own,
separate, cross-cutting Engineering Package rather than inside either
EP-050 or EP-051.

**Owner sign-off (D2): APPROVED — Option C.** A single category-level
gate (`browser.enabled`, default `false`) ships in v1. No per-action
confirmation framework is built inside EP-051. The general,
cross-cutting `CommandRouter` confirmation-channel gap remains
open and unscheduled, exactly as it does for EP-050's own D2.

---

### D3

**Question:** Is Section 19's fifteen-action v1 capability table the
right scope, or should it be narrowed further / widened?

**Options:**
A. Section 19's table exactly, as recommended.
B. Narrower — drop `press`, `exists`, or `screenshot` as
   non-essential for a true minimum viable v1.
C. Wider — pull `select` (dropdown) and/or an explicit `wait` action
   into v1 now.

**Recommended:** A.

**Reason:** Each included action either has no reasonable substitute
within the remaining set (`exists` is needed to support reliable
pre-checks before `click`/`type` without inventing a hidden retry
loop; `press` covers the common "Enter-to-submit" pattern `click`/
`type` alone cannot) or is cheap and low-risk given the chosen
technology (`screenshot`, `back`/`forward`/`reload` are near-free once
`launch`/`goto` exist). Each deferred action either adds real state-
model complexity (tabs) or a distinct, larger risk surface (JS
execution) disproportionate to v1's stated goal of a small, reliable
foundation.

**Impact if rejected (i.e. owner picks B or C):** B: Section 19's
table, Section 9's `BrowserBackend` Protocol method list, and Section
18's test list would all need to drop the corresponding rows/methods/
tests. C: the same three sections would need to add `select_option`
and/or an explicit `wait_for_selector`-style method and its own
Section 17 error rows (e.g. a distinct "wait timed out" case beyond
the general timeout row already present) — a materially larger STEP 2
scope, though still architecturally compatible with Section 9's
overall shape.

**Owner sign-off: APPROVED — Option A.** Section 19's fifteen-action
table stands as the confirmed v1 scope, consistent with the owner's
explicit approval of D7 (downloads/uploads excluded), D8 (JavaScript
execution excluded), and D12 (tabs/windows deferred) below — no
widening of the action set is approved for v1.

---

### D4

**Question:** `CommandRouter` vs. Tool Engine vs. a browser-specific
execution abstraction (Section 11)?

**Options:**
A. Direct `CommandRouter` integration, as recommended.
B. Extend Tool Engine for parameterized tools first, then build on
   top of that extension.
C. A new, browser-specific execution abstraction alongside
   `CommandRouter`.

**Recommended:** A.

**Reason:** Section 11 in full — identical to, and reinforcing,
`EP050_DESIGN.md`'s own Section 32 conclusion; Tool Engine's zero-
argument limitation blocks parameterized dispatch project-wide, not
uniquely for either EP-050 or EP-051, and is not something either EP
should fix unilaterally.

**Impact if rejected (i.e. owner picks B or C):** B: EP-051 STEP 2
cannot begin until a separate, dedicated "parameterized Tool support"
Engineering Package is scoped, designed, and implemented first —
recorded but left unscheduled and unnumbered by both `EP050_DESIGN.md`
Section 28 and this document, per the task's "leave a TODO, do not
invent it" policy. C: introduces a second, EP-051-only dispatch
mechanism the task's own instruction ("do not create unnecessary
Manager/Provider/Engine layers... reuse the repository's existing
architectural patterns") directly argues against.

**Owner sign-off: APPROVED — Option A.** Direct `CommandRouter`
integration is confirmed. Tool Engine (`src/core/tool/`) will NOT be
modified or extended by EP-051.

---

### D5

**Question:** Browser session model — single, lazily-created,
process-lifetime session (Section 10), or a multi-session/named-
session model now?

**Options:**
A. Single session only, as recommended (Section 10).
B. Multiple, independently-addressable named sessions
   (e.g. `browser launch --session work`) in v1.

**Recommended:** A.

**Reason:** No named consumer or use case in the current repository
requires more than one concurrent browser session; a single-session
model is the smallest state model that satisfies every v1 action
(Section 19) and avoids inventing a session-naming/addressing
convention with no current caller.

**Impact if rejected (i.e. owner picks B):** Section 10's state
model, every action's argument shape (Section 9/19 — a session
identifier would need to be threaded through every `browser` command)
and Section 18's test suite would all expand materially — a
significantly larger v1 scope, closer to "browser session manager"
than "browser automation foundation."

**Owner sign-off: APPROVED — Option A.** A single browser session is
confirmed for v1. No multi-session architecture, and no session
identifier/addressing convention, will be built in EP-051.

---

### D6

**Question:** Should EP-051 v1 include a `browser.allowed_domains`
navigation allow-list, or leave navigation unrestricted once
`browser.enabled` is true (Section 12/16)?

**Options:**
A. No allow-list in v1 — `browser goto` accepts any URL once enabled,
   as recommended.
B. A `browser.allowed_domains` config list restricting `browser goto`
   to a fixed set of domains.

**Recommended:** A.

**Reason:** Mirrors `EP050_DESIGN.md` Section 15's own explicit
"no allow-list/deny-list of specific coordinates or window titles"
deferred-by-design choice for Computer Use. A domain allow-list
without any per-action confirmation mechanism (Section 14/D2) is a
partial mitigation whose real-world value depends heavily on how it
is used/configured by the owner — better introduced deliberately,
with real requirements, once a concrete need or incident motivates
it, than spec'd speculatively now with no current consumer.

**Impact if rejected (i.e. owner picks B):** Section 16 gains a new
`browser.allowed_domains` config key (list of strings, default empty
= unrestricted, mirroring the "every key must have a concrete v1
purpose" configuration policy), and Section 17 gains a new error row
("navigation blocked: domain not in browser.allowed_domains") —
compatible with the existing architecture, but a real, additional
STEP 2 scope item, not a free addition.

**Owner sign-off: APPROVED — Option A.** No domain allow-list ships
in v1. Arbitrary navigation is permitted whenever `browser.enabled:
true` — recorded here, per the owner's explicit instruction, as a
**known, accepted security limitation** of EP-051 v1, not an
oversight (see also Section 12's risk table and Section 23).

---

### D7

**Question:** Should EP-051 v1 include any download or upload
capability at all (Section 6/12/19)?

**Options:**
A. Neither — both are complete Non-Goals in v1, as recommended.
B. A minimal download-only capability (no upload).
C. Both download and upload.

**Recommended:** A.

**Reason:** Section 20's EP-051/EP-052 boundary — both capabilities
sit conceptually nearer general file management (EP-052) than DOM
interaction, and neither has a named v1 use case forcing their
inclusion now. Excluding both entirely avoids having to design a
downloads directory / upload-source policy (itself a real, non-
trivial security and configuration surface) before EP-052 exists to
coordinate with.

**Impact if rejected (i.e. owner picks B or C):** Section 19's scope
table gains one or two new actions, Section 16 gains a
download-directory (and/or upload-source) configuration key, Section
12's security model gains dedicated rows beyond the current
placeholder table entries, and Section 20's EP-051/EP-052 boundary
statement would need to be renegotiated with whatever EP-052's own
eventual design assumes about download/upload ownership — a
coordination cost this recommendation avoids by deferring the whole
question.

**Owner sign-off: APPROVED — Option A.** Downloads and uploads are
completely excluded from EP-051 v1 — no `browser download`/`browser
upload` action of any kind will be implemented.

---

### D8

**Question:** Should EP-051 v1 expose any JavaScript execution
capability (e.g. `browser eval <script>`)?

**Options:**
A. No — permanently excluded as a Non-Goal pending a dedicated future
   security review, as recommended (Section 6).
B. Yes, with no restriction.
C. Yes, but restricted to a fixed, pre-approved script allow-list.

**Recommended:** A.

**Reason:** This is the single largest realistic risk surface a
browser automation library can introduce — arbitrary script execution
against whatever page and (if any) authenticated session is currently
loaded. None of EP-051 v1's stated goals (Section 5) require it; the
minimal action set (Section 19) is fully achievable via selector-
based `click`/`type`/`press` alone.

**Impact if rejected (i.e. owner picks B or C):** This would be a
substantial scope and risk-posture change requiring its own dedicated
security analysis beyond what Section 12/13 currently cover — not a
small addition to the existing action table. Recommend, if ever
pursued, treating it as a separate, explicitly-scoped future decision
rather than folding it into EP-051 v1 by amendment.

**Owner sign-off: APPROVED — Option A.** No JavaScript execution
capability of any kind (e.g. `browser eval`) will be exposed by
EP-051 v1.

---

### D9

**Question:** Screenshot policy (Section 6/17) — raw bytes only,
matching `EP050_DESIGN.md` Section 18/19's precedent exactly, or
should EP-051 include any minimal interpretation?

**Options:**
A. Exactly as designed: raw page-screenshot bytes only, zero content
   interpretation, as recommended.
B. Widen slightly (e.g. basic dimension/format metadata beyond what's
   already proposed, or simple diffing between two captures).

**Recommended:** A.

**Reason:** Identical to `EP050_DESIGN.md` Section 30 (D4)'s own
reasoning for Computer Use: any interpretation, however minimal,
starts down a path with no natural stopping point short of EP-053's
actual territory (Section 20), and risks exactly the scope creep this
document's Section 19 table is designed to prevent.

**Impact if rejected (i.e. owner picks B):** Section 17/20 would both
need revision to carve out the specific widened capability, and the
EP-051/EP-053 boundary table (Section 20) would need a new row —
meaningfully blurring, not just adjusting, a line this document
otherwise treats as firm.

**Owner sign-off: APPROVED — Option A.** `browser screenshot`
returns raw, uninterpreted bytes only. No OCR, visual interpretation,
or vision processing of any kind is implemented in EP-051 v1 — that
capability remains EP-053's sole responsibility (Section 20).

---

### D10

**Question:** Should the browser launch headless (invisible) or
headed (visible) by default?

**Options:**
A. `browser.headless` defaults to `false` (visible window), as
   recommended.
B. `browser.headless` defaults to `true` (invisible, background).

**Recommended:** A.

**Reason:** For a brand-new, risky-by-nature capability shipping with
only a category-level safety gate and no per-action confirmation
(Section 14/D2), a visible browser window is a free, incidental
observability aid — the owner can see what Jarvis's browser is doing
in real time, partially compensating (informally, not architecturally)
for the absence of a formal confirmation mechanism. This mirrors the
spirit, though not the letter, of the Human Approval principle without
requiring any new architecture.

**Impact if rejected (i.e. owner picks B):** No architectural change
— `browser.headless`'s default value simply flips in Section 16's
configuration table and in `PlaywrightBrowserBackend`'s construction
call; headless operation is fully supported by Playwright either way
(Section 7).

**Owner sign-off: APPROVED — Option A.** `browser.headless` defaults
to `false` — the browser remains visible by default in v1.

---

### D11

**Question:** Should `BrowserBackend`/`PlaywrightBrowserBackend` be
designed and verified as Windows-only (mirroring EP-050's own Owner
Decision D5), or as genuinely cross-platform from v1?

**Options:**
A. Design and implement as cross-platform from v1 — Playwright
   supports Windows/macOS/Linux identically, with no OS-specific
   backend variant needed (unlike `WindowsComputerUseBackend`'s own
   OS-specific implementation), as recommended.
B. Restrict to Windows-only in v1, matching EP-050's own scope
   decision, even though nothing about Playwright requires it.

**Recommended:** A.

**Reason:** Unlike PyAutoGUI's OS-specific quirks that motivated
EP-050's own D5 (`active_window_title()`'s platform-dependent
reliability, `EP050_DESIGN.md` Section 24), Playwright's browser
automation API is uniform across platforms by design — there is no
`WindowsBrowserBackend`-shaped code path this document would need to
carve out, and no cost to keeping the implementation genuinely
cross-platform. Manual verification (Section 18) still primarily
targets the real Windows workstation as the project's actual target
environment, but the architecture itself needs no Windows-only guard.

**Impact if rejected (i.e. owner picks B):** `PlaywrightBrowserBackend`
would need an explicit Windows-only startup guard (mirroring
`WindowsComputerUseBackendError`'s own platform check) with no
corresponding technical justification from the library itself —
recommended against, since it would add a restriction the technology
choice does not require.

**Owner sign-off: APPROVED — Option A, with an explicit added
constraint.** The architecture remains genuinely cross-platform (no
Windows-only guard is added to `BrowserBackend`/
`PlaywrightBrowserBackend`), and Windows remains the v1 manual-
verification target (Section 18). Per the owner's explicit
instruction, STEP 2 must not introduce artificial cross-platform
complexity either — no speculative per-OS branching, no macOS/Linux-
specific code paths, and no cross-platform test/verification
obligation beyond what Playwright's own uniform API already provides
for free. This does not change Section 11's recommendation; it
narrows how it may be implemented.

---

### D12

**Question:** Should EP-051 v1 include any explicit multiple-tab or
multiple-window management (new tab, switch tab, close tab, list
tabs/windows) — previously addressed only inside Section 19's scope
table as a deferred row, not as its own numbered Owner Decision?

**Options:**
A. Deferred — v1 ships a single-tab, single-window session only
   (Section 10/19), with no tab/window addressing, enumeration, or
   switching capability of any kind.
B. Pull explicit multi-tab/window management into EP-051 v1.

**Recommended:** A.

**Reason:** Identical to Section 19's original reasoning — explicit
tab/window management adds real state-model complexity (a tab index
or handle concept threaded through Section 10's session model and
every relevant action's arguments) for a capability no v1 goal
(Section 5) requires. A popup or a second tab opened by the page
itself is simply not automatically followed or exposed in v1
(Section 12's "Popups" row).

**Impact if rejected (i.e. owner picks B):** Section 10's state model
gains a tab/window handle concept, Section 9's `BrowserBackend`
Protocol gains `new_tab()`/`switch_tab()`/`close_tab()`/`list_tabs()`-
style methods, Section 19's scope table grows by several rows, and
Section 18's test suite gains corresponding multi-tab scenarios — a
materially larger v1 than currently designed.

**Owner sign-off: APPROVED — Option A.** No explicit multi-tab or
multi-window management is built in EP-051 v1, consistent with
Section 10's single-session, single-page state model.

---

## 22. STEP 2 Proposed Scope

**This is a plan only. No file below has been created or modified by
STEP 1.**

### CREATE

- `src/skills/browser/backend.py` — `BrowserBackend` Protocol,
  `BrowserBackendError`, and supporting plain dataclasses (mirroring
  `ComputerUseBackend`'s `Screenshot`/`ScreenSize`/`CursorPosition`
  shape) for whatever structured return values `browser` actions
  need beyond plain `str`/`bool`.
- `src/skills/browser/playwright_backend.py` — `PlaywrightBrowserBackend`,
  the real implementation (Owner Decision D1).
- `tests/EP051/__init__.py`
- `tests/EP051/test_browser.py` — deterministic, fake-backend-driven
  suite (Section 18).
- `tests/EP051/test_browser_integration.py` — optional, unregistered,
  real-Chromium-against-a-local-fixture-page suite (Section 18).

### MODIFY

- `src/skills/browser/skill.py` — currently a 0-byte placeholder;
  filled in with `BrowserModule` (Section 9). Listed as MODIFY rather
  than CREATE since the (empty) file already exists.
- `src/skills/browser/selenium_driver.py` — currently a 0-byte
  placeholder; per Owner Decision D1 (**APPROVED — Playwright**), this
  file will be **deleted** at STEP 2 rather than filled in, since it
  names a technology this document does not use. It is superseded by
  `playwright_backend.py` above.
- `src/bootstrap.py` — additive only: one new import, one new
  `PlaywrightBrowserBackend` construction (gated on
  `browser.enabled`, mirroring the existing `desktop.enabled` gating
  block exactly), one new `BrowserModule(...)` construction, added to
  `register_modules()`'s call list. No existing module's construction,
  order, or arguments changes.
- `config/config.yaml` — additive only: one new `browser:` block
  (Section 16). No existing key's meaning, default, or validation
  changes.
- `requirements.txt` — remove the unpinned `selenium` line (Section
  2/8); add a pinned `playwright==<latest-stable-at-STEP-2-time>`
  line, commented consistently with the file's existing convention
  (mirroring `openwakeword==0.6.0`'s own justification comment,
  Section 8).

### DO NOT MODIFY

- `src/core/command_router.py` (`CommandRouter`) — zero changes
  (Section 11).
- `src/core/tool/` (Tool Engine, EP-031) — zero changes (Section 11).
- `src/core/agent/`, `src/core/planning/`, `src/core/plan_execution/`
  (EP-028/029/030) — zero changes (Section 13).
- `src/core/execution/` (EP-003) — zero changes; process/application
  launching remains its job, not EP-051's.
- `src/skills/desktop/` (EP-050) — zero changes (Section 4).
- `src/skills/voice/` (EP-046/047/048/049) — zero changes; unrelated.
- `desktop/` (EP-044 PySide6 GUI client, a distinct, unrelated
  directory from `src/skills/desktop/`) — zero changes.
- `web/` (EP-045) — zero changes.
- `docs/architecture/designs/EP050_DESIGN.md`,
  `docs/architecture/audits/EP050_AUDIT.md`, and every other prior
  EP's design/audit document — zero changes.

### Dependencies that would need to change

- Remove: `selenium` (unpinned, unused — Section 2/8).
- Add: `playwright` (pinned to a specific version determined at STEP
  2 time), plus a documented one-time `playwright install` post-`pip
  install` step (not itself a `requirements.txt` entry — a setup/
  README instruction, per `playwright`'s own installation model,
  Section 8).

### Tests to be added

- `tests/EP051/test_browser.py` (Section 18, primary automated
  suite).
- `tests/EP051/test_browser_integration.py` (Section 18, optional,
  unregistered real-browser suite).

### Configuration changes

- New `browser:` block in `config/config.yaml` (Section 16):
  `browser.enabled` (default `false`), `browser.headless` (default
  `false`, pending D10), `browser.browser_type` (default
  `"chromium"`), `browser.default_timeout_ms` (a sane default, e.g.
  `30000`).

### Documentation changes that should happen later (STEP 3/4, not now)

- `docs/architecture/JARVIS_ROADMAP.md` — update EP-051's status line
  once STEP 2 begins/completes, following EP-050's own status-line
  format precedent exactly.
- `docs/BACKLOG.md` — update EP-051's entry analogously.
- A setup/README note documenting the required `playwright install`
  post-install step (Section 8), since it is not expressible purely
  through `requirements.txt`.
- `docs/architecture/audits/EP051_AUDIT.md` — created at STEP 4
  (Architecture Audit), not before.

None of the above has been performed during STEP 1. This section is
a plan only, per the task's explicit instruction.

---

## 23. Risks and Deferred Work

- **New dependency cost (Section 8/D1):** Playwright is a genuine new
  dependency requiring a `playwright install` post-install step this
  project has no precedent for (every other recent dependency,
  `openwakeword` included, needed only `pip install`). This should be
  documented clearly in setup instructions at STEP 3 so it is not a
  surprise to whoever runs STEP 2's implementation or later deploys
  it.
- **Human Approval gap carried forward, not closed (Section 14/D2):**
  identical in nature to EP-050's own disclosed gap — `browser.enabled`
  is a category gate, not per-action confirmation. This is a second,
  independent instance of the same unresolved cross-cutting need
  `EP050_DESIGN.md` Section 30 (D2) already flagged; it is not
  EP-051's job to resolve it, but the risk compounds as more
  categories (`desktop`, now potentially `browser`) rely on the same
  single-flag model without a general solution ever being scheduled.
- **Prompt injection boundary is currently unenforceable-in-code
  (Section 13):** the trust boundary is real and documented, but has
  no live enforcement point in the current codebase because no
  consumer of `browser page-text` output yet exists that could
  violate it. This is not a defect in EP-051 v1's design — it is a
  requirement recorded now for whichever future EP (a browsing-aware
  Agent/Planning extension, most plausibly) becomes that consumer,
  and that future EP's own design must re-confirm this boundary is
  actually respected in its own implementation, not merely assume
  EP-051 already solved it.
- **Tool Engine's zero-argument limitation is now confirmed a
  problem for a second, independent EP (Section 11/D4):** this
  strengthens, but does not itself resolve, the case for eventually
  scoping a dedicated "parameterized Tool support" Engineering
  Package. Still deliberately left unscheduled and unnumbered here,
  per the same policy `EP050_DESIGN.md` Section 28 already applied.
- **Single-session model (Section 10/D5) may prove limiting** if a
  future use case genuinely needs concurrent browser sessions (e.g.
  comparing two sites side by side); flagged as a straightforward,
  backward-compatible future extension rather than a v1 requirement.
- **No domain allow-list (Section 12/D6) means `browser.enabled: true`
  grants navigation to any reachable URL**, with no additional
  restriction beyond the single flag — an accepted, explicitly-named
  trade-off (Section 21, D6), not an oversight.
- **Deferred capabilities (`select`, general keyboard/hotkeys,
  explicit `wait`, tabs, JavaScript execution, downloads, uploads,
  Section 19)** are all realistic candidates for a future v1.1/v1.2
  widening once a concrete need is demonstrated; none require a
  redesign of Section 9's core architecture to add later — they are
  additive extensions to `BrowserBackend`'s method set and
  `BrowserModule`'s action-parsing table, matching how EP-050 itself
  frames deferred window-management (`EP050_DESIGN.md` Section 30,
  D6) as a low-risk future addition rather than a closed door.

---

## STEP 1 Final Conclusion

EP-051 STEP 1 (Architecture Discovery, Technology Evaluation &
Design) is complete. Owner Decisions D1–D12 (Section 21) are
**APPROVED** — each recorded inline with an explicit sign-off line
under its decision. No decision remains open.

Approval of the decisions is itself a documentation update only. No
source file, test file, configuration file, or dependency file has
been created or modified as a result. `src/skills/browser/` remains
exactly as found (two 0-byte placeholder files); `requirements.txt`
is unchanged; `src/bootstrap.py`, `src/core/command_router.py`,
`src/core/tool/`, and every EP-050/EP-049 file remain byte-identical
to their pre-EP-051 state. The only artifact created or modified by
EP-051 to date is this document,
`docs/architecture/designs/EP051_DESIGN.md`.

STEP 2 (Implementation) has still **NOT begun** and will not begin
until explicitly requested in a separate prompt, per
`AI_DEVELOPMENT_PLAYBOOK.md`'s Prompt Strategy ("Never continue
automatically. Always wait for the user's approval"). Approving the
Owner Decisions authorizes what STEP 2 *would* implement; it is not
itself an instruction to start STEP 2.
