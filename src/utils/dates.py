from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def _tz(tz_name: str = "Asia/Shanghai"):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    # fallback UTC+8
    return timezone(timedelta(hours=8))


def _mk_dt(y: int, m: int, d: int, hh: int = 0, mm: int = 0, tz_name: str = "Asia/Shanghai") -> datetime:
    dt_local = datetime(y, m, d, hh, mm, tzinfo=_tz(tz_name))
    return dt_local.astimezone(timezone.utc)


EN_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def parse_date_smart(s: str, now: Optional[datetime] = None, tz_name: str = "Asia/Shanghai") -> Optional[datetime]:
    """Robust parser for common CN/EN date expressions.

    Returns UTC datetime if parsed, else None.
    Heuristics:
    - support YYYY-MM-DD[/./ ] with optional HH:MM
    - support Chinese 年/月/日 格式，带或不带时间
    - support EN month names like 'Apr 5, 2026' with optional time and am/pm
    - support 'M月D日' without year: assume next occurrence (this year or next)
    - support ranges like '4/1-4/10' or '4月1日至4月10日': choose end date
    """
    if not s:
        return None
    txt = s.strip()
    now = now or datetime.now(timezone.utc)
    # Normalize now to local tz for comparisons
    now_local = now.astimezone(_tz(tz_name))

    # 1) Explicit Y-M-D separators with optional time
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2})(?::(\d{2}))?)?", txt)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4) or 0)
        mm = int(m.group(5) or 0)
        try:
            return _mk_dt(y, mo, d, hh, mm, tz_name)
        except Exception:
            return None

    # 2) Chinese YYYY年MM月DD日 [HH:MM]
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}):(\d{2}))?", txt)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4) or 0)
        mm = int(m.group(5) or 0)
        try:
            return _mk_dt(y, mo, d, hh, mm, tz_name)
        except Exception:
            return None

    # 3) EN 'Apr 5, 2026' or '5 Apr 2026' with optional time and am/pm
    m = re.search(r"(?:^|\s)([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(\d{4}))?(?:\s+(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)?)?", txt)
    if m:
        mon = EN_MONTHS.get(m.group(1).lower())
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now_local.year
        hh = int(m.group(4) or 0)
        mm = int(m.group(5) or 0)
        ap = (m.group(6) or '').lower()
        if ap in ('pm') and hh < 12:
            hh += 12
        if ap in ('am') and hh == 12:
            hh = 0
        if mon:
            try:
                dt = _mk_dt(year, mon, day, hh, mm, tz_name)
                # if no explicit year and date already passed significantly, assume next year
                if not m.group(3) and dt < now:
                    dt = _mk_dt(year + 1, mon, day, hh, mm, tz_name)
                return dt
            except Exception:
                return None

    # 4) Chinese 'M月D日' with optional time (no year)
    m = re.search(r"(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}):(\d{2}))?", txt)
    if m:
        mo = int(m.group(1))
        d = int(m.group(2))
        hh = int(m.group(3) or 0)
        mm = int(m.group(4) or 0)
        y = now_local.year
        try:
            dt = _mk_dt(y, mo, d, hh, mm, tz_name)
            if dt < now:
                dt = _mk_dt(y + 1, mo, d, hh, mm, tz_name)
            return dt
        except Exception:
            return None

    # 5) Range like '4/1-4/10' or '4月1日至4月10日' → use end date
    # MM/DD[- ]MM/DD
    m = re.search(r"(\d{1,2})[/.](\d{1,2})\s*[-~至到—–]+\s*(\d{1,2})[/.](\d{1,2})", txt)
    if m:
        y = now_local.year
        mo2, d2 = int(m.group(3)), int(m.group(4))
        try:
            dt = _mk_dt(y, mo2, d2, 23, 59, tz_name)
            if dt < now:
                dt = _mk_dt(y + 1, mo2, d2, 23, 59, tz_name)
            return dt
        except Exception:
            return None
    # Chinese MM月DD日 至 MM月DD日
    m = re.search(r"(\d{1,2})月(\d{1,2})日\s*[-~至到—–]+\s*(\d{1,2})月(\d{1,2})日", txt)
    if m:
        y = now_local.year
        mo2, d2 = int(m.group(3)), int(m.group(4))
        try:
            dt = _mk_dt(y, mo2, d2, 23, 59, tz_name)
            if dt < now:
                dt = _mk_dt(y + 1, mo2, d2, 23, 59, tz_name)
            return dt
        except Exception:
            return None

    return None


def parse_date_basic(s: str) -> Optional[datetime]:
    # Backward-compatible wrapper
    return parse_date_smart(s)


def is_within_days(dt: datetime, days: int, now: Optional[datetime] = None) -> bool:
    n = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return timedelta(days=0) <= (dt - n) <= timedelta(days=days)
