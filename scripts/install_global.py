"""Install Obsidianify globally for Codex and Claude Code."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OMI = ROOT / "scripts" / "omi.py"
OBSIDIANIFY_HOME = Path.home() / ".obsidianify"
OBSIDIANIFY_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
OBSIDIANIFY_UPDATE_SOURCE = "https://github.com/aesopscott/obsidianify"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", action="append", required=True, type=Path)
    parser.add_argument("--agent", action="append", choices=("codex", "claude", "cowork"), required=True)
    parser.add_argument("--default-task", default="general project session")
    args = parser.parse_args()

    vaults = [vault.resolve() for vault in args.vault]
    for vault in vaults:
        if not vault.exists():
            raise SystemExit(f"Vault not found: {vault}")

    OBSIDIANIFY_HOME.mkdir(parents=True, exist_ok=True)
    config_path = OBSIDIANIFY_HOME / "config.json"
    config = read_json_object(config_path)
    config.update(
        {
            "vaults": [
                {"name": vault.name, "path": str(vault), "enabled": True}
                for vault in vaults
            ],
            "store": str(OBSIDIANIFY_HOME / "store"),
            "defaultTask": config.get("defaultTask", args.default_task),
            "hookAuditLog": str(OBSIDIANIFY_HOME / "hook-audit.log"),
            "repo": str(ROOT),
            "version": OBSIDIANIFY_VERSION,
            "updateSource": OBSIDIANIFY_UPDATE_SOURCE,
        }
    )
    write_json(OBSIDIANIFY_HOME / "config.json", config)

    for agent in args.agent:
        if agent == "codex":
            install_codex_global()
        elif agent == "claude":
            install_claude_global()
        else:
            install_cowork_global()

    print(f"Installed Obsidianify {OBSIDIANIFY_VERSION} globally for: {', '.join(args.agent)}")
    print(f"Update source: {OBSIDIANIFY_UPDATE_SOURCE}")
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
        status_message=f"Refreshing Obsidianify {OBSIDIANIFY_VERSION} memory packet",
    )
    add_user_prompt_hook(
        hooks,
        command=global_prompt_command("codex"),
        status_message=f"Recording Obsidianify {OBSIDIANIFY_VERSION} prompt marker",
    )
    add_stop_hook(
        hooks,
        command=global_turn_command("codex"),
        status_message=f"Recording Obsidianify {OBSIDIANIFY_VERSION} turn memory",
    )
    write_json(hooks_path, hooks)
    append_block(
        codex_home / "AGENTS.md",
        "Obsidianify",
        f"""
## Obsidianify

Version: {OBSIDIANIFY_VERSION}

Authoritative update source: {OBSIDIANIFY_UPDATE_SOURCE}

When asked what Obsidian graph memory is loaded or injected, first read:

`.obsidian-memory/STATUS.json`

Then read:

`.obsidian-memory/CODEX_SESSION_CONTEXT.md`

Answer from that packet only. Do not use Graphify or inspect other files unless the user asks you to.

Obsidianify records prompt markers locally and classifies the latest prompt plus completed assistant outcome before writing turn-memory notes. Notes should contain distilled prompt memory and assistant outcome summaries, not raw full prompt transcripts unless the user explicitly asks for transcript capture.

Project-specific note routing comes from `~/.obsidianify/config.json`, including `projects.<name>.vaultPath` and `projects.<name>.writeRoot`.

If the packet is missing, say: "No Obsidianify session packet is available in this project yet."
""".strip(),
    )


def install_claude_global() -> None:
    claude_home = Path.home() / ".claude"
    claude_home.mkdir(parents=True, exist_ok=True)
    settings_path = claude_home / "settings.json"
    settings = read_json_object(settings_path)
    add_session_start_hook(settings, command=global_command("claude"), status_message=f"Refreshing Obsidianify {OBSIDIANIFY_VERSION} memory packet")
    add_user_prompt_hook(settings, command=global_prompt_command("claude"), status_message=f"Recording Obsidianify {OBSIDIANIFY_VERSION} prompt marker")
    add_stop_hook(settings, command=global_turn_command("claude"), status_message=f"Recording Obsidianify {OBSIDIANIFY_VERSION} turn memory")
    write_json(settings_path, settings)
    append_block(
        claude_home / "CLAUDE.md",
        "Obsidianify",
        f"""
## Obsidianify

Version: {OBSIDIANIFY_VERSION}

Authoritative update source: {OBSIDIANIFY_UPDATE_SOURCE}

When asked what Obsidian graph memory is loaded or injected, first read:

`.obsidian-memory/STATUS.json`

