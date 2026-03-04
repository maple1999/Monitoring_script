from __future__ import annotations

import json
import os
import ssl
from typing import Dict, Optional
from urllib import request, error

from src.models import Item
import hashlib
import re


class LLMError(Exception):
    pass


def build_prompt(item: Item, primary_lang: str = "zh") -> Dict:
    instruct = (
        "你是一个严格的技术评审助手。根据给定的条目内容，"
        "只输出单段文本，必须严格遵循以下模板与顺序，不得编造缺失信息：\n"
        "难点评估：数据难点=…；工程难点=…；数学/算法难点=…；"
        "匹配度：R/5（理由：…）；"
        "评价：…（2句，逻辑严谨、无比喻）；"
        "补充信息：…（无则写“无”）。"
    )
    context = {
        "category": item.category,
        "title": item.title,
        "source": item.source,
        "company_or_org": item.company_or_org,
        "summary": item.summary,
        "requirements": item.requirements,
        "deadline": item.deadline if item.category in ("contest", "activity") else None,
        "location": item.location if item.category == "internship" else None,
        "work_mode": item.work_mode if item.category == "internship" else None,
        "tags": item.tags,
        "url": item.url,
        "language": primary_lang,
    }
    if item.llm_context:
        # Provide an additional excerpt for richer context (plain text)
        context["context_excerpt"] = item.llm_context[:1200]
    user_msg = (
        "请按模板输出单段文本，不要加入额外说明或标头。"
        "若页面未提供/未解析到某信息，必须明确指出‘页面未提供/未解析到’。\n"
        f"条目内容: {json.dumps(context, ensure_ascii=False)}"
    )
    return {
        "messages": [
            {"role": "system", "content": instruct},
            {"role": "user", "content": user_msg},
        ]
    }


def compute_llm_cache_key(cfg: Dict, item: Item) -> str:
    """Compute a stable cache key for LLM evaluation based on content + model.

    Includes: category, title, summary, requirements, llm_context, deadline/location/work_mode,
    tags, url, primary_lang, provider, model.
    """
    primary_lang = cfg.get("language", {}).get("primary", "zh")
    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "openai_compatible")
    model = llm_cfg.get("model", "")
    payload = {
        "category": item.category,
        "title": item.title,
        "summary": item.summary,
        "requirements": item.requirements,
        "llm_context": item.llm_context,
        "deadline": item.deadline if item.category in ("contest", "activity") else None,
        "location": item.location if item.category == "internship" else None,
        "work_mode": item.work_mode if item.category == "internship" else None,
        "tags": item.tags,
        "url": item.url,
        "primary_lang": primary_lang,
        "provider": provider,
        "model": model,
    }
    h = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return h


_JSON_FENCE_RE = re.compile(r"```(?:json)?(.*?)```", re.S | re.I)


def _extract_json_blob(text: str) -> Optional[str]:
    t = text.strip()
    m = _JSON_FENCE_RE.search(t)
    if m:
        return m.group(1).strip()
    # try plain json
    if t.startswith("[") or t.startswith("{"):
        return t
    return None


