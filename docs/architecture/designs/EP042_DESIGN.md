# EP042 — Design

Status: **FINAL — implemented and verified through STEP 4.** Scope
confirmed directly by the project owner (see STEP 2 prompt), not
re-derived from ambiguous repository evidence — the EP042 STEP 1
investigation stopped because "Email Integration" alone
under-specified protocol, direction (read/write), and authentication.
This document designs against that owner-confirmed scope and reflects
the final, as-built implementation, including the corrections made
during the STEP 3 Deep Audit (final verdict: PASS WITH NOTES — see
CHANGELOG.md v0.1.9-ep042 "Fixed" for the three defects found and
corrected: malformed-charset header/body decoding, RFC 2047 decoding
of To/Cc headers, and explicit numeric UID ordering). Follows
`EP038_DESIGN.md`/`EP039_DESIGN.md`/`EP040_DESIGN.md`/
`EP041_DESIGN.md`'s structure and terminology, since Email Integration
is the direct architectural sibling of Git/GitHub/Telegram/Discord
Integration, next in Phase 6 (Integrations).

---

## 1. Problem

Jarvis has no way to read a user's email. Before this EP, no
email-related implementation, dependency, or configuration existed
anywhere in the codebase (confirmed by a repository-wide search during
STEP 1 and re-confirmed at STEP 2.1).

## 2. Existing State

- No email client, service, module, config, or test exists anywhere in
  the repository. No email-related third-party dependency
  (`imapclient`, `aiosmtplib`, `google-api-python-client`, `msal`, or
  otherwise) is present in `requirements.txt`.
- `requirements.txt` has no SMTP/IMAP dependency of any kind. The
  Python standard library (`imaplib`, `email`) is available with no
  additional dependency, and the project targets Python >= 3.12
  (`pyproject.toml`), which supports the `timeout=` constructor
  parameter on both `imaplib.IMAP4` and `imaplib.IMAP4_SSL`.
- `docs/architecture/JARVIS_ARCHITECTURE_VISION.md`'s "Tools" example
  list mentions "Email" only as an item in an illustrative,
  non-normative list (alongside Docker, Canva, Runway, Veo,
  ElevenLabs), and separately flags "Sending emails" under "Human
  Approval" as an irreversible action requiring explicit user
  confirmation — consistent with, but not the source of, the owner's
  explicit read-only decision below.
- EP-038 (Git), EP-039 (GitHub), EP-040 (Telegram Info), and EP-041
  (Discord) establish the only precedent for "Integration" EPs in this
  codebase: a Core → Service → Module subsystem, a flat per-subsystem
  error hierarchy, a frozen `<Name>Result(operation, data)` dataclass,
  environment-variable-only credentials, `Bootstrap` wiring gated by
  `<name>.enabled` with a try/except around construction, and
  dedicated `tests/EP0NN/` suites registered into `TestRegistry` via
  `src/modules/test_module.py`.

## 3. Owner-Confirmed Scope

