#!/usr/bin/env python3
"""Focused tests for staged maintenance and backup verification contracts."""

from __future__ import annotations

import datetime
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import time
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

    def test_renovate_detects_pinned_bentopdf_as_application_image(self):
        config = json.loads((ROOT / ".renovaterc.json").read_text(encoding="utf-8"))
        expression = config["customManagers"][0]["matchStrings"][0]
        python_expression = expression.replace("(?<", "(?P<")
        match = re.search(
            python_expression,
            (ROOT / "roles/bentopdf/defaults/main.yml").read_text(encoding="utf-8"),
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group("depType"), "application-image")
        self.assertEqual(match.group("currentValue"), "2.8.8")
        self.assertTrue(match.group("currentDigest").startswith("sha256:"))
        self.assertFalse(config["automerge"])


class BackupStatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.core = self.root / "core"
        self.latest = self.core / "2026-09-17_01-00-00"
        self.latest.mkdir(parents=True)
        for name in ("Stack.gz", "Stats.gz"):
            path = self.latest / name if name != "Stats.gz" else self.core / name
            with gzip.open(path, "wb") as output:
                output.write(b"{}\n")
        self.fake_docker = self.root / "docker"
        self.fake_docker.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import os
                from pathlib import Path
                import sys
                source = "NAS_JSON" if sys.argv[-1] == "/nas/borg-nuc-mini" else "LOCAL_JSON"
                print(Path(os.environ[source]).read_text(), end="")
                """
            ),
            encoding="utf-8",
        )
        self.fake_docker.chmod(0o755)
        self.fake_findmnt = self.root / "findmnt"
        self.fake_findmnt.write_text("#!/usr/bin/env bash\nprintf 'nfs4\\n'\n", encoding="utf-8")
        self.fake_findmnt.chmod(0o755)
        self.local_json = self.root / "local.json"
        self.nas_json = self.root / "nas.json"
        self._write_archive_json("same-id", "same-id")
        rendered = render_template(
            ROOT / "roles/backup/templates/scripts/verify-backup-status.sh.j2",
            backup_verification_max_age_hours=27,
            komodo_core_backup_host_path="/unused/core",
            nas_mount_host_path="/unused/nas",
            borg_repo_container_path="/repo",
            nas_mount_container_path="/nas",
            nas_share_subpath="borg-nuc-mini",
            komodo_core_required_artifacts=["Stack.gz"],
        )
        self.script = self.root / "verify-backup-status.sh"
        self.script.write_text(rendered, encoding="utf-8")
        self.script.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def _write_archive_json(self, local_id: str, nas_id: str) -> None:
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for path, archive_id in (
            (self.local_json, local_id),
            (self.nas_json, nas_id),
        ):
            path.write_text(
                json.dumps(
                    {
                        "archives": [
                            {"id": archive_id, "archive": "nuc-mini-current", "start": stamp}
                        ]
                    }
                ),
                encoding="utf-8",
            )

    def _run(self) -> subprocess.CompletedProcess[str]:
        environment = os.environ | {
            "CORE_BACKUP_ROOT": str(self.core),
            "DOCKER_BIN": str(self.fake_docker),
            "FINDMNT_BIN": str(self.fake_findmnt),
            "LOCAL_JSON": str(self.local_json),
            "NAS_JSON": str(self.nas_json),
        }
        return subprocess.run(
            [str(self.script)],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_current_matching_backups_pass(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Backup status verification passed", result.stdout)

    def test_stale_core_backup_fails(self):
        old = time.time() - (28 * 60 * 60)
        os.utime(self.latest, (old, old))
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("core_backup is stale", result.stderr)

    def test_missing_core_artifact_fails(self):
        (self.latest / "Stack.gz").unlink()
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required Core artifact is missing", result.stderr)

    def test_nas_archive_divergence_fails(self):
        self._write_archive_json("local-id", "nas-id")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NAS divergence", result.stderr)


class ProwlarrRestoreTests(unittest.TestCase):
    def _run(self, corrupt: bool) -> tuple[subprocess.CompletedProcess[str], list[Path]]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            restore_root = root / "restore-tests"
            restore_root.mkdir()
            fake_docker = root / "docker"
            fake_docker.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import os
                    from pathlib import Path
                    import sqlite3
                    import sys

                    args = sys.argv[1:]
                    if "extract" in args:
                        destination = Path(args[args.index("--destination") + 1])
                        archive_path = args[args.index("--path") + 1]
                        database = destination / archive_path
                        database.parent.mkdir(parents=True, exist_ok=True)
                        if os.environ.get("CORRUPT") == "1":
                            database.write_bytes(b"not sqlite")
                        else:
                            connection = sqlite3.connect(database)
                            connection.execute("create table test (id integer primary key)")
                            connection.commit()
                            connection.close()
                    elif "sqlite3" in args:
                        database = args[-2]
                        query = args[-1]
                        connection = sqlite3.connect(database)
                        if query == ".schema":
                            row = connection.execute(
                                "select sql from sqlite_master where sql is not null limit 1"
                            ).fetchone()
                            print(row[0] if row else "")
                        else:
                            print(connection.execute("PRAGMA integrity_check").fetchone()[0])
                        connection.close()
                    """
                ),
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            rendered = render_template(
                ROOT / "roles/backup/templates/scripts/verify-prowlarr-restore.sh.j2",
                prowlarr_restore_archive_path="dumps/sqlite/prowlarr_config_prowlarr.db",
                docker_base_path="/unused",
                stack_name="backup",
            )
            script = root / "verify-prowlarr-restore.sh"
            script.write_text(rendered, encoding="utf-8")
            script.chmod(0o755)
            environment = os.environ | {
                "CORRUPT": "1" if corrupt else "0",
                "DOCKER_BIN": str(fake_docker),
                "RESTORE_TMP_ROOT": str(restore_root),
                "RESTORE_CONTAINER_TMP_ROOT": str(restore_root),
            }
            result = subprocess.run(
                [str(script)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            remaining = list(restore_root.iterdir())
            return result, remaining

    def test_valid_restore_passes_and_cleans_temporary_files(self):
        result, remaining = self._run(corrupt=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("integrity=ok", result.stdout)
        self.assertEqual(remaining, [])

    def test_corrupt_restore_fails_and_cleans_temporary_files(self):
        result, remaining = self._run(corrupt=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(remaining, [])


if __name__ == "__main__":
    unittest.main()
