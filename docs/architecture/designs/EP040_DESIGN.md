# EP040 — Design

Status: STEP 1 (Design / Investigation) -- not yet implemented.

Scope confirmed directly by the project owner across two clarification rounds
(see conversation record); this document designs against that confirmed,
narrowed scope rather than re-deriving it from ambiguous repository evidence.
Follows `EP038_DESIGN.md`/`EP039_DESIGN.md`'s structure and terminology.

---

## Problem

Jarvis has no way to look up metadata for a known Telegram chat/channel
(title, type, description, member count, etc.) independent of EP-012's
Telegram Gateway, which is an inbound *control* mechanism (a human messages
Jarvis, Jarvis executes a command, a reply is sent back) with no read/lookup
capability of its own.

## Existing State

- **EP-012 "Telegram Gateway"** already exists and is fully wired
  (`src/core/telegram/telegram_client.py`, `telegram_router.py`,
  `src/services/telegram_service.py`, `src/modules/telegram_module.py`,
  681 lines total, registered in `src/bootstrap.py`). It is an *inbound*
  control gateway: `TelegramClient.fetch_updates()` polls Telegram's
  `getUpdates` Bot API method on a dedicated background thread
  (`TelegramService._poll_loop`/`_poll_once`, started via `telegram.auto_start`
  or the `telegram start` CLI command), routes each incoming message through
  `TelegramRouter` (chat-id allow-list check) into the same `CommandRouter`
  the interactive shell uses, and sends the result back via
  `TelegramClient.send_message`. **This design does not touch any of it.**
- `TelegramClient.fetch_updates()` is **stateful and consuming**: it passes
  `offset=self._update_offset` to `getUpdates` and then advances
  `self._update_offset = update_id + 1`. Telegram's own semantics: passing
  an offset confirms receipt of everything before it, so those updates are
  never redelivered. **This is the concrete, evidenced reason EP-040 cannot
  reuse `fetch_updates()` or share any offset/cursor with EP-012** -- doing
  so would race against EP-012's own live polling thread over the same
  consumable queue.
- `python-telegram-bot` 22.8 is already an installed, approved dependency
  (used by EP-012). Direct inspection of its `Bot` class confirms:
  - `get_chat(chat_id)` exists -- a stateless, read-only, single-known-chat
    lookup. This is the **only** requested EP-040 capability the Bot API
    actually supports.
  - No bulk/list-chats method exists anywhere in the Bot API.
  - No general chat-history-retrieval method exists anywhere in the Bot API
    (the only other message-retrieval method, `get_user_personal_chat_messages`,
    is a narrow, unrelated Business-Connection feature).
  - These two absences are *library/API limitations*, not Jarvis design
    choices, and are why "recent messages," "message history," and
    "chat/channel discovery" were explicitly dropped from EP-040's scope in
    the second clarification round.
- `config/config.yaml`'s existing `telegram` section (`enabled`,
  `auto_start`, `token`, `allowed_chat_ids`, `polling_interval`) is
  commented `# EP-012 Telegram Gateway`. `telegram.token` is the value
  EP-040 will read (never duplicated into a second key).

## Desired State

A new, independent `TelegramInfoService` exposes exactly one read-only
operation -- `get_chat(chat_id)` -- against the Telegram Bot API, using a
**second, independent `telegram.Bot` instance** (not `TelegramClient`),
authenticated with the same `telegram.token` value EP-012 already uses. A
`telegram-info` CLI namespace exposes this single operation. No polling, no
`getUpdates` call, no shared state or cursor with EP-012 anywhere in this
design.

## Scope

Included:
- `get_chat(chat_id)` -- chat/channel metadata for an already-known chat id.
- `telegram-info` CLI namespace: `telegram-info chat <chat_id>`, `help`.
- Reuse of the existing `telegram.token` config value (read-only, not
  duplicated).
- A new, independent `telegram_info.enabled` config toggle (no secret).
- Bootstrap wiring, following the EP-038/039 pattern.
- Tool-Engine-readiness by construction; no EP-031 file touched.

## Non-goals

Explicitly out of scope (per the two confirmed clarification rounds) --
none of the following exist anywhere in this design:
- Reading recent/new messages via `getUpdates` (would race EP-012's live
  polling cursor -- confirmed real conflict, not a style choice).
- Message history retrieval (no such Bot API method exists).
- Listing/discovering chats the bot is a member of (no such Bot API method
  exists).
