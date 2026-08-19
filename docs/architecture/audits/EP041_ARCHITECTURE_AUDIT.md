# EP041 STEP 4 — Architecture Audit

## 1. Architecture Status

PASS

Verified by direct inspection of every file in the subsystem:

- **Core** (`src/core/discord/discord_result.py`, `discord_error.py`,
  `__init__.py`): pure data. `DiscordResult` is a frozen dataclass;
  `DiscordError` and its six subclasses carry no HTTP logic. Neither
  file imports `requests`.
- **Service** (`src/services/discord_service.py`): owns the sole
  `requests.get(...)` call (`_get`, line 286) and the sole error
  mapping (`_parse_response`). `DISCORD_TOKEN` resolution
  (`_require_token`), URL construction, and configuration validation
  (`_resolve_api_base_url`, `_resolve_timeout_seconds`) all live here.
- **Module** (`src/modules/discord_module.py`): six thin handlers
  (`_guild`, `_channels`, `_channel`, `_member`, `_message`, `_help`)
  that validate argument count, call one `DiscordService` method
  unchanged, and format a `CommandResult`. No `requests` import, no
  `os.environ` access, no `DISCORD_TOKEN` reference anywhere in the
  file.
- **Bootstrap** (`src/bootstrap.py`, lines 1411–1436): constructs
  `DiscordService`, registers `DiscordModule` inside a
  `try/except DiscordServiceError`, gated by `discord.enabled`. No
  business logic, no direct HTTP call, no token handling.

Exactly one Discord HTTP call owner exists. Repository-wide search
confirms:

- `requests.get` appears as a real call only inside
  `discord_service.py`'s `_get` method (all other hits are docstring
  prose in this and sibling EP-039/040 files).
- `DiscordService` is referenced only in
  `src/modules/discord_module.py`, `src/services/discord_service.py`,
  `src/bootstrap.py`, `src/core/discord/*`, and `tests/EP041/*` — no
  reference anywhere else in `src/`.
- `DiscordModule` is referenced only in `discord_module.py`,
  `bootstrap.py`, and its own test file.
- `DISCORD_TOKEN` is referenced only inside the EP-041 subsystem
  (service, module docstrings, error docstrings), `bootstrap.py`
  (comment only — never read there), `config/config.yaml` (comment
  only, no key), and the EP-041 test/doc files.
- `discord.api_base_url` is referenced only in `discord_service.py`
  and the design/release docs.

## 2. Scope Compliance

PASS

`DiscordService`'s public API is exactly five methods: `get_guild`,
`list_guild_channels`, `get_channel`, `get_guild_member`,
`get_message`. No sixth public method exists.

Repository-wide search of `src/core/discord/`, `discord_service.py`,
`discord_module.py`, and `tests/EP041/` for send/edit/delete
message, message history/bulk retrieval, create/update/delete
channel, moderation, roles, reactions, invites, webhooks, Gateway,
WebSocket, polling, background listener, persistent cursor, and
update offset returned **no implementation matches** — every hit is
either a docstring statement of *absence* (e.g. "No create, update,
delete, moderation, webhook, role, reaction, invite... operation is
implemented") or an unrelated pre-existing EP-012 config key
(`telegram.polling_interval`) inside a full-config test fixture,
which has nothing to do with Discord.

The one `"role"` hit inside actual (non-docstring) code is
`nickname, roles, joined_at` in a docstring describing the *shape of
data Discord returns* for `get_guild_member` — not a role-management
operation.

Per the STEP 4 instruction: Discord's REST API does technically
support bulk message-history retrieval
(`GET /channels/{channel.id}/messages`), and this is *not* treated as
an implementation defect, since it was deliberately excluded from
EP041's confirmed scope (documented in `EP041_DESIGN.md`,
`docs/RELEASE_NOTES.md`) and does not exist anywhere in
`DiscordService`'s code.

## 3. Discord REST API Boundary

PASS

All five operations are single, stateless `requests.get(...)` calls
(confirmed: `_get` is the only call site, called once per public
method, no loop, no retry, no callback registration). API paths
verified against the intended resource:

| Operation | Path built | Correct? |
|---|---|---|
| `get_guild` | `/guilds/{guild_id}` | Yes |
| `list_guild_channels` | `/guilds/{guild_id}/channels` | Yes |
| `get_channel` | `/channels/{channel_id}` | Yes |
| `get_guild_member` | `/guilds/{guild_id}/members/{user_id}` | Yes |
| `get_message` | `/channels/{channel_id}/messages/{message_id}` | Yes |

Base URL defaults to `https://discord.com/api/v10` (REST API v10, as
specified). No `websocket`, `socket`, `asyncio` event-loop, or Discord
Gateway import exists anywhere in the subsystem. No persistent
`requests.Session` state is reused across calls beyond simple
connection pooling (the session object itself carries no
cursor/offset attribute). No polling loop or background thread is
started.

Every path parameter (`guild_id`, `channel_id`, `user_id`,
`message_id`) is passed through `urllib.parse.quote(str(...))` before
being interpolated into the URL — confirmed at all five call sites in
`discord_service.py`. `tests/EP041/test_discord_service.py`'s
`_test_path_segments_are_url_quoted` independently exercises this
with a space and a slash, confirming `%20`/`+` and `%2F` encoding.

## 4. Security

PASS

- `DISCORD_TOKEN` is read exclusively via `os.environ.get(...)`
  inside `_require_token`, called at the top of every `_get` call —
  never at `__init__`, never cached on `self`.
- Not present in `config/config.yaml` — the `discord:` section
  contains only `enabled`, `api_base_url`, `timeout_seconds`, with an
  explicit comment stating the token must never be placed there.
- Not accepted through any CLI argument — `DiscordModule`'s six
  handlers take only `guild_id`/`channel_id`/`user_id`/`message_id`
  arguments; no handler reads or forwards a token-like argument.
- Not logged — the only `logger` calls in `discord_service.py` are
  the `__init__` info line (api_base_url + timeout only) and three
  error-path lines in `_get` that log `operation` and, for the
  generic-exception branch, `str(exc)` from a `requests` exception —
  never the token itself, since the token is never part of the
  exception object `requests` raises for timeout/connection failures.
- Not included in exceptions — every `DiscordError` message in
  `_parse_response` and `_require_token` is built from fixed text
  only, never string-interpolating the token.
- Not included in CLI output — `DiscordModule` formats
  `CommandResult.message` from `str(result.data)` (the API response
  body, not the token) or `str(exc)` (a `DiscordError` message, which
  per the above never contains the token).
- Not unnecessarily cached — confirmed: `_require_token` returns a
  fresh local variable each call; no instance attribute stores it.
- `DiscordModule` never touches the token — confirmed by absence of
  `os.environ`, `DISCORD_TOKEN`, or any import of `os` in
  `discord_module.py`.

`tests/EP041/test_discord_service.py`'s
`_test_token_never_leaks_into_exception_messages` and
`test_discord_module.py`'s `_test_token_never_appears_in_command_result`
independently assert a fixed fake token value never appears in any
exception message or `CommandResult.message` across seven
error scenarios plus the missing-token case; both pass (see Section
8).

Repository-wide search for hard-coded Discord-token-like strings
(`discord`/`Token` near a 20+ character literal) found **no
real-looking secret** anywhere in the codebase. `.env` (the actual,
non-example environment file) contains no Discord-related entry at
all — only unrelated pre-existing UzAutoMotors credentials comments,
untouched by this EP.

One documentation-completeness observation, not a security defect:
`.env.example` lists `TELEGRAM_BOT_TOKEN` and `GITHUB_TOKEN` as
placeholder entries but has no `DISCORD_TOKEN=` placeholder line.
This does not affect functionality (the app reads the real
environment regardless of what `.env.example` documents) and
`.env.example` is not in the STEP 3/4 permitted-file list, so it was
left unmodified — noted here for future documentation completeness
only.

## 5. Configuration

PASS

`config/config.yaml`'s `discord:` section matches exactly:

```yaml
discord:
  enabled: true
  api_base_url: "https://discord.com/api/v10"
  timeout_seconds: 30
```

Confirmed by test and by code:

- `discord.enabled: false` → Bootstrap logs
  `"Discord Service disabled ('discord.enabled: false')."`, sets
  `self._discord_service = None`, and never registers `DiscordModule`
  (`_test_bootstrap_skips_discord_module_when_disabled`, passes).
- `discord.enabled: true` (default) → `DiscordService` is
  constructed and `DiscordModule` registered
  (`_test_bootstrap_registers_discord_module_when_enabled`, passes).
- Invalid `discord.timeout_seconds` (negative or non-numeric) and
  invalid `discord.api_base_url` (empty string) both raise
  `DiscordServiceError` at construction time, caught by Bootstrap's
  `try/except`, logged, and the subsystem disabled for that run
  rather than crashing startup
  (`_test_construction_rejects_invalid_timeout`,
  `_test_construction_rejects_empty_api_base_url`, both pass).
- No secret key exists in the `discord:` section.
- All pre-existing configuration sections (`telegram`, `telegram_info`,
  `github`, `git`, and every other section) are byte-identical to the
  STEP 2 baseline — confirmed via `diff` (Section 10).

## 6. Error Handling

PASS

Verified against the actual `_parse_response`/`_get` implementation,
not just docstrings:

| Condition | Mapped to | Verified in code |
|---|---|---|
| Missing/blank `DISCORD_TOKEN` | `DiscordAuthenticationError` | `_require_token`, raised before any HTTP call |
| HTTP 401 | `DiscordAuthenticationError` | `_parse_response` |
| HTTP 403 | `DiscordAuthenticationError` | `_parse_response` |
| HTTP 404 | `DiscordNotFoundError` | `_parse_response` |
| HTTP 429 | `DiscordRateLimitError` | `_parse_response` |
| Other non-2xx (e.g. 500) | `DiscordAPIError` | `_parse_response` |
| `requests.exceptions.Timeout` | `DiscordTimeoutError` | `_get` except clause |
| `requests.exceptions.ConnectionError` | `DiscordNetworkError` | `_get` except clause |
| Other `requests.exceptions.RequestException` | `DiscordNetworkError` | `_get` except clause |
| Malformed (non-JSON) response body | `DiscordAPIError` | `_parse_response`, catches `ValueError` from `.json()` |

Every mapping is independently exercised by a passing test
(`_test_401_raises_authentication_error` through
`_test_malformed_json_raises_api_error`, `_test_missing_token_raises_and_never_calls_session`,
`_test_blank_token_raises`). No raw `requests` exception or built-in
exception (`KeyError`, `ValueError`, etc.) can leak past
`DiscordService` to a caller — every code path in `_get` and
`_parse_response` either returns a `DiscordResult` or raises a
`DiscordError` subclass. `DiscordModule` catches `DiscordError`
uniformly in every handler, so no exception reaches the CLI layer.
Token non-leakage in error messages confirmed in Section 4.

This follows the EP-039 `GitHubService` pattern (same
`requests.exceptions` mapping shape, same "sole HTTP owner" structure)
where applicable — Discord's own status-code semantics (429
exclusively for rate limits, no 403-as-rate-limit overload the way
GitHub uses it) are correctly reflected in `_parse_response`.

## 7. CLI Boundary

PASS

Confirmed via direct inspection of `DiscordModule.__init__`'s
`_actions` dict (the single, exhaustive dispatch table) and
`HELP_TEXT`:

```
discord guild <guild_id>
discord channels <guild_id>
discord channel <channel_id>
discord member <guild_id> <user_id>
discord message <channel_id> <message_id>
discord help
```

Exactly six keys exist in `_actions`; no alternate dispatch path,
alias, or hidden command exists — `execute()` looks up `action` in
`_actions` and returns "Unknown command" for anything else
(`_test_unknown_action`, tested against `"send"`, passes).

