# Claude Code Adapter

The Claude adapter injects ranked Obsidian memory into Claude Code sessions globally.

## Installed Global Files

```text
~/.claude/settings.json
~/.claude/CLAUDE.md
~/.obsidianify/config.json
```

## Install

```powershell
python scripts\install_global.py `
  --vault "C:\path\to\ObsidianVault" `
  --agent claude
```

## What Happens

1. A Claude `SessionStart` hook refreshes the ranked memory packet.
2. Obsidianify detects the current project from the session working directory.
3. Global `CLAUDE.md` tells Claude to read `.obsidian-memory/CLAUDE_SESSION_CONTEXT.md`.
4. The hook emits `hookSpecificOutput.additionalContext` with the loaded packet.
5. Claude can answer what Obsidian-derived memory was injected.

## Reliability Note

`CLAUDE.md` is guidance, not enforcement. The hook is the stronger part of the adapter because it refreshes the packet outside the model. For a live demo, use the verification prompt below.

## Verification Prompt

```text
What Obsidian graph memory was injected into this Claude session? Answer only from .obsidian-memory/CLAUDE_SESSION_CONTEXT.md.
```

Fallback prompt:

```text
Read .obsidian-memory/CLAUDE_SESSION_CONTEXT.md and tell me exactly what Obsidian graph memory was injected. Answer only from that packet.
```
