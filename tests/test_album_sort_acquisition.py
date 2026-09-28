"""Render Album Sort's Compose file and check the acquisition handoff mounts and paths."""
from pathlib import Path, PurePosixPath
import unittest
import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/album_sort'


class AcquisitionHandoffTests(unittest.TestCase):
    def setUp(self):
        values = {}
        for path in ['group_vars/compute_servers/common.yml', 'group_vars/compute_servers/docker.yml', 'roles/album_sort/defaults/main.yml']:
            values.update(yaml.safe_load((ROOT / path).read_text()))
        values.update(ansible_managed='test fixture', music_volume_name='music', ansible_user='fixture')
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        self.values = values
        self.rendered = yaml.safe_load(env.from_string((ROLE / 'templates/compose.yaml.j2').read_text()).render(values))
        self.service = self.rendered['services']['album-sort']

    def test_mounts_the_downloads_volume_and_points_at_slskd_and_quarantine(self):
        self.assertIn('downloads:/downloads', self.service['volumes'])
        self.assertEqual(self.rendered['volumes']['downloads'], {'external': True})
        self.assertEqual(self.service['environment']['SLSKD_DOWNLOAD_DIR'], '/downloads/music')
        self.assertEqual(self.service['environment']['QUARANTINE_PATH'], '/downloads/album-sort/quarantine')

    def test_quarantine_does_not_overlap_download_or_library_roots(self):
        quarantine = PurePosixPath(self.values['album_sort_quarantine_path'])
        for key in ['album_sort_slskd_download_path', 'album_sort_unsorted_path', 'album_sort_sorted_path', 'album_sort_data_path']:
            other = PurePosixPath(self.values[key])
            self.assertFalse(quarantine == other or other in quarantine.parents or quarantine in other.parents, key)

    def test_creates_the_quarantine_before_deploying(self):
        tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        names = [task.get('name') for task in tasks]
        create = names.index('Create the Album Sort quarantine on the downloads volume')
        self.assertLess(create, names.index('Deploy compose file'))


if __name__ == '__main__':
    unittest.main()
