# EP042 STEP 4 — Architecture Audit

## 1. Executive Summary

EP042 gives Jarvis a way to read email from a standard,
provider-independent IMAP server: list mailboxes/folders, list recent
messages, retrieve a specific message, and search a mailbox. It is
implemented as a new, independent Core → Service → Module → Bootstrap
subsystem (`src/core/email/`, `src/services/email_service.py`,
`src/modules/email_module.py`), using only the Python standard
library (`imaplib` + `email`) — no third-party dependency, no
provider-specific API, no OAuth. Every operation is read-only: every
mailbox is opened with `SELECT ... readonly=True` (IMAP `EXAMINE`
semantics), and no send/reply/forward/delete/move/flag capability
exists anywhere in the subsystem.

This audit re-verifies the implementation by direct inspection of
every file in the subsystem (not by re-reading the STEP 3 report),
re-runs the full test suite, and re-confirms the STEP 3 findings and
fixes are present in the final code.

**Final audit result: PASS.**

## 2. Scope

Owner-confirmed scope (from the EP042 STEP 2 prompt), implemented
exactly as approved:

- Generic, provider-independent email integration using standard
  protocols — IMAP only.
- Read-only. Exactly four public operations on `EmailService`:
  `list_folders()`, `list_messages(folder, limit)`,
  `get_message(folder, uid)`, `search_messages(folder, criteria)`.
- Authentication via two configurable environment-variable names
  (`email.imap_username_env_var`/`email.imap_password_env_var`,
  defaulting to `EMAIL_IMAP_USERNAME`/`EMAIL_IMAP_PASSWORD`), read
  from `os.environ` at call time only.
- A dedicated `email:` configuration section
  (`config/config.yaml`), gated by `email.enabled`.
- Core → Service → Module → Bootstrap architecture, following the
  EP-038/039/040/041 precedent.

## 3. Non-Goals

Explicitly excluded from EP042, confirmed absent by repository-wide
search (see Section 15):

- Sending email / SMTP message submission of any kind.
- Reply, forward, delete, move, or flag/mark (read/unread) operations.
- Attachment content download (attachment *metadata* — filename,
  content type, size — is included; attachment *content* is not).
- Gmail API, Microsoft Graph, Outlook API, or any other
  provider-specific API.
- OAuth2 or any provider-specific authentication flow.
- Background/scheduled polling or any IMAP `IDLE` connection.
- EventBus integration.
- Tool Engine (EP-031) integration.

## 4. Repository Changes

**Core** (new):
- `src/core/email/__init__.py` — package docstring, public re-exports
- `src/core/email/email_result.py` — `EmailFolder`, `EmailAttachment`,
  `EmailMessageSummary`, `EmailMessage`, `EmailResult` (frozen
  dataclasses)
- `src/core/email/email_error.py` — `EmailError` and 8 subclasses
  (flat hierarchy)

**Service** (new):
- `src/services/email_service.py` (810 lines) — `EmailService`,
  `EmailServiceError`, `_IMAPConnection` protocol,
  `_default_connection_factory`

**Module** (new):
- `src/modules/email_module.py` (143 lines) — `EmailModule`,
  `HELP_TEXT`

**Bootstrap** (modified, additive only):
- `src/bootstrap.py` — `EmailService`/`EmailModule` imports,
  `self._email_service` field, `email.enabled`-gated construction
  block (mirrors the EP-041 Discord block), `email_service` property

**Configuration** (modified, additive only):
- `config/config.yaml` — new `email:` section (9 keys, no credential
  value key), inserted after the existing `discord:` section

**Tests** (new):
- `tests/EP042/__init__.py`
- `tests/EP042/test_email_service.py` — `EmailServiceTest`, 55
  assertions
- `tests/EP042/test_email_module.py` — `EmailModuleTest`, 28
  assertions (including 2 real `Bootstrap().initialize()` wiring
  tests)

**Test registration** (modified, additive only):
- `src/modules/test_module.py` — 2 new `import tests.EP042....` lines

**Documentation** (new/modified):
- `docs/architecture/designs/EP042_DESIGN.md` (new, 20 sections,
  status FINAL)
- `CHANGELOG.md` (new `v0.1.9-ep042` entry)
- `docs/BACKLOG.md` (EP-042 marked complete, EP-043 now next)
- `docs/architecture/JARVIS_ROADMAP.md` (EP-042 moved to Completed,
  EP-043 now Current)
