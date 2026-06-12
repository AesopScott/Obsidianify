# Cowork Adapter

Cowork is supported through a manual packet refresh workaround.

Cowork does not appear to run Claude Code's global `~/.claude/settings.json` hooks, so Obsidianify cannot currently auto-create a packet at Cowork session start.

## Manual Refresh

Run this from inside the project:

```bash
python3 /path/to/Obsidianify/scripts/omi.py refresh-global \
  --config "$HOME/.obsidianify/config.json" \
  --agent cowork
```

This creates:

```text
.obsidian-memory/COWORK_SESSION_CONTEXT.md
.obsidian-memory/STATUS.json
```

## Cowork Prompt

```text
Read .obsidian-memory/COWORK_SESSION_CONTEXT.md and tell me exactly what Obsidian graph memory was injected. Answer only from that packet.
```
