# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-042 — Email Integration

Not yet started. STEP 1 (Design) has not begun.

Note: EP-041 — Discord Integration is now fully complete through
STEP 4 (see CHANGELOG.md / docs/RELEASE_NOTES.md /
docs/architecture/audits/EP041_ARCHITECTURE_AUDIT.md), and is now
marked complete in docs/architecture/JARVIS_ROADMAP.md. It is a new,
independent Core -> Service -> Module subsystem
(`src/core/discord/`, `src/services/discord_service.py`,
`src/modules/discord_module.py`) exposing exactly five read-only
operations -- `get_guild(guild_id)`, `list_guild_channels(guild_id)`,
`get_channel(channel_id)`, `get_guild_member(guild_id, user_id)`,
`get_message(channel_id, message_id)` -- against the Discord REST
API v10, using the project's existing `requests` dependency directly.
No message history/bulk retrieval, and no write, moderation, role,
webhook, reaction, or invite operation exists anywhere in this
subsystem, and no Discord Gateway/WebSocket connection is opened.
Authentication uses the `DISCORD_TOKEN` environment variable only,
read per-call and never placed in config. `DiscordService` has no
dependency on any other Engineering Package's service or engine.

SCOPE NOTE: EP-041 STEP 4 was a read-only Architecture Audit and
returned a final verdict of PASS. No scope violation, layering
leakage, security leak, or documentation inconsistency was
identified. Exactly one authoritative `DiscordService`/`DiscordModule`
implementation was confirmed, with no duplicate/parallel client.

---

# Purpose

This document contains ideas, improvements, feature requests and future work that are not yet assigned to an Engineering Package.

Items in this document are not commitments.

They serve as a pool of potential future work.

---

# Rules

Items may be added at any time.

Items may be removed.

Items may later become Engineering Packages.

Priority may change.

---

# Current Backlog

## AI

- Improve project retrieval quality
- Support hybrid search
- Support code embeddings
- Improve provider selection
- Feed EP-022's assembled RAG context into the AI Provider Framework
  for chat completion (deliberately out of scope for EP-022 itself)

---

## User Experience

- Better shell autocomplete
- Command history search
- Improved progress indicators

---

## Tools

- Git integration improvements
- Local file watcher
- Background indexing

---

## Future Ideas

- Voice commands

- Browser automation

- Desktop assistant

- Plugin marketplace

---

End of document.