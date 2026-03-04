from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
import calendar

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


def _normalize_txt(s: str) -> str:
    if not s:
        return s
    trans = {
        ord('０'): '0', ord('１'): '1', ord('２'): '2', ord('３'): '3', ord('４'): '4',
        ord('５'): '5', ord('６'): '6', ord('７'): '7', ord('８'): '8', ord('９'): '9',
        ord('：'): ':', ord('－'): '-', ord('—'): '-', ord('–'): '-', ord('／'): '/', ord('．'): '.',
        ord('\u00A0'): ' ', ord('\u2002'): ' ', ord('\u2003'): ' ', ord('\u2009'): ' ', ord('\u202F'): ' ',
    }
    t = s.translate(trans)
    return t


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
    txt = _normalize_txt(s.strip())
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
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:\D*(\d{1,2})[:：](\d{2}))?", txt)
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

    # 6) Chinese partial 'YYYY年[MM月][DD日]' tolerate missing parts
    m = re.search(r"(\d{4})年\s*(\d{1,2})?月?\s*(\d{1,2})?日?", txt)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2)) if m.group(2) else 12
        try:
            last_day = calendar.monthrange(y, mo)[1]
        except Exception:
            last_day = 31
        d = int(m.group(3)) if m.group(3) else last_day
        try:
            return _mk_dt(y, mo, d, 23, 59, tz_name)
        except Exception:
            return None

    # 6b) dateparser generic fallback (if installed)
    try:
        import dateparser  # type: ignore
        dtp = dateparser.parse(txt, settings={
            'PREFER_DATES_FROM': 'future',
            'TIMEZONE': tz_name,
            'RETURN_AS_TIMEZONE_AWARE': True,
        })
        if dtp is not None:
            return dtp.astimezone(timezone.utc)
    except Exception:
        pass

    # 7) Relative expressions as last resort
    rel = _parse_relative(txt, now_local, tz_name)
    if rel is not None:
        return rel
    return None


def parse_date_basic(s: str) -> Optional[datetime]:
    # Backward-compatible wrapper
    return parse_date_smart(s)


def is_within_days(dt: datetime, days: int, now: Optional[datetime] = None) -> bool:
    n = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return timedelta(days=0) <= (dt - n) <= timedelta(days=days)


def _parse_relative(txt: str, now_local: datetime, tz_name: str) -> Optional[datetime]:
    ttxt = txt.lower()
    # Time of day if present
    tmatch = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)?", txt)
    hh = int(tmatch.group(1)) if tmatch else 23
    mm = int(tmatch.group(2)) if tmatch else 59
    ap = (tmatch.group(3) or '').lower() if tmatch else ''
    if ap == 'pm' and hh < 12:
        hh += 12
    if ap == 'am' and hh == 12:
        hh = 0

    # tonight 24:00 → 23:59
    if re.search(r"今晚\s*24[:：]?00", txt):
        hh, mm = 23, 59
        return _mk_dt(now_local.year, now_local.month, now_local.day, hh, mm, tz_name)

    # CN today/明天/后天
    if '今天' in txt or '今日' in txt:
        return _mk_dt(now_local.year, now_local.month, now_local.day, hh, mm, tz_name)
    if '明天' in txt or '次日' in txt:
        d = now_local + timedelta(days=1)
        return _mk_dt(d.year, d.month, d.day, hh, mm, tz_name)
    if '后天' in txt:
        d = now_local + timedelta(days=2)
        return _mk_dt(d.year, d.month, d.day, hh, mm, tz_name)

    # EN today/tomorrow/tonight
    if re.search(r"\btoday\b", ttxt):
        return _mk_dt(now_local.year, now_local.month, now_local.day, hh, mm, tz_name)
    if re.search(r"\btomorrow\b", ttxt):
        d = now_local + timedelta(days=1)
        return _mk_dt(d.year, d.month, d.day, hh, mm, tz_name)
    if re.search(r"\btonight\b", ttxt):
        hh2, mm2 = (23, 59) if not tmatch else (hh, mm)
        return _mk_dt(now_local.year, now_local.month, now_local.day, hh2, mm2, tz_name)

    # CN: 本周X/下周X
    cn_wk_map = {'一':0,'二':1,'三':2,'四':3,'五':4,'六':5,'日':6,'天':6}
    m = re.search(r"(本周|这周|下周)\s*([一二三四五六日天])", txt)
    if m:
        base = now_local
        target = cn_wk_map.get(m.group(2), None)
        if target is not None:
            current = base.weekday()  # Monday=0
            delta = (target - current) % 7
            if m.group(1) == '下周':
                delta = delta + (7 if delta == 0 else 7)
            # for 本周, if target is today and no time given, keep today
            day = base + timedelta(days=delta)
            return _mk_dt(day.year, day.month, day.day, hh, mm, tz_name)

    # CN: 月底/本月底/本月末
    if any(k in txt for k in ['月底', '本月底', '本月末']):
        y, m = now_local.year, now_local.month
        last_day = calendar.monthrange(y, m)[1]
        return _mk_dt(y, m, last_day, hh, mm, tz_name)

    # CN: 下月X日/号
    m = re.search(r"下月\s*(\d{1,2})[日号]", txt)
    if m:
        y, m0 = now_local.year, now_local.month
        nm = m0 + 1
        ny = y + (1 if nm == 13 else 0)
        nm = 1 if nm == 13 else nm
        d = min(int(m.group(1)), calendar.monthrange(ny, nm)[1])
        return _mk_dt(ny, nm, d, hh, mm, tz_name)

    # EN: EOD
    if re.search(r"\bEOD\b", txt, re.I):
        return _mk_dt(now_local.year, now_local.month, now_local.day, 23, 59, tz_name)

    # EN: 'Ends in 2 days', 'in 3 days', '2 days left'
    m = re.search(r"(?:ends?\s+in|in)\s+(\d+)\s*(day|days|hour|hours|minute|minutes)\b", txt, re.I)
    if not m:
        m = re.search(r"(\d+)\s*(day|days|hour|hours|minute|minutes)\s*(left|remaining)?\b", txt, re.I)
    if m:
        num = int(m.group(1))
        unit = m.group(2).lower()
        delta = None
        if unit.startswith('day'):
            delta = timedelta(days=num)
            dt_local = now_local.replace(hour=23, minute=59) + delta
        elif unit.startswith('hour'):
            delta = timedelta(hours=num)
            dt_local = now_local + delta
        else:
            delta = timedelta(minutes=num)
            dt_local = now_local + delta
        return dt_local.astimezone(timezone.utc)

    # CN: 'X天后', 'X小时后', '剩余X天/小时', '还剩X天/小时'
    m = re.search(r"(剩余|还剩)?\s*(\d+)\s*(天|日|小时|分钟)(?:后|之后|后截止|后结束|截止|结束)?", txt)
    if m:
        num = int(m.group(2))
        unit = m.group(3)
        if unit in ('天', '日'):
            dt_local = now_local.replace(hour=23, minute=59) + timedelta(days=num)
        elif unit == '小时':
            dt_local = now_local + timedelta(hours=num)
        else:
            dt_local = now_local + timedelta(minutes=num)
        return dt_local.astimezone(timezone.utc)

    return None
