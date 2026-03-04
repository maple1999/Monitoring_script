from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple


def _strip_comment(line: str) -> str:
    esc = False
    out = []
    for i, ch in enumerate(line):
        if ch == "#" and not esc:
            break
        if ch == "\\" and not esc:
            esc = True
            continue
        esc = False
        out.append(ch)
    return "".join(out).rstrip("\n\r")


def _parse_scalar(val: str):
    s = val.strip()
    if s == "":
        return ""
    if (s.startswith("\"") and s.endswith("\"")) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        pass
    return s


def parse_simple_yaml(text: str) -> Dict[str, Any]:
    # Minimal YAML subset: maps, lists, scalars, indentation (2 spaces typical), comments, quoted strings
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Any]] = [(-1, root)]

    def set_kv(container, key, value):
        if isinstance(container, dict):
            container[key] = value
        else:
            raise ValueError("Invalid container for key-value pair")

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = _strip_comment(raw)
        if not line.strip():
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        # Adjust stack by indentation
        while stack and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]

        if content.startswith("-"):
            # list item
            if not isinstance(parent, list):
                # create a list for previous key if parent is dict missing key
                raise ValueError("List item without list parent; this minimal parser expects explicit lists context")
            item_content = content[1:].strip()
            if ":" in item_content:
                # inline dict start
                key, val = item_content.split(":", 1)
                node: Dict[str, Any] = {}
                if val.strip():
                    node[key.strip()] = _parse_scalar(val)
                else:
                    # nested dict will be filled by child lines
                    pass
                parent.append(node)
                stack.append((indent, node))
            else:
                parent.append(_parse_scalar(item_content))
        else:
            # key: value or key:
            if ":" not in content:
                raise ValueError(f"Invalid line (missing colon): {content}")
            key, val = content.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val == "":
                # Start of nested map or list
                # Lookahead to decide list or dict
                # If next significant line starts with '-' at greater indent, treat as list
                j = i + 1
                kind = "dict"
                while j < len(lines):
                    nxt = _strip_comment(lines[j])
                    if not nxt.strip():
                        j += 1
                        continue
                    nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                    if nxt_indent <= indent:
                        break
                    if nxt.strip().startswith("-"):
                        kind = "list"
                    break
                if kind == "list":
                    node: List[Any] = []
                else:
                    node = {}
                if isinstance(parent, dict):
                    parent[key] = node
                else:
                    raise ValueError("Invalid nesting under non-dict parent")
                stack.append((indent, node))
            else:
                set_kv(parent, key, _parse_scalar(val))
        i += 1
    return root


def load_config() -> Dict[str, Any]:
    # Prefer user config; fallback to example
    base_path = os.path.join("configs", "config.yaml")
    example_path = os.path.join("configs", "config.example.yaml")
    path = base_path if os.path.exists(base_path) else example_path
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise TypeError("YAML root must be a mapping")
    except Exception:
        data = parse_simple_yaml(text)

    # Inject env secrets
    smtp_pw = os.getenv("SMTP_PASSWORD")
    if smtp_pw:
        data.setdefault("smtp", {})["password_env"] = "SMTP_PASSWORD"
    llm_key = os.getenv("LLM_API_KEY")
    if llm_key:
        data.setdefault("llm", {})["api_key_env"] = "LLM_API_KEY"
    return data

