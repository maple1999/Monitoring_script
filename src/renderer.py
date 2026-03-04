from __future__ import annotations

from typing import Dict, List
from datetime import datetime, timezone
from email.utils import formatdate

from src.models import Item


def _fmt_title(it: Item) -> str:
    # Title bilingual display when English-only detected and translation exists
    if it.title_en and it.title_zh:
        return f"[EN] {it.title_en} | [ZH] {it.title_zh}"
    return it.title


def _item_block_text(it: Item) -> str:
    lines = []
    lines.append(f"[{'新增' if it.is_new else '存量'}] {_fmt_title(it)}")
    lines.append(f"链接: {it.url}")
    if it.company_or_org:
        lines.append(f"主办/公司: {it.company_or_org}")
    if it.location and it.category == "internship":
        lines.append(f"地点/模式: {it.location} / {it.work_mode or 'offline'}")
    if it.category in ("contest", "activity"):
        if it.deadline:
            lines.append(f"时间: 截止 {it.deadline}")
        else:
            lines.append("时间: 未解析到DDL/页面未提供")
    if it.summary:
        if it.summary_en and it.summary_zh:
            lines.append(f"[EN] 摘要: {it.summary_en}")
            lines.append(f"[ZH] 摘要: {it.summary_zh}")
        else:
            lines.append(f"摘要: {it.summary}")
    if it.requirements:
        lines.append(f"要求: {it.requirements}")
    elif it.category in ("contest", "activity"):
        lines.append("要求: 未解析到/页面未提供")
    if it.llm_block:
        lines.append(f"{it.llm_block}")
    else:
        lines.append("评述: LLM 不可用，使用规则生成的简述。")
    return "\n".join(lines)


def _item_block_html(it: Item) -> str:
    parts = []
    badge = "新增" if it.is_new else "存量"
    parts.append(f"<p><strong>[{badge}] {_fmt_title(it)}</strong> — <a href='{it.url}'>链接</a></p>")
    parts.append("<ul>")
    if it.company_or_org:
        parts.append(f"<li>主办/公司: {it.company_or_org}</li>")
    if it.location and it.category == "internship":
        parts.append(f"<li>地点/模式: {it.location} / {it.work_mode or 'offline'}</li>")
    if it.category in ("contest", "activity"):
        if it.deadline:
            parts.append(f"<li>时间: 截止 {it.deadline}</li>")
        else:
            parts.append("<li>时间: 未解析到DDL/页面未提供</li>")
    if it.summary:
        if it.summary_en and it.summary_zh:
            parts.append(f"<li>[EN] 摘要: {it.summary_en}</li>")
            parts.append(f"<li>[ZH] 摘要: {it.summary_zh}</li>")
        else:
            parts.append(f"<li>摘要: {it.summary}</li>")
    if it.requirements:
        parts.append(f"<li>要求: {it.requirements}</li>")
    elif it.category in ("contest", "activity"):
        parts.append("<li>要求: 未解析到/页面未提供</li>")
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
    counts_line = overview.get("counts_line", "")
    new_line = overview.get("new_line", "")
    failures_line = overview.get("failures_line", "")
    ordering = overview.get("ordering", "last_seen")

    # compute ordering across categories: 新增优先 + 时间近（使用 last_seen/first_seen）
    items = list(selected.items())
    def sort_key(kv):
        _, it = kv
        t = getattr(it, f"{ordering}_time", None) or it.last_seen_time
        return (0 if it.is_new else 1, -t.timestamp())
    items.sort(key=sort_key)

    # text
    text_lines = [f"运行状态: {status}"]
    if top_notice:
        text_lines.append(f"提示: {top_notice}")
    if counts_line:
        text_lines.append(counts_line)
    if new_line:
        text_lines.append(new_line)
    if failures_line:
        text_lines.append(failures_line)
    for cat, it in items:
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
    if counts_line:
        html_parts.append(f"<p>{counts_line}</p>")
    if new_line:
        html_parts.append(f"<p>{new_line}</p>")
    if failures_line:
        html_parts.append(f"<p>{failures_line}</p>")
    for cat, it in items:
        html_parts.append(f"<h3>{cat.upper()}</h3>")
        html_parts.append(_item_block_html(it))
    html_parts.append("</body></html>")
    html_body = "".join(html_parts)

    return {"subject": subject, "text": text_body, "html": html_body}
