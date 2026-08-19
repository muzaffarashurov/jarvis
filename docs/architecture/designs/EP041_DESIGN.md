# EP041 — Design

Status: STEP 1-4 complete. Implemented, documented, and audited --
see `docs/architecture/audits/EP041_ARCHITECTURE_AUDIT.md` (Final
Verdict: EP041 STEP 4 -- PASS). This document reflects the design as
approved at STEP 1 and confirmed unchanged by the actual STEP 2
implementation and STEP 4 audit.

Scope confirmed directly by the project owner (see conversation record); this
document designs against that confirmed scope rather than re-deriving it from
ambiguous repository evidence. Follows `EP038_DESIGN.md`/`EP039_DESIGN.md`/
`EP040_DESIGN.md`'s structure and terminology, since Discord Integration is
the direct architectural sibling of Git/GitHub/Telegram Integration, next in
Phase 6 (Integrations).

---

## Problem

Jarvis has no way to read information from Discord -- server (guild),
channel, member, or message metadata. Before this EP, no Discord-related
implementation, dependency, or configuration existed anywhere in the
codebase (confirmed by a repository-wide search during STEP 1
investigation).

## Existing State

- No Discord client, service, module, config, or test exists anywhere in
  the repository. No Discord-related dependency (`discord.py`, `py-cord`,
  `hikari`, `aiohttp`, or otherwise) is present in `requirements.txt`.
  Unlike EP-039 (which reused the already-installed `requests`) and EP-040
  (which reused the already-installed `python-telegram-bot`, itself
  already used by EP-012), Discord had no existing dependency to reuse --
  this design uses the project's existing `requests` dependency directly
  against Discord's REST API, per your explicit instruction, adding no new
  dependency.
- `docs/architecture/JARVIS_ARCHITECTURE_VISION.md`'s "Tools" example list
  (`Git`, `GitHub`, `Docker`, `Python`, `FFmpeg`, `Google Drive`, `Google
  Sheets`) does not mention Discord at all -- a weaker evidentiary anchor
  than Git/GitHub/Telegram had, which is why STEP 1 stopped for explicit
  scope confirmation before this document was written.
- No EP-012-style Discord Gateway/inbound-control mechanism exists in this
  codebase (unlike Telegram, where EP-012 already existed before EP-040).
  This EP is the first Discord-related work of any kind in this project.

## Desired State

A new, independent `DiscordService` exposes a small set of read-only
operations against the Discord REST API (v10), using the project's
existing `requests` dependency directly, authenticated via the
`DISCORD_TOKEN` environment variable. A `discord` CLI namespace exposes
the same operations. No Gateway/WebSocket connection, no write/mutating
operation, and no new dependency anywhere in this design.

## Confirmed Scope

### API capability investigation (per your anti-guessing instruction)

Before finalizing the operation list, the actual Discord REST API v10
(bot-token-authenticated, stateless HTTP) was checked against each
requested operation:

| Requested | Discord REST API v10 endpoint | Verdict |
|---|---|---|
| `get_guild(guild_id)` | `GET /guilds/{guild.id}` | Supported -- stateless, single-shot |
| `list_guild_channels(guild_id)` | `GET /guilds/{guild.id}/channels` | Supported -- stateless, single-shot |
| `get_channel(channel_id)` | `GET /channels/{channel.id}` | Supported -- stateless, single-shot |
| `list_channel_members(guild_id, channel_id)` | **No such endpoint exists** | **Not supported -- see below** |
| `get_message(channel_id, message_id)` | `GET /channels/{channel.id}/messages/{message.id}` | Supported -- stateless, single-shot (requires `READ_MESSAGE_HISTORY` permission in that channel) |