The project owner explicitly confirmed the following (verbatim scope
from the STEP 2 prompt, restated here as the design's contract):

- **Protocol**: generic, provider-independent email via standard
  **IMAP** only. No provider-specific API (Gmail API, Microsoft Graph,
  Outlook API, Yahoo API, or other provider REST API).
- **Direction**: **read-only**. No SMTP message submission, no
  sending, replying, or forwarding.
- **Operations in scope**:
  1. Connect to an IMAP server.
  2. List available mail folders/mailboxes.
  3. List messages from a selected mailbox.
  4. Retrieve a specific message.
  5. Search messages using supported IMAP search capabilities.
  6. Connect safely using configured credentials.
  7. Return normalized results through the Jarvis architecture.
  8. Handle connection/authentication/protocol errors cleanly.
- **Authentication**: environment-variable credentials only (username
  + password), server settings configurable, no OAuth2.
- **Configuration**: a dedicated `email:` section following the
  existing integration pattern.
- **Architecture**: Core → Service → Module → Bootstrap, following
  EP038–EP041, adapted only where IMAP genuinely differs from a REST
  API (see §5, §14).

## 4. Non-goals

Explicitly out of scope for EP042 (owner-confirmed):

- Sending email / SMTP message submission of any kind.
- Reply, forward, delete, move, or flag/mark (read/unread) operations.
- Attachment upload or attachment content manipulation (attachment
  *metadata* — filename/content-type/size — is included; attachment
  *content extraction/download* is not).
- Any provider-specific API (Gmail API, Microsoft Graph, Outlook API,
  Yahoo API).
- OAuth2 or any provider-specific authentication flow.
- AI-generated email responses or any automatic email action.
- Background/scheduled email polling or any long-running daemon.
- EventBus integration.
- Tool Engine integration (no existing repository evidence requires
  it for this EP's interface — matching EP-038 through EP-041, none of
  which integrate with the Tool Engine either).
- SMTP is explicitly not implemented in any form in this EP (not even
  as a stub) — it may only be referenced as a *future* architectural
  possibility in documentation, never in code.

## 5. Architecture

```
Core         src/core/email/email_result.py, email_error.py
             (pure data: EmailFolder, EmailMessageSummary, EmailMessage,
             EmailAttachment, EmailResult, and the EmailError hierarchy
             — no protocol/network logic)

Service      src/services/email_service.py
             (EmailService — owns the one IMAP connection lifecycle
             per call: connect -> authenticate -> operate -> close.
             Normalizes raw IMAP/RFC 822 data into Core types.
             Translates imaplib/ssl/socket failures into EmailError
             subclasses)

Module       src/modules/email_module.py
             (EmailModule — the "email" CLI namespace: folders, list,
             message, search, help. Thin: parses arguments, calls
             EmailService, formats CommandResult, catches EmailError)

Bootstrap    src/bootstrap.py
             (constructs EmailService when 'email.enabled' is true,
             registers EmailModule, wrapped in try/except EmailServiceError,
             exposes an 'email_service' property — same shape as the
             EP-041 Discord wiring)
```

This is the same layering EP-038–EP-041 use. The one architectural
adaptation IMAP requires (vs. the REST APIs of EP-039/040/041) is
described in §8 and §14: instead of one stateless HTTP call per
operation, each `EmailService` operation opens one short-lived IMAP
connection, performs its single unit of work, and always closes the
connection before returning — so the service remains conceptually
stateless between calls (no persistent connection stored on `self`,
matching the EP-039/041 discipline), even though the underlying
protocol is itself connection-oriented.

## 6. Components

### `src/core/email/email_result.py`

Pure data, no protocol logic:

- `EmailFolder(name: str, delimiter: str, attributes: tuple[str, ...])`
  — one IMAP mailbox/folder entry, from `LIST`.
- `EmailAttachment(filename: str | None, content_type: str, size_bytes: int)`
  — attachment *metadata* only, no content.
- `EmailMessageSummary(uid: str, subject: str, sender: str, date: str | None, folder: str)`
  — a lightweight row used by `list_messages` and `search_messages`
  (headers only, no body — matches how `list_messages`/`search`
  operate on real IMAP servers without forcing a full-body fetch per
  message).
- `EmailMessage(uid: str, message_id: str | None, subject: str, sender: str, recipients: tuple[str, ...], cc: tuple[str, ...], date: str | None, body_text: str | None, body_html: str | None, folder: str, attachments: tuple[EmailAttachment, ...])`
  — the full normalized message, returned only by `get_message`.
- `EmailResult(operation: str, data: Any)` — the outcome of one
  successful `EmailService` call, mirroring `DiscordResult`/
  `GitHubResult`. `data` holds one of the above types (or a
  `list`/`tuple` of them for `list_folders`/`list_messages`/
  `search_messages`), never a raw IMAP/RFC 822 structure.

All five classes are frozen dataclasses, matching the existing
`<Name>Result` convention (EP-039/040/041).

### `src/core/email/email_error.py`

A flat, single-level hierarchy under one subsystem base, matching
`DiscordError`/`GitHubError`/`TelegramInfoError`:

- `EmailError` (base)
- `EmailAuthenticationError` — missing/blank credentials, or the IMAP
  server rejects login.
- `EmailConnectionError` — DNS/socket/refused-connection failure.
- `EmailTimeoutError` — the call exceeded `email.timeout_seconds`.
- `EmailTLSError` — TLS/certificate negotiation failure.
- `EmailMailboxError` — the requested folder does not exist, or
  `SELECT` fails.
- `EmailMessageNotFoundError` — the requested UID does not exist in
  the selected folder.
- `EmailSearchError` — the IMAP server rejected the search criteria.
- `EmailProtocolError` — any other IMAP protocol failure, or a
  malformed/unparseable server response.

`EmailServiceError` (raised only for invalid `email.*` configuration,
at `EmailService.__init__` time) intentionally does **not** subclass
`EmailError`, for the same reason `DiscordServiceError`/
`GitHubServiceError` don't: it can only ever occur from Bootstrap
construction, never from a running operation call. It is defined in
`src/services/email_service.py`, not in Core, matching that same
split.

### `src/services/email_service.py`

See §8.

### `src/modules/email_module.py`

See §9.

## 7. Core Contracts

Public API surface of `src/core/email/__init__.py` (re-exports only,
package docstring, no logic):

```
EmailFolder, EmailAttachment, EmailMessageSummary, EmailMessage, EmailResult
EmailError, EmailAuthenticationError, EmailConnectionError,
EmailTimeoutError, EmailTLSError, EmailMailboxError,
EmailMessageNotFoundError, EmailSearchError, EmailProtocolError
```

## 8. Service Design

`EmailService(config: Config, connection_factory: Callable[..., "_IMAPConnection"] | None = None)`

- `connection_factory` is the IMAP analogue of `DiscordService`'s
  injectable `session` — a callable `(host, port, tls_mode, timeout) ->
  connection`, where `connection` exposes the small subset of the
  standard `imaplib.IMAP4`/`IMAP4_SSL` interface this service actually
  uses (`login`, `select`, `list`, `uid`, `close`, `logout`). Defaults
  to a real factory that constructs `imaplib.IMAP4_SSL` (tls_mode
  `"ssl"`) or `imaplib.IMAP4` + `starttls()` (tls_mode `"starttls"`).
  Tests inject a small duck-typed stub instead, so no real IMAP server
  is ever contacted by this project's own test suite — exactly the
  role `session` plays in `DiscordService`/`GitHubService`.

Public operations (all read-only, all short-lived — open connection,
one unit of work, close connection, every single call):

- `list_folders() -> EmailResult` — `data` is `list[EmailFolder]`,
  from one `LIST` call.
- `list_messages(folder: str | None = None, limit: int | None = None) -> EmailResult`
  — `folder` defaults to `email.default_mailbox`; `limit` defaults to
  `email.default_message_limit`. Selects the folder read-only,
  fetches the most recent `limit` UIDs' envelope headers only (no
  body), returns `data` as `list[EmailMessageSummary]`, newest first.