- Any write/mutating Telegram operation (send/edit/delete message, join/
  leave/create chat, manage users, any administrative action).
- Any modification to EP-012 (`src/core/telegram/`,
  `src/services/telegram_service.py`, `src/modules/telegram_module.py`) --
  all three remain byte-for-byte untouched.
- Any new third-party dependency -- `python-telegram-bot` (already
  installed) is reused directly; no Telethon, Pyrogram, or other
  MTProto/User-API library, which would be required to implement the
  dropped history/discovery capabilities and is explicitly not approved.

## Architecture

```
Core                    src/core/telegram_info/telegram_info_result.py, telegram_info_error.py
  |                      (pure data: TelegramInfoResult, TelegramInfoError
  |                       hierarchy -- no Bot API call here, matching
  |                       GitHubResult/GitHubError's split in EP-039)
  v
Service                 src/services/telegram_info_service.py
  |                      (owns the one Bot API invocation; constructs its
  |                       own independent telegram.Bot instance; the only
  |                       component that ever calls Bot.get_chat(...))
  v
Module                  src/modules/telegram_info_module.py
  |                      ("telegram-info" CLI namespace; thin CommandResult
  |                       translation layer only, exactly like GitHubModule)
  v
Bootstrap               src/bootstrap.py
  |                      (constructs TelegramInfoService, registers
  |                       TelegramInfoModule, gated by
  |                       'telegram_info.enabled', try/except around
  |                       config validation -- mirrors the EP-039 block)
  v
Config                  config/config.yaml ('telegram_info' section, no
                         secret; reads 'telegram.token' read-only)
```

Naming deliberately avoids any collision with EP-012's `telegram`/
`TelegramClient`/`TelegramService`/`TelegramModule` symbols: every new
symbol is prefixed `TelegramInfo`/`telegram_info`, and the new package
lives at `src/core/telegram_info/`, a sibling of (not nested inside)
`src/core/telegram/`.

**EventBus**: not used, for the same reason EP-038/039 didn't use it -- a
single, stateless, synchronous, request/response lookup has no
completion-notification concept for another component to react to.

**Tool Engine (EP-031)**: not modified. `TelegramInfoService`'s single
side-effect-free method is a clean future `Tool` candidate, exactly like
`GitService`'s/`GitHubService`'s methods.

## Components

### `src/core/telegram_info/telegram_info_result.py`

```python
@dataclass(frozen=True)
class TelegramInfoResult:
    chat_id: int
    data: dict   # telegram.Chat.to_dict() -- raw passthrough, no
                 # further structure imposed, matching GitHubResult's
                 # "raw parsed data" philosophy
```

### `src/core/telegram_info/telegram_info_error.py`

```python
class TelegramInfoError(Exception):
    """Base class for every EP-040 Telegram Info exception."""

class TelegramInfoAuthenticationError(TelegramInfoError):
    """telegram.token is missing/blank, or Telegram rejected it
    (InvalidToken), or the bot has no access to the chat (Forbidden)."""

class TelegramInfoNotFoundError(TelegramInfoError):
    """The chat_id does not exist or is not resolvable (BadRequest)."""

class TelegramInfoRateLimitError(TelegramInfoError):
    """Telegram's rate limit was exceeded (RetryAfter)."""

class TelegramInfoTimeoutError(TelegramInfoError):
    """The call exceeded 'telegram_info.timeout_seconds' (TimedOut)."""

class TelegramInfoNetworkError(TelegramInfoError):
    """A connection-level failure occurred (NetworkError, other than
    TimedOut/BadRequest)."""

class TelegramInfoAPIError(TelegramInfoError):
    """Any other TelegramError subclass not covered above (ChatMigrated,
    Conflict, EndPointNotFound, PassportDecryptionError, ...)."""
```

A flat hierarchy per this project's convention, modeled on
`GitHubError`'s split, mapped onto `python-telegram-bot`'s actual
exception hierarchy (`telegram.error.TelegramError` and its subclasses
`InvalidToken`, `Forbidden`, `NetworkError` -> `BadRequest`/`TimedOut`,
`RetryAfter`, plus a handful of rarer `TelegramError` subclasses). This is
deliberately more granular than EP-012's own `TelegramClient`, which
catches only the broad base `TelegramError` -- justified because the
confirmed architecture instruction is to follow the EP-038/039 precedent
for this new EP, not EP-012's older, coarser pattern; EP-012 itself is not
touched or required to change.

