"""
scripts/restore_backup.py — Restore the database from a backup.

Stop ShaFin first, then run inside the container:

    docker compose run --rm shafin python -m scripts.restore_backup              # list backups
    docker compose run --rm shafin python -m scripts.restore_backup /app/data/backups/<file>.db

The backup's SHA-256 sidecar is checked, the live database is copied aside, the backup
is put in its place and opened with DB_MASTER_PASSWORD for PRAGMA integrity_check.
"""

import sys

from database.backup import list_backups, restore_database


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m scripts.restore_backup <backup file>\n\nBackups, newest first:")
        for b in list_backups():
            print(f"  {b['path']}  {b['size_mb']} MB  {b['mtime']}")
        return 2
    restore_database(argv[1])
    print(f"Restored {argv[1]}. Start ShaFin again.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
