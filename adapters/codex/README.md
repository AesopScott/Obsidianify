# Codex Adapter

The Codex adapter injects ranked Obsidian memory into Codex sessions globally.

## Installed Global Files

```text
~/.codex/hooks.json
~/.codex/AGENTS.md
~/.obsidianify/config.json
```

## Install

```powershell
python scripts\install_global.py `
  --vault "C:\path\to\ObsidianVault" `
  --agent codex
```

## What Happens

1. A `SessionStart` hook refreshes the ranked memory packet.
2. Obsidianify detects the current project from the session working directory.
3. Global `AGENTS.md` tells Codex to read `.obsidian-memory/CODEX_SESSION_CONTEXT.md`.
4. The hook also emits a best-effort context payload for agents that surface hook context.
5. Codex can answer what Obsidian-derived memory was injected.

## Verification Prompt

```text
What Obsidian graph memory was injected into this Codex session?
```

Fallback prompt:

```text
Read .obsidian-memory/CODEX_SESSION_CONTEXT.md and tell me exactly what Obsidian graph memory was injected. Answer only from that packet.
```