### `src/services/telegram_info_service.py`

```python
class TelegramInfoServiceError(Exception):
    """Raised only for invalid 'telegram_info.*' configuration, or a
    missing/blank 'telegram.token', at __init__ time -- mirrors
    GitHubServiceError/GitServiceError's split from their respective
    GitHubError/GitError hierarchies."""

class TelegramInfoService:
    def __init__(self, config: Config, bot: "telegram.Bot | None" = None) -> None: ...

    def get_chat(self, chat_id: int | str) -> TelegramInfoResult: ...
```

Design notes:
- **Constructs its own `telegram.Bot(token=...)` instance** at `__init__`
  time (unless one is injected for testing -- see Testing Strategy), reading
  `telegram.token` from config via `Config.get("telegram.token", "")`.
  Deliberately does **not** import or instantiate `TelegramClient` --
  confirmed architectural separation from EP-012, and `TelegramClient`
  doesn't expose `get_chat` today regardless.
- **Token validated at construction** (missing/blank ->
  `TelegramInfoServiceError`), unlike EP-039's GitHub token (which is
  checked per-call). This intentional difference matches EP-012's own
  precedent -- `TelegramClient.__init__` already requires a token
  up front to construct a `Bot` instance -- and there is no scenario
  analogous to GitHub's "the environment variable might be exported later"
  reasoning here, since `telegram.token` is ordinary (non-secret-rotating)
  config, read once like every other config value in this project.
- `get_chat` is a coroutine in `python-telegram-bot` 20+ (as
  `fetch_updates`/`send_message` already are in `TelegramClient`); the
  service bridges it to a synchronous call the same way `TelegramClient`
  already does (a private event loop, run once per call) -- this is
  unavoidable async-to-sync bridging mechanics, not a duplication of
  EP-012's *business* logic.
- No retry, no caching, no batching -- a single, cohesive method, matching
  `GitHubService`'s own restraint for a narrow scope.

### `src/modules/telegram_info_module.py`

```python
class TelegramInfoModule:
    def __init__(self, telegram_info_service: TelegramInfoService) -> None: ...

    @property
    def name(self) -> str: return "telegram-info"

    def execute(self, action: str, arguments: list[str]) -> CommandResult: ...
```

Actions: `chat <chat_id>`, `help`. Pure translation layer: calls
`TelegramInfoService.get_chat` unchanged and catches `TelegramInfoError` to
format `CommandResult(success=False, message=str(exc))`. Never imports
`telegram`/`python-telegram-bot` directly, never reads `telegram.token`.

## Public APIs

| Method | Parameters | Telegram Bot API call | Raises |
|---|---|---|---|
| `get_chat(chat_id)` | `chat_id: int \| str` (numeric id or `@username`, both valid per the Bot API) | `Bot.get_chat(chat_id)` | `TelegramInfoAuthenticationError`, `TelegramInfoNotFoundError`, `TelegramInfoRateLimitError`, `TelegramInfoTimeoutError`, `TelegramInfoNetworkError`, `TelegramInfoAPIError` |

## Configuration

New `telegram_info` section:

```yaml
telegram_info:
  enabled: true
  timeout_seconds: 10
```

- `enabled` defaults to `true`, matching every other soft-toggle subsystem
  -- independently toggleable from `telegram.enabled` (EP-012), so one can
  be on while the other is off.
