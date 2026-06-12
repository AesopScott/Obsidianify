"""Obsidianify CLI.

Local-first MVP:
- parse an Obsidian vault into graph-shaped JSON
- rank the whole graph
- generate a Codex or Claude session context packet
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_/-]+)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
    packet.add_argument("--agent", choices=("codex", "claude"), required=True)
    packet.add_argument("--limit", default=20, type=int)

    refresh = sub.add_parser("refresh", help="Sync, rank, and write a session packet.")
    refresh.add_argument("--vault", action="append", required=True, type=Path)
    refresh.add_argument("--store", default=Path(".omi-store"), type=Path)
    refresh.add_argument("--project", required=True)
    refresh.add_argument("--task", default="")
    refresh.add_argument("--target", required=True, type=Path)
    refresh.add_argument("--agent", choices=("codex", "claude"), required=True)
    refresh.add_argument("--limit", default=20, type=int)

    refresh_global = sub.add_parser("refresh-global", help="Refresh memory for the current working directory using global config.")
    refresh_global.add_argument("--config", default=Path.home() / ".obsidianify" / "config.json", type=Path)
    refresh_global.add_argument("--agent", choices=("codex", "claude"), required=True)
    refresh_global.add_argument("--limit", default=20, type=int)
    refresh_global.add_argument(
        "--emit-hook-context",
        action="store_true",
        help="Print hookSpecificOutput JSON for agents that accept hook-injected context.",
    )

    args = parser.parse_args()
    if args.command == "sync":
        sync_vaults(args.vault, args.store)
    elif args.command == "rank":
        rank_graph(args.store, args.project, args.task)
    elif args.command == "packet":
        generate_packet(args.store, args.project, args.task, args.target, args.agent, args.limit)
    elif args.command == "refresh":
        sync_vaults(args.vault, args.store)
        rank_graph(args.store, args.project, args.task)
        generate_packet(args.store, args.project, args.task, args.target, args.agent, args.limit)
    elif args.command == "refresh-global":
        refresh_from_global_config(args.config, args.agent, args.limit, args.emit_hook_context)
    return 0


def refresh_from_global_config(config_path: Path, agent: str, limit: int, emit_hook_context: bool = False) -> None:
    config = load_json(config_path)
    target = Path.cwd().resolve()
    project = detect_project_name(target, config)
    task = config.get("defaultTask", "general project session")
    vaults = config_vaults(config)
    store = Path(config.get("store", str(Path.home() / ".obsidianify" / "store")))
    if emit_hook_context:
        with contextlib.redirect_stdout(io.StringIO()):
            sync_vaults(vaults, store)
            rank_graph(store, project, task)
            packet_path = generate_packet(store, project, task, target, agent, limit)
        print(json.dumps(hook_context_payload(packet_path, project, agent), ensure_ascii=True))
    else:
        sync_vaults(vaults, store)
        rank_graph(store, project, task)
        generate_packet(store, project, task, target, agent, limit)


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
        aliases = frontmatter.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        tags = sorted(set(frontmatter.get("tags", []) if isinstance(frontmatter.get("tags"), list) else []))
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
    max_degree = max(degree.values(), default=1)
    max_incoming = max(incoming.values(), default=1)
    ranked = []
    for note in notes:
        text = " ".join(
            [
                note.get("title", ""),
                note.get("path", ""),
                " ".join(note.get("tags", [])),
                note.get("excerpt", ""),
            ]
        )
        relevance = text_relevance(terms, text)
        centrality = degree[note["id"]] / max_degree
        authority = incoming[note["id"]] / max_incoming
        freshness = freshness_score(note.get("modifiedAt", ""))
        bridge = bridge_score(note, degree[note["id"]], incoming[note["id"]], outgoing[note["id"]])
        evidence = evidence_score(note)
        score = (
            relevance * 0.35
            + centrality * 0.18
            + authority * 0.14
            + freshness * 0.10
            + bridge * 0.10
            + evidence * 0.08
            + min(len(note.get("tags", [])) / 8, 1.0) * 0.05
        )
        ranked.append(
            {
                "id": note["id"],
                "title": note.get("title", ""),
                "path": note.get("path", ""),
                "score": round(score, 4),
                "signals": {
                    "relevance": round(relevance, 4),
                    "centrality": round(centrality, 4),
                    "authority": round(authority, 4),
                    "freshness": round(freshness, 4),
                    "bridge": round(bridge, 4),
                    "evidence": round(evidence, 4),
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


def generate_packet(store: Path, project: str, task: str, target: Path, agent: str, limit: int) -> Path:
    rankings = load_json(store / "memory_rankings.json")
    top = rankings.get("ranked", [])[:limit]
    out_dir = target / ".obsidian-memory"
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_name = "CODEX_SESSION_CONTEXT.md" if agent == "codex" else "CLAUDE_SESSION_CONTEXT.md"
    packet_path = out_dir / packet_name
    status_path = out_dir / "STATUS.json"
    lines = [
        f"# {agent.title()} Session Context",
        "",
        "Source: ranked Obsidian knowledge graph",
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
        lines.append(f"   - Source: {item.get('path')}")
        if item.get("tags"):
            lines.append(f"   - Tags: {', '.join(item.get('tags', [])[:8])}")
        if item.get("excerpt"):
            lines.append(f"   - Why it may matter: {item.get('excerpt')}")
        signals = item.get("signals", {})
        lines.append(
            "   - Signals: "
            + ", ".join(f"{key}={value}" for key, value in signals.items() if value)
        )
        lines.append("")
    lines.extend(
        [
            "## Agent Instruction",
            "",
            "Use this packet as Obsidian-derived memory for this session. If asked what was injected, summarize this packet and cite the source paths above. Do not claim to know the whole vault from this packet.",
            "",
        ]
    )
    packet_path.write_text("\n".join(lines), encoding="utf-8")
    write_json(
        status_path,
        {
            "status": "loaded",
            "agent": agent,
            "project": project,
            "task": task,
            "packet": str(packet_path),
            "store": str(store.resolve()),
            "generatedAt": utc_now(),
            "memoryCount": len(top),
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


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip()
    body = text[end + 4 :].lstrip()
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            data[key] = [part.strip().strip('"').strip("'") for part in value[1:-1].split(",") if part.strip()]
        else:
            data[key] = value.strip('"').strip("'")
    return data, body


def parse_wikilinks(text: str) -> list[str]:
    links = []
    for raw in WIKILINK_RE.findall(text):
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            links.append(target)
    return sorted(set(links))


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
