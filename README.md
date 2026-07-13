# Obsidianify

Current version: 0.4.7

Authoritative update source: https://github.com/aesopscott/obsidianify

Obsidianify is Graphify-style graph intelligence for Obsidian, with agent memory injection.

It turns an entire Obsidian vault into ranked session memory for coding agents.

It is a public, local-first tool for people who use Obsidian as their knowledge system and want coding agents like **Codex** and **Claude Code** to receive the right memory at session start.

Cowork is supported through a manual packet refresh workaround because it does not appear to run Claude Code's global hook system.

The core idea:

```text
Graphify for Obsidian:
  rank the whole Obsidian graph
  -> select project-relevant memory by graph proximity
  -> generate a session packet
  -> inject it through Codex or Claude hooks
```

## What It Does

1. Reads an Obsidian vault.
2. Extracts notes, wikilinks, tags, aliases, frontmatter, folders, and excerpts.
3. Builds a local mirror of the Obsidian knowledge graph.
4. Writes a RAG-ready JSONL corpus from the vault.
5. Ranks the whole graph for strength, centrality, freshness, bridges, evidence quality, and usefulness.
6. Selects project-relevant memory by proximity to the project/task.
7. Generates a context packet.
8. Injects that packet through Codex or Claude startup hooks, or creates a manual Cowork packet.
9. Records prompt-submit markers, then classifies completed turn outcomes and writes valuable assistant/build results into Architecture, Configuration, Design, or Other session notes.

The project receiving memory does not need to own the memory system. The memory system can live anywhere, while the generated packet is written into any target project.

## Prerequisites

- Python 3.10 or newer
- Git
- At least one local Obsidian vault
- Codex, Claude Code, or both

## Global Install

Public repo target:

```text
https://github.com/AesopScott/Obsidianify
```

Clone the repo:

```powershell
git clone https://github.com/AesopScott/Obsidianify.git
cd Obsidianify
```

Install globally for both Codex and Claude:

```powershell
python scripts\install_global.py `
  --vault "G:\My Drive\Obsidian\Meridian_Build" `
  --vault "G:\My Drive\Obsidian\StarHistory" `
  --agent codex `
  --agent claude
```

Install for Codex only:

```powershell
python scripts\install_global.py `
  --vault "C:\path\to\ObsidianVault" `
  --agent codex
```

Install for Claude only:

```powershell
python scripts\install_global.py `
  --vault "C:\path\to\ObsidianVault" `
  --agent claude
```

Install Cowork workaround files:

```powershell
python scripts\install_global.py `
  --vault "C:\path\to\ObsidianVault" `
  --agent cowork
```

Then start a new Codex or Claude session in any project and ask:

```text
What Obsidian graph memory was injected into this session?
```

Obsidianify detects the current working directory, treats that as the active project, ranks all enabled Obsidian vaults as one knowledge graph, and writes the relevant packet into that project.

If the agent does not volunteer the packet, use the explicit fallback prompt:

```text
Read .obsidian-memory/CODEX_SESSION_CONTEXT.md and tell me exactly what Obsidian graph memory was injected. Answer only from that packet.
```

## Verify The Install

Global config:

```powershell
Get-Content "$env:USERPROFILE\.obsidianify\config.json"
```

Codex hook:

```powershell
Get-Content "$env:USERPROFILE\.codex\hooks.json"
```

Claude hook:

```powershell
Get-Content "$env:USERPROFILE\.claude\settings.json"
```

Manual refresh from inside any project:

```powershell
python "C:\path\to\Obsidianify\scripts\omi.py" refresh-global `
  --config "$env:USERPROFILE\.obsidianify\config.json" `
  --agent codex
```

On macOS/Linux:

```bash
python3 "$HOME/path/to/Obsidianify/scripts/omi.py" refresh-global \
  --config "$HOME/.obsidianify/config.json" \
  --agent codex
```

## macOS Notes

Global install creates global files in your home directory:

```text
~/.obsidianify/config.json
~/.codex/hooks.json
~/.codex/AGENTS.md
~/.claude/settings.json
~/.claude/CLAUDE.md
```

It does **not** immediately create `.obsidian-memory/` in every repo. That folder is created inside a project when a Codex or Claude session starts there, or when you manually refresh from inside that project.

To create the packet manually on macOS, first `cd` into the project:

