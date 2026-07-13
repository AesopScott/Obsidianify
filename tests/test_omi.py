from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import install  # noqa: E402
import install_global  # noqa: E402
import omi  # noqa: E402


class OmiTests(unittest.TestCase):
    def test_windows_hook_commands_use_powershell_call_operator(self) -> None:
        with mock.patch.object(install.os, "name", "nt"):
            self.assertTrue(install.hook_command('"C:\\Python\\python.exe" script.py').startswith("& "))

        with mock.patch.object(install_global.os, "name", "nt"):
            self.assertTrue(install_global.hook_command('"C:\\Python\\python.exe" script.py').startswith("& "))

    def test_non_windows_hook_commands_are_unchanged(self) -> None:
        command = '"/usr/bin/python3" script.py'

        with mock.patch.object(install.os, "name", "posix"):
            self.assertEqual(install.hook_command(command), command)

        with mock.patch.object(install_global.os, "name", "posix"):
            self.assertEqual(install_global.hook_command(command), command)

    def test_installer_writes_local_project_config_and_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "intranet"
            vault = target
            write_root = target / "Scott"
            config_path = base / ".obsidianify" / "config.json"
            target.mkdir()

            install.update_local_project_config(config_path, "intranet", target, vault, write_root)
            sidecar_path = install.write_project_sidecar(target, "intranet", vault, write_root)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            project = config["projects"]["intranet"]
            self.assertEqual(project["path"], str(target))
            self.assertEqual(project["vaultPath"], str(vault))
            self.assertEqual(project["writeRoot"], str(write_root))
            self.assertEqual(config["updateSource"], "https://github.com/aesopscott/obsidianify")

            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            texts = "\n".join(entry["text"] for entry in sidecar["entries"])
            self.assertIn(str(vault), texts)
            self.assertIn(str(write_root), texts)
            self.assertIn(".obsidian-memory is local", texts)
            self.assertIn("https://github.com/aesopscott/obsidianify", texts)

    def test_project_turn_hooks_use_local_config_for_write_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "intranet"
            vault = target
            target.mkdir()

            command = install.turn_command(target, [vault], "intranet", "codex")

            self.assertIn("--config", command)
            self.assertIn(str(install.OBSIDIANIFY_HOME / "config.json"), command)
            self.assertNotIn("--vault", command)

    def test_record_turn_syncs_write_root_from_sidecar_into_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            write_root = base / "Scott"
            store = base / "store"
            config = base / "config.json"
            session_log = base / "session.jsonl"
            vault.mkdir()
            target.mkdir()
            (target / ".obsidian-memory").mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"intranet": {"path": str(target)}},
                        "store": str(store),
                    }
                ),
                encoding="utf-8",
            )
            (target / ".obsidian-memory" / "sidecar_memory.json").write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "id": "obsidianify.local.writeRoot",
                                "key": "writeRoot",
                                "path": str(write_root),
                                "text": f"Intranet Obsidianify local config: this user's project writeRoot is {write_root}.",
                            },
                            {
                                "id": "obsidianify.local.vaultPath",
                                "key": "vaultPath",
                                "path": str(vault),
                                "text": f"Intranet Obsidianify local config: this user's project vaultPath is {vault}.",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            event = {
                "timestamp": "2026-06-19T10:01:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-sidecar-root",
                    "last_agent_message": "Implemented Obsidianify configuration routing for project write roots.",
                },
            }
            session_log.write_text(json.dumps(event) + "\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "replay-session",
                    "--config",
                    str(config),
                    "--project",
                    "intranet",
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--session-date",
                    "2026-06-19",
                    "--session-log",
                    str(session_log),
                ],
                check=True,
                text=True,
            )

            saved = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(saved["projects"]["intranet"]["writeRoot"], str(write_root))
            self.assertEqual(saved["projects"]["intranet"]["vaultPath"], str(vault))
            written_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (write_root / "session2026-06-19").glob("*.md")
            )
            self.assertIn("project write roots", written_text)
            self.assertFalse((vault / "intranet").exists())

    def test_cli_reports_version(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "omi.py"), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("Obsidianify 0.4.6", result.stdout)
        self.assertIn("https://github.com/aesopscott/obsidianify", result.stdout)

    def test_refresh_can_emit_hook_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            vault.mkdir()
            target.mkdir()
            (vault / "Alpha Project.md").write_text("Alpha context note.", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "refresh",
                    "--vault",
                    str(vault),
                    "--store",
                    str(store),
                    "--project",
                    "Alpha",
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--emit-hook-context",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertIn("hookSpecificOutput", payload)
            self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_multiline_yaml_frontmatter_tags_are_parsed(self) -> None:
        text = """---
title: Alpha Note
tags:
  - alpha
  - decision
aliases:
  - First Alpha
status: canonical
---
Body.
"""
        frontmatter, body = omi.split_frontmatter(text)

        self.assertEqual(frontmatter["title"], "Alpha Note")
        self.assertEqual(frontmatter["tags"], ["alpha", "decision"])
        self.assertEqual(frontmatter["aliases"], ["First Alpha"])
        self.assertEqual(body, "Body.\n")

    def test_graph_proximity_reaches_linked_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            store = base / "store"
            vault.mkdir()
            (vault / "Alpha Project.md").write_text("Project home.\n\n[[Decision Log]]", encoding="utf-8")
            (vault / "Decision Log.md").write_text("Important implementation decision.", encoding="utf-8")

            omi.sync_vaults([vault], store)
            omi.rank_graph(store, "Alpha", "")

            rankings = json.loads((store / "memory_rankings.json").read_text(encoding="utf-8"))
            decision = next(item for item in rankings["ranked"] if item["title"] == "Decision Log")
            self.assertGreater(decision["signals"]["proximity"], 0)
            self.assertEqual(decision["why"]["graphDistance"], 1)

    def test_record_prompt_stores_marker_without_writing_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            audit = base / "hook-audit.log"
            config = base / "config.json"
            vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"Alpha Project": {"path": str(target)}},
                        "store": str(store),
                        "hookAuditLog": str(audit),
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "record-prompt",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--session-date",
                    "2026-06-19",
                ],
                input=json.dumps({"prompt": "Please update the parser."}),
                check=True,
                text=True,
            )

            self.assertFalse((vault / "Alpha Project" / "session2026-06-19").exists())
            markers = (store / "prompt-markers.jsonl").read_text(encoding="utf-8")
            self.assertIn("Please update the parser.", markers)
            self.assertTrue(audit.exists())
            self.assertIn("record-prompt stored turn marker", audit.read_text(encoding="utf-8"))

    def test_prompt_memory_intent_writes_short_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            config = base / "config.json"
            session_log = base / "session.jsonl"
            vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"Alpha Project": {"path": str(target)}},
                        "store": str(store),
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "record-prompt",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                ],
                input=json.dumps(
                    {
                        "prompt": "Remember this decision: the intranet project should route turn memory under projects.intranet.writeRoot."
                    }
                ),
                check=True,
                text=True,
            )
            event = {
                "timestamp": "2026-06-19T10:01:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-short",
                    "last_agent_message": "Done.",
                },
            }
            session_log.write_text(json.dumps(event) + "\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "replay-session",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--session-date",
                    "2026-06-19",
                    "--session-log",
                    str(session_log),
                ],
                check=True,
                text=True,
            )

            note = vault / "Alpha Project" / "session2026-06-19" / "architecture.md"
            text = note.read_text(encoding="utf-8")
            self.assertIn("### Prompt Memory", text)
            self.assertIn("Remember this decision", text)
            self.assertIn("projects.intranet.writeRoot", text)
            self.assertIn("### Assistant Outcome", text)
            self.assertIn("Done.", text)
            self.assertIn("- Trigger Prompt Hash:", text)
            self.assertIn("- Reason: explicit user memory intent", text)

    def test_low_value_prompt_and_outcome_skip_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            config = base / "config.json"
            session_log = base / "session.jsonl"
            vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"Alpha Project": {"path": str(target)}},
                        "store": str(store),
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "record-prompt",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                ],
                input=json.dumps({"prompt": "thanks"}),
                check=True,
                text=True,
            )
            event = {
                "timestamp": "2026-06-19T10:01:00Z",
                "type": "event_msg",
                "payload": {"type": "task_complete", "turn_id": "turn-low", "last_agent_message": "ok"},
            }
            session_log.write_text(json.dumps(event) + "\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "replay-session",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--session-date",
                    "2026-06-19",
                    "--session-log",
                    str(session_log),
                ],
                check=True,
                text=True,
            )

            self.assertFalse((vault / "Alpha Project" / "session2026-06-19").exists())

    def test_git_only_prompt_and_outcome_skip_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            audit = base / "hook-audit.log"
            config = base / "config.json"
            session_log = base / "session.jsonl"
            vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"Alpha Project": {"path": str(target)}},
                        "store": str(store),
                        "hookAuditLog": str(audit),
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "record-prompt",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                ],
                input=json.dumps({"prompt": "commit all of the branch to origin main"}),
                check=True,
                text=True,
            )
            event = {
                "timestamp": "2026-06-19T10:01:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-git",
                    "last_agent_message": "Committed and pushed main to origin. Everything up-to-date.",
                },
            }
            session_log.write_text(json.dumps(event) + "\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "replay-session",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--session-date",
                    "2026-06-19",
                    "--session-log",
                    str(session_log),
                ],
                check=True,
                text=True,
            )

            self.assertFalse((vault / "Alpha Project" / "session2026-06-19").exists())
            self.assertIn("git operation noise", audit.read_text(encoding="utf-8"))

    def test_git_mentions_do_not_hide_durable_implementation_outcome(self) -> None:
        classification = omi.classify_turn_memory(
            "commit and push when done",
            "Implemented prompt classifier guard for git-only operations, committed, and pushed origin main.",
        )

        self.assertTrue(classification["valuable"])
        self.assertEqual(classification["reason"], "durable implementation outcome")

    def test_replay_session_routes_completed_turn_outcomes_and_skips_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            audit = base / "hook-audit.log"
            config = base / "config.json"
            session_log = base / "session.jsonl"
            vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"Alpha Project": {"path": str(target)}},
                        "store": str(store),
                        "hookAuditLog": str(audit),
                    }
                ),
                encoding="utf-8",
            )
            session_events = [
                {
                    "timestamp": "2026-06-19T10:00:00Z",
                    "type": "session_meta",
                    "payload": {"cwd": str(target)},
                },
                {
                    "timestamp": "2026-06-19T10:01:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_complete",
                        "turn_id": "turn-architecture",
                        "last_agent_message": "Implemented M2-M7 and M9-M11 MAPS phase skills, updated scaffold output, and validated the maps-data resource references.",
                    },
                },
                {
                    "timestamp": "2026-06-19T10:02:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_complete",
                        "turn_id": "turn-configuration",
                        "last_agent_message": "Updated hooks.json and config.toml guidance so the Stop hook records Obsidianify turn outcomes.",
                    },
                },
                {
                    "timestamp": "2026-06-19T10:03:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_complete",
                        "turn_id": "turn-design",
                        "last_agent_message": "Fixed the voice profile page layout and improved the profile UI.",
                    },
                },
                {
                    "timestamp": "2026-06-19T10:04:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_complete",
                        "turn_id": "turn-noise",
                        "last_agent_message": "vik-handoff-check: unchanged\nreid-handoff-check: unchanged\nliz-handoff-check: unchanged",
                    },
                },
            ]
            session_log.write_text("\n".join(json.dumps(event) for event in session_events) + "\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "replay-session",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--session-date",
                    "2026-06-19",
                    "--session-log",
                    str(session_log),
                ],
                check=True,
                text=True,
            )

            session_dir = vault / "Alpha Project" / "session2026-06-19"
            architecture = (session_dir / "architecture.md").read_text(encoding="utf-8")
            configuration = (session_dir / "configuration.md").read_text(encoding="utf-8")
            design = (session_dir / "design.md").read_text(encoding="utf-8")
            self.assertIn("M2-M7 and M9-M11 MAPS phase skills", architecture)
            self.assertIn("- Source: completed turn", architecture)
            self.assertIn("Stop hook records Obsidianify turn outcomes", configuration)
            self.assertIn("voice profile page layout", design)
            self.assertNotIn("handoff-check: unchanged", "\n".join(path.read_text(encoding="utf-8") for path in session_dir.glob("*.md")))
            self.assertIn("replay-session wrote 3 note(s)", audit.read_text(encoding="utf-8"))

    def test_intranet_project_write_root_overrides_default_turn_note_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            write_root = base / "Scott" / "intranet"
            store = base / "store"
            config = base / "config.json"
            session_log = base / "session.jsonl"
            vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"intranet": {"path": str(target), "writeRoot": str(write_root)}},
                        "store": str(store),
                    }
                ),
                encoding="utf-8",
            )
            event = {
                "timestamp": "2026-06-19T10:01:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-architecture",
                    "last_agent_message": "Implemented the Obsidianify architecture writer with a per-project write root.",
                },
            }
            session_log.write_text(json.dumps(event) + "\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "replay-session",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--session-date",
                    "2026-06-19",
                    "--session-log",
                    str(session_log),
                ],
                check=True,
                text=True,
            )

            architecture = write_root / "session2026-06-19" / "architecture.md"
            self.assertIn("per-project write root", architecture.read_text(encoding="utf-8"))
            self.assertFalse((vault / "intranet").exists())

    def test_project_vault_path_overrides_default_recording_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            project_vault = base / "ProjectVault"
            target = base / "TargetProject"
            store = base / "store"
            config = base / "config.json"
            session_log = base / "session.jsonl"
            vault.mkdir()
            project_vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"Alpha Project": {"path": str(target), "vaultPath": str(project_vault)}},
                        "store": str(store),
                    }
                ),
                encoding="utf-8",
            )
            event = {
                "timestamp": "2026-06-19T10:01:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-configuration",
                    "last_agent_message": "Updated the Obsidianify configuration writer to support per-project vault paths.",
                },
            }
            session_log.write_text(json.dumps(event) + "\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "omi.py"),
                    "replay-session",
                    "--config",
                    str(config),
                    "--target",
                    str(target),
                    "--agent",
                    "codex",
                    "--session-date",
                    "2026-06-19",
                    "--session-log",
                    str(session_log),
                ],
                check=True,
                text=True,
            )

            configuration = project_vault / "Alpha Project" / "session2026-06-19" / "configuration.md"
            self.assertIn("per-project vault paths", configuration.read_text(encoding="utf-8"))
            self.assertFalse((vault / "Alpha Project").exists())

    def test_completed_turn_dedupe_prevents_duplicate_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            config = base / "config.json"
            session_log = base / "session.jsonl"
            vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"Alpha Project": {"path": str(target)}},
                        "store": str(store),
                    }
                ),
                encoding="utf-8",
            )
            event = {
                "timestamp": "2026-06-19T10:01:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-architecture",
                    "last_agent_message": "Validated the MAPS scaffold and implemented the post-turn Obsidianify architecture writer.",
                },
            }
            session_log.write_text(json.dumps(event) + "\n", encoding="utf-8")

            command = [
                sys.executable,
                str(ROOT / "scripts" / "omi.py"),
                "replay-session",
                "--config",
                str(config),
                "--target",
                str(target),
                "--agent",
                "codex",
                "--session-date",
                "2026-06-19",
                "--session-log",
                str(session_log),
            ]
            subprocess.run(command, check=True, text=True)
            subprocess.run(command, check=True, text=True)

            architecture = vault / "Alpha Project" / "session2026-06-19" / "architecture.md"
            self.assertEqual(architecture.read_text(encoding="utf-8").count("post-turn Obsidianify architecture writer"), 1)

    def test_packet_includes_sidecar_memory_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            vault.mkdir()
            target.mkdir()
            (vault / "Alpha Project.md").write_text("Alpha context note.", encoding="utf-8")

            omi.sync_vaults([vault], store)
            omi.rank_graph(store, "Alpha", "")

            sidecar_path = omi.sidecar_memory_path(target)
            sidecar_path.parent.mkdir(parents=True, exist_ok=True)
            sidecar_path.write_text(
                json.dumps(
                    {"entries": [{"text": "Ship on Fridays only.", "addedAt": "2026-07-03", "addedBy": "scott"}]}
                ),
                encoding="utf-8",
            )

            packet_path = omi.generate_packet(store, "Alpha", "", target, "claude", 20)
            packet = packet_path.read_text(encoding="utf-8")

            self.assertIn("## Sidecar Memory", packet)
            self.assertIn("Ship on Fridays only.", packet)
            status = json.loads((target / ".obsidian-memory" / "STATUS.json").read_text(encoding="utf-8"))
            self.assertEqual(status["sidecarCount"], 1)

    def test_packet_omits_sidecar_section_when_file_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            store = base / "store"
            vault.mkdir()
            target.mkdir()
            (vault / "Alpha Project.md").write_text("Alpha context note.", encoding="utf-8")

            omi.sync_vaults([vault], store)
            omi.rank_graph(store, "Alpha", "")

            packet_path = omi.generate_packet(store, "Alpha", "", target, "claude", 20)
            packet = packet_path.read_text(encoding="utf-8")

            self.assertNotIn("Sidecar Memory", packet)
            status = json.loads((target / ".obsidian-memory" / "STATUS.json").read_text(encoding="utf-8"))
            self.assertEqual(status["sidecarCount"], 0)

    def test_load_sidecar_entries_ignores_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sidecar_memory.json"
            path.write_text("{not valid json", encoding="utf-8")
            self.assertEqual(omi.load_sidecar_entries(path), [])

    def test_dot_target_resolves_to_configured_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "Project"
            nested = project / "subdir"
            other = base / "Other"
            project.mkdir()
            nested.mkdir()
            other.mkdir()
            config = {"projects": {"Alpha": {"path": str(project)}}}

            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(nested)
                self.assertEqual(omi.resolve_hook_target(Path("."), config), project.resolve())
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