**`list_channel_members` is not a concept the Discord REST API exposes.**
Discord channels do not have their own membership roster -- channel
access is computed from guild membership plus role/channel permission
overwrites, not a per-channel member list. The closest real capability is
`GET /guilds/{guild.id}/members/{user.id}` (Get Guild Member) -- a
single, already-known user's membership info (nickname, roles,
`joined_at`, ...) within a guild. This maps directly onto your own CLI
section's `discord member <guild_id> <user_id>` (note the
`guild_id`/`user_id` argument shape, not `guild_id`/`channel_id`), and
onto your own hedge on this operation ("ONLY if directly supported by the
chosen API approach"). Per your instruction 7 ("STOP and report the exact
limitation instead of replacing it with Gateway/WebSocket, a user account
API, or another library"), this is reported here rather than silently
worked around with a different API tier: **the final operation is
`get_guild_member(guild_id, user_id)`, not `list_channel_members(guild_id,
channel_id)`** -- the same REST/bot-token approach, just the actual
supported shape of the one operation you already conditionally scoped.

**A separate, important finding requiring your attention, not acted on
here**: unlike Telegram's Bot API (which has no message-history endpoint
at all), Discord's REST API *does* support bulk historical message
retrieval statelessly -- `GET /channels/{channel.id}/messages` (with
`limit`/`before`/`after` query parameters), no Gateway/WebSocket
required. Your scope instruction excluded "message history / bulk
message retrieval unless the selected API supports it cleanly without
Gateway state" -- it does. This document does **not** add it to the
confirmed scope (per "do not silently expand scope"), but flags it as a
capability you may want to explicitly approve for a later step, since it
is technically available.

Fetching a single already-known guild member (`get_guild_member`) does
**not** require Discord's privileged `GUILD_MEMBERS` intent -- that
privileged-intent restriction applies to the Gateway member-stream and to
the bulk "List"/"Search" Guild Members REST endpoints, not to a
single-member-by-id lookup. No privileged intent request is needed for
this design.

### Final confirmed operations (read-only only)

1. `get_guild(guild_id)`
2. `list_guild_channels(guild_id)`
3. `get_channel(channel_id)`
4. `get_guild_member(guild_id, user_id)` (renamed from `list_channel_members`, see above)
5. `get_message(channel_id, message_id)`

## Explicit Non-Goals

None of the following exist anywhere in this design:

- Bulk/history message retrieval (`GET /channels/{channel.id}/messages`)
  -- technically available without Gateway state (see finding above), but
  not included without your explicit further approval.
- Any channel-scoped member listing -- not a Discord API concept (see
  above).
- Send, edit, or delete a message.
- Create, update, or delete a channel, guild, or role.
- Any moderation action (kick, ban, timeout, ...).
- Webhooks (creation or invocation).
- Role management or assignment.
- Reactions (add/remove).
- Invites (creation or lookup).
- Any Discord Gateway/WebSocket connection of any kind.
- Any new third-party dependency (`discord.py`, `py-cord`, `hikari`,
  `aiohttp`, or otherwise).
- Any modification to EP-031 Tool Engine.

## Architecture

```
Core                    src/core/discord/discord_result.py, discord_error.py
  |                      (pure data: DiscordResult, DiscordError hierarchy
  |                       -- no HTTP call here, matching GitHubResult/
  |                       GitHubError's split in EP-039)
  v
Service                 src/services/discord_service.py
  |                      (owns the one HTTP-invocation strategy; resolves
  |                       'discord.*' config and DISCORD_TOKEN; the only
  |                       component that ever calls requests.get(...))
  v
Module                  src/modules/discord_module.py
  |                      ("discord" CLI namespace; thin CommandResult
  |                       translation layer only, exactly like GitHubModule)
  v
Bootstrap               src/bootstrap.py
  |                      (constructs DiscordService, registers
  |                       DiscordModule, gated by 'discord.enabled',
  |                       try/except around config validation --
  |                       mirrors the EP-039/040 blocks)
  v
Config                  config/config.yaml ('discord' section, no secret)
```

Naming avoids any collision with any other subsystem: `Discord*`/
`discord_*` symbols, `src/core/discord/` as a sibling of
`src/core/github/`/`src/core/telegram_info/`.

**EventBus**: not used, for the same reason EP-038/039/040 didn't use it
-- a one-shot, synchronous, stateless HTTP lookup has no
completion-notification concept for another component to react to.

**Tool Engine (EP-031)**: not modified. `DiscordService`'s five
side-effect-free methods are clean future `Tool` candidates, exactly like
`GitService`'s/`GitHubService`'s/`TelegramInfoService`'s methods. No
`Tool` entry, import, or reference is added anywhere.

## Components

### `src/core/discord/discord_result.py`

```python
@dataclass(frozen=True)
class DiscordResult:
    operation: str        # e.g. "get_guild", for logging/debugging
    status_code: int
    data: dict             # parsed JSON body -- raw passthrough, no
                            # further structure imposed, matching
                            # GitHubResult's philosophy
```

### `src/core/discord/discord_error.py`

