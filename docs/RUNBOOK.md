# Runbook

Operating ShaFin on your own machine. Commands assume the default `docker-compose.yml`.

## Start, stop, logs

```bash
docker compose up --build -d     # start (builds the image the first time)
docker compose logs -f shafin    # follow the structured logs
docker compose down              # stop; the data volume is kept
```

ShaFin refuses to start, with the reason in the log, when liboqs or its algorithms are
missing, when `DB_MASTER_PASSWORD` does not open the database, or when the security
self-test fails. Check `/health` (signed in) for the full status.

## Backups

- Taken at every start and daily at 01:00 Asia/Karachi, by `VACUUM INTO` on the live
  encrypted connection, so a backup is encrypted with the same `DB_MASTER_PASSWORD`.
- Kept: the last 14, in `/app/data/backups/` inside the `shafin_data` volume, each with a
  `.sha256` file.
- Off-machine copies: set `BACKUP_COPY_DIR` to a folder mounted into the container, or copy
  them out: `docker cp shafin:/app/data/backups ./shafin-backups`.
- Keep `DB_MASTER_PASSWORD` somewhere other than the backups. Without it a backup cannot be
  opened; with it, anyone holding the file can read it.

## Restore

```bash
docker compose stop shafin
docker compose run --rm shafin python -m scripts.restore_backup            # lists backups
docker compose run --rm shafin python -m scripts.restore_backup /app/data/backups/shafin_<date>.db
docker compose start shafin
```

The restore checks the backup's SHA-256 file, copies the live database aside as
`shafin.pre_restore_<time>.db`, puts the backup in place and runs
`PRAGMA integrity_check` with `DB_MASTER_PASSWORD`. It stops with an error on any mismatch.

## Read a backup without restoring it

Open it read-only in DB Browser for SQLCipher (see the README), or with the `sqlcipher`
command-line tool in the image:

```bash
docker compose run --rm shafin sqlcipher -readonly /app/data/backups/shafin_<date>.db
```

then type `PRAGMA key = '<your DB_MASTER_PASSWORD>';` and query, for example
`SELECT name, company_type FROM companies;`. In read-only mode any write is refused.

## Upgrade

1. Take a backup (restart ShaFin, or copy the newest one out).
2. `git pull`, then `docker compose up --build -d`.
3. Startup takes a backup before applying any schema change; schema changes only add
   tables and columns. Check `/health`.

## Rotating secrets

- `APP_SECRET_KEY`: change it in `.env` and restart. Everyone is signed out; nothing else
  changes.
- `DB_MASTER_PASSWORD`: the database is keyed with it and company keys derive from it.
  ShaFin has no re-key command in this edition; changing it means the existing database
  and backups no longer open. Do not change it on a database you want to keep.
- The key-derivation labels in `docs/SECURITY.md` must never change.

## Two-factor authentication

Turn it on in Settings. If the authenticator is lost, there is no recovery code in this
edition: restore a backup taken before 2FA was turned on, or clear it from a shell in the
container with SQLCipher (`UPDATE users SET totp_enabled = 0, totp_secret = NULL`), which
the audit log will not show, so note it yourself.

## Demo

```bash
docker compose -f docker-compose.demo.yml up --build -d
docker compose -f docker-compose.demo.yml down -v      # removes the demo data
```

The demo has its own `shafin_demo_data` volume and public demo secrets. It never shares a
volume with the real instance.
