"""Exercise the guarded, repeatable Maps frontend compatibility patch."""
import importlib.util
from pathlib import Path
import unittest
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('patch_maps', ROOT / 'roles/degoog/files/patch_maps.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class MapsPatchTests(unittest.TestCase):
    def test_places_referrer_is_scoped_to_https_carto(self):
        old, new = patch.PLACES_REPLACEMENTS[0]
        self.assertEqual(patch.patched(old, patch.PLACES_REPLACEMENTS), new)
        self.assertEqual(patch.patched(new, patch.PLACES_REPLACEMENTS), new)
        pattern = new.split('(/', 1)[1].split('/i.test(src)', 1)[0].replace(r'\/', '/')
        self.assertIn("? 'strict-origin' : 'no-referrer'", new)
        cases = {
            'https://basemaps.cartocdn.com/0/0/0.png?key=test': 'strict-origin',
            'https://a.basemaps.cartocdn.com/0/0/0.png': 'strict-origin',
            'https://tile.openstreetmap.org/0/0/0.png': 'no-referrer',
            'http://basemaps.cartocdn.com/0/0/0.png': 'no-referrer',
            'https://basemaps.cartocdn.com.evil.test/0.png': 'no-referrer',
        }
        for src, expected in cases.items():
            actual = 'strict-origin' if re.search(pattern, src, re.I) else 'no-referrer'
            self.assertEqual(actual, expected)

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