Argument validation confirmed for every action requiring arguments:
`guild`/`channels`/`channel` reject an empty argument list;
`member`/`message` reject fewer than two arguments — each returns
`CommandResult(success=False, ...)` with a descriptive message rather
than raising (four dedicated tests, all pass).

`_test_help_action` asserts `HELP_TEXT` contains only the six
approved commands and explicitly asserts that none of `"send"`,
`"edit"`, `"delete"`, `"create"`, `"ban"`, `"kick"`, `"webhook"`,
`"role"`, `"react"`, `"invite"` appear anywhere in the help output —
passes.

No write operation is reachable through any CLI path: every handler
in `_actions` maps to one of `DiscordService`'s five read-only
methods; there is no method on `DiscordService` that performs a
write, so no dispatch path could reach one even if a hidden alias
existed (and none does).

## 8. Testing

Both EP041 test suites (`test_discord_service.py`,
`test_discord_module.py`, registered under the single `"EP041"`
suite name) were re-run for this audit — not merely inspected.

```
EP041:
Passed:  39
Failed:  0
Skipped: 0
```

Verified by direct inspection (not just test names/comments) that
this coverage is genuine:

- All five operations: dedicated success-path test per operation,
  each asserting both `result.data` content and the exact request
  URL built (`_test_get_guild_success` through
  `_test_get_message_success`).
- Missing token: asserts `DiscordAuthenticationError` **and** that
  zero HTTP calls were attempted (`session.calls` length 0).
- Blank (whitespace-only) token: separately tested.
- HTTP error mapping: 401, 403, 404, 429, 500 each independently
  tested against the real `_parse_response` code path via a stub
  response object, not mocked at a higher level.
- Timeout / network errors: `requests.exceptions.Timeout`,
  `ConnectionError`, and a generic `RequestException` each
  independently raised by the stub session and asserted to map to
  the correct `DiscordError` subclass.
- Malformed JSON: stub response's `.json()` raises `ValueError`,
  asserted to become `DiscordAPIError`.
- URL/path encoding: space and slash characters in `guild_id`/
  `user_id` asserted to appear percent-encoded in the constructed
  URL.
- CLI dispatch: every one of the six commands exercised via
  `module.execute(...)`, plus an unknown-command case.
- Invalid arguments: four dedicated missing-argument tests (guild,
  channel, member, message).
- Help: content assertion plus an explicit forbidden-substring
  assertion (see Section 7).
- Bootstrap behavior: both `discord.enabled: true` and `false` paths
  exercised through a **real** `Bootstrap.initialize()` call against
  a full, valid config fixture (not a mock), asserting
  `bootstrap.discord_service` is or is not `None` accordingly.
- Token non-leakage: exercised twice, once at the service layer
  (seven error scenarios plus missing-token) and once at the module
  layer (`CommandResult.message`), both asserting the fake token
  string is absent.
- Read-only boundary: `_test_help_action`'s forbidden-substring list
  functions as this project's read-only-boundary test, matching the
  STEP 2 design note.

No test trusts a comment or docstring — every assertion inspects an
actual return value, raised exception type, or recorded HTTP call
made against a duck-typed stub, and none makes a real network call
(confirmed: `_StubSession`/`_StubResponse` are the only session
objects constructed anywhere in either test file; no real
`requests.Session()` is ever instantiated in the test suite).

## 9. Regression

All suites were re-run individually for this audit (not `test all`):

```
EP040       : 25 passed / 0 failed / 0 skipped
EP039       : 36 passed / 0 failed / 0 skipped
EP038       : 30 passed / 0 failed / 0 skipped
EP037       : 87 passed / 0 failed / 0 skipped
EP036       : 101 passed / 0 failed / 0 skipped
EP036-STEP2 : 48 passed / 0 failed / 0 skipped
EP036-STEP3 : 53 passed / 0 failed / 0 skipped
EP035       : 143 passed / 0 failed / 0 skipped
EP034       : 113 passed / 0 failed / 0 skipped
EP033       : 182 passed / 0 failed / 0 skipped
EP001       : 20 passed / 0 failed / 0 skipped
```

