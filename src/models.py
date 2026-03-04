from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib


SINGAPORE_TZ = timezone(timedelta(hours=8))


class RunStatus(str, Enum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"


def gen_item_id(source: str, url: str) -> str:
    h = hashlib.sha256()
    h.update((source.strip() + "|" + url.strip()).encode("utf-8"))
    return h.hexdigest()[:16]


@dataclass
class Item:
    item_id: str
    category: str  # contest | activity | internship
    title: str
    url: str
    source: str
    company_or_org: Optional[str] = None
    summary: Optional[str] = None
    requirements: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None  # remote | onsite | hybrid | offline
    deadline: Optional[str] = None   # raw string, best-effort
    title_en: Optional[str] = None
    title_zh: Optional[str] = None
    summary_en: Optional[str] = None
    summary_zh: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    first_seen_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_new: bool = True
    status: str = "active"  # active | expired | invalid
    # scoring
    match_score: Optional[float] = None
    # rendered
    llm_block: Optional[str] = None
    # extra context for LLM (plain text snippet)
    llm_context: Optional[str] = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_sgt() -> datetime:
    return datetime.now(SINGAPORE_TZ)

