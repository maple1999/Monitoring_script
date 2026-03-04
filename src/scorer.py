from __future__ import annotations

from typing import Dict, List
from datetime import datetime, timezone

from src.models import Item
from src.sources.allowlist import derive_domain


def score_items(cfg: Dict, items: List[Item]):
    weights = cfg.get("scoring", {}).get("weights", {})
    w_new = float(weights.get("w_new", 2.0))
    w_time = float(weights.get("w_time", 1.0))
    w_scale = float(weights.get("w_scale", 1.0))
    w_topic = float(weights.get("w_topic", 1.5))
    w_urgency = float(weights.get("w_urgency", 0.5))

    now = datetime.now(timezone.utc)
    for it in items:
        score = 0.0
        # newness
        score += w_new if it.is_new else 0.0
        # recency (hours)
        try:
            hours = (now - it.last_seen_time).total_seconds() / 3600.0
            score += w_time * max(0.0, 48.0 - hours) / 48.0
        except Exception:
            pass
        # topic tags
        tags = set(map(str.lower, it.tags or []))
        if any(t in tags for t in ["cv", "computer vision"]):
            score += w_topic
        elif any(t in tags for t in ["多模态", "multimodal", "aigc", "vlm", "llm"]):
            score += 0.7 * w_topic
        # scale proxy by domain/company
        dom = derive_domain(it.url)
        top_domains = set(cfg.get("sources", {}).get("top_company_domains", []))
        if dom and any(dom == d or dom.endswith("." + d) for d in top_domains):
            score += w_scale
        # urgency for contest/activity
        if it.category in ("contest", "activity") and it.deadline:
            # simple heuristic: if contains '2026' like strings and soon
            score += 0.2 * w_urgency
        it.match_score = round(score, 3)
