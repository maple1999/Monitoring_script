from __future__ import annotations

import os
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

from src.config import parse_simple_yaml


DEFAULT_ALLOWLIST = {
    "contest": [
        "kaggle.com",
    ],
    "activity": [
        "devpost.com",
    ],
    "internship": [
        "tencent.com",
        "alibaba.com",
        "bytedance.com",
        "meituan.com",
        "jd.com",
        "pinduoduo.com",
        "baidu.com",
        "kuaishou.com",
        "xiaomi.com",
        "ctrip.com",
        "antgroup.com",
        "netease.com",
        "didiglobal.com",
        "zhihu.com",
        "xiaohongshu.com",
        "huawei.com",
        "iflytek.com",
        "lenovo.com",
        "byd.com",
        "dji.com",
        "deepseek.com",
    ],
}


def derive_domain(u: str) -> str:
    try:
        p = urlparse(u)
        host = p.netloc.lower()
        return host.split(":")[0]
    except Exception:
        return ""


def load_allowlist(path: str) -> Dict[str, List[str]]:
    if not os.path.exists(path):
        return DEFAULT_ALLOWLIST
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise TypeError
        return {k: list(v or []) for k, v in data.items()}
    except Exception:
        data = parse_simple_yaml(text)
        return {k: list(v or []) for k, v in data.items()}


def save_allowlist(path: str, allow: Dict[str, List[str]]):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lines = []
    for k in ("contest", "activity", "internship"):
        lines.append(f"{k}:")
        for d in sorted(set(allow.get(k, []))):
            lines.append(f"  - {d}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def autogen_update(path: str, from_urls: List[str]) -> Dict[str, List[str]]:
    allow = load_allowlist(path)
    # simple inference: just add domains to all categories for now
    domains: Set[str] = set(derive_domain(u) for u in from_urls if u)
    for k in ("contest", "activity", "internship"):
        cur = set(allow.get(k, []))
        cur.update(domains)
        allow[k] = sorted(cur)
    save_allowlist(path, allow)
    return allow

