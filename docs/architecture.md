# Architecture

Obsidianify is Graphify-style graph intelligence for Obsidian. It has one shared core, two global hook adapters, and a Cowork manual adapter.

The public product is not a per-project note filter. It ranks all enabled Obsidian vaults as one knowledge graph, then injects project-proximate memory into the active agent session.

```text
Obsidian vault(s)
  -> whole-graph mirror
  -> whole-graph ranking
  -> project proximity selection
  -> generated context packet
  -> global Codex / Claude startup hook, or manual Cowork packet
  -> valuable completed turn outcomes appended to typed Obsidian session notes
```

## Shared Core

- `scripts/omi.py sync`: parse the Obsidian vault into local graph JSON.
- `scripts/omi.py sync`: also writes `memory_rag_documents.jsonl`, a portable RAG-ready corpus.
- `scripts/omi.py rank`: rank the whole graph and score project/task proximity.
- `scripts/omi.py packet`: generate a session context packet.
- `scripts/omi.py refresh`: run all three for a connected project.
- `scripts/omi.py refresh-global`: detect the current working directory and run the global install path.
- `scripts/omi.py record-prompt`: read prompt hook JSON from stdin and store a lightweight marker for turn correlation.
- `scripts/omi.py record-turn`: read the completed session turn and append valuable assistant/build outcomes to an Obsidian session note.
- `scripts/omi.py replay-session`: backfill valuable completed outcomes from an existing Codex session log.

## Ranking Philosophy

Rules are signals, not boundaries.

The ranker currently uses:

- project/task term anchors
- title/path/tag matches
- backlinks and outgoing links
- graph centrality
- graph-distance proximity from matched anchor notes
- bridge value
- freshness
- evidence quality

Future ranking can add embeddings, folder proximity, and prior usefulness.

The system should decide the injected slice. Humans should not have to maintain a list of notes to inject.

## Codex Adapter

- `~/.codex/hooks.json` runs `omi.py refresh-global` at `SessionStart`.
- `~/.codex/hooks.json` runs `omi.py record-prompt` at `UserPromptSubmit`.
- `~/.codex/hooks.json` runs `omi.py record-turn` at `Stop`.
- `~/.codex/AGENTS.md` tells Codex to read `.obsidian-memory/CODEX_SESSION_CONTEXT.md`.
- Obsidianify detects the active project from the session working directory.
- Turn outcomes are classified as valuable or not valuable. Valuable writes route into Architecture, Configuration, Design, or Other notes.
- The hook emits a best-effort `hookSpecificOutput.additionalContext` payload. If Codex does not surface hook output as context, the packet file and instruction block remain the fallback.

## Claude Adapter

- `~/.claude/settings.json` runs `omi.py refresh-global` at `SessionStart`.
- `~/.claude/settings.json` runs `omi.py record-prompt` at `UserPromptSubmit`.
- `~/.claude/settings.json` runs `omi.py record-turn` at `Stop` when a compatible session log is available.
- `~/.claude/CLAUDE.md` tells Claude to read `.obsidian-memory/CLAUDE_SESSION_CONTEXT.md`.
- Obsidianify detects the active project from the session working directory.
- Turn outcomes are classified as valuable or not valuable. Valuable writes route into Architecture, Configuration, Design, or Other notes.
- The hook emits `hookSpecificOutput.additionalContext` with the loaded packet.

## Cowork Adapter

- Cowork does not appear to run Claude Code's global hook system.
- Use `omi.py refresh-global --agent cowork` manually from inside a project.
- The command writes `.obsidian-memory/COWORK_SESSION_CONTEXT.md`.
- Ask Cowork to read that packet explicitly.

## Reliability Stack

1. Direct hook context when supported.
2. Generated packet file in `.obsidian-memory/`.
3. Typed completed-turn notes in `<vault>/<project>/sessionYYYY-MM-DD/{architecture,configuration,design,other}.md`.
4. Global agent instruction to read the packet.
5. User fallback prompt for live verification.

## Sidecar Memory

- `.obsidian-memory/sidecar_memory.json` is a per-project, hand-editable memory source that rides along in the same packet as ranked Obsidian memory.
- Format: `{"entries": [{"text": "...", "addedAt": "...", "addedBy": "..."}]}`. `text` is required; `addedAt`/`addedBy` are optional display metadata.
- Scott can edit the file directly, or ask an assistant to append/edit an entry in it — same file, no separate mechanism.
- `scripts/omi.py packet` reads it and appends a `## Sidecar Memory` section (most recent `SIDECAR_DISPLAY_LIMIT` entries) before the Agent Instruction block.
- Absent or empty sidecar file: no section is added, `STATUS.json.sidecarCount` is `0`, ranked-memory injection is unchanged.
- No dedupe against ranked memory: the two are shown as distinct sections, sidecar entries are treated as directly authoritative curated notes.

## Storage

The MVP uses local JSON in `.omi-store/`.

The local store includes:

- `memory_nodes.json`
- `memory_edges.json`
- `memory_rankings.json`
- `memory_rag_documents.jsonl`

`memory_rag_documents.jsonl` includes vault metadata and can be imported into a vector database, Firebase-backed RAG pipeline, SQLite FTS table, or other retrieval backend.

Future stores can implement the same shape:

- Firebase
- SQLite
- Supabase
- Postgres
- vector DB
