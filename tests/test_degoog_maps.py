"""Exercise the guarded, repeatable Maps frontend compatibility patch."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('patch_maps', ROOT / 'roles/degoog/files/patch_maps.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class MapsPatchTests(unittest.TestCase):
    def test_patch_preserves_unrelated_code_and_is_idempotent(self):
        original = '\n'.join(old for old, _ in patch.REPLACEMENTS) + '\n// untouched\n'
        result = patch.patched(original)
        for old, new in patch.REPLACEMENTS:
            self.assertNotIn(old, result)
            self.assertIn(new, result)
        self.assertTrue(result.endswith('// untouched\n'))
        self.assertEqual(patch.patched(result), result)

    def test_unknown_upstream_is_rejected(self):
        with self.assertRaises(ValueError):
            patch.patched('// different upstream implementation')

    def test_duplicate_targets_are_rejected(self):
        with self.assertRaises(ValueError):
            patch.patched('\n'.join(old for old, _ in patch.REPLACEMENTS) * 2)


if __name__ == '__main__':
    unittest.main()
