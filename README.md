# Monitoring Script

Daily digest for CV-related contests, activities, and internships. Sends one email per day with top 3 items (one per category). Built to be resilient, configurable, and minimal-dependency.

## Status

- M2 with LLM, alerts, scheduler-ready. Uses fixtures by default; enable live collection via config.

## Quick Start

1) Create your config from the example:

- Copy `configs/config.example.yaml` to `configs/config.yaml` and fill SMTP and receiver fields.
- Set environment secrets, e.g. `SMTP_PASSWORD` and `LLM_API_KEY` (optional for later milestones).

2) Run once locally

```
python -m src.main --once
```

3) Enable live collectors (optional)

- Edit `configs/config.yaml`:
  - `sources.enable_live_collect: true`
  - Fill `sources.list_pages.*` with list pages you trust
  - Ensure `configs/domains_allowlist.yaml` 包含可信域名（或开启自动维护）
  - 若在阿里云广州等环境，请在 `network.http_proxy/https_proxy` 中设置代理

4) Schedule on server (recommended)

- Use systemd timer or crontab to run `python -m src.main --once` daily at 08:45 Singapore time. 或使用内置调度：

```
python - <<'PY'
from src.scheduler import run_daily
from src.main import run_once
run_daily('08:45', lambda: run_once(False))
PY
```

## Config

- See `configs/config.example.yaml` for all knobs and defaults.
- Secrets must be passed via environment variables (no secrets in git).
 - LLM config in `llm.*`，支持 OpenAI 兼容接口；翻译仅在纯英文标题/摘要时启用。

## Development

- Install Python 3.10+
- Optional: `pip install -r requirements-dev.txt` (only for running tests; the core app uses stdlib only in M1)
- Run tests:

```
pytest -q
```

## Notes

- Network collectors are stubbed in M1 to avoid external dependencies and network flakiness. You can enable live collectors in M2+ via config flags and proxies.
- LLM integration is planned for M3; for now, the digest includes a simple fallback note.
