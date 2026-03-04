from datetime import datetime, timezone, timedelta

from src.utils.dates import parse_date_basic, parse_date_smart, is_within_days


def test_parse_date_basic():
    dt = parse_date_basic("2026-04-05")
    assert dt and dt.year == 2026 and dt.month == 4 and dt.tzinfo is not None


def test_parse_date_smart_cn_full():
    dt = parse_date_smart("报名截止：2026年04月05日 23:59")
    assert dt and dt.year == 2026 and dt.month == 4 and dt.day == 5


def test_parse_date_smart_en():
    dt = parse_date_smart("Deadline: Apr 5, 2026 11:59 pm")
    assert dt and dt.year == 2026 and dt.month == 4 and dt.day == 5


def test_parse_date_smart_range():
    ref = datetime(2026, 3, 1, tzinfo=timezone.utc)
    dt = parse_date_smart("活动时间 4/1-4/10", now=ref)
    assert dt and dt.month == 4 and dt.day == 10


def test_is_within_days():
    now = datetime(2026, 3, 4, tzinfo=timezone.utc)
    future = now + timedelta(days=10)
    assert is_within_days(future, 14, now=now)
    past = now - timedelta(days=1)
    assert not is_within_days(past, 14, now=now)
