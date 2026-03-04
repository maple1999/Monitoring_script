from datetime import datetime, timezone, timedelta

from src.utils.dates import parse_date_basic, is_within_days


def test_parse_date_basic():
    dt = parse_date_basic("2026-04-05")
    assert dt and dt.year == 2026 and dt.month == 4 and dt.tzinfo is not None


def test_is_within_days():
    now = datetime(2026, 3, 4, tzinfo=timezone.utc)
    future = now + timedelta(days=10)
    assert is_within_days(future, 14, now=now)
    past = now - timedelta(days=1)
    assert not is_within_days(past, 14, now=now)