```python
class DiscordError(Exception):
    """Base class for every Discord Integration exception."""

class DiscordAuthenticationError(DiscordError):
    """DISCORD_TOKEN is missing/blank, or Discord rejected it/denied
    access (HTTP 401 or 403)."""

class DiscordNotFoundError(DiscordError):
    """The requested guild/channel/member/message does not exist, or
    the bot cannot see it (HTTP 404)."""

class DiscordRateLimitError(DiscordError):
    """Discord's rate limit was exceeded (HTTP 429)."""

class DiscordTimeoutError(DiscordError):
    """The request exceeded 'discord.timeout_seconds'."""

class DiscordNetworkError(DiscordError):
    """A connection-level failure occurred."""

class DiscordAPIError(DiscordError):
    """Discord returned any other non-2xx status, or an unparseable
    response body."""
```

A flat hierarchy per this project's convention, modeled directly on
`GitHubError`'s split (both subsystems use `requests` directly, unlike
EP-040's library-specific exception mapping). Discord does not overload
HTTP 403 for rate-limiting the way GitHub does -- Discord uses 429
exclusively for rate limits, so the mapping is simpler than GitHub's: 401
and 403 both map to `DiscordAuthenticationError` (bad token vs. forbidden
access respectively), with no rate-limit-header disambiguation needed.

`DiscordServiceError` (raised only for invalid `discord.*` configuration,
at `DiscordService.__init__` time) is defined in
`src/services/discord_service.py`, not in `discord_error.py`, mirroring
`GitHubServiceError`/`GitServiceError`/`TelegramInfoServiceError`'s split
from their respective error hierarchies.

### `src/services/discord_service.py`

```python
class DiscordService:
    def __init__(
        self,
        config: Config,
        session: "requests.Session | None" = None,
    ) -> None: ...

    def get_guild(self, guild_id: str) -> DiscordResult: ...
    def list_guild_channels(self, guild_id: str) -> DiscordResult: ...
    def get_channel(self, channel_id: str) -> DiscordResult: ...
    def get_guild_member(self, guild_id: str, user_id: str) -> DiscordResult: ...
    def get_message(self, channel_id: str, message_id: str) -> DiscordResult: ...
```

Design notes, directly mirroring EP-039's established pattern:

