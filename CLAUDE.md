@AGENTS.md

## Claude Code

- This repository keeps shared agent instructions in `AGENTS.md`. Treat that file as the source of truth.
- Project skills are exposed to Claude Code through `.claude/skills/`, which symlinks to `.agents/skills/`.
- When `AGENTS.md` or spec notes say to invoke `$kiro-...`, use the corresponding Claude Code skill command `/kiro-...`.
- When a local skill mentions Codex-specific tool names, follow the intent using Claude Code's equivalent file, shell, search, task, and review tools.
- Keep responses in Japanese unless the user explicitly asks otherwise.
