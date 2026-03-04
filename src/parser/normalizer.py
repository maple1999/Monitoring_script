from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime, timezone

from src.models import Item, gen_item_id, now_utc


def normalize_raw(category: str, raw: Dict[str, Any]) -> Item:
    source = raw.get("source") or raw.get("site") or "unknown"
    url = raw.get("url") or ""
    title = raw.get("title") or raw.get("name") or ""
    item = Item(
        item_id=gen_item_id(source, url),
        category=category,
        title=title,
        url=url,
        source=source,
        company_or_org=raw.get("company_or_org") or raw.get("company") or raw.get("org"),
        summary=raw.get("summary"),
        requirements=raw.get("requirements"),
        location=raw.get("location"),
        work_mode=raw.get("work_mode"),
        deadline=raw.get("deadline"),
        title_en=raw.get("title_en"),
        title_zh=raw.get("title_zh"),
        summary_en=raw.get("summary_en"),
        summary_zh=raw.get("summary_zh"),
        tags=list(raw.get("tags", [])),
        llm_context=raw.get("llm_context"),
        first_seen_time=now_utc(),
        last_seen_time=now_utc(),
        is_new=True,
        status="active",
    )
    return item