```bash
cd /path/to/project

python3 /path/to/Obsidianify/scripts/omi.py refresh-global \
  --config "$HOME/.obsidianify/config.json" \
  --agent claude
```

After that, the project should contain:

```text
.obsidian-memory/CLAUDE_SESSION_CONTEXT.md
.obsidian-memory/STATUS.json
```

If the folder does not appear after starting a new agent session, the hook probably did not run. Check that the global hook exists and that the agent trusts/runs hooks:

```bash
cat "$HOME/.claude/settings.json"
cat "$HOME/.codex/hooks.json"
```

## Adapter Docs

- Codex adapter: `adapters/codex/`
- Claude Code adapter: `adapters/claude/`

The shared core is `scripts/omi.py`. The adapters install global agent hooks and global guidance files.

## Global Install Files

For Codex, the global installer creates or updates:

```text
~/.codex/hooks.json
~/.codex/AGENTS.md
~/.obsidianify/config.json
```

The config supports multiple vaults:

```json
{
  "vaults": [
    {"name": "Meridian_Build", "path": "G:\\My Drive\\Obsidian\\Meridian_Build", "enabled": true},
    {"name": "StarHistory", "path": "G:\\My Drive\\Obsidian\\StarHistory", "enabled": true}
  ]
}
```

For Claude, the global installer creates or updates:

```text
~/.claude/settings.json
~/.claude/CLAUDE.md
~/.obsidianify/config.json
```

For Cowork, the global installer creates:

```text
~/.obsidianify/COWORK.md
```

Cowork does not auto-run Obsidianify hooks. Use manual refresh from inside the project:

```bash
python3 /path/to/Obsidianify/scripts/omi.py refresh-global \
  --config "$HOME/.obsidianify/config.json" \
  --agent cowork
```

Then ask Cowork:

```text
Read .obsidian-memory/COWORK_SESSION_CONTEXT.md and tell me exactly what Obsidian graph memory was injected. Answer only from that packet.
```

When a session starts in a project, Obsidianify writes:

```text
<current-project>/.obsidian-memory/CODEX_SESSION_CONTEXT.md
<current-project>/.obsidian-memory/CLAUDE_SESSION_CONTEXT.md
<current-project>/.obsidian-memory/COWORK_SESSION_CONTEXT.md
<current-project>/.obsidian-memory/STATUS.json
```

On prompt submission, Obsidianify records a lightweight marker for correlation. After the turn finishes, the post-turn hook reads the latest prompt marker and completed session outcome together, skips low-value or noisy turns, and writes valuable prompt intent or assistant/build results to one of four bucket notes:

```text
<vault>/<project-name>/sessionYYYY-MM-DD/architecture.md
<vault>/<project-name>/sessionYYYY-MM-DD/configuration.md
<vault>/<project-name>/sessionYYYY-MM-DD/design.md
<vault>/<project-name>/sessionYYYY-MM-DD/other.md
```

Existing Codex session logs can be backfilled with a bounded replay:

```powershell
python scripts\omi.py replay-session `
  --config "$env:USERPROFILE\.obsidianify\config.json" `
  --target "C:\path\to\project" `
  --agent codex `
  --session-log "$env:USERPROFILE\.codex\sessions\YYYY\MM\DD\rollout-....jsonl" `
  --limit 25
