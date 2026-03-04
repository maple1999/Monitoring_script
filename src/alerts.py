from __future__ import annotations

import json
from typing import Dict, Optional

from src.mailer import send_email, MailError


def send_alert(cfg: Dict, run_id: Optional[int], error_type: str, affected: str, error_summary: str, degraded: bool) -> None:
    alert_cfg = cfg.get("alerts", {})
    if not alert_cfg.get("enabled", True):
        return
    subject = f"[ALERT] CV Digest {'Degraded' if degraded else 'Failed'} - Run {run_id or '-'}"
    lines = [
        f"错误类型: {error_type}",
        f"影响范围: {affected}",
        f"关键错误信息: {error_summary}",
        f"Run ID: {run_id or '-'}",
        "建议操作: 检查SMTP/LLM Key/站点结构与网络代理设置",
    ]
    text = "\n".join(lines)
    html = "<html><body>" + "".join(f"<p>{l}</p>" for l in lines) + "</body></html>"
    try:
        send_email(cfg, subject, text, html)
    except MailError:
        # If alert cannot be sent, silently ignore here; main flow can log this into DB if needed
        pass