- `get_message(folder: str, uid: str) -> EmailResult` — selects the
  folder read-only, fetches `RFC822` for the given UID, parses it with
  the standard-library `email` package, returns `data` as one
  `EmailMessage`.
- `search_messages(folder: str, criteria: str) -> EmailResult` —
  selects the folder read-only, runs one `UID SEARCH` with the given
  raw IMAP search-key string (e.g. `'UNSEEN'`, `'SUBJECT "invoice"'`,
  `'SINCE 01-Jan-2026'`), then fetches envelope headers for the
  matching UIDs the same way `list_messages` does, returning `data` as
  `list[EmailMessageSummary]`. The criteria string is passed to the
  server as a single already-formed IMAP search-key expression — this
  service does not invent a query DSL on top of it; it is the
  caller's/module's responsibility to supply valid IMAP search-key
  syntax, and a rejected/invalid expression surfaces as
  `EmailSearchError`.

Internal responsibilities:

- `_require_credentials()` — reads username/password from
  `os.environ` using the two *configured* env-var names
  (`email.imap_username_env_var`/`email.imap_password_env_var`, see
  §11), at the start of every operation call (never at `__init__`,
  never cached on `self` beyond one call, never logged). Missing or
  blank values raise `EmailAuthenticationError` before any connection
  is opened — matching `DiscordService._require_token`.
- `_connect_and_login()` — opens one connection via
  `connection_factory`, calls `login(username, password)`, translating
  every possible failure into the matching `EmailError` subclass (see
  §16). Always wrapped so the connection is closed
  (`try/finally: logout()`/`close()`) even when a later step in the
  same call raises.
