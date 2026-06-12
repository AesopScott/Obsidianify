"""Install Obsidianify into a target Codex/Claude project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OMI = ROOT / "scripts" / "omi.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--vault", action="append", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", action="append", choices=("codex", "claude"), required=True)
    parser.add_argument("--task", default="general project session")
    args = parser.parse_args()

    target = args.target.resolve()
    if not target.exists():
        raise SystemExit(f"Target project not found: {target}")
    vaults = [vault.resolve() for vault in args.vault]
    for agent in args.agent:
        install_agent(target, vaults, args.project, args.task, agent)
    return 0


def install_agent(target: Path, vaults: list[Path], project: str, task: str, agent: str) -> None:
    target_memory = target / ".obsidian-memory"
    target_memory.mkdir(parents=True, exist_ok=True)
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
            ]
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
    return (
        f'"{sys.executable}" "{OMI}" refresh '
        f'{vault_command_args(vaults)} '
        f'--store "{ROOT / ".omi-store"}" '
        f'--project "{project}" '
        f'--task "{task}" '
        f'--target "{target}" '
        f'--agent "{agent}" '
        f'--emit-hook-context'
    )


def vault_args(vaults: list[Path]) -> list[str]:
    args: list[str] = []
    for vault in vaults:
        args.extend(["--vault", str(vault)])
    return args


def vault_command_args(vaults: list[Path]) -> str:
    return " ".join(f'--vault "{vault}"' for vault in vaults)


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