Every count is identical to the last recorded validation for each
suite (see `CHANGELOG.md`'s `v0.1.7-ep040` entry). No regression was
introduced by EP041 STEP 2/3. `test all` was not run, per instruction.

## 10. EP-040 / Previous EP Integrity

PASS

Confirmed via direct `diff` against the pre-STEP-3 (STEP 2 approved)
baseline, re-verified during this audit:

- **EP-040 source**: `src/core/telegram_info/*`,
  `src/services/telegram_info_service.py`,
  `src/modules/telegram_info_module.py` — byte-identical.
- **EP-040 tests**: `tests/EP040/test_telegram_info_service.py`,
  `tests/EP040/test_telegram_info_module.py` — byte-identical, and
  re-run clean (25/0/0, Section 9).
- **EP-040 audit**: `docs/architecture/audits/EP040_ARCHITECTURE_AUDIT.md`
  — untouched by this EP041 work (not in the STEP 3/4 permitted-file
  list; confirmed unmodified).
- **EP-039 source/tests**: `src/core/github/*`,
  `src/services/github_service.py`, `src/modules/github_module.py`,
  `tests/EP039/*` — byte-identical, and re-run clean (36/0/0).
- **EP-012 Telegram files**: `src/core/telegram/telegram_client.py`,
  `telegram_router.py`, `src/services/telegram_service.py`,
  `src/modules/telegram_module.py` — byte-identical, confirmed via
  `diff` against the originally uploaded archive.
- **EP-031 Tool Engine files**: `src/core/tool/*`
  (`tool.py`, `tool_engine.py`, `tool_manager.py`, `tool_provider.py`,
  `tool_execution_provider.py`, `tool_registry.py`, `tool_result.py`),
  `src/services/tool_service.py`, `src/modules/tool_module.py` — all
  byte-identical, confirmed via `diff`.

A full `diff -r` of `src/` and `tests/` between the originally
uploaded archive and the current state (excluding `__pycache__`)
returned **zero differences**. `config/config.yaml` and
`requirements.txt` are byte-identical.

## 11. EP-031 Tool Engine Boundary

PASS

Repository-wide search for `Tool(`, `ToolManager`, `ToolRegistry` in
combination with `DiscordService` found no registration —
`DiscordService` is never passed to, imported by, or referenced from
`src/core/tool/`, `src/services/tool_service.py`, or
`src/modules/tool_module.py`. `discord_service.py` and
`discord_module.py` do not import anything from `src.core.tool` or
`src.services.tool_service`.

This is the deliberate, documented scope decision (matching
EP-039/EP-040's own deferred Tool Engine registration) and is **not**
treated as architecture debt.

## 12. Future Discord Gateway Boundary

PASS

Confirmed by inspection: `DiscordService` holds no persistent
connection object, no event loop, no WebSocket client, no
message-cursor/offset attribute, and starts no background thread at
construction (`__init__` only resolves config and builds a
`requests.Session`). Every one of its five public methods is a
single synchronous `requests.get(...)` call that returns or raises
before the method returns — no long-lived state is created or
mutated between calls. No inbound Discord message handling exists
anywhere in this subsystem (there is no code path that receives an
unsolicited Discord event). This matches the design's stated
intent that a future Discord Gateway EP could be added later without
sharing state with, or being blocked by, this subsystem.

## 13. Duplicate Implementation Check

PASS

Repository-wide search for `DiscordService`, `DiscordModule`,
`discord_info`, `discord_service`, `discord_module`, and Discord-URL
literals found exactly one implementation of each:
`src/services/discord_service.py` (one `DiscordService` class),
`src/modules/discord_module.py` (one `DiscordModule` class),
`src/core/discord/` (one Core package). No `discord_info` variant
exists (unlike the EP-012/EP-040 Telegram split, Discord had no
pre-existing subsystem to duplicate against). No second
`requests.get(...)` call against a Discord URL exists anywhere in the
codebase outside `discord_service.py`.

## 14. Documentation Consistency

PASS

Cross-checked `docs/architecture/designs/EP041_DESIGN.md`,
`docs/RELEASE_NOTES.md`, `CHANGELOG.md`, and `docs/BACKLOG.md`
against the actual implementation:

- **Five operations**: design, release notes, and changelog all list
  exactly `get_guild`, `list_guild_channels`, `get_channel`,
  `get_guild_member`, `get_message` — matches `DiscordService`'s
  public API exactly (Section 2).
- **Read-only scope**: all four documents state no write/moderation
  operation exists — matches (Section 2).
- **REST API v10**: all four documents specify
  `https://discord.com/api/v10` — matches
  `_DEFAULT_API_BASE_URL` and `config/config.yaml`.
- **DISCORD_TOKEN**: all four documents describe environment-only,
  per-call resolution, never in config — matches
  `_require_token`/`_TOKEN_ENV_VAR` (Section 4).
- **No Gateway**: all four documents state no
  Gateway/WebSocket connection is opened — matches (Section 3, 12).
- **No message history**: all four documents explicitly flag this as
  a deliberate exclusion, not a limitation of the API — matches
  (Section 2).
- **No Tool Engine registration**: `docs/RELEASE_NOTES.md`'s "Tool
  Engine boundary" section and `CHANGELOG.md`'s "Known limitations"
  both state this — matches (Section 11).
- `docs/RELEASE_NOTES.md`'s CLI block and `docs/BACKLOG.md`'s scope
  summary were directly diffed against `DiscordModule.HELP_TEXT` at
  runtime — byte-for-byte identical command list (verified by
  importing the module and printing `HELP_TEXT`).
- `docs/architecture/JARVIS_ROADMAP.md` correctly shows EP-040 marked
  complete (`✓`) and EP-041 as the unmarked "Current" entry, matching
  `docs/BACKLOG.md`'s STEP 1-3-complete/STEP-4-pending status.

No discrepancy was found between what any of the five documentation
files claims and what the code actually does.

## 15. Architecture Debt

None.

`docs/architecture/ARCHITECTURE_DEBT.md`,
`docs/architecture/ARCHITECTURE_DECISIONS.md`, and
`docs/architecture/JARVIS_ARCHITECTURE_VISION.md` were inspected; none
currently reference Discord (consistent with EP-039/EP-040, which are
also absent from `ARCHITECTURE_DEBT.md`). No genuine architectural
defect was found in EP041's implementation. The following are
confirmed deliberate scope decisions, not debt, per the STEP 4
instruction: absence of message history, absence of a Gateway
connection, absence of write operations, absence of Tool Engine
registration, and no new third-party Discord library. Unlike EP-035's
`AD-004` (an unreachable exception handler), EP-041's
`DiscordServiceError` handler in Bootstrap **is** reachable — invalid
`discord.api_base_url`/`discord.timeout_seconds` genuinely raise it
from `DiscordService.__init__`, confirmed by
`_test_construction_rejects_invalid_timeout` and
`_test_construction_rejects_empty_api_base_url` (both pass) — so no
analogous debt item applies here.

One non-debt observation carried over from Section 4: `.env.example`
has no `DISCORD_TOKEN=` placeholder line (unlike `GITHUB_TOKEN` and
`TELEGRAM_BOT_TOKEN`, which do have one). This is a minor
documentation-completeness gap, not a security or architecture
defect, and `.env.example` was left unmodified as it is outside the
STEP 3/4 permitted-file list.

## 16. Runtime Artifacts

PASS

`__pycache__/` directories and `logs/*.log` files exist in the
repository tree, but a `diff` against the originally uploaded archive
confirms all of them were already present before this audit began —
none were created or modified by STEP 4's inspection or test run.
Running the EP041 and regression test suites during this audit
produced no new file anywhere in the repository — reconfirmed via a
full `diff -r` of `src/` and `tests/` (excluding `__pycache__`)
immediately after the test run, which returned zero differences from
the pre-test-run state.

## 17. Files Modified

NEW:
- docs/architecture/audits/EP041_ARCHITECTURE_AUDIT.md

MODIFIED:
- None

## 18. Final Verdict

EP041 STEP 4 — PASS
