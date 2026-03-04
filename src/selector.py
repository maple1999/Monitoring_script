from __future__ import annotations

from typing import Dict, List, Tuple
from src.models import Item
from src.storage.db import Database


def pick_top1_per_category(db: Database, cfg: Dict, items_by_cat: Dict[str, List[Item]]) -> Dict[str, Item]:
    result: Dict[str, Item] = {}
    limits = cfg.get("limits", {})
    max_days_active = int(cfg.get("staleness", {}).get("max_days_active", 30))

    for cat in ("contest", "activity", "internship"):
        candidates = sorted(items_by_cat.get(cat, []), key=lambda x: (-(x.is_new), -(x.match_score or 0.0)))
        if candidates:
            result[cat] = candidates[0]
            continue
        # fallback to history
        hist = db.history_candidates(cat, max_days_active, limit=10)
        if hist:
            # choose the first
            h = hist[0]
            item = Item(
                item_id=h["item_id"],
                category=h["category"],
                title=h["title"],
                url=h["url"],
                source=h["source"],
                company_or_org=h.get("company_or_org"),
                summary=h.get("summary"),
                requirements=h.get("requirements"),
                location=h.get("location"),
                work_mode=h.get("work_mode"),
                deadline=h.get("deadline"),
                title_en=h.get("title_en"),
                title_zh=h.get("title_zh"),
                summary_en=h.get("summary_en"),
                summary_zh=h.get("summary_zh"),
                tags=(h.get("tags") or "").split(",") if h.get("tags") else [],
                is_new=False,
                status=h.get("status", "active"),
            )
            result[cat] = item
    return result