- `docs/RELEASE_NOTES.md` (new `EP-042 — Email Integration` section)
- `docs/architecture/audits/EP042_ARCHITECTURE_AUDIT.md` (this
  document, new)

Repository-wide diff against the pre-EP042 baseline confirms this is
the **complete and exact** set of changed/created files — no other
file in the repository differs (verified with `diff -rq` across the
full tree).

## 5. Architecture Compliance

**PASS.**

```
Core         src/core/email/{email_result,email_error,__init__}.py
             ↓
Service      src/services/email_service.py
             ↓
Module       src/modules/email_module.py
             ↓
Bootstrap    src/bootstrap.py (email.enabled gate)
```

Verified by direct inspection of every file:

- **Core**: pure data. `email_result.py` imports only `dataclasses`
  and `typing`; `email_error.py` imports nothing beyond
  `__future__.annotations`. Neither file imports `imaplib`, `os`,
  `socket`, or `ssl`. Every mention of `EmailService` inside
  `src/core/email/*` is docstring prose, not an import — confirmed by
  grep (`grep -n "EmailService" src/core/email/*.py` returns only
  comment/docstring lines).
- **Service**: owns the sole IMAP connection-creation call
  (`self._connection_factory(...)`, line 367, inside `_connect`) and
  the sole mailbox-selection call (`connection.select(...)`, line 404,
  always `readonly=True`). Credential resolution (`_require_credentials`,
  line ~300), connection lifecycle (`_connect`, `_session`,
  `EmailService._Session`), and all six configuration-validation
  methods (`_resolve_imap_host` through `_resolve_timeout_seconds`)
  live here.
- **Module**: five thin handlers (`_folders`, `_list`, `_message`,
  `_search`, `_help`) that validate argument count/type, call one
  `EmailService` method unchanged, and format a `CommandResult`. No
  `imaplib` import, no `os.environ` access anywhere in the file
  (confirmed by grep and by a dedicated in-suite source-inspection
  test, `_test_module_never_accesses_credentials`).
- **Bootstrap** (`src/bootstrap.py`): constructs `EmailService`,
  registers `EmailModule` inside a `try/except EmailServiceError`,
  gated by `email.enabled`. No business logic, no direct IMAP call,
  no credential handling.

Repository-wide reference search confirms exactly one implementation
of each component:

- `EmailService` is referenced only in `src/bootstrap.py`,
  `src/core/email/*` (docstring only), `src/modules/email_module.py`,
  `src/services/email_service.py`, and `tests/EP042/*` — no reference
  anywhere else in `src/`.
- `EmailModule` is referenced only in `src/bootstrap.py`,
  `src/modules/email_module.py`, and its own test file.
- `EMAIL_IMAP_USERNAME`/`EMAIL_IMAP_PASSWORD` are referenced only in
  `config/config.yaml`, `src/services/email_service.py`, EP-042 test
  and documentation files — no reference anywhere in `src/core/`,
  `src/modules/`, or any prior-EP file.

## 6. Core Layer Audit

**PASS.**

- `EmailFolder`, `EmailAttachment`, `EmailMessageSummary`,
  `EmailMessage`, `EmailResult` are all `@dataclass(frozen=True)` —
  immutable, matching the `DiscordResult`/`GitHubResult` convention.
- Full type annotations on every field (`str`, `str | None`,
  `tuple[str, ...]`, `tuple[EmailAttachment, ...]`, `int`, `Any` only
  for `EmailResult.data`, which by design holds one of several typed
  shapes depending on `operation`).
- `EmailError` hierarchy is flat: `EmailError` as base, 8 direct
  subclasses (`EmailAuthenticationError`, `EmailConnectionError`,
  `EmailTimeoutError`, `EmailTLSError`, `EmailMailboxError`,
  `EmailMessageNotFoundError`, `EmailSearchError`,
  `EmailProtocolError`), no further nesting — matching
  `DiscordError`'s shape.
- `EmailServiceError` is deliberately **not** part of the `EmailError`
  hierarchy and is **not** defined in Core — it lives in
  `src/services/email_service.py`, since it can only ever be raised
  from `EmailService.__init__` (invalid configuration), never from a
  running operation call. This exactly mirrors `DiscordServiceError`'s
  split from `DiscordError` in EP-041.
