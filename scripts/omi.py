"""Obsidianify CLI.

Local-first MVP:
- parse an Obsidian vault into graph-shaped JSON
- rank the whole graph
- generate a Codex or Claude session context packet
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OBSIDIANIFY_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_/-]+)")
INFORMATION_BUCKET_FILES = {
    "Architecture": "architecture.md",
    "Configuration": "configuration.md",
    "Design": "design.md",
    "Other": "other.md",
}
SIDECAR_FILENAME = "sidecar_memory.json"
SIDECAR_DISPLAY_LIMIT = 50
LOW_VALUE_PROMPTS = {
    "ok",
    "okay",
    "yes",
    "no",
    "y",
    "n",
    "thanks",
    "thank you",
    "continue",
    "go on",
    "proceed",
    "sounds good",
}
NOISE_TERMS = {
    "heartbeat-check",
    "handoff-check",
    "unchanged",
}
DELEGATION_MARKERS = {
    "<codex_delegation>",
    "</codex_delegation>",
}
VALUABLE_TERMS = {
    "add",
    "agent",
    "architecture",
    "authority",
    "build",
    "change",
    "classify",
    "config",
    "configuration",
    "contract",
    "create",
    "decision",
    "design",
    "enable",
    "fix",
    "handoff",
    "hook",
    "implement",
    "install",
    "memory",
    "obsidian",
    "obsidianify",
    "pipeline",
    "project",
    "record",
    "repo",
    "role",
    "scaffold",
    "skill",
    "test",
    "trust",
    "update",
    "write",
}
CONFIGURATION_TERMS = {
    ".env",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    "automation",
    "caveman",
    "config",
    "configuration",
    "enabled",
    "hook",
    "install",
    "path",
    "setting",
    "setup",
    "toml",
    "trust",
}
ARCHITECTURE_TERMS = {
    "adapter",
    "agent",
    "architecture",
    "authority",
    "backfill",
    "boundary",
    "classifier",
    "contract",
    "controller",
    "eval",
    "handoff",
    "maps",
    "memory",
    "m0",
    "m1",
    "m2",
    "m3",
    "m4",
    "m5",
    "m6",
    "m7",
    "m8",
    "m9",
    "m10",
    "m11",
    "operator",
    "orchestration",
    "pipeline",
    "post-turn",
    "role",
    "runtime",
    "skill",
    "scaffold",
    "system",
    "validator",
}
DESIGN_TERMS = {
    "component",
    "design",
    "flow",
    "interface",
    "layout",
    "page",
    "profile",
    "screen",
    "ui",
    "ux",
    "voice",
}
OUTCOME_TERMS = {
    "added",
    "approved",
    "built",
    "changed",
    "completed",
    "created",
    "fixed",
    "implemented",
    "outcome",
    "passed",
    "routed",
    "updated",
    "validated",
    "verified",
}
MEMORY_INTENT_PHRASES = {
    "remember",
    "memorize",
    "save this",
    "note this",
    "write this down",
    "record this",
    "store this",
    "keep this",
}
PREFERENCE_TERMS = {
    "always",
    "default",
    "defaults",
    "prefer",
    "preference",
    "remember",
    "should",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"Obsidianify {OBSIDIANIFY_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Read an Obsidian vault and write graph JSON.")
    sync.add_argument("--vault", action="append", required=True, type=Path)
    sync.add_argument("--store", default=Path(".omi-store"), type=Path)

    rank = sub.add_parser("rank", help="Rank the whole graph for a project/task.")
    rank.add_argument("--store", default=Path(".omi-store"), type=Path)
    rank.add_argument("--project", required=True)
    rank.add_argument("--task", default="")

    packet = sub.add_parser("packet", help="Generate a session context packet.")
    packet.add_argument("--store", default=Path(".omi-store"), type=Path)
    packet.add_argument("--project", required=True)
    packet.add_argument("--task", default="")
    packet.add_argument("--target", required=True, type=Path)
    packet.add_argument("--agent", choices=("codex", "claude", "cowork"), required=True)
    packet.add_argument("--limit", default=20, type=int)
    packet.add_argument("--max-excerpt-chars", default=None, type=int, help="Max chars per node excerpt (default: 260).")
    packet.add_argument("--signals-verbosity", default=None, choices=("full", "compact", "none"), help="Signal metadata verbosity: full (all 7), compact (top 3), none (omit).")

    refresh = sub.add_parser("refresh", help="Sync, rank, and write a session packet.")
    refresh.add_argument("--vault", action="append", required=True, type=Path)
    refresh.add_argument("--store", default=Path(".omi-store"), type=Path)
    refresh.add_argument("--project", required=True)
    refresh.add_argument("--task", default="")
    refresh.add_argument("--target", required=True, type=Path)
    refresh.add_argument("--agent", choices=("codex", "claude", "cowork"), required=True)
    refresh.add_argument("--limit", default=20, type=int)
    refresh.add_argument("--max-excerpt-chars", default=None, type=int, help="Max chars per node excerpt (default: 260).")
    refresh.add_argument("--signals-verbosity", default=None, choices=("full", "compact", "none"), help="Signal metadata verbosity: full (all 7), compact (top 3), none (omit).")
    refresh.add_argument(
        "--emit-hook-context",
        action="store_true",
        help="Print hookSpecificOutput JSON for agents that accept hook-injected context.",
    )

    refresh_global = sub.add_parser("refresh-global", help="Refresh memory for the current working directory using global config.")
    refresh_global.add_argument("--config", default=Path.home() / ".obsidianify" / "config.json", type=Path)
    refresh_global.add_argument("--agent", choices=("codex", "claude", "cowork"), required=True)
    refresh_global.add_argument("--limit", default=20, type=int)
    refresh_global.add_argument("--max-excerpt-chars", default=None, type=int, help="Max chars per node excerpt (default: config or 260).")
    refresh_global.add_argument("--signals-verbosity", default=None, choices=("full", "compact", "none"), help="Signal metadata verbosity: full (all 7), compact (top 3), none (omit).")
    refresh_global.add_argument(
        "--emit-hook-context",
        action="store_true",
        help="Print hookSpecificOutput JSON for agents that accept hook-injected context.",
    )

    record_prompt = sub.add_parser("record-prompt", help="Record a prompt-submit marker for the next post-turn write.")
    record_prompt.add_argument("--config", default=None, type=Path)
    record_prompt.add_argument("--vault", default=None, type=Path)
    record_prompt.add_argument("--project", default="")
    record_prompt.add_argument("--target", default=Path.cwd(), type=Path)
    record_prompt.add_argument("--agent", choices=("codex", "claude", "cowork"), required=True)
    record_prompt.add_argument("--session-date", default="")

    record_turn = sub.add_parser("record-turn", help="Write valuable completed turn outcomes into typed Obsidian notes.")
    record_turn.add_argument("--config", default=None, type=Path)
    record_turn.add_argument("--vault", default=None, type=Path)
    record_turn.add_argument("--project", default="")
    record_turn.add_argument("--target", default=Path.cwd(), type=Path)
    record_turn.add_argument("--agent", choices=("codex", "claude", "cowork"), required=True)
    record_turn.add_argument("--session-date", default="")
    record_turn.add_argument("--session-log", default=None, type=Path)

    replay_session = sub.add_parser("replay-session", help="Backfill valuable completed turn outcomes from a Codex session log.")
    replay_session.add_argument("--config", default=None, type=Path)
    replay_session.add_argument("--vault", default=None, type=Path)
    replay_session.add_argument("--project", default="")
    replay_session.add_argument("--target", default=Path.cwd(), type=Path)
    replay_session.add_argument("--agent", choices=("codex", "claude", "cowork"), required=True)
    replay_session.add_argument("--session-date", default="")
    replay_session.add_argument("--session-log", required=True, type=Path)
    replay_session.add_argument("--limit", default=25, type=int, help="Max newest completed turns to replay. Use 0 for all.")

    args = parser.parse_args()
    if args.command == "sync":
        sync_vaults(args.vault, args.store)
    elif args.command == "rank":
        rank_graph(args.store, args.project, args.task)
    elif args.command == "packet":
        generate_packet(args.store, args.project, args.task, args.target, args.agent, args.limit, args.max_excerpt_chars, args.signals_verbosity)
    elif args.command == "refresh":
        refresh_project(args.vault, args.store, args.project, args.task, args.target, args.agent, args.limit, args.emit_hook_context, args.max_excerpt_chars, args.signals_verbosity)
    elif args.command == "refresh-global":
        refresh_from_global_config(args.config, args.agent, args.limit, args.emit_hook_context, args.max_excerpt_chars, args.signals_verbosity)
    elif args.command == "record-prompt":
        record_prompt_from_hook(args.config, args.vault, args.project, args.target, args.agent, args.session_date)
    elif args.command == "record-turn":
        record_turn_from_hook(args.config, args.vault, args.project, args.target, args.agent, args.session_date, args.session_log)
    elif args.command == "replay-session":
        replay_session_log(args.config, args.vault, args.project, args.target, args.agent, args.session_date, args.session_log, args.limit)
    return 0


def refresh_project(
    vaults: list[Path],
    store: Path,
    project: str,
    task: str,
    target: Path,
    agent: str,
    limit: int,
    emit_hook_context: bool = False,
    max_excerpt_chars: int | None = None,
    signals_verbosity: str | None = None,
) -> None:
    if emit_hook_context:
        with contextlib.redirect_stdout(io.StringIO()):
            sync_vaults(vaults, store)
            rank_graph(store, project, task)
            packet_path = generate_packet(store, project, task, target, agent, limit, max_excerpt_chars, signals_verbosity)
        print(json.dumps(hook_context_payload(packet_path, project, agent), ensure_ascii=True))
    else:
        sync_vaults(vaults, store)
        rank_graph(store, project, task)
        generate_packet(store, project, task, target, agent, limit, max_excerpt_chars, signals_verbosity)


def refresh_from_global_config(
    config_path: Path,
    agent: str,
    limit: int,
    emit_hook_context: bool = False,
    max_excerpt_chars: int | None = None,
    signals_verbosity: str | None = None,
) -> None:
    config = load_json(config_path)
    target = Path.cwd().resolve()
    project = detect_project_name(target, config)
    task = config.get("defaultTask", "general project session")
    vaults = config_vaults(config)
    store = Path(config.get("store", str(Path.home() / ".obsidianify" / "store")))
    resolved_max_excerpt = max_excerpt_chars if max_excerpt_chars is not None else config.get("maxExcerptChars")
    resolved_signals_verbosity = signals_verbosity if signals_verbosity is not None else config.get("signalsVerbosity")
    if emit_hook_context:
        with contextlib.redirect_stdout(io.StringIO()):
            sync_vaults(vaults, store)
            rank_graph(store, project, task)
            packet_path = generate_packet(store, project, task, target, agent, limit, resolved_max_excerpt, resolved_signals_verbosity)
        print(json.dumps(hook_context_payload(packet_path, project, agent), ensure_ascii=True))
    else:
        sync_vaults(vaults, store)
        rank_graph(store, project, task)
        generate_packet(store, project, task, target, agent, limit, resolved_max_excerpt, resolved_signals_verbosity)


def detect_project_name(target: Path, config: dict[str, Any]) -> str:
    projects = config.get("projects", {})
    target_text = str(target).lower()
    for name, data in projects.items():
        path = str(data.get("path", "")).lower()
        if path and target_text.startswith(path):
            return name
    return target.name


def config_vaults(config: dict[str, Any]) -> list[Path]:
    if "vaults" in config:
        vaults = []
        for item in config.get("vaults", []):
            if isinstance(item, str):
                vaults.append(Path(item))
            elif item.get("enabled", True):
                vaults.append(Path(item["path"]))
        return vaults
    if "vault" in config:
        return [Path(config["vault"])]
    raise SystemExit("No vaults configured.")


def sync_vaults(vaults: list[Path], store: Path) -> None:
    all_notes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    statuses = []
    for vault in vaults:
        notes, edges, status = read_vault(vault)
        all_notes.extend(notes)
        all_edges.extend(edges)
        statuses.append(status)

    store.mkdir(parents=True, exist_ok=True)
    write_json(store / "memory_nodes.json", all_notes)
    write_json(store / "memory_edges.json", all_edges)
    write_rag_documents(store / "memory_rag_documents.jsonl", all_notes)
    write_json(
        store / "sync_status.json",
        {
            "status": "synced",
            "vaults": statuses,
            "notes": len(all_notes),
            "edges": len(all_edges),
            "ragDocuments": len(all_notes),
            "syncedAt": utc_now(),
        },
    )
    print(f"Synced {len(all_notes)} notes, {len(all_edges)} edges, and {len(all_notes)} RAG docs from {len(vaults)} vault(s) -> {store}")


def read_vault(vault: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    vault = vault.resolve()
    if not vault.exists():
        raise SystemExit(f"Vault not found: {vault}")
    vault_name = vault.name
    notes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    by_stem: dict[str, str] = {}

    md_files = [
        path
        for path in vault.rglob("*.md")
        if ".obsidian" not in path.parts and not any(part.startswith(".trash") for part in path.parts)
    ]
    for path in md_files:
        rel = path.relative_to(vault).as_posix()
        by_stem[path.stem.lower()] = rel

    for path in md_files:
        rel = path.relative_to(vault).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        frontmatter, body = split_frontmatter(text)
        title = frontmatter.get("title") or path.stem
        aliases = as_string_list(frontmatter.get("aliases", []))
        tags = sorted(set(as_string_list(frontmatter.get("tags", []))))
        tags = sorted(set(tags) | set(TAG_RE.findall(body)))
        links = parse_wikilinks(body)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        excerpt = compact_excerpt(body)
        folder = Path(rel).parent.as_posix()
        notes.append(
            {
                "id": note_id(vault_name, rel),
                "vault": vault_name,
                "vaultPath": str(vault),
                "path": rel,
                "title": str(title),
                "aliases": aliases,
                "folder": "" if folder == "." else folder,
                "tags": tags,
                "links": links,
                "modifiedAt": mtime,
                "excerpt": excerpt,
                "frontmatter": frontmatter,
            }
        )
        for link in links:
            target_key = link.lower()
            target = by_stem.get(target_key)
            edges.append(
                {
                    "source": note_id(vault_name, rel),
                    "target": note_id(vault_name, target) if target else f"unresolved:{slug(vault_name)}:{slug(link)}",
                    "vault": vault_name,
                    "vaultPath": str(vault),
                    "targetLabel": link,
                    "relation": "wikilink",
                    "resolved": bool(target),
                }
            )

    return notes, edges, {"name": vault_name, "path": str(vault), "notes": len(notes), "edges": len(edges)}


def rank_graph(store: Path, project: str, task: str) -> None:
    notes = load_json(store / "memory_nodes.json")
    edges = load_json(store / "memory_edges.json")
    degree = Counter()
    incoming = Counter()
    outgoing = Counter()
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
        outgoing[edge["source"]] += 1
        incoming[edge["target"]] += 1

    terms = terms_for(f"{project} {task}")
    searchable_text = {note["id"]: note_search_text(note) for note in notes}
    anchor_scores = {
        note["id"]: text_relevance(terms, searchable_text[note["id"]])
        for note in notes
    }
    anchor_scores = {note_id_value: score for note_id_value, score in anchor_scores.items() if score > 0}
    adjacency = graph_adjacency(edges)
    proximity_scores, proximity_sources = graph_proximity(anchor_scores, adjacency)
    notes_by_id = {note["id"]: note for note in notes}
    max_degree = max(degree.values(), default=1)
    max_incoming = max(incoming.values(), default=1)
    ranked = []
    for note in notes:
        text = searchable_text[note["id"]]
        relevance = text_relevance(terms, text)
        proximity = proximity_scores.get(note["id"], 0.0)
        centrality = degree[note["id"]] / max_degree
        authority = incoming[note["id"]] / max_incoming
        freshness = freshness_score(note.get("modifiedAt", ""))
        bridge = bridge_score(note, degree[note["id"]], incoming[note["id"]], outgoing[note["id"]])
        evidence = evidence_score(note)
        score = (
            proximity * 0.30
            + relevance * 0.25
            + centrality * 0.15
            + authority * 0.10
            + freshness * 0.08
            + evidence * 0.07
            + bridge * 0.05
            + min(len(note.get("tags", [])) / 8, 1.0) * 0.05
        )
        matched = sorted(terms & set(re.findall(r"[a-z0-9_]+", text.lower())))
        source = proximity_sources.get(note["id"], {})
        anchor_note = notes_by_id.get(source.get("anchor", ""))
        anchor_label = ""
        if anchor_note:
            anchor_label = f"{anchor_note.get('title', '')} ({anchor_note.get('path', '')})"
        ranked.append(
            {
                "id": note["id"],
                "title": note.get("title", ""),
                "vault": note.get("vault", ""),
                "path": note.get("path", ""),
                "score": round(score, 4),
                "signals": {
                    "proximity": round(proximity, 4),
                    "relevance": round(relevance, 4),
                    "centrality": round(centrality, 4),
                    "authority": round(authority, 4),
                    "freshness": round(freshness, 4),
                    "bridge": round(bridge, 4),
                    "evidence": round(evidence, 4),
                },
                "why": {
                    "matchedTerms": matched[:12],
                    "anchor": anchor_label,
                    "graphDistance": source.get("distance"),
                },
                "tags": note.get("tags", []),
                "excerpt": note.get("excerpt", ""),
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    write_json(
        store / "memory_rankings.json",
        {
            "project": project,
            "task": task,
            "rankedAt": utc_now(),
            "ranked": ranked,
        },
    )
    print(f"Ranked {len(ranked)} notes for {project!r} -> {store / 'memory_rankings.json'}")


def sidecar_memory_path(target: Path) -> Path:
    return target / ".obsidian-memory" / SIDECAR_FILENAME


def load_sidecar_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict) and str(entry.get("text", "")).strip()]


def sidecar_memory_lines(path: Path) -> list[str]:
    entries = load_sidecar_entries(path)
    if not entries:
        return []
    shown = entries[-SIDECAR_DISPLAY_LIMIT:]
    lines = ["## Sidecar Memory", ""]
    if len(shown) < len(entries):
        lines.append(f"(Showing most recent {len(shown)} of {len(entries)} entries. Edit {path} directly to prune.)")
        lines.append("")
    for index, entry in enumerate(shown, start=1):
        text = str(entry.get("text", "")).strip()
        meta_parts = []
        if entry.get("addedAt"):
            meta_parts.append(str(entry["addedAt"]))
        if entry.get("addedBy"):
            meta_parts.append(f"by {entry['addedBy']}")
        meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
        lines.append(f"{index}. {text}{meta}")
    lines.append("")
    return lines


def generate_packet(
    store: Path,
    project: str,
    task: str,
    target: Path,
    agent: str,
    limit: int,
    max_excerpt_chars: int | None = None,
    signals_verbosity: str | None = None,
) -> Path:
    excerpt_limit = max_excerpt_chars if max_excerpt_chars is not None else 260
    sig_verbosity = signals_verbosity if signals_verbosity is not None else "full"
    rankings = load_json(store / "memory_rankings.json")
    top = rankings.get("ranked", [])[:limit]
    out_dir = target / ".obsidian-memory"
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_name = packet_filename(agent)
    packet_path = out_dir / packet_name
    status_path = out_dir / "STATUS.json"
    lines = [
        f"# {agent.title()} Session Context",
        "",
        "Source: ranked Obsidian knowledge graph",
        f"Obsidianify-Version: {OBSIDIANIFY_VERSION}",
        f"Generated: {utc_now()}",
        f"Project: {project}",
        f"Task: {task or 'general project session'}",
        "",
        "## What Was Injected",
        "",
        "This packet contains the ranked portions of the Obsidian graph that relate to this project/session. It is not the entire vault.",
        "",
        "## Ranked Memories",
        "",
    ]
    for index, item in enumerate(top, start=1):
        lines.append(f"{index}. {item.get('title')} [{item.get('score')}]")
        source = f"{item.get('vault')}/{item.get('path')}" if item.get("vault") else item.get("path")
        lines.append(f"   - Source: {source}")
        if item.get("tags"):
            lines.append(f"   - Tags: {', '.join(item.get('tags', [])[:8])}")
        why = item.get("why", {})
        why_parts = []
        if why.get("matchedTerms"):
            why_parts.append("matched terms: " + ", ".join(why.get("matchedTerms", [])[:8]))
        if why.get("anchor"):
            why_parts.append(f"nearest anchor: {why.get('anchor')} at distance {why.get('graphDistance')}")
        if why_parts:
            lines.append(f"   - Selection reason: {'; '.join(why_parts)}")
        if item.get("excerpt"):
            excerpt = item.get("excerpt", "")
            if len(excerpt) > excerpt_limit:
                excerpt = excerpt[:excerpt_limit].rstrip() + "…"
            lines.append(f"   - Why it may matter: {excerpt}")
        signals = item.get("signals", {})
        if sig_verbosity == "full":
            lines.append(
                "   - Signals: "
                + ", ".join(f"{key}={value}" for key, value in signals.items() if value)
            )
        elif sig_verbosity == "compact":
            top = sorted(signals.items(), key=lambda kv: kv[1], reverse=True)[:3]
            lines.append(
                "   - Signals: "
                + ", ".join(f"{key}={value}" for key, value in top if value)
            )
        # sig_verbosity == "none": omit signals line
        lines.append("")
    sidecar_path = sidecar_memory_path(target)
    sidecar_entries = load_sidecar_entries(sidecar_path)
    lines.extend(sidecar_memory_lines(sidecar_path))
    instruction = "Use this packet as Obsidian-derived memory for this session. If asked what was injected, summarize this packet and cite the source paths above. Do not claim to know the whole vault from this packet."
    if sidecar_entries:
        instruction += " Sidecar Memory entries are hand-maintained; treat them as directly authoritative."
    lines.extend(["## Agent Instruction", "", instruction, ""])
    packet_path.write_text("\n".join(lines), encoding="utf-8")
    write_json(
        status_path,
        {
            "status": "loaded",
            "obsidianifyVersion": OBSIDIANIFY_VERSION,
            "agent": agent,
            "project": project,
            "task": task,
            "packet": str(packet_path),
            "store": str(store.resolve()),
            "generatedAt": utc_now(),
            "memoryCount": len(top),
            "sidecarCount": len(sidecar_entries),
        },
    )
    print(f"Wrote {agent} packet -> {packet_path}")
    return packet_path


def hook_context_payload(packet_path: Path, project: str, agent: str) -> dict[str, Any]:
    packet = packet_path.read_text(encoding="utf-8", errors="ignore")
    max_chars = 12000
    if len(packet) > max_chars:
        packet = packet[:max_chars].rstrip() + "\n\n[Obsidianify packet truncated for hook context; read the packet file for full context.]"
    context = (
        "Obsidianify loaded ranked Obsidian graph memory for this session.\n\n"
        f"Project: {project}\n"
        f"Agent: {agent}\n"
        f"Packet: {packet_path}\n\n"
        "If asked what Obsidian graph memory was injected, answer from the packet below "
        "and cite source paths. Do not use Graphify or inspect files unless the user asks.\n\n"
        f"{packet}"
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }


def record_prompt_from_hook(
    config_path: Path | None,
    vault: Path | None,
    project: str,
    target: Path,
    agent: str,
    session_date: str = "",
) -> Path | None:
    config, project_name, resolved_target, _vault_path = resolve_recording_context(config_path, vault, project, target)
    raw_payload = sys.stdin.read()
    prompt_text = extract_prompt_text(raw_payload)
    if not prompt_text:
        prompt_text = "[No prompt text found in hook payload.]"
    marker = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "agent": agent,
        "project": project_name,
        "target": str(resolved_target),
        "promptHash": short_hash(prompt_text),
        "prompt": prompt_text,
    }
    append_jsonl(prompt_marker_path(config), marker)
    write_hook_audit(config, "record-prompt stored turn marker", agent, project_name, resolved_target, None)
    return None


def record_turn_from_hook(
    config_path: Path | None,
    vault: Path | None,
    project: str,
    target: Path,
    agent: str,
    session_date: str = "",
    session_log: Path | None = None,
) -> Path | None:
    config, project_name, resolved_target, vault_path = resolve_recording_context(config_path, vault, project, target)
    if not vault_path:
        write_hook_audit(config, "record-turn skipped: no session log vault", agent, project_name, resolved_target, None)
        return None
    log_path = session_log or find_latest_session_log(resolved_target, agent)
    if not log_path:
        write_hook_audit(config, "record-turn skipped: no session log found", agent, project_name, resolved_target, None)
        return None
    turns = read_completed_turns(log_path, agent)
    if not turns:
        write_hook_audit(config, f"record-turn skipped: no completed turns in {log_path}", agent, project_name, resolved_target, None)
        return None
    turn = turns[-1]
    return write_turn_note(config, vault_path, project_name, resolved_target, agent, session_date, log_path, turn)


def replay_session_log(
    config_path: Path | None,
    vault: Path | None,
    project: str,
    target: Path,
    agent: str,
    session_date: str = "",
    session_log: Path | None = None,
    limit: int = 25,
) -> list[Path]:
    if session_log is None:
        raise SystemExit("--session-log is required")
    config, project_name, resolved_target, vault_path = resolve_recording_context(config_path, vault, project, target)
    if not vault_path:
        write_hook_audit(config, "replay-session skipped: no session log vault", agent, project_name, resolved_target, None)
        return []
    written = []
    turns = read_completed_turns(session_log, agent)
    if limit > 0:
        turns = turns[-limit:]
    for turn in turns:
        out_path = write_turn_note(config, vault_path, project_name, resolved_target, agent, session_date, session_log, turn)
        if out_path:
            written.append(out_path)
    write_hook_audit(config, f"replay-session wrote {len(written)} note(s)", agent, project_name, resolved_target, None)
    return written


def write_turn_note(
    config: dict[str, Any],
    vault_path: Path,
    project_name: str,
    resolved_target: Path,
    agent: str,
    session_date: str,
    session_log: Path,
    turn: dict[str, str],
) -> Path | None:
    outcome_text = turn.get("outcome", "").strip()
    marker = latest_prompt_marker(config, project_name, resolved_target)
    prompt_text = marker.get("prompt", "").strip()
    classification = classify_turn_memory(prompt_text, outcome_text)
    turn_key = turn_hash(session_log, turn)
    if processed_turn(config, turn_key):
        write_hook_audit(config, f"record-turn skipped: duplicate turn {turn_key}", agent, project_name, resolved_target, None)
        return None
    if not classification["valuable"]:
        mark_turn_processed(config, turn_key)
        write_hook_audit(
            config,
            f"record-turn skipped: not valuable ({classification['reason']})",
            agent,
            project_name,
            resolved_target,
            None,
        )
        return None
    date_part = session_date or datetime.now().strftime("%Y-%m-%d")
    out_dir = resolve_turn_note_root(config, vault_path, project_name, resolved_target) / f"session{date_part}"
    out_dir.mkdir(parents=True, exist_ok=True)
    info_type = classification["information_type"]
    out_path = out_dir / INFORMATION_BUCKET_FILES[info_type]
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    entry = [
        f"## {timestamp}",
        "",
        f"- Agent: {agent}",
        f"- Project: {project_name}",
        f"- Target: {resolved_target}",
        f"- Source: completed turn",
        f"- Session Log: {session_log}",
        f"- Turn Id: {turn.get('turn_id', '')}",
        f"- Classification: valuable",
        f"- Information Type: {info_type}",
        f"- Reason: {classification['reason']}",
        f"- Trigger Prompt Hash: {marker.get('promptHash', '')}",
        "",
        "### Prompt Memory",
        "",
        summarize_prompt_text(prompt_text),
        "",
        "### Assistant Outcome",
        "",
        summarize_outcome_text(outcome_text),
        "",
    ]
    with out_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(entry))
    mark_turn_processed(config, turn_key)
    write_hook_audit(config, f"record-turn wrote {info_type.lower()} note", agent, project_name, resolved_target, out_path)
    return out_path


def classify_prompt_write(prompt_text: str) -> dict[str, Any]:
    return classify_turn_memory(prompt_text, "")


def classify_turn_write(text: str) -> dict[str, Any]:
    return classify_turn_memory("", text)


def classify_turn_memory(prompt_text: str, outcome_text: str) -> dict[str, Any]:
    prompt_normalized = re.sub(r"\s+", " ", prompt_text).strip()
    outcome_normalized = re.sub(r"\s+", " ", outcome_text).strip()
    combined = " ".join(part for part in (prompt_normalized, outcome_normalized) if part).strip()
    lowered = combined.lower()
    prompt_lowered = prompt_normalized.lower()
    outcome_lowered = outcome_normalized.lower()
    token_set = set(re.findall(r"[a-z0-9_+-]+", lowered))
    prompt_tokens = set(re.findall(r"[a-z0-9_+-]+", prompt_lowered))
    outcome_tokens = set(re.findall(r"[a-z0-9_+-]+", outcome_lowered))
    if not lowered:
        return {"valuable": False, "information_type": "Other", "reason": "empty"}
    if prompt_lowered in LOW_VALUE_PROMPTS and (not outcome_lowered or outcome_lowered in LOW_VALUE_PROMPTS):
        return {"valuable": False, "information_type": "Other", "reason": "low-value acknowledgement"}
    if is_noise_payload(outcome_lowered, outcome_tokens) or (
        is_noise_payload(prompt_lowered, prompt_tokens) and not has_explicit_memory_intent(prompt_lowered)
    ):
        return {"valuable": False, "information_type": "Other", "reason": "routine automation/delegation noise"}
    scores = information_scores(lowered, token_set)
    if prompt_tokens & PREFERENCE_TERMS and any(term in lowered for term in ("default", "prefer", "always", "should")):
        scores["Configuration"] += 1
    explicit_memory = has_explicit_memory_intent(prompt_lowered)
    signal_terms = token_set & (VALUABLE_TERMS | OUTCOME_TERMS | ARCHITECTURE_TERMS | CONFIGURATION_TERMS | DESIGN_TERMS)
    valuable = explicit_memory or bool(signal_terms) or max(scores.values(), default=0) >= 2
    if not valuable:
        return {"valuable": False, "information_type": "Other", "reason": "no durable signal"}
    info_type = max(scores, key=scores.get)
    if scores[info_type] <= 0:
        info_type = "Other"
    if explicit_memory:
        reason = "explicit user memory intent"
    elif outcome_tokens & OUTCOME_TERMS:
        reason = "durable implementation outcome"
    else:
        reason = "durable prompt/outcome signal"
    return {"valuable": True, "information_type": info_type, "reason": reason}


def has_explicit_memory_intent(lowered_prompt: str) -> bool:
    return any(phrase in lowered_prompt for phrase in MEMORY_INTENT_PHRASES)


def information_scores(lowered: str, token_set: set[str]) -> dict[str, int]:
    scores = {
        "Architecture": score_terms(lowered, token_set, ARCHITECTURE_TERMS),
        "Configuration": score_terms(lowered, token_set, CONFIGURATION_TERMS | {"hook trust", "hooks.json", "config.toml"}),
        "Design": score_terms(lowered, token_set, DESIGN_TERMS),
        "Other": 0,
    }
    outcome_hits = len(token_set & OUTCOME_TERMS)
    if outcome_hits:
        scores["Architecture"] += outcome_hits
    if any(term in lowered for term in ("validated", "validator", "scaffold", "maps-data", "phase skill", "post-turn", "runtime gate")):
        scores["Architecture"] += 3
    if any(term in lowered for term in ("voice profile", "profile page", "layout", "ui", "interface")):
        scores["Design"] += 3
    if any(term in lowered for term in ("config", "hook", "toml", "json", "path")) and scores["Architecture"] < 3:
        scores["Configuration"] += 1
    return scores


def score_terms(lowered: str, token_set: set[str], terms: set[str]) -> int:
    score = len(token_set & terms)
    score += sum(1 for term in terms if " " in term and term in lowered)
    return score


def is_noise_payload(lowered: str, token_set: set[str]) -> bool:
    if any(marker in lowered for marker in DELEGATION_MARKERS):
        return True
    if token_set & NOISE_TERMS and "unchanged" in token_set and "outcome" not in token_set:
        return True
    unchanged_lines = sum(1 for line in lowered.splitlines() if "handoff-check" in line and "unchanged" in line)
    return unchanged_lines >= 3


def resolve_recording_context(
    config_path: Path | None,
    vault: Path | None,
    project: str,
    target: Path,
) -> tuple[dict[str, Any], str, Path, Path | None]:
    config: dict[str, Any] = {}
    if config_path:
        config = load_json(config_path)
    resolved_target = resolve_hook_target(target, config)
    if project:
        project_name = project
    elif config:
        project_name = detect_project_name(resolved_target, config)
    else:
        project_name = resolved_target.name
    return config, project_name, resolved_target, resolve_session_log_vault(config, vault, project_name, resolved_target)


def session_log_root(agent: str) -> Path | None:
    if agent == "codex":
        return Path.home() / ".codex" / "sessions"
    if agent == "claude":
        return Path.home() / ".claude" / "projects"
    return None


def find_latest_session_log(target: Path, agent: str) -> Path | None:
    root = session_log_root(agent)
    if root is None or not root.exists():
        return None
    candidates = sorted(root.rglob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates[:80]:
        cwd = session_log_cwd(candidate)
        if cwd and (cwd == target or target in cwd.parents or cwd in target.parents):
            return candidate
    # codex: legacy fallback to newest log. claude logs for every project live under one
    # root, so a blind newest-fallback would bleed another project's turn into this vault.
    # Require a cwd match for claude instead.
    if agent == "codex":
        return candidates[0] if candidates else None
    return None


def session_log_cwd(path: Path) -> Path | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                # claude: cwd is stamped on every top-level event.
                cwd = event.get("cwd")
                # codex: cwd lives in the session_meta payload.
                if not cwd and event.get("type") == "session_meta":
                    cwd = event.get("payload", {}).get("cwd")
                if cwd:
                    return Path(str(cwd)).resolve()
    except Exception:
        return None
    return None


def read_completed_turns(path: Path, agent: str = "codex") -> list[dict[str, str]]:
    if agent == "claude":
        return read_claude_turns(path)
    return read_codex_turns(path)


def read_codex_turns(path: Path) -> list[dict[str, str]]:
    turns = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                payload = event.get("payload", {})
                if event.get("type") != "event_msg" or payload.get("type") != "task_complete":
                    continue
                outcome = str(payload.get("last_agent_message", "")).strip()
                if not outcome:
                    continue
                turns.append(
                    {
                        "turn_id": str(payload.get("turn_id", "")),
                        "timestamp": str(event.get("timestamp", "")),
                        "outcome": outcome,
                    }
                )
    except FileNotFoundError:
        return []
    return turns


def read_claude_turns(path: Path) -> list[dict[str, str]]:
    # A completed claude turn is an assistant message that stopped to hand control back
    # to the user (stop_reason == "end_turn"); messages that stop for "tool_use" are
    # mid-turn. The outcome is the concatenation of that message's text blocks.
    turns = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "assistant":
                    continue
                message = event.get("message", {})
                if message.get("stop_reason") != "end_turn":
                    continue
                outcome = "".join(
                    block.get("text", "")
                    for block in message.get("content", [])
                    if isinstance(block, dict) and block.get("type") == "text"
                ).strip()
                if not outcome:
                    continue
                turns.append(
                    {
                        "turn_id": str(event.get("uuid", "")),
                        "timestamp": str(event.get("timestamp", "")),
                        "outcome": outcome,
                    }
                )
    except FileNotFoundError:
        return []
    return turns


def summarize_outcome_text(text: str, limit: int = 1800) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n\n[Outcome truncated by Obsidianify.]"


def summarize_prompt_text(text: str, limit: int = 700) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not cleaned:
        return "[No prompt marker found.]"
    if wants_full_transcript_capture(cleaned):
        return summarize_outcome_text(cleaned, 1800).replace(
            "[Outcome truncated by Obsidianify.]",
            "[Prompt transcript truncated by Obsidianify.]",
        )
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    memory_lines = [
        line
        for line in lines
        if any(term in line.lower() for term in MEMORY_INTENT_PHRASES | VALUABLE_TERMS | CONFIGURATION_TERMS | ARCHITECTURE_TERMS | DESIGN_TERMS)
    ]
    distilled = "\n".join(memory_lines[:6]) if memory_lines else cleaned
    if len(distilled) <= limit:
        return distilled
    return distilled[:limit].rstrip() + "\n\n[Prompt excerpt truncated by Obsidianify.]"


def wants_full_transcript_capture(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in ("full transcript", "verbatim transcript", "capture the full prompt"))


def prompt_marker_path(config: dict[str, Any]) -> Path:
    store = Path(config.get("store", str(Path.home() / ".obsidianify" / "store")))
    return store / "prompt-markers.jsonl"


def latest_prompt_marker(config: dict[str, Any], project: str, target: Path) -> dict[str, str]:
    path = prompt_marker_path(config)
    if not path.exists():
        return {}
    latest: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            marker = json.loads(raw)
            if marker.get("project") == project and marker.get("target") == str(target):
                latest = {str(key): str(value) for key, value in marker.items()}
    except Exception:
        return latest
    return latest


def turn_state_path(config: dict[str, Any]) -> Path:
    store = Path(config.get("store", str(Path.home() / ".obsidianify" / "store")))
    return store / "turn-writes.json"


def processed_turn(config: dict[str, Any], turn_key: str) -> bool:
    path = turn_state_path(config)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return turn_key in set(data.get("processed", []))


def mark_turn_processed(config: dict[str, Any], turn_key: str) -> None:
    path = turn_state_path(config)
    data = {"processed": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            pass
    processed = list(dict.fromkeys([*data.get("processed", []), turn_key]))
    data["processed"] = processed[-5000:]
    write_json(path, data)


def turn_hash(session_log: Path, turn: dict[str, str]) -> str:
    return short_hash(f"{session_log.resolve()}::{turn.get('turn_id')}::{turn.get('outcome')}")


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=True) + "\n")


def resolve_hook_target(target: Path, config: dict[str, Any]) -> Path:
    if str(target) not in {"", "."}:
        return target.resolve()
    cwd = Path.cwd().resolve()
    target_overrides = config.get("hookTargets", {})
    if isinstance(target_overrides, dict):
        for configured in target_overrides.values():
            path = Path(str(configured)).expanduser().resolve()
            if cwd == path or path in cwd.parents:
                return path
    projects = config.get("projects", {})
    if isinstance(projects, dict):
        for data in projects.values():
            if not isinstance(data, dict) or not data.get("path"):
                continue
            path = Path(str(data["path"])).expanduser().resolve()
            if cwd == path or path in cwd.parents:
                return path
    return cwd


def resolve_session_log_vault(
    config: dict[str, Any],
    vault: Path | None,
    project_name: str = "",
    target: Path | None = None,
) -> Path | None:
    if vault:
        return vault.resolve()
    if project_name and target is not None:
        project = project_config(config, project_name, target)
        if project:
            for key in ("vaultPath", "sessionLogVault", "recordingVault"):
                configured = project.get(key)
                if configured:
                    return Path(str(configured)).expanduser().resolve()
    configured = config.get("sessionLogVault")
    if configured:
        return Path(configured).resolve()
    vaults = config_vaults(config) if config else []
    return vaults[0].resolve() if vaults else None


def resolve_turn_note_root(config: dict[str, Any], vault_path: Path, project_name: str, target: Path) -> Path:
    project = project_config(config, project_name, target)
    if project:
        for key in ("writeRoot", "sessionWriteRoot", "turnNoteRoot"):
            configured = project.get(key)
            if configured:
                return Path(str(configured)).expanduser().resolve()
    return vault_path / safe_obsidian_segment(project_name)


def project_config(config: dict[str, Any], project_name: str, target: Path) -> dict[str, Any] | None:
    projects = config.get("projects", {})
    if not isinstance(projects, dict):
        return None
    exact = projects.get(project_name)
    if isinstance(exact, dict):
        return exact
    resolved_target = target.resolve()
    for data in projects.values():
        if not isinstance(data, dict) or not data.get("path"):
            continue
        configured_path = Path(str(data["path"])).expanduser().resolve()
        if resolved_target == configured_path or configured_path in resolved_target.parents:
            return data
    return None


def write_hook_audit(
    config: dict[str, Any],
    message: str,
    agent: str,
    project: str,
    target: Path,
    output: Path | None,
) -> None:
    audit_path = Path(config.get("hookAuditLog", str(Path.home() / ".obsidianify" / "hook-audit.log")))
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "message": message,
        "agent": agent,
        "project": project,
        "target": str(target),
        "output": str(output) if output else "",
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=True) + "\n")


def extract_prompt_text(raw_payload: str) -> str:
    text = raw_payload.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    found = find_prompt_value(payload)
    if found:
        return found
    return json.dumps(payload, indent=2, ensure_ascii=False)


def find_prompt_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("prompt", "userPrompt", "message", "content", "text"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
        for item in value.values():
            found = find_prompt_value(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_prompt_value(item)
            if found:
                return found
    return ""


def safe_obsidian_segment(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    return cleaned or "project"


def packet_filename(agent: str) -> str:
    if agent == "codex":
        return "CODEX_SESSION_CONTEXT.md"
    if agent == "claude":
        return "CLAUDE_SESSION_CONTEXT.md"
    if agent == "cowork":
        return "COWORK_SESSION_CONTEXT.md"
    raise ValueError(f"Unsupported agent: {agent}")


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip()
    body = text[end + 4 :].lstrip()
    parsed = parse_yaml_frontmatter(raw)
    if parsed is not None:
        return parsed, body
    return parse_frontmatter_fallback(raw), body


def parse_yaml_frontmatter(raw: str) -> dict[str, Any] | None:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        data = yaml.safe_load(raw) or {}
    except Exception:
        return None
    return normalize_frontmatter(data) if isinstance(data, dict) else {}


def parse_frontmatter_fallback(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key = ""
    for line in raw.splitlines():
        if current_key and line.startswith((" ", "\t")):
            stripped = line.strip()
            if stripped.startswith("- "):
                data.setdefault(current_key, []).append(stripped[2:].strip().strip('"').strip("'"))
            continue
        current_key = ""
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            data[key] = [part.strip().strip('"').strip("'") for part in value[1:-1].split(",") if part.strip()]
        elif value == "":
            data[key] = []
            current_key = key
        else:
            data[key] = value.strip('"').strip("'")
    return data


def normalize_frontmatter(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_frontmatter(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_frontmatter(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def parse_wikilinks(text: str) -> list[str]:
    links = []
    for raw in WIKILINK_RE.findall(text):
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            links.append(target)
    return sorted(set(links))


def note_search_text(note: dict[str, Any]) -> str:
    frontmatter = note.get("frontmatter", {})
    frontmatter_values = []
    if isinstance(frontmatter, dict):
        for value in frontmatter.values():
            if isinstance(value, list):
                frontmatter_values.extend(str(item) for item in value)
            elif isinstance(value, (str, int, float)):
                frontmatter_values.append(str(value))
    return " ".join(
        [
            note.get("title", ""),
            note.get("path", ""),
            note.get("folder", ""),
            " ".join(str(item) for item in note.get("aliases", [])),
            " ".join(str(item) for item in note.get("tags", [])),
            " ".join(frontmatter_values),
            note.get("excerpt", ""),
        ]
    )


def graph_adjacency(edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target or str(target).startswith("unresolved:"):
            continue
        adjacency[source].add(target)
        adjacency[target].add(source)
    return adjacency


def graph_proximity(
    anchor_scores: dict[str, float],
    adjacency: dict[str, set[str]],
    max_distance: int = 3,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    scores: dict[str, float] = {}
    sources: dict[str, dict[str, Any]] = {}
    queue: deque[tuple[str, str, int, float]] = deque(
        [
            (anchor_id, anchor_id, 0, min(score, 1.0))
            for anchor_id, score in anchor_scores.items()
        ]
    )
    seen: set[tuple[str, str]] = set()
    while queue:
        node_id, anchor_id, distance, anchor_score = queue.popleft()
        key = (node_id, anchor_id)
        if key in seen:
            continue
        seen.add(key)
        distance_score = anchor_score / (distance + 1)
        if distance_score > scores.get(node_id, 0.0):
            scores[node_id] = distance_score
            sources[node_id] = {"anchor": anchor_id, "distance": distance}
        if distance >= max_distance:
            continue
        for neighbor in adjacency.get(node_id, set()):
            queue.append((neighbor, anchor_id, distance + 1, anchor_score))
    return scores, sources


def compact_excerpt(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", re.sub(r"```.*?```", " ", text, flags=re.S)).strip()
    return cleaned[:260]


def terms_for(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "this", "that", "session", "project"}
    return {term for term in re.findall(r"[a-z0-9_]+", text.lower()) if len(term) > 2 and term not in stop}


def text_relevance(terms: set[str], text: str) -> float:
    if not terms:
        return 0.0
    haystack = set(re.findall(r"[a-z0-9_]+", text.lower()))
    overlap = terms & haystack
    return min(len(overlap) / math.sqrt(len(terms)), 1.0)


def freshness_score(value: str) -> float:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return 0.5
    age_days = max((datetime.now(timezone.utc) - dt).days, 0)
    return max(0.2, 1.0 - min(age_days, 365) / 365)


def bridge_score(note: dict[str, Any], degree: int, incoming: int, outgoing: int) -> float:
    text = f"{note.get('title', '')} {note.get('path', '')}".lower()
    bridge_terms = ("bridge", "handoff", "context", "memory", "injection", "codex", "claude", "rag")
    base = 0.5 if incoming and outgoing else 0.0
    if any(term in text for term in bridge_terms):
        base += 0.35
    if degree >= 8:
        base += 0.15
    return min(base, 1.0)


def evidence_score(note: dict[str, Any]) -> float:
    if note.get("frontmatter", {}).get("status") in {"canonical", "decision", "source"}:
        return 1.0
    if note.get("excerpt"):
        return 0.75
    return 0.4


def note_id(vault: str, path: str) -> str:
    return "note:" + slug(vault) + ":" + slug(path)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def write_rag_documents(path: Path, notes: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for note in notes:
        text = "\n".join(
            part
            for part in [
                f"Title: {note.get('title', '')}",
                f"Path: {note.get('path', '')}",
                f"Tags: {', '.join(note.get('tags', []))}" if note.get("tags") else "",
                f"Links: {', '.join(note.get('links', []))}" if note.get("links") else "",
                "",
                note.get("excerpt", ""),
            ]
            if part
        )
        doc = {
            "id": note.get("id"),
            "text": text,
            "metadata": {
                "source": "obsidian",
                "vault": note.get("vault", ""),
                "vaultPath": note.get("vaultPath", ""),
                "path": note.get("path", ""),
                "title": note.get("title", ""),
                "folder": note.get("folder", ""),
                "tags": note.get("tags", []),
                "aliases": note.get("aliases", []),
                "links": note.get("links", []),
                "modifiedAt": note.get("modifiedAt", ""),
            },
        }
        lines.append(json.dumps(doc, ensure_ascii=True))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