- `timeout_seconds` bounds the single Bot API call (mirroring
  `git.timeout_seconds`/`github.timeout_seconds`'s defensive purpose).
- **No token key.** `telegram.token` (EP-012's existing key) is read
  directly by `TelegramInfoService`, never duplicated into
  `telegram_info.*`. If `telegram.token` is missing/blank,
  `TelegramInfoServiceError` is raised at construction -- the same
  fail-fast pattern `GitService`/`GitHubService` use for their own
  construction-time validation.
- Disabled behavior: identical to EP-038/039 -- when `telegram_info.enabled`
  is `False`, Bootstrap never constructs `TelegramInfoService` and never
  registers `TelegramInfoModule`; `telegram-info <anything>` falls through
  to "Unknown command."

## CLI

Namespace: `telegram-info`

| Command | Arguments | Success | Error |
|---|---|---|---|
| `telegram-info chat` | `<chat_id>` | Chat metadata (title/type/description/etc., as returned by Telegram) | `TelegramInfoError` message, or "requires a chat_id" if omitted |
| `telegram-info help` | none | Static help text listing only the one read command above | n/a |

No message-reading, history, listing, or write command exists anywhere in
`TelegramInfoModule`'s dispatch table.

## Security

- `telegram.token` is read once via `Config.get`, used only to construct
  the `Bot` instance, never re-logged, never included in a `CommandResult`
  message or exception message -- every error message in this design is
  built from fixed text and/or the Telegram API's own error type, never
  the token value.
- No new secret is introduced. No secret is duplicated.
- No write/mutating capability exists, so no human-confirmation
  requirement applies (unlike a hypothetical future `send_message`-class
  operation).
- The `Bot` instance is independent of EP-012's -- two live connections to
  the same bot token can coexist safely (Telegram permits multiple API
  clients per token; only `getUpdates` polling has the shared-cursor
  conflict this design specifically avoids by never calling it).

## Error Handling

| Failure | `python-telegram-bot` exception | EP-040 exception |
|---|---|---|
| Missing/blank `telegram.token` | n/a (checked before any call) | `TelegramInfoServiceError` (construction-time) |
| Invalid token | `InvalidToken` | `TelegramInfoAuthenticationError` |
| Bot has no access to the chat | `Forbidden` | `TelegramInfoAuthenticationError` |
| Chat not found / bad id | `BadRequest` | `TelegramInfoNotFoundError` |
| Rate limited | `RetryAfter` | `TelegramInfoRateLimitError` |
| Call exceeds `telegram_info.timeout_seconds` | `TimedOut` | `TelegramInfoTimeoutError` |
| Other connection-level failure | `NetworkError` (base) | `TelegramInfoNetworkError` |
| Any other `TelegramError` subclass | `ChatMigrated`/`Conflict`/`EndPointNotFound`/`PassportDecryptionError` | `TelegramInfoAPIError` |

`TelegramInfoModule` catches `TelegramInfoError` (the common base of the
first six) and formats it as `CommandResult(success=False, ...)`, matching
`GitHubModule`'s pattern exactly. `TelegramInfoServiceError` can only be
raised during Bootstrap construction, never from a running CLI call.

## Testing Strategy

New suite: `tests/EP040/test_telegram_info_service.py` +
`tests/EP040/test_telegram_info_module.py`, one shared `"EP040"` suite.

**Isolation strategy**: no real Telegram API call is ever made, and no real
bot token is required. `TelegramInfoService.__init__` accepts an injectable
`bot` parameter (mirroring `GitHubService`'s injectable `session`); tests
pass a small duck-typed stub object exposing a `get_chat(chat_id)`
coroutine-or-callable that returns a scripted fake `Chat`-like object (or
raises a scripted `telegram.error.TelegramError` subclass), the same
technique used in `tests/EP039/test_github_service.py`. `telegram.token` is
set to a fixed fake value in a throwaway config for tests that need
construction to succeed; a separate test covers the missing-token path.

Planned assertions:
- `get_chat` returns a `TelegramInfoResult` with correct `chat_id`/`data`
  for a scripted successful response.
- Missing/blank `telegram.token` -> `TelegramInfoServiceError` at
  construction, before any Bot API call.
- Each `python-telegram-bot` exception type (`InvalidToken`, `Forbidden`,
  `BadRequest`, `RetryAfter`, `TimedOut`, a generic `NetworkError`, and one
  "other" `TelegramError` subclass) maps to the correct EP-040 exception.
- `GitHubModule`-equivalent CLI tests: `chat` with/without an argument,
  `help` (asserting no message/history/list/write command is advertised),
  an unknown action.
- Bootstrap wiring for both `telegram_info.enabled` states.
- A dedicated test asserting the fake token value never appears in any
  exception message.
- A dedicated test/assertion confirming `TelegramInfoService` never calls
  `get_updates`/`fetch_updates` and shares no offset/cursor state with
  anything -- e.g. the stub `bot` object exposes only `get_chat`, so any
  accidental call to a polling-related method would fail loudly with an
  `AttributeError`, structurally proving no such call path exists.

Regression suites to still pass unchanged: `EP039`, `EP038`, `EP037`,
`EP036`, `EP036-STEP2`, `EP036-STEP3`, `EP035`, `EP034`, `EP033`, `EP001`.
(EP-012 has no numbered test suite of its own in the current test registry
to re-verify, but its source files will be confirmed byte-identical
before/after STEP 2.)

## Bootstrap Wiring

Mirrors the EP-038/039 block exactly:

```python
if bool(config.get("telegram_info.enabled", True)):
    try:
        telegram_info_service = TelegramInfoService(config=config)
        self._telegram_info_service = telegram_info_service
        router.register(TelegramInfoModule(telegram_info_service))
    except TelegramInfoServiceError as exc:
        logger.error(f"Telegram Info Service disabled: {exc}")
        self._telegram_info_service = None
else:
    logger.info("Telegram Info Service disabled ('telegram_info.enabled: false').")
    self._telegram_info_service = None
```

No cross-EP hard-dependency gate needed -- `TelegramInfoService` depends
only on `Config` (for `telegram_info.*` and read-only access to
`telegram.token`), not on `TelegramClient`/`TelegramService` or any other
EP's engine. A `telegram_info_service` property is added to `Bootstrap`,
mirroring `git_service`/`github_service`. **`src/core/telegram/`,
`src/services/telegram_service.py`, and `src/modules/telegram_module.py`
(EP-012) are not imported, modified, or referenced by any of this new
code.**

## Tool Engine Integration Strategy

Identical reasoning to EP-038/039: no `Tool` entry added, no `src/core/tool/`
file touched. `TelegramInfoService.get_chat` is a clean future `Tool`
candidate.

## File-Level Implementation Plan for STEP 2

### Created
```
src/core/telegram_info/__init__.py
src/core/telegram_info/telegram_info_result.py
src/core/telegram_info/telegram_info_error.py
src/services/telegram_info_service.py
src/modules/telegram_info_module.py
tests/EP040/__init__.py
tests/EP040/test_telegram_info_service.py
tests/EP040/test_telegram_info_module.py
```

### Modified
```
src/bootstrap.py            (construct TelegramInfoService, register TelegramInfoModule, telegram_info_service property)
config/config.yaml           ('telegram_info' section: enabled, timeout_seconds -- no token)
src/modules/test_module.py   (register EP040 test suite)
```

### Explicitly protected / untouched
```
src/core/telegram/                          (EP-012 -- fetch_updates, offset/cursor, polling thread)
src/services/telegram_service.py            (EP-012)
src/modules/telegram_module.py              (EP-012)
config/config.yaml's existing 'telegram:' section (EP-012) -- read from, never modified
src/core/tool/                              (EP-031)
src/core/git/, src/services/git_service.py, src/modules/git_module.py       (EP-038)
src/core/github/, src/services/github_service.py, src/modules/github_module.py  (EP-039)
requirements.txt                            (no new dependency)
tests/EP033/, EP034/, EP035/, EP036/, EP037/, EP038/, EP039/
```

## Risks

- **Two live Bot connections to the same token**: if both `telegram.enabled`
  (EP-012) and `telegram_info.enabled` (EP-040) are true simultaneously,
  two independent `telegram.Bot` instances hold the same token
  concurrently. Telegram's Bot API permits this (unlike `getUpdates`
  polling, a single stateless `get_chat` call has no exclusivity
  requirement), but it is a real resource-duplication characteristic worth
  the project owner's awareness, not a defect.
- **`BadRequest` also covers non-"not found" bad-request cases** (e.g. a
  malformed chat_id string) in the real API -- mapping all of `BadRequest`
  to `TelegramInfoNotFoundError` is a simplification, matching this
  project's general preference for a small, cohesive exception set over a
  larger, more precise one (the same tradeoff `GitHubService` made for its
  own status-code mapping).
- **Alternative considered**: extending `TelegramClient` (EP-012) with a
  new `get_chat` method instead of a second `Bot` instance. Rejected per
  your explicit instruction not to modify EP-012, and because it would
  couple EP-040's read-only lookup to EP-012's stateful, lock-guarded,
  single-event-loop object for no necessary reason.
- **Alternative considered**: implementing message-history/chat-discovery
  via Telethon/Pyrogram (User API). Rejected per your explicit instruction
  -- no new dependency, and those capabilities remain genuinely dropped
  from EP-040's scope, not deferred to a "future step" of this EP.
- **Compatibility risk**: none identified -- wholly new, additive
  subsystem; EP-012 is read from (one config key) but never written to or
  imported.