- No IMAP/network code, no configuration loading, no environment
  access, and no logging call exists anywhere in `src/core/email/`
  (confirmed: zero `logger`, `os.environ`, `imaplib`, or `socket`
  references in either file).
- Core has no dependency on Service or Module — confirmed by import
  inspection (Section 5).

## 7. Service Layer Audit

**PASS.**

**Connection**: `_connect(username, password)` is the sole entry
point that creates a connection (via the injectable
`connection_factory`, defaulting to `_default_connection_factory`,
which builds a real `imaplib.IMAP4_SSL` for `tls_mode == "ssl"` or an
`imaplib.IMAP4` + `starttls()` for `"starttls"`). `EmailService._Session`
(a context manager) guarantees `logout()` is called in `__exit__`
even when the `with` block raises — verified by a dedicated test
(`_test_logout_called_after_every_operation`) and by direct code
inspection showing the `try/finally`-equivalent `__exit__` pattern.

**TLS behavior**: `tls_mode` is validated at construction to be
exactly `"ssl"` or `"starttls"` (`_resolve_tls_mode`) — no third value
is accepted, so no code path connects over plaintext IMAP.
`ssl.create_default_context()` is used for both modes, providing
standard certificate-chain and hostname verification with no
configuration escape hatch to disable it.

**Timeout behavior**: `timeout_seconds` (default 30, validated
positive) is passed to the `imaplib` constructor in both TLS modes.
`socket.timeout` is caught at both the connection-creation step and
the `login()` step, translated to `EmailTimeoutError` in each case.

**Connection cleanup / logout behavior**: every public method uses
`with self._session() as connection:` — a single context manager
covering the connection's entire lifetime for that call. No method
stores a connection on `self`.

**Exception handling**: `_connect` translates `socket.timeout` →
`EmailTimeoutError`, `ssl.SSLError` → `EmailTLSError`,
`(OSError, ConnectionError)` → `EmailConnectionError` at the
connection-creation step, and `imaplib.IMAP4.error` →
`EmailAuthenticationError`, `socket.timeout` → `EmailTimeoutError` at
the login step.

**Authentication**: `_require_credentials()` reads
`os.environ.get(self._username_env_var)` and
`os.environ.get(self._password_env_var)` — the only two `os.environ`
references in the entire file (verified by grep). Called at the start
of every public operation (inside `EmailService._Session.__enter__`,
*before* `_connect` is invoked) — never at `__init__`, never cached on
`self` beyond the local variables returned to the caller. Blank or
missing values raise `EmailAuthenticationError` **before** any
connection is opened — verified by
`_test_missing_username_raises_and_never_connects`, which asserts the
connection factory was never called. Credentials are never logged —
the single `logger.info(...)` call in `__init__` (line 174) logs only
`imap_host`, `imap_port`, `tls_mode`, `timeout_seconds`. Credentials
never appear in an exception — verified by
`_test_credentials_never_leak_into_exception_messages`, which asserts
a fixed fake username/password never appear in the raised
`EmailAuthenticationError`'s message.

