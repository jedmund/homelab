#!/usr/bin/env python3
"""Focused tests for staged maintenance and backup verification contracts."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tomllib
import unittest

from jinja2 import Environment, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]


def render_template(path: Path, **values: object) -> str:
    environment = Environment(undefined=StrictUndefined, keep_trailing_newline=True)
    return environment.from_string(path.read_text(encoding="utf-8")).render(
        ansible_managed="test managed file",
        **values,
    )


class BentoPdfMaintenanceTests(unittest.TestCase):
    def test_stage_allowlist_and_command(self):
        approved = subprocess.run(
            [
                "make",
                "stage",
                "STACK=bentopdf",
                "ANSIBLE=true",
                "VAULT_PASS=/nonexistent",
            ],
            cwd=ROOT / "deploy",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(approved.returncode, 0, approved.stderr)
        rejected = subprocess.run(
            [
                "make",
                "stage",
                "STACK=prowlarr",
                "ANSIBLE=true",
                "VAULT_PASS=/nonexistent",
            ],
            cwd=ROOT / "deploy",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("has not implemented staging", rejected.stdout)

    def test_rendered_healthcheck_and_digest_contract(self):
        defaults = (ROOT / "roles/bentopdf/defaults/main.yml").read_text(
            encoding="utf-8"
        )
        compose = (ROOT / "roles/bentopdf/templates/compose.yaml.j2").read_text(
            encoding="utf-8"
        )
        self.assertRegex(defaults, r"bentopdf_image_digest: sha256:[0-9a-f]{64}")
        self.assertIn('image: "{{ bentopdf_image_reference }}"', compose)
        self.assertIn("wget --quiet --spider", compose)
        self.assertIn("healthcheck:", compose)
        script = render_template(
            ROOT / "roles/bentopdf/templates/maintenance-check.sh.j2",
            config_base="/opt/docker/bentopdf",
            bentopdf_image="ghcr.io/alam00000/bentopdf-simple",
            bentopdf_image_reference=(
                "ghcr.io/alam00000/bentopdf-simple:2.8.8@"
                "sha256:3d62b8f8eece5fe947026ac3925ff08fda245b3d6ba2c3916b94da91e0010c74"
            ),
            bentopdf_image_digest=(
                "sha256:3d62b8f8eece5fe947026ac3925ff08fda245b3d6ba2c3916b94da91e0010c74"
            ),
        )
        syntax = subprocess.run(
            ["bash", "-n"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_procedure_references_check_action_and_stack(self):
        document = tomllib.loads(
            (ROOT / "komodo/stacks.toml").read_text(encoding="utf-8")
        )
        procedure = next(
            item for item in document["procedure"] if item["name"] == "maintain-bentopdf"
        )
        executions = [
            item["execution"]
            for stage in procedure["config"]["stage"]
            for item in stage["executions"]
        ]
        self.assertEqual(
            [execution["type"] for execution in executions],
            ["RunAction", "DeployStack", "RunAction"],
        )
        self.assertEqual(executions[1]["params"]["stack"], "bentopdf")
        self.assertTrue(
            all(
                execution["params"]["action"] == "bentopdf-maintenance-check"
                for execution in (executions[0], executions[2])
            )
        )

if __name__ == "__main__":
    unittest.main()
