from __future__ import annotations

import json
import os
from typing import Any, Dict, List


FIXTURE_DIR = os.path.join("data", "fixtures")


def _load_fixture(name: str) -> List[Dict[str, Any]]:
    path = os.path.join(FIXTURE_DIR, f"{name}.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect(category: str, limit: int) -> List[Dict[str, Any]]:
    if category not in ("contest", "activity", "internship"):
        raise ValueError("Unknown category")
    items = _load_fixture(category)
    return items[:limit]

