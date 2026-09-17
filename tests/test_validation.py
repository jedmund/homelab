#!/usr/bin/env python3
"""Regression tests for validation planning and fast repository checks."""

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci"))
import validation  # noqa: E402


class PlanTests(unittest.TestCase):
    def test_documentation_and_komodo_use_fast_checks(self):
        plan = validation.classify(["docs/operations.md", "komodo/stacks.toml"])
        self.assertFalse(plan["static"])
        self.assertFalse(plan["full"])
        self.assertEqual(plan["roles"], [])

    def test_fixture_roles_select_only_their_groups(self):
        plan = validation.classify(
            ["roles/prowlarr/tasks/main.yml", "roles/line/templates/compose.yaml.j2"]
        )
        self.assertTrue(plan["static"])
        self.assertFalse(plan["full"])
        self.assertEqual(plan["groups"]["1"], ["prowlarr"])
        self.assertEqual(plan["groups"]["3"], ["line"])

    def test_shared_unknown_and_uncovered_role_select_full(self):
        for path in ("inventory/hosts.yml", "ci/run", "roles/traefik/tasks/main.yml"):
            with self.subTest(path=path):
                plan = validation.classify([path])
                self.assertTrue(plan["full"])
                self.assertEqual(set(plan["roles"]), validation.FIXTURE_ROLES)

    def test_missing_base_selects_full(self):
        plan = validation.classify([], fallback="comparison base is unavailable")
        self.assertTrue(plan["full"])
        self.assertIn("safe fallback", plan["reasons"][0])

    def test_rename_parser_returns_both_paths(self):
        raw = "R100\0old.md\0new.md\0M\0roles/line/tasks/main.yml\0"
        self.assertEqual(
            validation.parse_name_status(raw),
            ["old.md", "new.md", "roles/line/tasks/main.yml"],
        )

    def test_dotenv_uses_single_line_group_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "selection.env"
            plan = validation.classify(["roles/prowlarr/tasks/main.yml"])
            validation.write_dotenv(str(path), plan)
            self.assertIn(
                "VALIDATION_GROUP_1=prowlarr\n", path.read_text(encoding="utf-8")
            )


class FastValidationTests(unittest.TestCase):
    def test_markdown_links_and_duplicate_anchors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.md"
            target.write_text("# Same\n\n# Same\n", encoding="utf-8")
            source = root / "source.md"
            source.write_text(
                "[first](target.md#same) [second](target.md#same-1)\n",
                encoding="utf-8",
            )
            self.assertEqual(validation.validate_markdown(root, [source, target]), [])
            source.write_text("[missing](target.md#absent)\n", encoding="utf-8")
            self.assertIn(
                "missing anchor", validation.validate_markdown(root, [source])[0]
            )

    def test_markdown_ignores_fenced_examples_and_external_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            source.write_text(
                "[external](https://example.com/x)\n```md\n[example](missing.md)\n```\n",
                encoding="utf-8",
            )
            self.assertEqual(validation.validate_markdown(root, [source]), [])

    def test_komodo_rejects_duplicates_and_accepts_external_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stacks.toml"
            path.write_text(
                '[[stack]]\nname="one"\n[stack.config]\nserver="external"\n'
                '[[stack]]\nname="one"\n[stack.config]\nserver="external"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                validation.validate_komodo(path), ["duplicate stack name: one"]
            )
            path.write_text(
                '[[stack]]\nname="one"\ntags=["homelab"]\n'
                '[stack.config]\nserver="external"\nfile_paths=["compose.yaml"]\n',
                encoding="utf-8",
            )
            self.assertEqual(validation.validate_komodo(path), [])

    def test_malformed_toml_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stacks.toml"
            path.write_text("[[stack]\n", encoding="utf-8")
            self.assertTrue(validation.validate_komodo(path))


if __name__ == "__main__":
    unittest.main()