**Read-only behavior — critical, verified explicitly**: repository-wide
search of `src/core/email/`, `src/services/email_service.py`, and
`src/modules/email_module.py` for `STORE`, `EXPUNGE`, `APPEND` (as an
IMAP command, not the unrelated `list.append(...)` Python calls),
`COPY`, `MOVE`, `DELETE`, `SMTP`, `sendmail` returns **zero
implementation matches** — every hit is either a docstring statement
of absence or an unrelated Python `.append(...)` method call on a
`list`. The only mailbox-selection call site
(`connection.select(folder, readonly=True)`, line 404) is the single
`select` call in the file, and it unconditionally passes
`readonly=True`, which corresponds to the IMAP `EXAMINE` command
(not `SELECT`'s read-write semantics) — this subsystem cannot set the
`\Seen` flag or otherwise mutate a mailbox as a side effect of any
operation.

**UID handling**: all four operations use IMAP `UID` command variants
(`connection.uid("search", ...)`, `connection.uid("fetch", ...)`) —
never a raw sequence-number command. `_search_uids` explicitly sorts
the returned UIDs ascending by numeric value
(`uids.sort(key=lambda candidate: int(candidate))`) before use — this
was a STEP 3 audit finding (RFC 3501 does not guarantee `SEARCH`
result order) and is now covered by a dedicated regression test
(`_test_list_messages_orders_by_uid_not_server_order`).

**Error translation**: verified against the full failure-mode table
in `EP042_DESIGN.md` §16 — every category (authentication, connection,
TLS, timeout, mailbox, message-not-found, search, malformed response)
maps to a distinct `EmailError` subclass, each with a dedicated test.

## 8. Module Layer Audit

**PASS.**

- `EmailModule.execute(action, arguments)` dispatches to one of five
  handlers via a `dict[str, ActionHandler]` — unknown actions return
  `CommandResult(success=False, message='Unknown command: ...')`
  rather than raising.
- Commands verified: `email folders`, `email list [folder] [limit]`,
  `email message <folder> <uid>`, `email search <folder>
  <criteria...>`, `email help`. No sixth command exists in the
  dispatch table (`self._actions` has exactly 5 entries).
- Argument validation: `_list` validates `limit` is a parseable
  integer before calling the service (returns a `CommandResult`
  error, does not call `EmailService`, if not); `_message` and
  `_search` validate minimum argument count before calling the
  service.
- Error handling: every handler that calls `EmailService` wraps the
  call in `try: ... except EmailError as exc: return
  CommandResult(success=False, message=str(exc))`. `EmailServiceError`
  is deliberately not caught here, since it can only be raised during
  Bootstrap construction of `EmailService`, never from a running
  module call — if construction fails, Bootstrap never registers this
  module at all (Section 9).
- No IMAP protocol logic, no credential handling anywhere in this
  file — confirmed by grep (no `imaplib`, no `os.environ`) and by
  `_test_module_never_accesses_credentials`.

## 9. Bootstrap Integration

**PASS.**

- `email.enabled` (default `false` in `config/config.yaml`) gates
  construction. This default deliberately differs from
  EP-039/040/041's `true` default: IMAP has no safe universal default
  host (unlike a fixed REST API root), so an operator must supply
  `imap_host` and explicitly enable the subsystem.
- **Disabled behavior**: verified by a real `Bootstrap(...).initialize()`
  test (`_test_bootstrap_skips_email_module_when_disabled`) — asserts
  `bootstrap.email_service is None`. No credential is read, no
  connection is attempted (the `EmailService` constructor is never
  called at all when `email.enabled` is `false`).
- **Enabled behavior**: verified by a real
  `Bootstrap(...).initialize()` test
  (`_test_bootstrap_registers_email_module_when_enabled`) against a
  full, minimal config with a valid `imap_host` — asserts
  `bootstrap.email_service is not None`. Construction only validates
  configuration; it never opens a network connection (no `_connect`
  call happens until a public operation method is invoked).
- **Failure isolation**: construction is wrapped in
  `try/except EmailServiceError`, logging the error and leaving
  `self._email_service = None` rather than crashing Bootstrap — this
  is structurally identical to the EP-041 Discord wiring block, placed
  immediately after it in `src/bootstrap.py`.
- **Consistency with previous integration EPs**: the wiring block,
  the `email_service` property, and the import lines are a structural
  mirror of the EP-041 Discord block — confirmed by direct diff
  comparison of the two blocks' shape (gate → try → construct →
  register → except → log → else → log).

## 10. Configuration Audit

**PASS.**

```yaml
email:
  enabled: false
  imap_host: ""
  imap_port: 993
  tls_mode: "ssl"
  imap_username_env_var: "EMAIL_IMAP_USERNAME"
  imap_password_env_var: "EMAIL_IMAP_PASSWORD"
  default_mailbox: "INBOX"
  default_message_limit: 50
  timeout_seconds: 30
```

- No credential value key exists — only the two environment-variable
  *names* are configurable, which are not secrets themselves.
- `EmailService.__init__` validates all 9 keys via 6 `_resolve_*`
  methods, each raising `EmailServiceError` with a specific message on
  invalid input: `imap_host` (non-empty when `enabled` is true),
  `imap_port` (integer, 1–65535), `tls_mode` (exactly `"ssl"` or
  `"starttls"`), both env-var names (non-empty strings),
  `default_mailbox` (non-empty string), `default_message_limit`
  (positive integer), `timeout_seconds` (positive number). All 5
  invalid-input paths have a dedicated test.
- Defaults confirmed applied when omitted:
  `_test_construction_defaults_applied` verifies port 993, tls_mode
  `"ssl"`, default_mailbox `"INBOX"`, default_message_limit 50 when
  not specified in config.
- `config/config.yaml` parses successfully — re-verified this audit
  via `yaml.safe_load`.