- **`DISCORD_TOKEN` is read via `os.environ.get("DISCORD_TOKEN")` at the
  start of every operation call** (via a shared `_require_token()`
  helper), never at `__init__`, never cached beyond the duration of a
  single call. Missing/blank token raises `DiscordAuthenticationError`
  immediately, before any HTTP call is attempted -- identical pattern to
  `GitHubService`, and consistent with your instruction ("read at call
  time or the safest equivalent pattern consistent with EP039").
- **`session` is an injectable, optional `requests.Session`-like
  parameter**, defaulting to a real `requests.Session()`, enabling
  dependency-free test doubles -- identical to `GitHubService`.
- Every method builds a full URL from `discord.api_base_url` + a fixed
  path template, with `guild_id`/`channel_id`/`user_id`/`message_id`
  URL-quoted (`urllib.parse.quote`) before interpolation -- the same
  defensive construction `GitHubService` already uses.
- The `Authorization` header uses Discord's own scheme: `Bot <token>`
  (distinct from GitHub's `token <token>` and Telegram's Bot-object
  construction pattern).
- No retry, no caching, no pagination handling -- cohesive and minimal,
  matching every prior integration EP's restraint.

### `src/modules/discord_module.py`

```python
class DiscordModule:
    def __init__(self, discord_service: DiscordService) -> None: ...

    @property
    def name(self) -> str: return "discord"

    def execute(self, action: str, arguments: list[str]) -> CommandResult: ...
```

Actions: `guild <guild_id>`, `channels <guild_id>`, `channel <channel_id>`,
`member <guild_id> <user_id>`, `message <channel_id> <message_id>`, `help`.
Pure translation layer: calls `DiscordService`'s existing public methods
unchanged and catches `DiscordError` to format
`CommandResult(success=False, message=str(exc))`, matching `GitHubModule`
exactly. Never imports `requests`, never reads `DISCORD_TOKEN`.

## Public APIs

| Method | Parameters | Discord endpoint | Raises |
|---|---|---|---|
| `get_guild(guild_id)` | required | `GET /guilds/{guild_id}` | `DiscordAuthenticationError`, `DiscordNotFoundError`, `DiscordRateLimitError`, `DiscordTimeoutError`, `DiscordNetworkError`, `DiscordAPIError` |
| `list_guild_channels(guild_id)` | required | `GET /guilds/{guild_id}/channels` | same set |
| `get_channel(channel_id)` | required | `GET /channels/{channel_id}` | same set |
| `get_guild_member(guild_id, user_id)` | both required | `GET /guilds/{guild_id}/members/{user_id}` | same set |
| `get_message(channel_id, message_id)` | both required | `GET /channels/{channel_id}/messages/{message_id}` | same set |

## Configuration

New `discord` section:

```yaml
discord:
  enabled: true
  api_base_url: "https://discord.com/api/v10"
  timeout_seconds: 30
```

- `enabled` defaults to `true`, matching every other soft-toggle
  subsystem.
- `api_base_url` defaults to Discord's current REST API version root;
  present as a plain override point (Discord does periodically version
  its API), validated non-empty at construction.
- `timeout_seconds` defaults to `30`, matching `github.timeout_seconds`'s
  reasoning (a remote HTTP round-trip, not a local subprocess call).
- **`DISCORD_TOKEN` is never read from, written to, or validated against
  `config/config.yaml` anywhere in this design.** It exists only as an
  environment variable.
- Disabled behavior: identical to every prior integration EP -- when
  `discord.enabled` is `false`, Bootstrap never constructs
  `DiscordService` and never registers `DiscordModule`; `discord
  <anything>` falls through to "Unknown command."

## CLI

Namespace: `discord`

| Command | Arguments | Success | Error |
|---|---|---|---|
| `discord guild` | `<guild_id>` | Guild JSON summary | `DiscordError` message, or "requires a guild_id" if omitted |
| `discord channels` | `<guild_id>` | List of channel objects | `DiscordError` message, or "requires a guild_id" |
| `discord channel` | `<channel_id>` | Channel JSON summary | `DiscordError` message, or "requires a channel_id" |
| `discord member` | `<guild_id> <user_id>` | Guild member JSON summary | `DiscordError` message, or "requires guild_id and user_id" |
| `discord message` | `<channel_id> <message_id>` | Message JSON summary | `DiscordError` message, or "requires channel_id and message_id" |
| `discord help` | none | Static help text listing only the five read commands above | n/a |

No `send`/`edit`/`delete`/`create`/`ban`/`kick`/`webhook`/`role`/`react`/
`invite` command exists anywhere in `DiscordModule`'s dispatch table --
not merely unadvertised, absent from the code entirely.

## Authentication / Security

- `DISCORD_TOKEN` is read fresh via `os.environ.get()` inside
  `DiscordService` at the start of every call, never cached beyond that
  call, never logged.
- Sent only as the `Authorization: Bot <token>` request header; never
  included in a `CommandResult` message, log line, or exception message
  -- every error message in this design is built from fixed text and/or
  the HTTP response's status code, never the token value.
- `DiscordModule` never reads or handles the token at all -- no code path
  in that file could leak it.
- No new secret is introduced; the token is never placed in
  `config/config.yaml`.
- No write/mutating capability exists, so no human-confirmation
  requirement applies.
- `guild_id`/`channel_id`/`user_id`/`message_id` are URL-quoted before
  being interpolated into the request path -- the same defensive
  construction `GitHubService` already uses for its own path segments.

## Error Handling

| Failure | Exception | CLI-visible message |
|---|---|---|
| `DISCORD_TOKEN` unset/blank | `DiscordAuthenticationError` | "DISCORD_TOKEN environment variable is not set." |
| HTTP 401 (bad token) | `DiscordAuthenticationError` | "Discord rejected the configured token." |
| HTTP 403 (forbidden/missing access) | `DiscordAuthenticationError` | "Discord denied access to this resource." |
| HTTP 404 | `DiscordNotFoundError` | "Discord resource not found." |
| HTTP 429 | `DiscordRateLimitError` | "Discord API rate limit exceeded." |
| `requests.exceptions.Timeout` | `DiscordTimeoutError` | "Discord request timed out after Ns." |
| `requests.exceptions.ConnectionError` | `DiscordNetworkError` | "Could not reach the Discord API." |
| Any other non-2xx, or unparseable JSON | `DiscordAPIError` | "Discord request failed (HTTP &lt;code&gt;)." / "Discord returned an invalid response body." |
| Invalid `discord.*` configuration at construction | `DiscordServiceError` | (Bootstrap-level: subsystem disabled, logged) |

`DiscordModule` catches `DiscordError` (the common base of the first
seven) and formats it as `CommandResult(success=False, ...)`, identical
to `GitHubModule`'s pattern.

## Testing Strategy

New suite: `tests/EP041/test_discord_service.py` +
`tests/EP041/test_discord_module.py`, one shared `"EP041"` suite,
following EP-039's exact testing pattern (the most directly applicable
precedent, since both subsystems use `requests` directly).

