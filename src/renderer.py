from __future__ import annotations

from typing import Dict, List
from datetime import datetime, timezone
from email.utils import formatdate

from src.models import Item


def _item_block_text(it: Item) -> str:
    lines = []
    lines.append(f"[{'新增' if it.is_new else '存量'}] {it.title}")
    lines.append(f"链接: {it.url}")
    if it.company_or_org:
        lines.append(f"主办/公司: {it.company_or_org}")
    if it.location and it.category == "internship":
        lines.append(f"地点/模式: {it.location} / {it.work_mode or 'offline'}")
    if it.deadline and it.category in ("contest", "activity"):
        lines.append(f"截止: {it.deadline}")
    if it.summary:
        lines.append(f"摘要: {it.summary}")
    if it.llm_block:
        lines.append(f"{it.llm_block}")
    else:
        lines.append("评述: LLM 不可用，使用规则生成的简述。")
    return "\n".join(lines)


def _item_block_html(it: Item) -> str:
    parts = []
    badge = "新增" if it.is_new else "存量"
    parts.append(f"<p><strong>[{badge}] {it.title}</strong> — <a href='{it.url}'>链接</a></p>")
    parts.append("<ul>")
    if it.company_or_org:
        parts.append(f"<li>主办/公司: {it.company_or_org}</li>")
    if it.location and it.category == "internship":
        parts.append(f"<li>地点/模式: {it.location} / {it.work_mode or 'offline'}</li>")
    if it.deadline and it.category in ("contest", "activity"):
        parts.append(f"<li>截止: {it.deadline}</li>")
    if it.summary:
        parts.append(f"<li>摘要: {it.summary}</li>")
    if it.llm_block:
        parts.append(f"<li>{it.llm_block}</li>")
    else:
        parts.append("<li>评述: LLM 不可用，使用规则生成的简述。</li>")
    parts.append("</ul>")
    return "".join(parts)


def render_email(selected: Dict[str, Item], overview: Dict[str, str]) -> Dict[str, str]:
    date_str = datetime.now(timezone.utc).date().isoformat()
    subject = f"Daily CV Digest - {date_str}（比赛/活动/实习各 1）"
    status = overview.get("status", "success")
    top_notice = overview.get("notice", "")

    # text
    text_lines = [f"运行状态: {status}"]
    if top_notice:
        text_lines.append(f"提示: {top_notice}")
    for cat in ("contest", "activity", "internship"):
        it = selected.get(cat)
        if not it:
            continue
        text_lines.append("")
        text_lines.append(f"=== {cat.upper()} ===")
        text_lines.append(_item_block_text(it))
    text_body = "\n".join(text_lines)

    # html
    html_parts = [
        "<html><body>",
        f"<p>运行状态: <strong>{status}</strong></p>",
    ]
    if top_notice:
        html_parts.append(f"<p>提示: {top_notice}</p>")
    for cat in ("contest", "activity", "internship"):
        it = selected.get(cat)
        if not it:
            continue
        html_parts.append(f"<h3>{cat.upper()}</h3>")
        html_parts.append(_item_block_html(it))
    html_parts.append("</body></html>")
    html_body = "".join(html_parts)

    return {"subject": subject, "text": text_body, "html": html_body}
