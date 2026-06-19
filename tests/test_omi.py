from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import omi  # noqa: E402


class OmiTests(unittest.TestCase):
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

    def test_record_prompt_writes_to_project_session_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "Vault"
            target = base / "TargetProject"
            config = base / "config.json"
            vault.mkdir()
            target.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "vaults": [{"name": "Vault", "path": str(vault), "enabled": True}],
                        "projects": {"Alpha Project": {"path": str(target)}},
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

            prompt_note = vault / "Alpha Project" / "session2026-06-19" / "prompts.md"
            self.assertTrue(prompt_note.exists())
            self.assertIn("Please update the parser.", prompt_note.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
