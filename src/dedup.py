from __future__ import annotations

from typing import List, Tuple
from datetime import datetime, timezone

from src.models import Item
from src.storage.db import Database


def apply_dedup(db: Database, items: List[Item], by_url: bool = True) -> Tuple[List[Item], int]:
    seen_urls = set()
    out: List[Item] = []
    dropped = 0
    for it in items:
        if by_url:
            if it.url in seen_urls:
                dropped += 1
                continue
            seen_urls.add(it.url)
            existing = db.get_by_url(it.url)
            if existing is None:
                it.is_new = True
            else:
                it.is_new = False
                # preserve first_seen_time from DB, update last_seen_time
                try:
                    it.first_seen_time = datetime.fromisoformat(existing["first_seen_time"])  # type: ignore
                except Exception:
                    pass
        out.append(it)
    return out, dropped

