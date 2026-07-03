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
2. A `UserPromptSubmit` hook records a lightweight turn marker.
3. A `Stop` hook reads the completed Codex turn and writes valuable assistant/build outcomes into typed notes under `<vault>/<project>/sessionYYYY-MM-DD/`.
4. Obsidianify detects the current project from the session working directory.
5. Global `AGENTS.md` tells Codex to read `.obsidian-memory/CODEX_SESSION_CONTEXT.md`.
6. The hook also emits a best-effort context payload for agents that surface hook context.
7. Codex can answer what Obsidian-derived memory was injected.

## Verification Prompt

```text
What Obsidian graph memory was injected into this Codex session?
```

Fallback prompt:

```text
Read .obsidian-memory/CODEX_SESSION_CONTEXT.md and tell me exactly what Obsidian graph memory was injected. Answer only from that packet.
```