**Isolation strategy**: no real Discord API call is ever made. Every test
constructs `DiscordService` with a small, duck-typed stub `session`
object in place of a real `requests.Session` -- the same
`_StubSession`/`_StubResponse` technique already used in
`tests/EP039/test_github_service.py`. `DISCORD_TOKEN` is set to a fixed
fake value around tests that need it present, and explicitly unset for
the missing-token test, mirroring EP-039's pattern.

Planned assertions:
- Each of the five operations, given a stub session returning a
  realistic-shaped 200 JSON body, returns a `DiscordResult` with the
  right `status_code`/`data`.
- Missing/blank `DISCORD_TOKEN` -> `DiscordAuthenticationError`, and the
  stub session's `.get()` is never called.
- Stub response 401 -> `DiscordAuthenticationError`; 403 ->
  `DiscordAuthenticationError`; 404 -> `DiscordNotFoundError`; 429 ->
  `DiscordRateLimitError`; 500 -> `DiscordAPIError`.
- Stub session raising `requests.exceptions.Timeout` ->
  `DiscordTimeoutError`; raising `requests.exceptions.ConnectionError` ->
  `DiscordNetworkError`.
- Malformed (non-JSON) response body -> `DiscordAPIError`, not a raw
  `ValueError`/`JSONDecodeError`.
- Constructing `DiscordService` with an invalid `timeout_seconds` or
  empty `api_base_url` raises `DiscordServiceError`.
- `DiscordModule`: each action dispatches to the right `DiscordService`
  method with the right arguments; missing arguments return a CLI-level
  error, not a crash; an unknown action returns the same "Unknown
  command" shape every other module uses.
- `discord.enabled=False` -> Bootstrap never registers `DiscordModule`.
- A dedicated test asserting a fixed fake token value never appears in
  any exception message across all seven error scenarios.
- A read-only-boundary test asserting none of "send"/"edit"/"delete"/
  "create"/"ban"/"kick"/"webhook"/"role"/"react"/"invite" appear in the
  `help` output.

Regression suites to still pass unchanged: `EP040`, `EP039`, `EP038`,
`EP037`, `EP036`, `EP036-STEP2`, `EP036-STEP3`, `EP035`, `EP034`,
`EP033`, `EP001`.

## Regression Safety

No dependency on any other Engineering Package's service or engine --
`DiscordService` depends only on `Config` and, at call time, the process
environment, identical in shape to `GitService`/`GitHubService`/
`TelegramInfoService`. No existing file is modified except `bootstrap.py`,
`config/config.yaml`, and `src/modules/test_module.py`, following the
exact same minimal-footprint pattern every prior integration EP used.
`requirements.txt` is unchanged.

## Risks and Limitations

- **`list_channel_members` was not implementable as literally named** --
  resolved by substituting the actual supported operation
  (`get_guild_member`), reported explicitly above rather than silently
  reinterpreted.
- **Bulk message history is technically available but not included** --
  flagged above as a capability you may want to explicitly approve later;
  not acted on without further confirmation, per "do not silently expand
  scope."
- **No pagination** for `list_guild_channels` (Discord returns the full
  channel list in one response for this endpoint, so this is moot for
  that operation specifically, but worth noting `get_guild_member`/
  `get_message`/`get_channel`/`get_guild` are all single-resource lookups
  with no list-pagination concern either).
- **Rate limiting**: Discord's per-route rate limits are stricter and
  more granular than GitHub's; this design surfaces `DiscordRateLimitError`
  clearly but implements no backoff/retry, consistent with
  `GitService`/`GitHubService`/`TelegramInfoService`'s shared restraint.
- **Alternative considered**: a Discord wrapper library (`discord.py`,
  `py-cord`, `hikari`). Rejected per explicit scope constraint, and
  because `requests` already has two proven, reusable patterns in this
  codebase (`claude_provider.py`, `github_service.py`) that a new
  library would duplicate rather than complement.
- **Compatibility risk**: none identified -- wholly new, additive
  subsystem with no existing caller and no cross-EP dependency.

