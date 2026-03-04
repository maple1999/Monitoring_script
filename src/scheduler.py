from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Callable

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def _now_in_tz(tz_name: str) -> datetime:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    # fallback: common UTC+8 for Asia/Shanghai
    if tz_name in ("Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin", "Asia/Urumqi", "Asia/Singapore"):
        return datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(hours=8)
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def next_run_time_tz(target_hh: int, target_mm: int, tz_name: str) -> datetime:
    now = _now_in_tz(tz_name)
    run = now.replace(hour=target_hh, minute=target_mm, second=0, microsecond=0)
    if run <= now:
        run = run + timedelta(days=1)
    return run


def run_daily(target_time_str: str, job: Callable[[], int], tz_name: str = "Asia/Shanghai"):
    hh, mm = map(int, target_time_str.split(":"))
    while True:
        run_at_local = next_run_time_tz(hh, mm, tz_name)
        # compute sleep seconds in UTC terms
        if ZoneInfo is not None:
            try:
                run_utc = run_at_local.astimezone(timezone.utc)
            except Exception:
                run_utc = run_at_local - timedelta(hours=8)
        else:
            run_utc = run_at_local - timedelta(hours=8)
        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        secs = (run_utc - now_utc).total_seconds()
        if secs > 0:
            time.sleep(min(secs, 3600))
            # re-loop to correct drift
            continue
        try:
            job()
        except Exception:
            pass
