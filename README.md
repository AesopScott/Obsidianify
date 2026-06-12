# Obsidianify

Obsidianify is Graphify-style graph intelligence for Obsidian, with agent memory injection.

It turns an entire Obsidian vault into ranked session memory for coding agents.

It is a public, local-first tool for people who use Obsidian as their knowledge system and want coding agents like **Codex** and **Claude Code** to receive the right memory at session start.

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
8. Injects that packet through Codex or Claude startup hooks.

The project receiving memory does not need to own the memory system. The memory system can live anywhere, while the generated packet is written into any target project.

## Quick Start

Public repo target:

```text
https://github.com/AesopScott/Obsidianify
```

Local install from GitHub:

```powershell
git clone https://github.com/AesopScott/Obsidianify.git
cd Obsidianify
```

```powershell
python scripts\install_global.py `
  --vault "G:\My Drive\Obsidian\Meridian_Build" `
  --vault "G:\My Drive\Obsidian\StarHistory" `
  --agent codex `
  --agent claude
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

When a session starts in a project, Obsidianify writes:

```text
<current-project>/.obsidian-memory/CODEX_SESSION_CONTEXT.md
<current-project>/.obsidian-memory/CLAUDE_SESSION_CONTEXT.md
<current-project>/.obsidian-memory/STATUS.json
```

## Reliability Stack

Obsidianify uses four layers:

1. **Hook context:** the `SessionStart` hook emits a best-effort context payload with the loaded packet.
2. **RAG store:** the hook refreshes `~/.obsidianify/store/memory_rag_documents.jsonl`.
3. **Packet file:** the hook writes `.obsidian-memory/*_SESSION_CONTEXT.md` into the active project.
4. **Agent instruction:** global `AGENTS.md` / `CLAUDE.md` tells the agent to read the packet when asked what was injected.

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
