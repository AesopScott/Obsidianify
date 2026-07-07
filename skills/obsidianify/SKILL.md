---
name: obsidianify
description: Use when setting up, refreshing, debugging, or explaining Obsidianify for Codex or Claude sessions. Reads Obsidian vaults, ranks graph memory by project proximity, creates session context packets, and records valuable completed turn outcomes into typed Obsidian session notes.
---

# Obsidianify

Current version: 0.4.0

Use this skill when a user wants to inject Obsidian-derived memory into a Codex or Claude project session, or record agent turn outcomes back into an Obsidian vault.

## Workflow

1. Prefer global install unless the user needs a project-local override.
2. Run `python scripts/install_global.py --vault <vault> --agent codex --agent claude` from the plugin repo for global install.
3. For project-local install, run `python scripts/install.py --target <project> --vault <vault> --project <name> --agent codex --agent claude`.
4. Start a new agent session in the target project.
5. Ask what Obsidian graph memory was injected.
6. If memory is missing, inspect `<target>/.obsidian-memory/STATUS.json`.

## Reliability

- `SessionStart` hooks refresh the packet.
- `UserPromptSubmit` hooks record lightweight turn markers.
- `Stop` hooks classify the latest prompt plus completed turn outcome and write valuable entries into typed notes under `<vault>/<project>/sessionYYYY-MM-DD/`.
- Turn notes include distilled prompt memory and assistant outcome summaries; raw full prompts stay in the local marker store unless the user explicitly asks for transcript capture.
- A project config can set `vaultPath` to choose the recording vault for that project: `projects.<name>.vaultPath`.
- A project config can set `writeRoot` to write turn notes under a project-specific root instead: `projects.<name>.writeRoot/sessionYYYY-MM-DD/`.
- `AGENTS.md` or `CLAUDE.md` tells the agent to read the packet.
- The first user prompt can force verification.

Do not claim the model remembered Obsidian by itself. The injected context comes from the generated packet.