- `_select_folder(connection, folder)` — `SELECT` (read-only mode via
  `select(folder, readonly=True)` — this subsystem never opens a
  mailbox for write, an extra safety margin beyond "no write
  operation exists", consistent with §4).
- `_parse_envelope(...)`/`_parse_message(...)` — normalization, using
  only the standard-library `email` package's `email.message_from_bytes`
  and its header-decoding helpers (`email.header.decode_header`) — no
  third-party MIME library.
- No method stores an open connection on `self`; no method is called
  outside the lifetime of the `with`/`try...finally` block that opened
  it. No background thread, timer, or event loop exists anywhere in
  this module.

## 9. Module Design

`EmailModule` — the `"email"` CLI namespace, exactly mirroring
`DiscordModule`'s shape:

```
email folders
email list [folder] [limit]
email message <folder> <uid>
email search <folder> <criteria...>
email help
```

- `folders` → `EmailService.list_folders()`.
- `list` → `EmailService.list_messages(folder, limit)`; `folder`/
  `limit` are optional positional arguments (defaults resolved inside
  the service from config, per §8).
- `message` → `EmailService.get_message(folder, uid)`; both arguments
  required.
- `search` → `EmailService.search_messages(folder, criteria)`; the
  remaining arguments after `folder` are rejoined with spaces into one
  raw IMAP search-key string, so a user can type e.g.
  `email search INBOX SUBJECT "invoice"` from the shell.
- `help` → static `HELP_TEXT`.

The module never touches `imaplib`, `email`, `os.environ`, or any
credential — it only calls `EmailService`'s existing public methods
and catches `EmailError` to format `CommandResult(success=False,
message=str(exc))`, never letting a raw exception (or a password, per
§13) reach the shell. `EmailServiceError` is not caught here, for the
same reason it isn't caught in `DiscordModule` (§8 of
`EP041_DESIGN.md`): it can only be raised during Bootstrap
construction, never from a running module call.

## 10. Bootstrap Integration

Mirrors the EP-041 Discord wiring exactly:

```python
# EP-042 Email Integration. Read-only IMAP-only email access. Like
# DiscordService/GitHubService, EmailService has no dependency on any
# other Engineering Package's service or engine. Credentials are never
# read here or anywhere in Bootstrap -- EmailService reads them
# directly from the environment (via the configured env-var names) at
# call time. EmailService opens/closes one short-lived IMAP connection
# per operation call -- no persistent connection, background thread,
# or polling is started at construction time.
if bool(config.get("email.enabled", False)):
    try:
        email_service = EmailService(config=config)
        self._email_service = email_service
        router.register(EmailModule(email_service))
    except EmailServiceError as exc:
        logger.error(
            f"Email Service disabled: invalid 'email.*' configuration "
            f"({exc}). Fix config/config.yaml and restart to re-enable it."
        )
        self._email_service = None
else:
    logger.info("Email Service disabled ('email.enabled: false').")
    self._email_service = None
```

`self._email_service: EmailService | None = None` is initialized in
`__init__` alongside the other integration services, and an
`email_service` property is added after `discord_service`'s, returning
the constructed instance or `None`.

