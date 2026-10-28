"""
core/scheduler.py — Background scheduler. ShaFin has one job: the daily encrypted
database backup, which also deletes expired sessions. Nothing is fetched from any website.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import structlog

log = structlog.get_logger()

PKT = ZoneInfo("Asia/Karachi")
_TICK_SECONDS = 60


def _now() -> datetime:
    return datetime.now(PKT)


@dataclass
class Job:
    id: str
    label: str
    fn: Callable[[], object]
    cadence: str
    due: Callable[[datetime, Optional[datetime]], bool]
    last_run: Optional[datetime] = field(default=None, repr=False)


def _daily_at(hh: int, mm: int = 0):
    def due(now: datetime, last: Optional[datetime]) -> bool:
        if now.time() < dtime(hh, mm):
            return False
        if last is None:
            return True
        return last.date() < now.date()
    return due


def _backup_job() -> None:
    from database.backup import backup_database
    from security.auth import purge_expired_sessions
    backup_database()
    purge_expired_sessions()


def build_jobs() -> list[Job]:
    return [Job("daily_backup", "Database backup and expired-session purge", _backup_job, "daily 01:00 PKT",
                _daily_at(1, 0))]


async def run_scheduler() -> None:
    """Tick every minute and run whichever job is due, in the default executor."""
    jobs = build_jobs()
    from database.backup import latest_backup
    last = latest_backup()
    for job in jobs:
        if job.id == "daily_backup" and last:
            # A backup was just taken at startup: the next one is due tomorrow.
            job.last_run = datetime.fromisoformat(last["mtime"].rstrip("Z") + "+00:00").astimezone(PKT)
        log.info("Job enabled", job=job.id, label=job.label, cadence=job.cadence)
    loop = asyncio.get_running_loop()
    while True:
        now = _now()
        for job in jobs:
            if not job.due(now, job.last_run):
                continue
            job.last_run = now
            log.info("Job starting", job=job.id)
            try:
                await loop.run_in_executor(None, job.fn)
            except Exception as e:
                import traceback as _tb
                log.warning("Job failed", job=job.id, error=str(e)[:200],
                            traceback=_tb.format_exc()[-2000:])
        await asyncio.sleep(_TICK_SECONDS)