## 11. Security Audit

**PASS.**

- Credential handling: environment-variable-only, read at call time,
  never cached, never logged, never in exceptions (Section 7).
- TLS: mandatory, no plaintext path exists (Section 7).
- Certificate validation: `ssl.create_default_context()`, no
  configuration option to disable it (Section 7).
- Logging: the sole `logger.info` call logs connection *parameters*
  (host/port/tls_mode/timeout), never credentials (Section 7).
- Exceptions: every `raise EmailAuthenticationError(...)` (and every
  other `EmailError` subclass) is built from fixed text and/or
  non-secret server response text; `EmailAuthenticationError`'s
  login-rejected message is always the fixed string `"IMAP server
  rejected the configured credentials."`, never the raw server
  response, to guarantee a password embedded in a server's error
  response can never leak through that path.
- Secret exposure: repository-wide search for hard-coded
  credential-like literals near `imap`/`password`/`email` found **no
  real-looking secret** anywhere in the EP042 subsystem, its tests, or
  its documentation. Test fixtures use obviously-synthetic values
  (`fake-user@example.com`, `fake-password-for-tests-xyz123`).
  `.env.example` (the pre-existing, non-real environment file) was
  not modified by EP042 and contains no email-related placeholder —
  noted as a documentation-completeness observation only, not a
  security defect, matching the equivalent observation in the EP-041
  audit for `DISCORD_TOKEN`.
- Read-only guarantees: Section 7 ("Read-only behavior") and Section
  15 (Scope-Creep Audit) both independently confirm no mutation
  operation exists.

## 12. Dependency Audit

**PASS.**

- `requirements.txt` is byte-identical to the pre-EP042 baseline
  (diff-verified).
- `src/services/email_service.py` imports only standard-library
  modules: `email`, `imaplib`, `os`, `re`, `socket`, `ssl`, plus
  `typing.Callable`/`typing.Protocol` and the project's own
  `loguru`/`Config`/Core-layer imports (both pre-existing project
  dependencies, not new).
- No `pip install` or new package reference exists anywhere in the
  EP042 subsystem.

## 13. Testing Audit

Re-run fresh for this audit (not reused from the STEP 3/4 report):

```
EP042 Service : 55 passed / 0 failed
EP042 Module  : 28 passed / 0 failed

Full project (test all, via the project's actual test runner):
5376 passed / 0 failed / 0 skipped
```

These numbers were obtained by direct invocation of
`EmailServiceTest().run()` and `EmailModuleTest().run()`, and by
running `TestModule().runner.run_all()` for the full suite, in this
audit session — not copied from a prior report.

## 14. Regression Audit

**PASS.**

- `tests/EP001` through `tests/EP041` are diff-verified byte-identical
  to the pre-EP042 baseline — no existing test file was modified.
- Every prior-EP source file (`src/core/discord/`, `src/core/github/`,
  `src/core/git/`, `src/core/telegram*/`, and their corresponding
  `services`/`modules` files) is diff-verified byte-identical to the
  pre-EP042 baseline.
- `src/bootstrap.py`'s diff against the pre-EP042 baseline is purely
  additive (every changed line is an insertion; no existing line was
  altered).
- The full regression run (Section 13) shows 5376 passed / 0 failed —
  matching the STEP 3/4 baseline exactly, confirming no prior-EP
  behavior regressed.

## 15. Scope-Creep Audit

**PASS — all explicitly confirmed absent.**

Repository-wide search of `src/core/email/`, `src/services/email_service.py`,
`src/modules/email_module.py`, and `config/config.yaml`'s `email:`
section for implementation matches of: SMTP sending, email sending,
Gmail API, Microsoft Graph, OAuth, EventBus, Tool Engine, background
polling, message mutation (`STORE`/`EXPUNGE`/`APPEND`/`COPY`/`MOVE`/
`DELETE` as IMAP commands) — **zero implementation matches**. Every
grep hit is either a docstring/comment statement of *absence* (e.g.
"No send, reply, forward, delete, move, or flag/mark... operation is
implemented") or an unrelated Python `.append(...)` list method call
misidentified by a case-insensitive substring match on "append".

The `tool.default_provider: "tool_engine"` and `agent.startup_mode:
"idle"` keys that appear in `config/config.yaml` are **pre-existing,
unrelated** configuration for EP-031 (Tool Engine) and EP-028 (Agent
Framework) respectively — confirmed present in the pre-EP042 baseline
and untouched by this EP; they are not EP-042 Tool Engine integration.

## 16. Known Technical Debt

`TestRegistry.register` keys test suites by `NAME.upper()`. Both
`EmailServiceTest` (in `tests/EP042/test_email_service.py`) and
`EmailModuleTest` (in `tests/EP042/test_email_module.py`) use
`NAME = "EP042"`, so the second class imported in
`src/modules/test_module.py` (`EmailModuleTest`) silently overwrites
the first in the registry dict — only one of the two suites is
reachable through the CLI `test EP042` command at a time.

- **It predates EP042**: the identical collision exists for every
  prior integration EP's Service/Module test-class pair (confirmed
  present for EP-038 through EP-041 by inspection of their `NAME`
  class attributes).
