# Monitoring Script

Daily digest for CV-related contests, activities, and internships. Sends one email per day with top 3 items (one per category). Built to be resilient, configurable, and minimal-dependency.

## Status

- M1 baseline (no LLM) — offline-friendly. Uses fixtures for tests and structure to plug collectors later.

## Quick Start

1) Create your config from the example:

- Copy `configs/config.example.yaml` to `configs/config.yaml` and fill SMTP and receiver fields.
- Set environment secrets, e.g. `SMTP_PASSWORD` and `LLM_API_KEY` (optional for later milestones).

2) Run once locally

```
python -m src.main --once
```

3) Schedule on server (recommended)

- Use systemd timer or crontab (`Asia/Singapore` time zone) to run `python -m src.main` daily at 08:45.

## Config

- See `configs/config.example.yaml` for all knobs and defaults.
- Secrets must be passed via environment variables (no secrets in git).

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

