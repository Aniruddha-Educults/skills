# Memory System

Location: `${AOP_MEMORY_DIR}` (default `~/.copilot/memories/`; on Windows `%USERPROFILE%\.copilot\memories\`).
User-global, shared across workspaces, never committed.

| File | Purpose | Cap |
|---|---|---|
| USER.md | Preferences, communication style, expectations | `${AOP_USER_MEMORY_CHAR_LIMIT}` (1375) |
| MEMORY.md | Environment facts, conventions, project state, verified doc URLs + date | `${AOP_AGENT_MEMORY_CHAR_LIMIT}` (2200) |

Semantics
- These files are a storage convention, not a guarantee of automatic loading by any client. Read the relevant
  file explicitly when needed unless the runtime has already supplied it. Never claim a read or write not performed.
- Entries separated by a `§` line; may be multiline. Preserve unrelated entries and use precise edits.
- Check character budgets before writing. If consolidation would drop relevant entries, surface the candidates
  to the user and stop. No silent truncation and no assumption that the filesystem enforces these caps.

Write triggers: stable preference -> USER.md; inspected environment fact -> MEMORY.md; verified doc URL with
date -> MEMORY.md; user correction -> replace stale entry.

Write only when persistent memory is authorized and useful across sessions. Skill and instruction files
already persist their own rules; do not duplicate them in memory. Keep task progress in session state.

Never store: transient state, one-off values, unverified claims, secrets, credentials, unrequested PII.
