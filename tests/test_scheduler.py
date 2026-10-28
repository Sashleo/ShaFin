"""core/scheduler.py: ShaFin has exactly one job, the daily backup."""

from datetime import datetime
from zoneinfo import ZoneInfo

from core.scheduler import _daily_at, build_jobs

PKT = ZoneInfo("Asia/Karachi")


def _dt(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=PKT)


def test_daily_at_respects_time_of_day():
    due = _daily_at(1, 0)
    assert due(_dt(2026, 7, 29, 0, 59), None) is False
    assert due(_dt(2026, 7, 29, 1, 0), None) is True


def test_daily_at_only_once_per_day():
    due = _daily_at(1, 0)
    last = _dt(2026, 7, 29, 1, 5)
    assert due(_dt(2026, 7, 29, 14, 0), last) is False
    assert due(_dt(2026, 7, 30, 1, 0), last) is True


def test_the_only_job_is_the_daily_backup():
    assert [j.id for j in build_jobs()] == ["daily_backup"]