Then read:

`.obsidian-memory/CLAUDE_SESSION_CONTEXT.md`

Answer from that packet only. Do not inspect other files unless the user asks you to.

Obsidianify records prompt markers locally and classifies the latest prompt plus completed assistant outcome before writing turn-memory notes. Notes should contain distilled prompt memory and assistant outcome summaries, not raw full prompt transcripts unless the user explicitly asks for transcript capture.

Project-specific note routing comes from `~/.obsidianify/config.json`, including `projects.<name>.vaultPath` and `projects.<name>.writeRoot`.

If the packet is missing, say: "No Obsidianify session packet is available in this project yet."
""".strip(),
    )


def install_cowork_global() -> None:
    note_path = OBSIDIANIFY_HOME / "COWORK.md"
    note_path.write_text(
        f"""
# Obsidianify Cowork Workaround

Version: {OBSIDIANIFY_VERSION}

Authoritative update source: {OBSIDIANIFY_UPDATE_SOURCE}

Cowork does not appear to run Claude Code's global `~/.claude/settings.json` hooks.

To use Obsidianify with Cowork, run this from inside the project before asking Cowork about Obsidian memory:

```bash
python3 /path/to/Obsidianify/scripts/omi.py refresh-global \\
  --config "$HOME/.obsidianify/config.json" \\
  --agent cowork
```

Then ask Cowork:

```text
Read .obsidian-memory/COWORK_SESSION_CONTEXT.md and tell me exactly what Obsidian graph memory was injected. Answer only from that packet.
```
""".strip()
        + "\n",
        encoding="utf-8",
    )


def add_session_start_hook(settings: dict[str, Any], command: str, status_message: str | None = None) -> None:
    settings.setdefault("hooks", {})
    session_hooks = settings["hooks"].setdefault("SessionStart", [])
    hook_entry: dict[str, Any] = {"type": "command", "command": command}
    if status_message:
        hook_entry["statusMessage"] = status_message
    new_group = {"matcher": "startup|resume", "hooks": [hook_entry]}
    remove_obsidianify_hooks(session_hooks)
    session_hooks.append(new_group)


def add_user_prompt_hook(settings: dict[str, Any], command: str, status_message: str | None = None) -> None:
    settings.setdefault("hooks", {})
    prompt_hooks = settings["hooks"].setdefault("UserPromptSubmit", [])
    hook_entry: dict[str, Any] = {"type": "command", "command": command}
    if status_message:
        hook_entry["statusMessage"] = status_message
    new_group = {"hooks": [hook_entry]}
    remove_obsidianify_hooks(prompt_hooks)
    prompt_hooks.append(new_group)


def add_stop_hook(settings: dict[str, Any], command: str, status_message: str | None = None) -> None:
    settings.setdefault("hooks", {})
    stop_hooks = settings["hooks"].setdefault("Stop", [])
    hook_entry: dict[str, Any] = {"type": "command", "command": command}
    if status_message:
        hook_entry["statusMessage"] = status_message
    new_group = {"hooks": [hook_entry]}
    remove_obsidianify_hooks(stop_hooks)
    stop_hooks.append(new_group)


def remove_obsidianify_hooks(groups: list[dict[str, Any]]) -> None:
    kept_groups = []
    for group in groups:
        hooks = group.get("hooks")
        if not isinstance(hooks, list):
            kept_groups.append(group)
            continue
        filtered_hooks = [
            hook
            for hook in hooks
            if "Obsidianify" not in json.dumps(hook) and str(OMI) not in json.dumps(hook)
        ]
        if filtered_hooks:
            group["hooks"] = filtered_hooks
            kept_groups.append(group)
    groups[:] = kept_groups


def global_command(agent: str) -> str:
    return hook_command(
        f'"{sys.executable}" "{OMI}" refresh-global '
        f'--config "{OBSIDIANIFY_HOME / "config.json"}" '
        f'--agent "{agent}" '
        f'--emit-hook-context'
    )


def global_prompt_command(agent: str) -> str:
    return hook_command(
        f'"{sys.executable}" "{OMI}" record-prompt '
        f'--config "{OBSIDIANIFY_HOME / "config.json"}" '
        f'--target "." '
        f'--agent "{agent}"'
    )


def global_turn_command(agent: str) -> str:
    return hook_command(
        f'"{sys.executable}" "{OMI}" record-turn '
        f'--config "{OBSIDIANIFY_HOME / "config.json"}" '
        f'--target "." '
        f'--agent "{agent}"'
    )


def hook_command(command: str) -> str:
    if os.name == "nt":
        return f"& {command}"
    return command


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