```

Use `--limit 0` only when intentionally replaying every completed turn in a long session.

Set `sessionLogVault` in `~/.obsidianify/config.json` to choose a different prompt-log vault:

```json
{
  "sessionLogVault": "G:\\My Drive\\Obsidian\\SessionLogs"
}
```

Set `projects.<name>.vaultPath` to choose a different prompt-log vault for one project:

```json
{
  "projects": {
    "Alpha Project": {
      "path": "C:\\path\\to\\project",
      "vaultPath": "G:\\My Drive\\Obsidian\\Client Vault"
    }
  }
}
```

Turn notes store distilled prompt memory plus an assistant outcome summary. Full prompt text remains in the local marker store by default, unless the prompt explicitly asks for transcript capture.

Set `projects.<name>.writeRoot` to write completed-turn notes directly under a project-specific Obsidian root instead of `<vaultPath>/<project-name>/`:

```json
{
  "projects": {
    "Alpha Project": {
      "path": "C:\\path\\to\\project",
      "writeRoot": "G:\\My Drive\\Obsidian\\Alpha Project"
    }
  }
}
```

## Reliability Stack

Obsidianify uses five layers:

1. **Hook context:** the `SessionStart` hook emits a best-effort context payload with the loaded packet.
2. **RAG store:** the hook refreshes `~/.obsidianify/store/memory_rag_documents.jsonl`.
3. **Packet file:** the hook writes `.obsidian-memory/*_SESSION_CONTEXT.md` into the active project.
4. **Turn outcome log:** the `UserPromptSubmit` hook records a marker, and the `Stop` hook classifies the completed response/build outcome into typed Obsidian session notes.
5. **Agent instruction:** global `AGENTS.md` / `CLAUDE.md` tells the agent to read the packet when asked what was injected.

The explicit fallback prompt is still useful for demos and for agents that do not surface hook output as context.

## Local Store

The default storage is local JSON:

```text
.omi-store/memory_nodes.json
.omi-store/memory_edges.json
.omi-store/memory_rankings.json
.omi-store/memory_rag_documents.jsonl
```

Firebase, Supabase, SQLite, or another database can be added later. The core loop is the same:

```text
read Obsidian -> write RAG corpus -> rank graph -> generate packet -> inject packet
```

`memory_rag_documents.jsonl` is the portable RAG export. Each line contains a document with `id`, `text`, and metadata such as vault, source path, title, tags, links, and modified time.

The ranker uses matched project/task terms to identify anchor notes, then propagates graph proximity through resolved wikilinks. Linked notes can be selected because they are close to a relevant anchor, even when they do not repeat the project name directly.

## Optional Project Connect Mode

The default install is global. Project connect mode is only for teams that want a project-specific override.

```powershell
python scripts\install.py `
  --target "C:\path\to\project" `
  --vault "C:\path\to\ObsidianVault" `
  --vault "C:\path\to\SecondVault" `
  --project "Project Name" `
  --agent codex
```

Project connect mode creates project-local hooks and instruction files.

## Target Project Files In Project Connect Mode

For Codex, the installer creates or updates:

```text
<target>/.codex/hooks.json
<target>/.obsidian-memory/CODEX_SESSION_CONTEXT.md
<target>/.obsidian-memory/STATUS.json
<target>/AGENTS.md
```

For Claude, the installer creates or updates:

```text
<target>/.claude/settings.json
<target>/.obsidian-memory/CLAUDE_SESSION_CONTEXT.md
<target>/.obsidian-memory/STATUS.json
<target>/CLAUDE.md
```

## Manual Refresh

```powershell
python scripts\omi.py refresh-global `
  --config "$env:USERPROFILE\.obsidianify\config.json" `
  --agent codex
```

Project-local installs prompt for local routing when `--vault` or `--write-root` is omitted. The selected values are written to `~/.obsidianify/config.json` for hook routing and to `<target>/.obsidian-memory/sidecar_memory.json` so the session packet can remind agents which local vault path and write route belong to that user. The `.obsidian-memory/` directory should stay gitignored because these paths are user-specific.

When a project sidecar contains installer-managed `vaultPath` or `writeRoot` entries, `refresh-global` and turn recording sync those paths back into `~/.obsidianify/config.json`. This keeps hook routing authoritative even when the agent sees the right sidecar path but would otherwise fall back to the repo root.

## Before / After Demo Prompt

Before installing:

```text
What do you know about this project from my Obsidian knowledge graph ONLY right now? Do not inspect files. Do not go looking.
```

After installing and starting a new session:

```text
What Obsidian graph memory was injected into this session?
```

Fallback:

```text
Read .obsidian-memory/CODEX_SESSION_CONTEXT.md and tell me exactly what Obsidian graph memory was injected. Answer only from that packet.
```

## Security Note

This tool reads local Markdown files and writes generated context packets. Review the generated packet before using it with sensitive vaults.

## Product Direction

This is not intended to be a folder-filter tool.

It is also not just an Obsidian search plugin.

The product is closer to:

```text
Obsidianify = Graphify for Obsidian + Codex/Claude memory injection
```

It should not rely on brittle rules like:

```text
only inject notes in /Projects/Meridian
only inject #meridian notes
only inject notes with "Meridian" in the title
```

Those are useful signals, not hard boundaries.

The intended product behavior is:

```text
Given the whole Obsidian graph and a project session,
determine which notes, paths, hubs, bridges, and evidence are close enough,
important enough, and current enough to inject.
```

Humans choose the project. The system determines the memory slice.
