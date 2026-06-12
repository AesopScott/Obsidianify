# Public Product Spec

## Name

Obsidianify

## One-Line Description

Graphify-style graph intelligence for Obsidian: rank an entire Obsidian knowledge graph and inject project-proximate memory into Codex and Claude sessions.

## Problem

AI coding agents start sessions without the user's wider knowledge system. They can inspect the current repo, but they do not automatically know the user's Obsidian notes, decisions, teaching material, project memory, or cross-project context.

Manual prompts and hand-written memory files do not scale. Rule-based injection eventually fails because useful memory may live outside the expected folder, tag, or project note.

## Solution

Use Obsidian as the human knowledge graph, then build a local-first graph intelligence and memory injection tool:

1. Mirror all enabled vault graphs.
2. Rank the combined whole graph.
3. Select project-proximate memory at session start.
4. Generate a compact context packet.
5. Inject through Codex and Claude hooks.

## Core Principle

The whole graph across all enabled vaults is ranked. The project only determines which ranked portions are injected.

Plain-English version:

```text
Graphify for Obsidian.
```

## MVP

- Local Markdown parser for Obsidian notes.
- Multi-vault config.
- Local JSON graph store.
- RAG-ready JSONL export.
- Whole-graph ranking.
- Project/task proximity scoring.
- Global Codex install adapter.
- Global Claude install adapter.
- Cowork manual packet adapter.
- Generated Markdown packet.
- Status file for verification.

## Future

- Firebase/Supabase/SQLite backends.
- Embeddings and semantic reranking.
- MCP server for live graph queries.
- Obsidian community plugin.
- Feedback loop from session outcomes.
- UI for inspecting why memory was injected.
