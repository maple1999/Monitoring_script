from __future__ import annotations

import json
import os
import ssl
from typing import Dict, Optional
from urllib import request, error

from src.models import Item


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

    prompt = build_prompt(item, primary_lang)
    messages = prompt["messages"]

    if provider == "openai_compatible":
        text = call_openai_compatible(
            api_key=api_key,
            model=model,
            base_url=base_url,
            messages=messages,
            temperature=temperature,
            timeout=timeout,
            proxies=proxies,
        )
    else:
        raise LLMError(f"Unsupported provider: {provider}")

    if not validate_llm_block(text):
        # one retry with stricter instruction
        messages2 = messages + [
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
