# Architecture

Obsidianify is Graphify-style graph intelligence for Obsidian. It has one shared core and two global agent adapters.

The public product is not a per-project note filter. It ranks the whole Obsidian vault, then injects project-proximate memory into the active agent session.

```text
Obsidian vault
  -> whole-graph mirror
  -> whole-graph ranking
  -> project proximity selection
  -> generated context packet
  -> global Codex / Claude startup hook
```

## Shared Core

- `scripts/omi.py sync`: parse the Obsidian vault into local graph JSON.
- `scripts/omi.py sync`: also writes `memory_rag_documents.jsonl`, a portable RAG-ready corpus.
- `scripts/omi.py rank`: rank the whole graph and score project/task proximity.
- `scripts/omi.py packet`: generate a session context packet.
- `scripts/omi.py refresh`: run all three for a connected project.
- `scripts/omi.py refresh-global`: detect the current working directory and run the global install path.

## Ranking Philosophy

Rules are signals, not boundaries.

The ranker can use:

- semantic relevance
- title/path/tag matches
- backlinks and outgoing links
- graph centrality
- bridge value
- freshness
- evidence quality
- folder proximity
- prior usefulness

The system should decide the injected slice. Humans should not have to maintain a list of notes to inject.

## Codex Adapter

- `~/.codex/hooks.json` runs `omi.py refresh-global` at `SessionStart`.
- `~/.codex/AGENTS.md` tells Codex to read `.obsidian-memory/CODEX_SESSION_CONTEXT.md`.
- Obsidianify detects the active project from the session working directory.
- The hook emits a best-effort `hookSpecificOutput.additionalContext` payload. If Codex does not surface hook output as context, the packet file and instruction block remain the fallback.

## Claude Adapter

- `~/.claude/settings.json` runs `omi.py refresh-global` at `SessionStart`.
- `~/.claude/CLAUDE.md` tells Claude to read `.obsidian-memory/CLAUDE_SESSION_CONTEXT.md`.
- Obsidianify detects the active project from the session working directory.
- The hook emits `hookSpecificOutput.additionalContext` with the loaded packet.

## Reliability Stack

1. Direct hook context when supported.
2. Generated packet file in `.obsidian-memory/`.
3. Global agent instruction to read the packet.
4. User fallback prompt for live verification.

## Storage

The MVP uses local JSON in `.omi-store/`.

The local store includes:

- `memory_nodes.json`
- `memory_edges.json`
- `memory_rankings.json`
- `memory_rag_documents.jsonl`

`memory_rag_documents.jsonl` can be imported into a vector database, Firebase-backed RAG pipeline, SQLite FTS table, or other retrieval backend.

Future stores can implement the same shape:

- Firebase
- SQLite
- Supabase
- Postgres
- vector DB