def batch_generate_llm(cfg: Dict, items: list[Item]) -> Dict[str, Dict[str, str]]:
    """Batch-generate LLM evaluations for multiple items in one request.

    Returns a mapping by url: { 'llm_block': str, 'title_zh': str|None, 'summary_zh': str|None }
    """
    if not items:
        return {}
    llm_cfg = cfg.get("llm", {})
    api_key = os.getenv(llm_cfg.get("api_key_env", "LLM_API_KEY"))
    if not api_key:
        return {}
    provider = llm_cfg.get("provider", "openai_compatible")
    model = llm_cfg.get("model", "gpt-3.5-turbo")
    base_url = llm_cfg.get("base_url", "https://api.openai.com/v1")
    temperature = float(llm_cfg.get("temperature", 0.2))
    timeout = int(llm_cfg.get("timeout_seconds", 20))
    primary_lang = cfg.get("language", {}).get("primary", "zh")

    proxies = None
    net_cfg = cfg.get("network", {})
    http_proxy = net_cfg.get("http_proxy") or os.getenv("HTTP_PROXY")
    https_proxy = net_cfg.get("https_proxy") or os.getenv("HTTPS_PROXY")
    if http_proxy or https_proxy:
        proxies = {"http": http_proxy or "", "https": https_proxy or ""}

    def need_trans_title(it: Item) -> bool:
        return primary_lang == "zh" and it.title and is_english_text(it.title)

    def need_trans_summary(it: Item) -> bool:
        return primary_lang == "zh" and it.summary and is_english_text(it.summary or "")

    payload_items = []
    for it in items:
        payload_items.append({
            "id": it.url,  # stable key
            "category": it.category,
            "title": it.title,
            "summary": it.summary,
            "requirements": it.requirements,
            "deadline": it.deadline if it.category in ("contest", "activity") else None,
            "location": it.location if it.category == "internship" else None,
            "work_mode": it.work_mode if it.category == "internship" else None,
            "tags": it.tags,
            "need_trans_title": need_trans_title(it),
            "need_trans_summary": need_trans_summary(it),
            "context_excerpt": (it.llm_context or "")[:1200],
        })

    system = (
        "你是一个严格的技术评审助手。对每个条目生成单段落的评审文本（严格按模板），"
        "并将评审文本与（如需）中文翻译一起以 JSON 数组返回。JSON 中每个对象必须包含：\n"
        "id, llm_block, title_zh(可为空), summary_zh(可为空)。\n"
        "llm_block 必须严格按模板且是单段文本：\n"
        "难点评估：数据难点=…；工程难点=…；数学/算法难点=…；匹配度：R/5（理由：…）；评价：…（2句，逻辑严谨、无比喻）；补充信息：…（无则写“无”）。\n"
        "如果 need_trans_title 为 true，提供 title_zh 为中文标题；否则 title_zh 为空字符串。\n"
        "如果 need_trans_summary 为 true，提供 summary_zh 为中文摘要；否则 summary_zh 为空字符串。\n"
        "不要输出除 JSON 以外的任何内容。"
    )
    user = json.dumps({"items": payload_items, "language": primary_lang}, ensure_ascii=False)

    try:
        content = call_openai_compatible(
            api_key=api_key,
            model=model,
            base_url=base_url,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            timeout=timeout,
            proxies=proxies,
        )
        blob = _extract_json_blob(content) or content
        data = json.loads(blob)
        out: Dict[str, Dict[str, str]] = {}
        if isinstance(data, list):
            for obj in data:
                try:
                    _id = obj.get("id")
                    if not _id:
                        continue
                    out[_id] = {
                        "llm_block": (obj.get("llm_block") or "").strip(),
                        "title_zh": (obj.get("title_zh") or "").strip(),
                        "summary_zh": (obj.get("summary_zh") or "").strip(),
                    }
                except Exception:
                    continue
        return out
    except Exception:
        return {}


def validate_llm_block(text: str) -> bool:
    if not text:
        return False
    req_keys = ["难点评估", "匹配度", "评价", "补充信息"]
    return all(k in text for k in req_keys) and ("\n" not in text.strip() or len(text.strip().splitlines()) <= 6)


