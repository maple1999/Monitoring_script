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

3) Enable live collectors or Kaggle API (optional)

- Edit `configs/config.yaml`:
  - 使用 Kaggle 官方 API（推荐）：
    - `sources.kaggle.use_api: true`
    - 设置环境变量 `KAGGLE_USERNAME` 和 `KAGGLE_KEY`，或将 `kaggle.json` 放到用户目录（~/.kaggle/kaggle.json / C:\Users\你\.kaggle\kaggle.json）
    - 可调整 `sources.kaggle.search_terms` 以聚焦 CV 相关竞赛
  - 或开启页面抓取（可选）：
    - `sources.enable_live_collect: true`
    - 填充 `sources.list_pages.*`，并在 `configs/domains_allowlist.yaml` 维护可信域名
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

### NVIDIA 免费 API 配置

- 该项目已兼容 NVIDIA AI Endpoints（OpenAI-Compatible）。示例配置：

```
llm:
  enabled: true
  provider: openai_compatible
  base_url: https://integrate.api.nvidia.com/v1
  model: meta/llama-3.1-8b-instruct
  temperature: 0.2
  timeout_seconds: 20
  api_key_env: NVIDIA_API_KEY
```

- 设置环境变量：

```
export NVIDIA_API_KEY=your_key_here   # Linux/macOS
setx NVIDIA_API_KEY your_key_here     # Windows PowerShell 需重新打开终端
```

- 烟囱测试（不会发送邮件）：

```
python scripts/llm_smoke.py
```

- 若需代理（阿里云广州等环境）：在 `configs/config.yaml` 中设置 `network.http_proxy/https_proxy`。

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
