from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple, Optional
from urllib import request, error
from html import unescape
from urllib.parse import urljoin, urlparse

from src.sources.allowlist import derive_domain
from src.utils.dates import parse_date_basic


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
_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
_META_DESC_RE = re.compile(r"<meta[^>]+name=\"description\"[^>]+content=\"([^\"]*)\"[^>]*>", re.I)


def _extract_links(base_url: str, html: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for m in _A_RE.finditer(html):
        href = unescape(m.group(1))
        text = unescape(m.group(2))
        text = _TAG_RE.sub(" ", text)
        full = urljoin(base_url, href)
        out.append((full, " ".join(text.split())))
    return out


def _strip_tags(html: str) -> str:
    return " ".join(_TAG_RE.sub(" ", html).split())


def _first_paragraph(html: str) -> Optional[str]:
    m = _META_DESC_RE.search(html)
    if m:
        desc = m.group(1).strip()
        if len(desc) >= 20:
            return desc
    for pm in _P_RE.finditer(html):
        text = _strip_tags(pm.group(1))
        if len(text) >= 15:
            return text
    body = _strip_tags(html)
    return body[:280] if body else None


def _find_deadline(text: str) -> Optional[str]:
    # find date token near deadline keywords (中英)
    if not text:
        return None
    # collect candidate date strings
    date_pat = re.compile(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})")
    # search windows around keywords
    for kw in ["截止", "报名截止", "截止日期", "deadline", "close", "报名截至"]:
        for m in re.finditer(re.escape(kw), text, re.I):
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            win = text[start:end]
            dm = date_pat.search(win)
            if dm:
                ds = dm.group(1)
                if parse_date_basic(ds):
                    return ds
    # fallback: first date in text
    m = date_pat.search(text)
    if m and parse_date_basic(m.group(1)):
        return m.group(1)
    return None


def _find_requirements(html: str) -> Optional[str]:
    # simple heuristic: extract lines near requirement keywords or list items
    text = _strip_tags(html)
    blocks = []
    for kw in ["要求", "资格", "报名条件", "参与方式", "任职要求", "职责", "submission", "requirement", "eligibility"]:
        for m in re.finditer(re.escape(kw), text, re.I):
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 160)
            blk = text[start:end].strip()
            if blk and blk not in blocks:
                blocks.append(blk)
    if not blocks:
        return None
    # compress
    joined = "; ".join(blocks)
    return joined[:500]


def _find_location_and_mode(text: str) -> Tuple[Optional[str], Optional[str]]:
    location = None
    work_mode = None
    # work mode detect
    if re.search(r"远程|remote", text, re.I):
        work_mode = "remote"
    elif re.search(r"混合|hybrid", text, re.I):
        work_mode = "hybrid"
    elif re.search(r"现场|线下|onsite", text, re.I):
        work_mode = "onsite"
    # location detect
    m = re.search(r"(地点|location)[：: ]{0,2}([\u4e00-\u9fa5A-Za-z\-/ ]{2,30})", text, re.I)
    if m:
        location = m.group(2).strip()
    # also common city keywords (simple list)
    for city in ["北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "武汉", "苏州", "南京", "厦门", "长沙", "青岛", "天津", "重庆", "Hong Kong", "Beijing", "Shanghai", "Guangzhou", "Shenzhen", "Hangzhou"]:
        if city in text:
            location = location or city
            break
    return location, work_mode


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
            item = {
                "source": dom or urlparse(url).netloc,
                "url": url,
                "title": title,
            }
            # Detail-page enrichment for activity/internship
            if category in ("activity", "internship"):
                try:
                    dhtml = _fetch(url, timeout=timeout, proxies=proxies)
                    summary = _first_paragraph(dhtml)
                    req = _find_requirements(dhtml)
                    plain = _strip_tags(dhtml)
                    deadline = None
                    location = None
                    work_mode = None
                    if category == "activity":
                        deadline = _find_deadline(plain)
                    else:
                        location, work_mode = _find_location_and_mode(plain)
                    if summary:
                        item["summary"] = summary
                    if req:
                        item["requirements"] = req
                    if deadline:
                        item["deadline"] = deadline
                    if location:
                        item["location"] = location
                    if work_mode:
                        item["work_mode"] = work_mode
                except Exception:
                    # keep minimal item
                    failed_pages.append(url)
            results.append(item)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return results, failed_pages
