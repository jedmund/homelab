#!/usr/bin/env python3
"""Regression tests for the Gatus alert relay's Discord embeds."""

from pathlib import Path
import os
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("GATUS_DISCORD_WEBHOOK_URL", "http://discord.invalid/webhook")
os.environ.setdefault("KOMODO_URL", "https://komodo.invalid/")
os.environ.setdefault("KOMODO_RUNBOOK_URL", "https://runbook.invalid/komodo")
sys.path.insert(0, str(ROOT / "roles" / "gatus" / "files"))
import relay  # noqa: E402


def fields(body):
    return {field["name"]: field["value"] for field in body["embeds"][0]["fields"]}


class KomodoEmbedTests(unittest.TestCase):
    def test_server_disk_names_the_root_filesystem(self):
        body = relay.build_komodo_embed({
            "level": "WARNING",
            "resolved": False,
            "target": {"type": "Server", "id": "699f8458f42b46fdb0e63a78"},
            "data": {"type": "ServerDisk", "data": {
                "id": "699f8458f42b46fdb0e63a78", "name": "Workstation",
                "path": "/etc/hostname", "used_gb": 853.1, "total_gb": 1830.2,
            }},
        })
        embed = body["embeds"][0]
        self.assertEqual(embed["title"], "🟡 Warning: komodo/Workstation disk")
        self.assertEqual(fields(body)["What happened"], "root filesystem at 46.6% (853.1 / 1830.2 GiB)")
        self.assertEqual(fields(body)["Komodo"], "https://komodo.invalid/servers/699f8458f42b46fdb0e63a78")
        self.assertEqual(fields(body)["Runbook"], "https://runbook.invalid/komodo")

    def test_resolved_alert_is_green_whatever_its_level(self):
        body = relay.build_komodo_embed({
            "level": "CRITICAL",
            "resolved": True,
            "target": {"type": "Server", "id": "abc"},
            "data": {"type": "ServerUnreachable", "data": {"id": "abc", "name": "NUC", "err": None}},
        })
        embed = body["embeds"][0]
        self.assertTrue(embed["title"].startswith("🟢 Resolved: komodo/NUC"))
        self.assertEqual(embed["color"], relay.KOMODO_RESOLVED["color"])

    def test_stack_state_change_reads_as_a_sentence(self):
        body = relay.build_komodo_embed({
            "level": "CRITICAL",
            "resolved": False,
            "target": {"type": "Stack", "id": "s1"},
            "data": {"type": "StackStateChange", "data": {
                "id": "s1", "name": "gitlab", "server_name": "NUC",
                "from": "running", "to": "unhealthy",
            }},
        })
        embed = body["embeds"][0]
        self.assertEqual(embed["title"], "🔴 Critical: komodo/gitlab")
        self.assertEqual(embed["description"], "Stack gitlab on NUC changed state.")
        self.assertEqual(fields(body)["What happened"], "running to unhealthy")

    def test_server_unreachable_uses_the_error_message(self):
        body = relay.build_komodo_embed({
            "level": "CRITICAL",
            "resolved": False,
            "target": {"type": "Server", "id": "abc"},
            "data": {"type": "ServerUnreachable", "data": {
                "id": "abc", "name": "Workstation", "err": {"error": "connection refused", "trace": []},
            }},
        })
        self.assertEqual(fields(body)["What happened"], "connection refused")

    def test_unknown_alert_type_still_renders(self):
        body = relay.build_komodo_embed({
            "level": "WARNING",
            "resolved": False,
            "target": {"type": "System", "id": ""},
            "data": {"type": "FutureAlert", "data": {"value": 1}},
        })
        self.assertIn("FutureAlert", body["embeds"][0]["title"])
        self.assertEqual(fields(body)["Komodo"], "https://komodo.invalid")


class GatusEmbedTests(unittest.TestCase):
    def test_failed_condition_is_humanized(self):
        body = relay.build_embed({
            "state": "TRIGGERED",
            "group": "core",
            "name": "PocketID",
            "description": "PocketID is down.",
            "conditions": "❌ - `[STATUS] (502) == 200`",
            "errors": "",
        })
        self.assertEqual(body["embeds"][0]["title"], "🔴 Down: core/PocketID")
        self.assertEqual(fields(body)["What happened"], "HTTP 502 (expected 200)")


if __name__ == "__main__":
    unittest.main()
