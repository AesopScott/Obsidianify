---
name: obsidianify
description: Use when setting up, refreshing, debugging, or explaining Obsidianify for Codex or Claude sessions. Reads an Obsidian vault, ranks graph memory, and creates session context packets.
---

# Obsidianify

Use this skill when a user wants to inject Obsidian-derived memory into a Codex or Claude project session.

## Workflow

1. Confirm the target project directory and Obsidian vault directory.
2. Run `python scripts/install.py --target <project> --vault <vault> --project <name> --agent codex --agent claude` from the plugin repo.
3. Start a new agent session in the target project.
4. Ask what Obsidian graph memory was injected.
5. If memory is missing, inspect `<target>/.obsidian-memory/STATUS.json`.

## Reliability

- Hooks refresh the packet.
- `AGENTS.md` or `CLAUDE.md` tells the agent to read the packet.
- The first user prompt can force verification.

Do not claim the model remembered Obsidian by itself. The injected context comes from the generated packet.