def call_openai_compatible(
    api_key: str,
    model: str,
    base_url: str,
    messages: list,
    temperature: float = 0.2,
    timeout: int = 20,
    proxies: Optional[Dict[str, str]] = None,
) -> str:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    data = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Proxy handling
    opener = None
    if proxies and (proxies.get("http") or proxies.get("https")):
        proxy_handler = request.ProxyHandler({
            k: v for k, v in proxies.items() if v
        })
        opener = request.build_opener(proxy_handler)
    else:
        opener = request.build_opener()

    req = request.Request(endpoint, data=data, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with opener.open(req, timeout=timeout, context=ctx) as resp:  # type: ignore
            body = resp.read()
            obj = json.loads(body)
            content = obj.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise LLMError("Empty content from LLM provider")
            return content.strip()
    except error.HTTPError as e:
        raise LLMError(f"HTTPError: {e.code} {e.reason}")
    except error.URLError as e:
        raise LLMError(f"URLError: {e.reason}")
    except Exception as e:
        raise LLMError(str(e))


def generate_llm_block(cfg: Dict, item: Item) -> Optional[str]:
    llm_cfg = cfg.get("llm", {})
    if not llm_cfg or not llm_cfg.get("enabled", True):
        return None

    api_key = os.getenv(llm_cfg.get("api_key_env", "LLM_API_KEY"))
    if not api_key:
        return None

    provider = llm_cfg.get("provider", "openai_compatible")
    model = llm_cfg.get("model", "gpt-3.5-turbo")
    base_url = llm_cfg.get("base_url", "https://api.openai.com/v1")
    temperature = float(llm_cfg.get("temperature", 0.2))
    timeout = int(llm_cfg.get("timeout_seconds", 20))
    primary_lang = cfg.get("language", {}).get("primary", "zh")

    proxies = None
    net_cfg = cfg.get("network", {})
    http_proxy = net_cfg.get("http_proxy") or os.getenv("HTTP_PROXY")
    https_proxy = net_cfg.get("https_proxy") or os.getenv("HTTPS_PROXY")
    if http_proxy or https_proxy:
        proxies = {"http": http_proxy or "", "https": https_proxy or ""}

    # Single-item combined evaluation + optional translations via JSON
    need_trans_title = (primary_lang == "zh" and item.title and is_english_text(item.title)) and not item.title_zh
    need_trans_summary = (primary_lang == "zh" and item.summary and is_english_text(item.summary or "")) and not item.summary_zh
    system = (
        "你是一个严格的技术评审助手。你需要基于提供的条目信息："
        "(1) 生成一个单段落评审文本（严格按模板）；(2) 如需要则返回中文标题与中文摘要。\n"
        "仅输出一个 JSON 对象，包含字段：llm_block, title_zh, summary_zh。\n"
        "llm_block 必须严格按模板且为单段文本："
        "难点评估：数据难点=…；工程难点=…；数学/算法难点=…；匹配度：R/5（理由：…）；评价：…（2句，逻辑严谨、无比喻）；补充信息：…（无则写“无”）。\n"
        "如果不需要翻译，将 title_zh 或 summary_zh 设为空字符串。不要输出除 JSON 以外的任何内容。"
    )
    user_obj = {
        "item": {
            "category": item.category,
            "title": item.title,
            "summary": item.summary,
            "requirements": item.requirements,
            "deadline": item.deadline if item.category in ("contest", "activity") else None,
            "location": item.location if item.category == "internship" else None,
            "work_mode": item.work_mode if item.category == "internship" else None,
            "tags": item.tags,
            "url": item.url,
            "context_excerpt": (item.llm_context or "")[:1200],
        },
        "language": primary_lang,
        "need_trans_title": bool(need_trans_title),
        "need_trans_summary": bool(need_trans_summary),
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_obj, ensure_ascii=False)},
    ]

    if provider != "openai_compatible":
        raise LLMError(f"Unsupported provider: {provider}")

    content = call_openai_compatible(
        api_key=api_key,
        model=model,
        base_url=base_url,
        messages=messages,
        temperature=temperature,
        timeout=timeout,
        proxies=proxies,
    )
    blob = _extract_json_blob(content) or content
    try:
        obj = json.loads(blob)
        llm_block = (obj.get("llm_block") or "").strip()
        if obj.get("title_zh") and not item.title_zh:
            item.title_zh = (obj.get("title_zh") or "").strip()
        if obj.get("summary_zh") and not item.summary_zh:
            item.summary_zh = (obj.get("summary_zh") or "").strip()
        if validate_llm_block(llm_block):
            return llm_block
    except Exception:
        pass

    # fallback: use previous single-text prompt then validate
    prompt = build_prompt(item, primary_lang)
    text = call_openai_compatible(
        api_key=api_key,
        model=model,
        base_url=base_url,
        messages=prompt["messages"],
        temperature=temperature,
        timeout=timeout,
        proxies=proxies,
    )
    if not validate_llm_block(text):
        messages2 = prompt["messages"] + [
            {"role": "system", "content": "你上次未严格遵循模板。请严格按模板输出单段文本，不要添加额外内容。"}
        ]
        text = call_openai_compatible(
            api_key=api_key,
            model=model,
            base_url=base_url,
            messages=messages2,
            temperature=0.1,
            timeout=timeout,
            proxies=proxies,
        )
        if not validate_llm_block(text):
            return None
    return text.strip()


def is_english_text(s: str) -> bool:
    if not s:
        return False
    letters = sum(1 for ch in s if "a" <= ch.lower() <= "z" or ch in " -_,.;:!?()[]'\"\n")
    ratio = letters / max(1, len(s))
    return ratio > 0.8


def translate_title_summary(cfg: Dict, item: Item) -> None:
    # Only translate when primary language is zh and content is English-only
    primary_lang = cfg.get("language", {}).get("primary", "zh")
    mode = cfg.get("translation", {}).get("mode", "title_and_summary")
    if primary_lang != "zh" or mode != "title_and_summary":
        return
    need_title = item.title and is_english_text(item.title)
    need_summary = item.summary and is_english_text(item.summary or "")
    if not (need_title or need_summary):
        return

    llm_cfg = cfg.get("llm", {})
    api_key = os.getenv(llm_cfg.get("api_key_env", "LLM_API_KEY"))
    if not api_key:
        return
    model = llm_cfg.get("model", "gpt-3.5-turbo")
    base_url = llm_cfg.get("base_url", "https://api.openai.com/v1")
    timeout = int(llm_cfg.get("timeout_seconds", 20))

    def _ask(text: str) -> str:
        msgs = [
            {"role": "system", "content": "你是专业翻译，请将英文精准翻译成中文，不添加解释。"},
            {"role": "user", "content": text},
        ]
        return call_openai_compatible(api_key, model, base_url, msgs, temperature=0.0, timeout=timeout)

    try:
        if need_title:
            item.title_en = item.title
            item.title_zh = _ask(item.title)
        if need_summary and item.summary:
            item.summary_en = item.summary
            item.summary_zh = _ask(item.summary)
    except Exception:
        # best-effort; ignore translation failures
        pass