**Default-disabled, unlike EP-039/040/041 (design decision, flagged
for review):** every other Phase-6 integration EP defaults its
`enabled` flag to `true`, because each has a safe, universal default
endpoint (GitHub's/Discord's fixed REST API root, Telegram's already-
configured `token`). Email/IMAP has no such default — `imap_host` is
inherently server-specific and empty by default (§11), so an
`enabled: true` default would still do nothing useful without further
configuration but would make Bootstrap attempt (and fail) `EmailService`
construction on every fresh checkout with an empty host. Defaulting to
`false` (matching the only other "requires real external setup before
it can do anything" precedent in this codebase — EP-012 Telegram
Gateway's `telegram.enabled: false`) keeps a fresh checkout free of a
logged construction failure while still working exactly like every
other integration once the operator supplies `imap_host` and flips
`enabled: true`. This does not change any EP-038–EP-041 default.

No existing Bootstrap wiring, service, or module is modified.

## 11. Configuration

New `email:` section in `config/config.yaml`, inserted after the
existing `discord:` section, following the same commented style:

```yaml
email:
  # EP-042 Email Integration. Read-only IMAP access (list folders,
  # list messages, get message, search) against a standard,
  # provider-independent IMAP server, using the Python standard
  # library ('imaplib' + 'email') only -- no third-party dependency,
  # no provider-specific API (Gmail API / Microsoft Graph / Outlook
  # API), no OAuth. No send/reply/forward/delete/move/flag operation
  # is implemented -- this subsystem can only ever read from the
  # configured mailbox. This subsystem has no dependency on any other
  # Engineering Package's service or engine, and is stateless between
  # calls -- each operation opens one short-lived IMAP connection and
  # always closes it before returning; no persistent connection,
  # background thread, or polling exists anywhere in this subsystem.
  #
  # IMPORTANT: authentication uses environment variables ONLY -- the
  # two names below (defaults shown) tell EmailService which
  # environment variables to read the username/password from. The
  # actual credential values must never be placed here or in any
  # other config file.
  #
  # "enabled" defaults to false, unlike discord/github/telegram_info
  # above -- IMAP has no safe universal default host (unlike a fixed
  # REST API root), so this subsystem stays off until an operator
  # supplies "imap_host" and explicitly enables it.
  #
  # "tls_mode" must be "ssl" (implicit TLS, IMAPS, the default) or
  # "starttls" (plaintext connection upgraded via STARTTLS). Plaintext,
  # unencrypted IMAP is not supported by this subsystem.
  #
  # "timeout_seconds" bounds every IMAP call, so a hung/slow network
  # request cannot hang the calling thread indefinitely.
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

`EmailService.__init__` validates (raising `EmailServiceError` on
failure, matching `DiscordServiceError`'s construction-time-only
validation):

- `imap_host`: if `enabled` is true, must be a non-empty string.
- `imap_port`: integer in `1..65535`.
- `tls_mode`: must be exactly `"ssl"` or `"starttls"`.
- `imap_username_env_var`/`imap_password_env_var`: non-empty strings
  (the *names*, not the secrets — resolved from the environment at
  call time, per §12).
- `default_mailbox`: non-empty string.
- `default_message_limit`: positive integer.
- `timeout_seconds`: positive number.

## 12. Authentication

- Credentials are **never** placed in `config/config.yaml` or any
  other config file — only the two environment-variable *names* are
  configurable (§11), matching the owner's explicit instruction and
  extending (not replacing) the EP-039/041 "fixed env-var name"
  pattern to a *configurable* env-var name, since a generic
  multi-provider IMAP integration cannot assume one fixed variable
  name the way a single-provider API (Discord, GitHub) can.
- `EmailService._require_credentials()` reads
  `os.environ[imap_username_env_var]` and
  `os.environ[imap_password_env_var]` at the start of every operation
  call — never at `__init__`, never cached on `self`.
- Missing or blank username/password raises `EmailAuthenticationError`
  before any network connection is opened.
- No OAuth2 flow of any kind is implemented (owner-confirmed
  non-goal).

## 13. Security

- Passwords/usernames are never logged, at any log level, anywhere in
  `EmailService`/`EmailModule`.
- Every `EmailError` message is built from fixed text and/or
  non-secret server response text (e.g. an IMAP status string) —
  never from the credential values. Where the raw IMAP server response
  to a failed `LOGIN` might itself echo back part of the submitted
  command (some servers do this), `EmailAuthenticationError`'s message
  is always the fixed string `"IMAP server rejected the configured
  credentials."`, never the raw server response, to guarantee the
  password can never leak through that path.
- TLS is mandatory: `tls_mode` only accepts `"ssl"` or `"starttls"`
  (§11) — there is no configuration value that connects over plaintext
  IMAP.
- Certificate validation uses `ssl.create_default_context()` (standard
  Python trust store and hostname verification) — this design exposes
  no configuration option to disable certificate verification.
- No credential or connection state is written to disk anywhere in
  this subsystem (no cache file, no session persistence).

## 14. IMAP Protocol Strategy

- **Standard library only**: `imaplib` (protocol) + `email` (RFC 822
  parsing/decoding) — both already available with Python >= 3.12, no
  new entry in `requirements.txt`. This satisfies the owner's
  instruction to prefer the standard library and to STOP before adding
  a third-party dependency; no third-party dependency is genuinely
  required for this scope, so none is added or proposed.
- **UID-based, not sequence-number-based**: all operations use IMAP's
  `UID` command variants (`UID SEARCH`, `UID FETCH`) rather than raw
  message sequence numbers, since UIDs are stable across a session and
  match `EmailMessageSummary.uid`/`EmailMessage.uid` being used as a
  durable per-message identifier across separate `list_messages` /
  `get_message` calls (each call opens a new connection — see below).
  RFC 3501 does not guarantee `SEARCH` results are returned in any
  particular order, so `EmailService` explicitly sorts UIDs ascending
  by numeric value before determining "most recent"/order, rather than
  trusting server-returned order (a real-world ordering-correctness
  defect found and fixed during the STEP 3 audit).
- **One connection per call, not one persistent connection**: unlike
  `DiscordService`/`GitHubService` (where "stateless" simply means "no
  session state beyond one HTTP request"), IMAP is inherently
  connection-oriented — a mailbox must be `SELECT`ed before any
  `SEARCH`/`FETCH`. This design keeps the *service* stateless (no
  connection object stored on `self`, matching the discipline of
  EP-039/041) by opening a brand-new connection, logging in, selecting
  the folder, performing the one requested operation, and always
  logging out/closing before the method returns — for every single
  public method call. This is the one place EP042 must deviate from
  the letter of "one call = one request" (as REST integrations do) —
  it preserves the same *spirit* (no held state between calls, no
  background connection) while respecting IMAP's actual protocol
  shape. This deviation is called out explicitly per the anti-guessing
  instruction to report where precedent doesn't map cleanly, rather
  than silently forcing IMAP into a REST-shaped implementation.
- **Read-only folder selection**: `select(folder, readonly=True)` is
  used everywhere — IMAP's `SELECT` (as opposed to `EXAMINE`) can
  itself set the `\Seen` flag as a side effect of a later `FETCH`, so
  this design consistently avoids that entirely rather than relying on
  fetch-flag arguments to prevent it.
- **No background polling, no IDLE**: `imaplib` supports `IDLE` via
  extensions, but this design never opens or maintains a connection
  long enough to use it — explicitly out of scope (§4).

## 15. Message Normalization

- `list_messages`/`search_messages` fetch only header-level data
  (`UID FETCH ... (BODY.PEEK[HEADER])`) — subject, from, date — into
  `EmailMessageSummary`, never the full body, so listing/searching a
  large mailbox does not force downloading every matching message
  body.
- `get_message` fetches the full `RFC822` body for exactly one UID and
  parses it with `email.message_from_bytes(...)`, then:
  - decodes `Subject`/`From`/`To`/`Cc` headers via
    `email.header.decode_header` (handles RFC 2047 encoded-word
    headers safely, without hand-rolled decoding). If the header
    declares a malformed or unrecognized charset, decoding falls back
    to a best-effort UTF-8 decode (`errors="replace"`) rather than
    raising — a real-world defect found and fixed during the STEP 3
    audit (a bare, untyped `LookupError` previously escaped every
    operation that touches a Subject/From/To/Cc header).
  - for a multipart message, walks `message.walk()` once and applies a
    predictable, minimal strategy: the first `text/plain` part becomes
    `body_text`, the first `text/html` part becomes `body_html`; every
    other part with a `Content-Disposition: attachment` (or a
    filename) becomes one `EmailAttachment` entry (filename,
    content-type, and `len()` of its decoded payload as `size_bytes`)
    — attachment *content* is never stored on `EmailMessage`, matching
    §4's "metadata only" non-goal. Body-part text decoding has the
    same malformed-charset fallback as header decoding, for the same
    reason.
  - a non-multipart message maps its single body directly to
    `body_text` or `body_html` depending on its declared
    `Content-Type`.
  - this is deliberately the simplest strategy that satisfies "a
    predictable and safe extraction strategy" from the owner's
    instructions — no recursive nested-multipart special-casing beyond
    what `message.walk()` already provides, no charset-guessing beyond
    what the `email` package already exposes via `get_content_charset()`,
    with a safe fallback (rather than a raised exception) when even
    that declared charset is unusable.

## 16. Error Handling

| Failure | Raised as |
|---|---|
| `email.enabled` true but `imap_host` blank, or any other invalid `email.*` config value | `EmailServiceError` (construction only) |
| Username/password env var unset or blank | `EmailAuthenticationError` |
| IMAP server rejects `LOGIN` | `EmailAuthenticationError` |
| DNS failure / connection refused / socket error opening the connection | `EmailConnectionError` |
| `socket.timeout` at any step | `EmailTimeoutError` |
| `ssl.SSLError` during connect/`starttls()` | `EmailTLSError` |
| `SELECT` fails / folder does not exist | `EmailMailboxError` |
| `UID FETCH` for a UID not present in the selected folder | `EmailMessageNotFoundError` |
| `UID SEARCH` rejected by the server (bad criteria) | `EmailSearchError` |
| `UID SEARCH` returns a non-numeric UID (unparseable response) | `EmailProtocolError` |
| Any other `imaplib.IMAP4.error`/`imaplib.IMAP4.abort`, or an unparseable server response | `EmailProtocolError` |
| Malformed/unrecognized MIME charset in a header or body part | Not raised — falls back to a best-effort UTF-8 decode (see §15) |


Every raise site wraps the originating exception with `raise ... from
exc`, matching the EP-039/041 convention, and no raise site ever
interpolates the username/password value into a message (§13).

## 17. Testing Strategy

`tests/EP042/test_email_service.py` and
`tests/EP042/test_email_module.py`, following the exact structure of
`tests/EP041/test_discord_service.py`/`test_discord_module.py`:
`BaseTest` subclasses registered via `@TestRegistry.register`, `NAME =
"EP042"`, a small duck-typed stub connection (`_StubConnection`)
standing in for `imaplib.IMAP4_SSL`/`IMAP4` so no real IMAP server is
ever contacted, and a credential-env-var guard (mirroring
`_TokenGuard`) that sets/unsets the two configured env vars around
each test and always restores the prior environment afterward.

At minimum, covering every category the owner's prompt specifies:

- **Configuration**: disabled integration (Bootstrap does not
  construct `EmailService`/register `EmailModule`); enabled with valid
  config; missing/invalid `imap_host`/`imap_port`/`tls_mode`/
  `default_message_limit`/`timeout_seconds` each raise
  `EmailServiceError`.
- **Authentication**: successful login; missing username env var;
  missing password env var; blank credential; server-rejected login.
- **Connection**: successful connect; connection refused/DNS failure;
  TLS/certificate failure; timeout.
- **Mailboxes**: `list_folders` success; `SELECT` failure on an
  unknown folder.
- **Messages**: `list_messages` success (including default
  folder/limit resolution); `get_message` success (including a
  multipart message with one attachment, verifying normalization);
  message-not-found; malformed/unparseable server response.
- **Search**: successful search with results; empty result set;
  server-rejected criteria.
- **Security**: a test asserting the configured password value never
  appears in any raised exception's `str(...)`, and never appears in
  any log record captured during a full failure path (auth failure,
  connection failure).
- **Malformed input** (added during STEP 3): a body part and a header
  each declaring an unrecognized MIME charset, verifying the
  best-effort UTF-8 fallback rather than a raised `LookupError`;
  RFC 2047-encoded To/Cc addresses, verifying they decode the same way
  Subject/From do; `SEARCH` results returned out of numeric order by
  the (stub) server, verifying `list_messages` still orders "most
  recent first" correctly.
- **Bootstrap wiring** (added during STEP 3, closing a gap versus the
  EP-041 precedent): a real `Bootstrap(...).initialize()` against a
  full minimal config, asserting `bootstrap.email_service is not None`
  when `email.enabled: true` and `is None` when `false`.
- **Regression**: `tests/EP001` through `tests/EP041` are not
  modified; final verification (STEP 3 and STEP 4) confirms they
  still pass (see §18).

Final counts: `EmailServiceTest` 55/55 passed, `EmailModuleTest`
28/28 passed (both verified by direct invocation, since only one is
reachable through the single CLI `test EP042` command — see §19's
`TestRegistry` NAME-collision entry).

## 18. Regression Safety

Before implementation (STEP 2.1): the existing test suite registered
39 EP041 assertions, plus the full EP001–EP040 regression set already
recorded in `CHANGELOG.md`'s EP-041 entry. `test_module.py`,
`TestRegistry`, `TestRunner`, `BaseTest`, and every existing
`tests/EP0NN/` suite were extended, not altered, by this EP.

Final verification (STEP 3, re-confirmed at STEP 4): the full project
suite, run via the project's actual test runner, passed **5376 passed
/ 0 failed / 0 skipped**, with every prior EP's assertion count
unchanged from its last recorded baseline. No existing test file was
modified. `src/modules/test_module.py` gained exactly two new
`import` lines (`tests.EP042.test_email_service`,
`tests.EP042.test_email_module`), matching how every prior integration
EP registered its suite — no other line in that file changed.

## 19. Risks

- **`TestRegistry` NAME collision (pre-existing, not introduced by
  EP042; unresolved by design)**: `TestRegistry.register` keys suites
  by `NAME.upper()`, and every EP03x/04x integration EP already
  registers *two* classes (`<Name>ServiceTest`, `<Name>ModuleTest`)
  under the *same* `NAME` (e.g. both Discord test classes use
  `NAME = "EP041"`), so the second `import` silently overwrites the
  first in the registry dict, and `test EP041`/`test EP042` only ever
  runs whichever suite was imported last. This is an existing
  repository condition (present since at least EP-038); EP-042 follows
  the same convention for consistency rather than silently fixing it,
  and it was confirmed still present, unfixed, and out of EP-042's
  boundary as of STEP 4. Both `EmailServiceTest` and `EmailModuleTest`
  were verified passing in full (55/55, 28/28) by direct invocation.
- **IMAP server variability (unresolved by design, inherent to the
  protocol)**: real-world IMAP servers vary in extension support
  (e.g. some don't support `SEARCH` on certain criteria, some
  folder-name separators differ). `EmailSearchError`/
  `EmailMailboxError` exist specifically so these surface as clear,
  typed errors rather than silent failures; this design does not
  attempt to normalize away every server's quirks.
- **Attachment metadata accuracy (accepted, unresolved by design)**:
  `size_bytes` is computed from the decoded MIME part's payload length
  as parsed by `email`, which may not exactly equal the
  server-reported attachment size for all encodings — acceptable for
  metadata purposes per the owner's "do not over-engineer MIME
  parsing" instruction.
- **`enabled: false` default deviates from EP-039/040/041's
  `enabled: true` default** — see §10 for the rationale; confirmed
  unchanged through STEP 4.
- **Message decoding crashing on malformed input — found during STEP
  3, resolved**: a malformed/unrecognized MIME charset in a header or
  body part previously raised a bare, untyped `LookupError` out of
  `get_message`/`list_messages`/`search_messages`. Fixed by falling
  back to a best-effort UTF-8 decode (§15/§16); covered by dedicated
  regression tests.
- **To/Cc headers not RFC 2047-decoded — found during STEP 3,
  resolved**: the original implementation only comma-split To/Cc
  headers without decoding encoded-word display names, contradicting
  this design's own §15. Fixed; covered by a dedicated regression
  test.
- **SEARCH result ordering not guaranteed — found during STEP 3,
  resolved**: `list_messages`/`search_messages` trusted server-returned
  `SEARCH` order for "most recent"/ordering, which RFC 3501 does not
  guarantee. Fixed by explicit numeric UID sorting; covered by a
  dedicated regression test.
- **No upper bound on retrieved message size (accepted, unresolved by
  design)**: `get_message` fetches the full message body for the
  requested UID with no size cap — inherent to "retrieve a specific
  message" being in the owner-confirmed scope; no limit was requested,
  so none was invented.

## 20. Final Implementation Summary

Implemented, verified, and released as of STEP 4 (v0.1.9-ep042).

### Files created

- `src/core/email/__init__.py`
- `src/core/email/email_result.py`
- `src/core/email/email_error.py`
- `src/services/email_service.py`
- `src/modules/email_module.py`
- `tests/EP042/__init__.py`
- `tests/EP042/test_email_service.py` (55 assertions)
- `tests/EP042/test_email_module.py` (28 assertions)
- `docs/architecture/designs/EP042_DESIGN.md` (this document)

### Files modified (additive only, diff-verified against the pre-EP042 baseline)

- `config/config.yaml` — the `email:` section from §11, inserted after
  the existing `discord:` section.
- `src/bootstrap.py` — the `EmailService`/`EmailModule` imports, the
  `self._email_service` field, the wiring block from §10 (after the
  EP-041 Discord block), and the `email_service` property.
- `src/modules/test_module.py` — exactly two new `import
  tests.EP042....` lines.
- `CHANGELOG.md` — new `v0.1.9-ep042` entry.
- `docs/BACKLOG.md` — "Next Engineering Package" updated to EP-043,
  with an EP-042-complete handoff note.
- `docs/architecture/JARVIS_ROADMAP.md` — `EP-042 Email Integration`
  moved from "Current" to "Completed"; `EP-043 REST API` is now
  "Current".
- `docs/RELEASE_NOTES.md` — new `EP-042 — Email Integration` section.

### Files confirmed NOT modified

- Every `src/core/discord/`, `src/core/github/`, `src/core/git/`,
  `src/core/telegram*/` file.
- Every `src/services/discord_service.py`, `github_service.py`,
  `git_service.py`, `telegram*_service.py`.
- Every `src/modules/discord_module.py`, `github_module.py`,
  `git_module.py`, `telegram*_module.py`.
- Every existing test file under `tests/EP001`–`tests/EP041`.
- `requirements.txt` (no new dependency was needed — see §14).

### Final verification (STEP 4)

`EmailServiceTest`: 55 passed / 0 failed. `EmailModuleTest`: 28
passed / 0 failed. Full project suite (`test all`, run via the
project's actual test runner): **5376 passed / 0 failed / 0
skipped**. No `__pycache__`/`.pyc`/temporary/scratch files remain in
the repository.
