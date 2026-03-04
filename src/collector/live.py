from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
from urllib import request, error
from html import unescape
from urllib.parse import urljoin, urlparse

from src.sources.allowlist import derive_domain


def _fetch(url: str, timeout: int, proxies: Dict[str, str] | None = None, ua: str | None = None) -> str:
    handlers = []
    if proxies and (proxies.get("http") or proxies.get("https")):
        handlers.append(request.ProxyHandler({k: v for k, v in proxies.items() if v}))
    opener = request.build_opener(*handlers)
    headers = {"User-Agent": ua or "Mozilla/5.0 (MonitoringScript)"}
    req = request.Request(url, headers=headers)
    with opener.open(req, timeout=timeout) as resp:  # type: ignore
        data = resp.read()
        # naive encoding detection
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="ignore")
        return text


_A_RE = re.compile(r"<a\s+[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_links(base_url: str, html: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for m in _A_RE.finditer(html):
        href = unescape(m.group(1))
        text = unescape(m.group(2))
        text = _TAG_RE.sub(" ", text)
        full = urljoin(base_url, href)
        out.append((full, " ".join(text.split())))
    return out


def collect_from_pages(
    category: str,
    pages: List[str],
    allow_domains: List[str],
    include_kw: List[str],
    exclude_kw: List[str],
    limit: int,
    timeout: int,
    proxies: Dict[str, str] | None = None,
) -> tuple[List[Dict[str, Any]], List[str]]:
    results: List[Dict[str, Any]] = []
    failed_pages: List[str] = []
    for pg in pages:
        try:
            html = _fetch(pg, timeout=timeout, proxies=proxies)
        except Exception:
            failed_pages.append(pg)
            continue
        for url, text in _extract_links(pg, html):
            dom = derive_domain(url)
            if dom and allow_domains and all(dom != d and (not dom.endswith("." + d)) for d in allow_domains):
                continue
            low = (text or "") .lower()
            if include_kw and not any(k.lower() in low for k in include_kw):
                continue
            if exclude_kw and any(k.lower() in low for k in exclude_kw):
                continue
            title = text[:200] if text else url
            results.append({
                "source": dom or urlparse(url).netloc,
                "url": url,
                "title": title,
            })
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return results, failed_pages
