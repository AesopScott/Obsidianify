"""Install Obsidianify globally for Codex and Claude Code."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OMI = ROOT / "scripts" / "omi.py"
OBSIDIANIFY_HOME = Path.home() / ".obsidianify"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", action="append", required=True, type=Path)
    parser.add_argument("--agent", action="append", choices=("codex", "claude"), required=True)
    parser.add_argument("--default-task", default="general project session")
    args = parser.parse_args()

    vaults = [vault.resolve() for vault in args.vault]
    for vault in vaults:
        if not vault.exists():
            raise SystemExit(f"Vault not found: {vault}")

    OBSIDIANIFY_HOME.mkdir(parents=True, exist_ok=True)
    config = {
        "vaults": [
            {"name": vault.name, "path": str(vault), "enabled": True}
            for vault in vaults
        ],
        "store": str(OBSIDIANIFY_HOME / "store"),
        "defaultTask": args.default_task,
        "repo": str(ROOT),
    }
    write_json(OBSIDIANIFY_HOME / "config.json", config)

    for agent in args.agent:
        if agent == "codex":
            install_codex_global()
        else:
            install_claude_global()

    print(f"Installed Obsidianify globally for: {', '.join(args.agent)}")
    print(f"Config: {OBSIDIANIFY_HOME / 'config.json'}")
    return 0


def install_codex_global() -> None:
    codex_home = Path.home() / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    hooks_path = codex_home / "hooks.json"
    hooks = read_json_object(hooks_path)
    add_session_start_hook(
        hooks,
        command=global_command("codex"),
        status_message="Refreshing Obsidianify memory packet",
    )
    write_json(hooks_path, hooks)
    append_block(
        codex_home / "AGENTS.md",
        "Obsidianify",
        """
## Obsidianify

When asked what Obsidian graph memory is loaded or injected, first read:

`.obsidian-memory/STATUS.json`

Then read:

`.obsidian-memory/CODEX_SESSION_CONTEXT.md`

Answer from that packet only. Do not use Graphify or inspect other files unless the user asks you to.

If the packet is missing, say: "No Obsidianify session packet is available in this project yet."
""".strip(),
    )


def install_claude_global() -> None:
    claude_home = Path.home() / ".claude"
    claude_home.mkdir(parents=True, exist_ok=True)
    settings_path = claude_home / "settings.json"
    settings = read_json_object(settings_path)
    add_session_start_hook(settings, command=global_command("claude"))
    write_json(settings_path, settings)
    append_block(
        claude_home / "CLAUDE.md",
        "Obsidianify",
        """
## Obsidianify

When asked what Obsidian graph memory is loaded or injected, first read:

`.obsidian-memory/STATUS.json`

Then read:

`.obsidian-memory/CLAUDE_SESSION_CONTEXT.md`

Answer from that packet only. Do not inspect other files unless the user asks you to.

If the packet is missing, say: "No Obsidianify session packet is available in this project yet."
""".strip(),
    )


def add_session_start_hook(settings: dict[str, Any], command: str, status_message: str | None = None) -> None:
    settings.setdefault("hooks", {})
    session_hooks = settings["hooks"].setdefault("SessionStart", [])
    hook_entry: dict[str, Any] = {"type": "command", "command": command}
    if status_message:
        hook_entry["statusMessage"] = status_message
    new_group = {"matcher": "startup|resume", "hooks": [hook_entry]}
    session_hooks[:] = [
        group
        for group in session_hooks
        if "Obsidianify" not in json.dumps(group) and str(OMI) not in json.dumps(group)
    ]
    session_hooks.append(new_group)


def global_command(agent: str) -> str:
    return (
        f'"{sys.executable}" "{OMI}" refresh-global '
        f'--config "{OBSIDIANIFY_HOME / "config.json"}" '
        f'--agent "{agent}" '
        f'--emit-hook-context'
    )


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def append_block(path: Path, label: str, content: str) -> None:
    marker_start = f"<!-- {label}: start -->"
    marker_end = f"<!-- {label}: end -->"
    block = f"\n\n{marker_start}\n{content}\n{marker_end}\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker_start in existing and marker_end in existing:
        before, rest = existing.split(marker_start, 1)
        _, after = rest.split(marker_end, 1)
        path.write_text(before.rstrip() + block + after.lstrip(), encoding="utf-8")
    else:
        path.write_text(existing.rstrip() + block, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
