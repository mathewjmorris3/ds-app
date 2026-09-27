import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backup_native', Path(__file__).with_name('backup_native.py'))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mount = Path(self.temp.name)
        self.root = self.mount / 'dsapp'
        self.root.mkdir()
        self.env = patch.dict(os.environ, {'BACKUP_MOUNT': str(self.mount), 'BACKUP_ROOT': str(self.root), 'POSTGRES_DB': 'test', 'POSTGRES_USER': 'test', 'POSTGRES_PASSWORD': 'test'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_missing_mount_fails_before_dump(self):
        with patch.object(Path, 'is_mount', return_value=False), patch.object(backup.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                backup.run_backup()
            run.assert_not_called()

    def test_destination_outside_mount_rejected(self):
        with patch.dict(os.environ, {'BACKUP_ROOT': '/tmp'}), patch.object(Path, 'is_mount', return_value=True):
            with self.assertRaises(RuntimeError):
                backup.run_backup()

    def test_failed_dump_preserves_old_archives_and_cleans_partial(self):
        daily = self.root / 'daily'
        daily.mkdir()
        old = daily / 'dsapp-old.dump'
        old.write_bytes(b'old')
        with patch.object(Path, 'is_mount', return_value=True), patch.object(backup.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'pg_dump')):
            with self.assertRaises(subprocess.CalledProcessError):
                backup.run_backup()
        self.assertEqual(list(daily.iterdir()), [old])

    def test_success_publishes_and_prunes_only_own_dumps(self):
        daily = self.root / 'daily'
        daily.mkdir()
        for n in range(9):
            (daily / f'dsapp-2000-01-{n:02}.dump').write_bytes(b'old')
        unrelated = daily / 'keep.dump'
        unrelated.write_bytes(b'keep')
        def run(args, **kwargs):
            if args[0] == 'pg_dump':
                Path(args[-1]).write_bytes(b'test archive')
        with patch.object(Path, 'is_mount', return_value=True), patch.object(backup.subprocess, 'run', side_effect=run):
            backup.run_backup()
        self.assertEqual(len(list(daily.glob('dsapp-*.dump'))), 7)
        self.assertTrue(unrelated.exists())
        self.assertFalse(list(daily.glob('.partial-*')))


if __name__ == '__main__':
    unittest.main()