- **It affects previous integration EPs**: EP-038, EP-039, EP-040,
  and EP-041 all have this same condition.
- **It was not fixed**: `TestRegistry`'s architecture and every
  EP-038–EP-041 test file were left untouched by EP042, per this EP's
  explicit boundary.
- **It is outside EP042 scope**: this audit does not treat it as an
  EP042 defect — both `EmailServiceTest` and `EmailModuleTest` were
  independently verified to pass in full (55/55, 28/28) by direct
  invocation, so no EP042 assertion is actually unverified; only the
  single-command CLI convenience is affected.
- **It should be handled separately**: by a dedicated future
  maintenance EP addressing `TestRegistry` itself, not by any single
  integration EP. No solution is proposed or implemented here.

## 17. Risks and Limitations

Verified, not invented:

- No upper bound on retrieved message size — `get_message` fetches
  the full message body for the requested UID with no size cap. This
  is inherent to "retrieve a specific message" being in the
  owner-confirmed scope; no limit was requested, so none was added.
- IMAP server variability — real-world servers vary in extension
  support (e.g. some don't support `SEARCH` on certain criteria, some
  folder-name separators differ, some report `NIL` rather than a
  quoted delimiter in `LIST` responses, which `EmailFolder.delimiter`
  currently stores as the literal string `"NIL"` rather than `""`).
  `EmailSearchError`/`EmailMailboxError` exist so search/mailbox
  failures surface as clear, typed errors; this is a cosmetic parsing
  edge case with no security or correctness impact on any in-scope
  operation, left unfixed as a P3 item per the STEP 3 fix policy.
- Attachment `size_bytes` is computed from the decoded MIME part's
  payload length as parsed by the `email` package, which may not
  exactly equal the server-reported attachment size for all encodings
  — acceptable for metadata purposes per the owner's "do not
  over-engineer MIME parsing" instruction.
- `email.enabled` defaults to `false`, unlike EP-039/040/041's `true`
  default — a deliberate, documented design decision (Section 9), not
  a limitation, but noted here since it differs from precedent.
- The `TestRegistry` NAME-collision technical debt (Section 16) means
  only one EP042 test class is reachable via the single-command CLI
  `test EP042` — both were independently verified to compensate.

## 18. Final Audit Verdict

**EP042 STEP 4 — PASS**

No new defect was discovered during this audit beyond what STEP 3
already found, fixed, and verified. All architecture, security,
configuration, scope-boundary, and regression checks pass by direct
re-inspection of the final code (not by trusting the prior report).

## 19. Evidence

- Implementation: `src/core/email/{__init__,email_result,email_error}.py`,
  `src/services/email_service.py` (810 lines), `src/modules/email_module.py`
  (143 lines), `src/bootstrap.py` (EP-042 wiring block), `config/config.yaml`
  (`email:` section).
- Design document: `docs/architecture/designs/EP042_DESIGN.md` (FINAL
  status, 20 sections).
- Test results: `EmailServiceTest` 55/55, `EmailModuleTest` 28/28, full
  suite 5376/0/0 — all re-run fresh during this audit session
  (Section 13).
- Regression results: `tests/EP001`–`tests/EP041` and every prior-EP
  source file diff-verified byte-identical to the pre-EP042 baseline
  (Section 14).
- Configuration: `config/config.yaml`'s `email:` section, re-parsed
  successfully via `yaml.safe_load` during this audit.
- Previous EP architecture: `src/core/discord/`,
  `src/services/discord_service.py`, `src/modules/discord_module.py`
  (EP-041), used throughout this audit as the direct structural
  precedent for every EP-042 comparison.
