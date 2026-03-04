from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional


def parse_date_basic(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    # common formats: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, with optional HH:MM
    patterns = [
        (r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?$", "-"),
        (r"^(\d{4})/(\d{1,2})/(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?$", "/"),
        (r"^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?$", "."),
    ]
    for pat, _ in patterns:
        m = re.match(pat, s)
        if m:
            y, mo, d, hh, mm = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            try:
                if hh and mm:
                    dt = datetime(int(y), int(mo), int(d), int(hh), int(mm), tzinfo=timezone.utc)
                else:
                    dt = datetime(int(y), int(mo), int(d), tzinfo=timezone.utc)
                return dt
            except Exception:
                return None
    return None


def is_within_days(dt: datetime, days: int, now: Optional[datetime] = None) -> bool:
    n = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return timedelta(days=0) <= (dt - n) <= timedelta(days=days)