## EP-031 Tool Engine Boundary

Not modified. `DiscordService`'s five side-effect-free methods are clean
future `Tool` candidates by construction, exactly matching the conclusion
already reached for `GitService`/`GitHubService`/`TelegramInfoService`.
No `Tool` entry, import, or reference is added anywhere in this design.

## Future Discord Gateway Boundary

This design is built so a future inbound Discord Gateway/WebSocket EP
(an EP-012-style control mechanism, should one ever be proposed) could
coexist without shared state or hidden coupling, mirroring exactly how
EP-040 was designed relative to EP-012:

- `DiscordService` holds no persistent connection, no event loop, no
  background thread, and no consumable cursor/offset of any kind -- each
  method is a single, stateless HTTP request. A future Gateway EP would
  own its own WebSocket connection entirely independently; there is no
  shared resource for the two to race over (unlike Telegram's
  `getUpdates` offset, Discord's Gateway uses a persistent session/resume
  token, not a REST-polling cursor -- structurally, there is nothing in
  this design analogous to what EP-040 had to avoid sharing).
- Naming (`Discord*`/`discord_*` under `src/core/discord/`) leaves the
  namespace open for a future `discord_gateway`-style sibling package,
  the same way `src/core/telegram_info/` sits alongside
  `src/core/telegram/` without collision.
- The `discord.token` reuse pattern (env-var-only) is documented clearly
  enough that a future Gateway EP could either reuse the same
  `DISCORD_TOKEN` variable (bot tokens are typically shared across a
  single application's REST and Gateway usage) or introduce its own,
  without this design assuming either choice.

## Exact STEP 2 File Plan

### Created
```
src/core/discord/__init__.py
src/core/discord/discord_result.py
src/core/discord/discord_error.py
src/services/discord_service.py
src/modules/discord_module.py
tests/EP041/__init__.py
tests/EP041/test_discord_service.py
tests/EP041/test_discord_module.py
```

### Modified
```
src/bootstrap.py            (construct DiscordService, register DiscordModule, discord_service property)
config/config.yaml           ('discord' section: enabled, api_base_url, timeout_seconds -- no token)
src/modules/test_module.py   (register EP041 test suite)
```

### Explicitly protected / untouched
```
src/core/tool/                              (EP-031)
src/core/telegram/, src/services/telegram_service.py, src/modules/telegram_module.py  (EP-012)
src/core/telegram_info/, src/services/telegram_info_service.py, src/modules/telegram_info_module.py  (EP-040)
src/core/github/, src/services/github_service.py, src/modules/github_module.py  (EP-039)
src/core/git/, src/services/git_service.py, src/modules/git_module.py  (EP-038)
requirements.txt                            (no new dependency)
tests/EP033/, EP034/, EP035/, EP036/, EP037/, EP038/, EP039/, EP040/
```

## STEP 2 Implementation Plan

```
STEP 2.1 — src/core/discord/discord_result.py, discord_error.py:
            DiscordResult dataclass, DiscordError hierarchy
            (DiscordAuthenticationError, DiscordNotFoundError,
            DiscordRateLimitError, DiscordTimeoutError,
            DiscordNetworkError, DiscordAPIError).

STEP 2.2 — src/services/discord_service.py: DiscordService with
            get_guild/list_guild_channels/get_channel/get_guild_member/
            get_message, config resolution + validation
            (DiscordServiceError), per-call DISCORD_TOKEN resolution,
            requests.get(..., timeout=...) as the sole invocation point,
            URL-quoted path segments.
            Tests: tests/EP041/test_discord_service.py against a stub
            requests.Session.

STEP 2.3 — src/modules/discord_module.py: "discord" CLI namespace, thin
            CommandResult translation, HELP_TEXT matching
            git/github/telegram-info style.
            Tests: tests/EP041/test_discord_module.py.

STEP 2.4 — config/config.yaml: new 'discord' section (enabled,
            api_base_url, timeout_seconds), commented in the same style
            as the existing 'github'/'telegram_info' sections.

STEP 2.5 — src/bootstrap.py: construct DiscordService, register
            DiscordModule, try/except (DiscordServiceError) -> log +
            disable, matching the GitHubService/TelegramInfoService
            wiring template exactly.

STEP 2.6 — src/modules/test_module.py: register the EP041 suite.

STEP 2.7 — Individual validation: test EP041, plus the full
            EP033-040 + EP001 regression set. Do not require test all.
```
