"""Install Obsidianify into a target Codex/Claude project."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OMI = ROOT / "scripts" / "omi.py"
OBSIDIANIFY_HOME = Path.home() / ".obsidianify"
OBSIDIANIFY_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
OBSIDIANIFY_UPDATE_SOURCE = "https://github.com/aesopscott/obsidianify"
SIDECAR_FILENAME = "sidecar_memory.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--vault", action="append", type=Path)
    parser.add_argument("--write-root", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", action="append", choices=("codex", "claude"), required=True)
    parser.add_argument("--task", default="general project session")
    args = parser.parse_args()

    target = args.target.resolve()
    if not target.exists():
        raise SystemExit(f"Target project not found: {target}")
    vaults = resolve_install_vaults(args.vault, target)
    write_root = resolve_install_write_root(args.write_root, target, args.project)
    for agent in args.agent:
        install_agent(target, vaults, args.project, args.task, agent, write_root)
    return 0


def install_agent(target: Path, vaults: list[Path], project: str, task: str, agent: str, write_root: Path) -> None:
    target_memory = target / ".obsidian-memory"
    target_memory.mkdir(parents=True, exist_ok=True)
    ensure_gitignore_entry(target, ".obsidian-memory/")
    write_root.mkdir(parents=True, exist_ok=True)
    update_local_project_config(OBSIDIANIFY_HOME / "config.json", project, target, vaults[0], write_root)
    write_project_sidecar(target, project, vaults[0], write_root)
    if agent == "codex":
        install_codex(target, vaults, project, task)
    else:
        install_claude(target, vaults, project, task)
    run_refresh(target, vaults, project, task, agent)


def install_codex(target: Path, vaults: list[Path], project: str, task: str) -> None:
    codex_dir = target / ".codex"
    codex_dir.mkdir(exist_ok=True)
    hook = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(target, vaults, project, task, "codex"),
                            "statusMessage": "Refreshing Obsidian memory packet",
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": prompt_command(target, vaults, project, "codex"),
                            "statusMessage": "Recording Obsidianify turn marker",
                        }
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": turn_command(target, vaults, project, "codex"),
                            "statusMessage": "Recording Obsidianify turn outcome",
                        }
                    ]
                }
            ],
        }
    }
    (codex_dir / "hooks.json").write_text(json.dumps(hook, indent=2), encoding="utf-8")
    append_block(
        target / "AGENTS.md",
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


def install_claude(target: Path, vaults: list[Path], project: str, task: str) -> None:
    claude_dir = target / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    settings.setdefault("hooks", {})
    settings["hooks"]["SessionStart"] = [
        {
            "matcher": "startup|resume",
            "hooks": [
                {
                    "type": "command",
                    "command": command(target, vaults, project, task, "claude"),
                }
            ],
        }
    ]
    settings["hooks"]["UserPromptSubmit"] = [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": prompt_command(target, vaults, project, "claude"),
                }
            ]
        }
    ]
    settings["hooks"]["Stop"] = [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": turn_command(target, vaults, project, "claude"),
                }
            ]
        }
    ]
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    append_block(
        target / "CLAUDE.md",
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


def run_refresh(target: Path, vaults: list[Path], project: str, task: str, agent: str) -> None:
    import subprocess

    subprocess.run(
        [
            sys.executable,
            str(OMI),
            "refresh",
            *vault_args(vaults),
            "--store",
            str(ROOT / ".omi-store"),
            "--project",
            project,
            "--task",
            task,
            "--target",
            str(target),
            "--agent",
            agent,
        ],
        check=True,
    )


def command(target: Path, vaults: list[Path], project: str, task: str, agent: str) -> str:
    return hook_command(
        f'"{sys.executable}" "{OMI}" refresh '
        f'{vault_command_args(vaults)} '
        f'--store "{ROOT / ".omi-store"}" '
        f'--project "{project}" '
        f'--task "{task}" '
        f'--target "{target}" '
        f'--agent "{agent}" '
        f'--emit-hook-context'
    )


def prompt_command(target: Path, vaults: list[Path], project: str, agent: str) -> str:
    return hook_command(
        f'"{sys.executable}" "{OMI}" record-prompt '
        f'--config "{OBSIDIANIFY_HOME / "config.json"}" '
        f'--target "{target}" '
        f'--agent "{agent}"'
    )


def turn_command(target: Path, vaults: list[Path], project: str, agent: str) -> str:
    return hook_command(
        f'"{sys.executable}" "{OMI}" record-turn '
        f'--config "{OBSIDIANIFY_HOME / "config.json"}" '
        f'--target "{target}" '
        f'--agent "{agent}"'
    )


def vault_args(vaults: list[Path]) -> list[str]:
    args: list[str] = []
    for vault in vaults:
        args.extend(["--vault", str(vault)])
    return args


def vault_command_args(vaults: list[Path]) -> str:
    return " ".join(f'--vault "{vault}"' for vault in vaults)


def hook_command(command_text: str) -> str:
    if os.name == "nt":
        return f"& {command_text}"
    return command_text


def resolve_install_vaults(vaults: list[Path] | None, target: Path) -> list[Path]:
    if vaults:
        resolved = [vault.expanduser().resolve() for vault in vaults]
    else:
        resolved = [prompt_path("Default Obsidian vault path", target, must_exist=True)]
    for vault in resolved:
        if not vault.exists():
            raise SystemExit(f"Vault not found: {vault}")
    return resolved


def resolve_install_write_root(write_root: Path | None, target: Path, project: str) -> Path:
    if write_root:
        return write_root.expanduser().resolve()
    return prompt_path("Default Obsidianify write route", target / safe_segment(project), must_exist=False)


def prompt_path(label: str, default: Path, must_exist: bool) -> Path:
    if not sys.stdin.isatty():
        return default.expanduser().resolve()
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        path = Path(raw).expanduser() if raw else default
        resolved = path.resolve()
        if must_exist and not resolved.exists():
            print(f"Path not found: {resolved}")
            continue
        return resolved


def update_local_project_config(config_path: Path, project: str, target: Path, vault: Path, write_root: Path) -> None:
    config = read_json_object(config_path)
    projects = config.setdefault("projects", {})
    if not isinstance(projects, dict):
        projects = {}
        config["projects"] = projects
    project_config = projects.setdefault(project, {})
    if not isinstance(project_config, dict):
        project_config = {}
        projects[project] = project_config
    project_config.update(
        {
            "path": str(target),
            "vaultPath": str(vault),
            "writeRoot": str(write_root),
        }
    )
    config.setdefault("store", str(OBSIDIANIFY_HOME / "store"))
    config.setdefault("hookAuditLog", str(OBSIDIANIFY_HOME / "hook-audit.log"))
    config["repo"] = str(ROOT)
    config["version"] = OBSIDIANIFY_VERSION
    config["updateSource"] = OBSIDIANIFY_UPDATE_SOURCE
    write_json(config_path, config)


def write_project_sidecar(target: Path, project: str, vault: Path, write_root: Path) -> Path:
    sidecar_path = target / ".obsidian-memory" / SIDECAR_FILENAME
    sidecar = read_json_object(sidecar_path)
    entries = sidecar.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    managed_ids = {
        "obsidianify.local.vaultPath",
        "obsidianify.local.writeRoot",
        "obsidianify.local.memoryPolicy",
        "obsidianify.updateSource",
    }
    filtered = [
        entry
        for entry in entries
        if not (isinstance(entry, dict) and entry.get("id") in managed_ids)
    ]
    today = date.today().isoformat()
    project_label = project.title()
    filtered.extend(
        [
            {
                "id": "obsidianify.local.vaultPath",
                "key": "vaultPath",
                "path": str(vault),
                "text": f"{project_label} Obsidianify local config: this user's project vaultPath is {vault}. This is the local Obsidian vault root for the project.",
                "addedAt": today,
                "addedBy": "Obsidianify installer",
            },
            {
                "id": "obsidianify.local.writeRoot",
                "key": "writeRoot",
                "path": str(write_root),
                "text": f"{project_label} Obsidianify local config: this user's project writeRoot is {write_root}. Turn-memory notes should write under this folder for this local user.",
                "addedAt": today,
                "addedBy": "Obsidianify installer",
            },
            {
                "id": "obsidianify.local.memoryPolicy",
                "text": f"{project_label} Obsidianify local config: .obsidian-memory is local generated/user memory and is gitignored. User-specific absolute paths belong here or in ~/.obsidianify/config.json, not in synced repo files.",
                "addedAt": today,
                "addedBy": "Obsidianify installer",
            },
            {
                "id": "obsidianify.updateSource",
                "text": f"Obsidianify authoritative update source is {OBSIDIANIFY_UPDATE_SOURCE}. Use this GitHub repository for updates.",
                "addedAt": today,
                "addedBy": "Obsidianify installer",
            },
        ]
    )
    write_json(sidecar_path, {"entries": filtered})
    return sidecar_path


def read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def safe_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "-" for ch in value).strip()
    return cleaned or "project"


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


def ensure_gitignore_entry(target: Path, entry: str) -> None:
    path = target / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [line.strip() for line in existing.splitlines()]
    if entry.rstrip("/") in lines or entry in lines:
        return
    prefix = "" if not existing.strip() else "\n"
    path.write_text(existing.rstrip() + prefix + entry + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
