from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple, Optional
from urllib import request, error
from html import unescape
from urllib.parse import urljoin, urlparse

from src.sources.allowlist import derive_domain
from src.utils.dates import parse_date_smart


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
_META_OG_DESC_RE = re.compile(r"<meta[^>]+property=\"og:description\"[^>]+content=\"([^\"]*)\"[^>]*>", re.I)
_META_TW_DESC_RE = re.compile(r"<meta[^>]+name=\"twitter:description\"[^>]+content=\"([^\"]*)\"[^>]*>", re.I)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_HEAD_RE = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.I | re.S)
_UL_RE = re.compile(r"<ul[^>]*>(.*?)</ul>", re.I | re.S)
_LI_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.I | re.S)


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
    m = _META_DESC_RE.search(html) or _META_OG_DESC_RE.search(html) or _META_TW_DESC_RE.search(html)
    if m:
        desc = m.group(1).strip()
        if len(desc) >= 20:
            return desc
    for pm in _P_RE.finditer(html):
        text = _strip_tags(pm.group(1))
        if len(text) >= 15:
            return text
    # remove scripts/styles before stripping
    body = _strip_tags(_SCRIPT_STYLE_RE.sub(" ", html))
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
                if parse_date_smart(ds):
                    return ds
    # fallback: first date in text
    m = date_pat.search(text)
    if m and parse_date_smart(m.group(1)):
        return m.group(1)
    return None


def _find_requirements(html: str) -> Optional[str]:
    # Extract around headings and list items
    candidates = []
    html2 = _SCRIPT_STYLE_RE.sub(" ", html)
    # 1) Headings-based extraction
    heading_kws = [
        "要求", "任职要求", "岗位要求", "职位要求", "资格", "条件",
        "职责", "岗位职责", "职位描述", "工作内容",
        "Requirement", "Requirements", "Qualifications", "Responsibilities", "Job Description",
    ]
    for hm in _HEAD_RE.finditer(html2):
        htxt = _strip_tags(hm.group(1))
        if any(kw.lower() in htxt.lower() for kw in heading_kws):
            # window: until next heading or 1500 chars
            start = hm.end()
            next_h = _HEAD_RE.search(html2, start)
            end = next_h.start() if next_h else min(len(html2), start + 4000)
            win = html2[start:end]
            # gather list items first
            lis = _LI_RE.findall(win)
            li_text = "; ".join([_strip_tags(li) for li in lis])
            if li_text:
                candidates.append(li_text)
            # then paragraphs
            ps = _P_RE.findall(win)
            ps_text = "; ".join([_strip_tags(p) for p in ps])
            if ps_text:
                candidates.append(ps_text)
            if candidates:
                break
    # 2) Keyword-window if no heading section found
    if not candidates:
        text = _strip_tags(html2)
        blocks = []
        for kw in ["要求", "资格", "报名条件", "参与方式", "任职要求", "职责", "submission", "requirement", "eligibility"]:
            for m in re.finditer(re.escape(kw), text, re.I):
                s = max(0, m.start() - 120)
                e = min(len(text), m.end() + 240)
                blk = text[s:e].strip()
                if blk and blk not in blocks:
                    blocks.append(blk)
        if blocks:
            candidates.append("; ".join(blocks))
    if not candidates:
        return None
    joined = "; ".join(candidates)
    return joined[:800]


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
                    plain = _strip_tags(_SCRIPT_STYLE_RE.sub(" ", dhtml))
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
                    # llm context: title + summary + req + body snippet
                    ctx_parts = [title]
                    if summary:
                        ctx_parts.append(summary)
                    if req:
                        ctx_parts.append(req)
                    if plain:
                        ctx_parts.append(plain[:1000])
                    item["llm_context"] = "\n".join(ctx_parts)[:1500]
                except Exception:
                    # keep minimal item
                    failed_pages.append(url)
            results.append(item)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return results, failed_pages


def fetch_detail(
    category: str,
    url: str,
    timeout: int,
    proxies: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Deep-fetch a single URL to enrich fields for LLM and rendering.

    Returns a dict possibly containing: summary, requirements, deadline,
    location, work_mode, llm_context.
    """
    out: Dict[str, Any] = {}
    try:
        dhtml = _fetch(url, timeout=timeout, proxies=proxies)
    except Exception:
        return out
    summary = _first_paragraph(dhtml)
    req = _find_requirements(dhtml)
    plain = _strip_tags(_SCRIPT_STYLE_RE.sub(" ", dhtml))
    deadline = None
    location = None
    work_mode = None
    if category in ("contest", "activity"):
        deadline = _find_deadline(plain)
    if category == "internship":
        location, work_mode = _find_location_and_mode(plain)
    if summary:
        out["summary"] = summary
    if req:
        out["requirements"] = req
    if deadline:
        out["deadline"] = deadline
    if location:
        out["location"] = location
    if work_mode:
        out["work_mode"] = work_mode
    # Build llm_context from available pieces; include a body snippet
    parts: List[str] = []
    # title will be added by caller if desired; here we focus on body
    if summary:
        parts.append(summary)
    if req:
        parts.append(req)
    if plain:
        parts.append(plain[:1200])
    if parts:
        out["llm_context"] = "\n".join(parts)[:1500]
    return out
