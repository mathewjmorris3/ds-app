#!/usr/bin/env python3
"""Native PostgreSQL backups. Configuration is supplied by systemd EnvironmentFile."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime


def run_backup():
    mount = Path(os.environ['BACKUP_MOUNT']).resolve()
    root = Path(os.environ['BACKUP_ROOT']).resolve()
    if not mount.is_mount() or root == mount or mount not in root.parents:
        raise RuntimeError('Backup destination must be beneath the mounted BACKUP_MOUNT')
    if not root.is_dir():
        raise RuntimeError('Provision BACKUP_ROOT on the mounted destination first')
    os.umask(0o077)
    with (root / '.backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        env = os.environ.copy()
        env.update(PGHOST=env.get('POSTGRES_HOST', '127.0.0.1'),
                   PGPORT=env.get('POSTGRES_PORT', '5432'),
                   PGUSER=env['POSTGRES_USER'], PGPASSWORD=env['POSTGRES_PASSWORD'],
                   PGDATABASE=env['POSTGRES_DB'], PGCONNECT_TIMEOUT='15')
        now = datetime.now().astimezone()
        stamp = now.strftime('%Y-%m-%d_%H%M%S_%f')
        for name in ('daily', 'weekly', 'monthly'):
            (root / name).mkdir(mode=0o700, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.partial-', dir=root / 'daily')
        os.close(fd)
        temporary = Path(temporary)
        try:
            subprocess.run(['pg_dump', '--no-password', '--format=custom', '--file', str(temporary)], env=env, check=True)
            subprocess.run(['pg_restore', '--list', str(temporary)], check=True, stdout=subprocess.DEVNULL)
            if not temporary.stat().st_size:
                raise RuntimeError('Empty dump')
            with temporary.open('rb') as stream:
                os.fsync(stream.fileno())
            final = root / 'daily' / f'dsapp-{stamp}.dump'
            temporary.replace(final)
        finally:
            temporary.unlink(missing_ok=True)
        # Promote only complete dumps; retain weekly/monthly copies on calendar boundaries.
        for name, due in [('weekly', now.weekday() == 6), ('monthly', now.day == 1)]:
            if due:
                target = root / name / final.name
                partial = target.with_suffix('.partial')
                try:
                    shutil.copyfile(final, partial)
                    with partial.open('rb') as stream:
                        os.fsync(stream.fileno())
                    partial.replace(target)
                finally:
                    partial.unlink(missing_ok=True)
        for name, keep in [('daily', 7), ('weekly', 4), ('monthly', 12)]:
            for old in sorted((root / name).glob('dsapp-*.dump'), reverse=True)[keep:]:
                old.unlink()
        print(f'Backup complete: {final}', flush=True)


if __name__ == '__main__':
    run_backup()
