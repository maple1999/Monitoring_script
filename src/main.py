from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Dict, List

from src.config import load_config
from src.storage.db import Database
from src.models import Item, RunStatus
from src.collector.stub import collect as collect_stub
from src.collector.live import collect_from_pages
from src.collector.kaggle_api import collect_kaggle_contests
from src.parser.normalizer import normalize_raw
from src.dedup import apply_dedup
from src.scorer import score_items
from src.selector import pick_top1_per_category
from src.renderer import render_email
from src.mailer import send_email, MailError
from src.llm import generate_llm_block, translate_title_summary, LLMError
from src.alerts import send_alert
from src.sources.allowlist import load_allowlist
from src.utils.dates import parse_date_basic, is_within_days


def run_once(dry_run: bool = False) -> int:
    cfg = load_config()
    db = Database()
    prev_runs = db.last_runs(1)
    prev_status = prev_runs[0]["status"] if prev_runs else None
    run_id = db.insert_run(RunStatus.SUCCESS, stats_json=None, error_summary=None)
    degraded_notice: List[str] = []
    alert_events: List[Dict[str, str]] = []

    try:
        limits = cfg.get("limits", {})
        per_cat_limits = {
            "contest": int(limits.get("contest_candidates", 15)),
            "activity": int(limits.get("activity_candidates", 15)),
            "internship": int(limits.get("internship_candidates", 30)),
        }

        items_by_cat: Dict[str, List[Item]] = {"contest": [], "activity": [], "internship": []}
        stats: Dict[str, Dict[str, int]] = {"contest": {}, "activity": {}, "internship": {}}
        failed_pages_all: List[str] = []

        include_kw = list(cfg.get("keywords", {}).get("include", []))
        exclude_kw = list(cfg.get("keywords", {}).get("exclude", []))
        net_cfg = cfg.get("network", {})
        proxies = {
            "http": net_cfg.get("http_proxy") or "",
            "https": net_cfg.get("https_proxy") or "",
        }
        timeout = int(net_cfg.get("timeout_seconds", 10))

        # choose collector
        live_enabled = bool(cfg.get("sources", {}).get("enable_live_collect", False))
        allowlist_file = cfg.get("sources", {}).get("allowlist_file", "configs/domains_allowlist.yaml")
        allow = load_allowlist(allowlist_file)
        list_pages = cfg.get("sources", {}).get("list_pages", {})

        for cat in items_by_cat.keys():
            if live_enabled:
                pages = list(list_pages.get(cat, []))
                allow_domains = list(allow.get(cat, []))
                raws, failed_pages = collect_from_pages(
                    cat, pages, allow_domains, include_kw, exclude_kw, per_cat_limits[cat], timeout, proxies
                )
                failed_pages_all.extend(failed_pages)
            else:
                # If Kaggle API enabled and category is contest, use it
                if cat == "contest" and cfg.get("sources", {}).get("kaggle", {}).get("use_api", True):
                    kt = cfg.get("sources", {}).get("kaggle", {})
                    terms = list(kt.get("search_terms", []))
                    pages_k = int(kt.get("pages", 1))
                    raws, k_err = collect_kaggle_contests(terms, include_kw, exclude_kw, per_cat_limits[cat], pages=pages_k)
                    if k_err:
                        failed_pages_all.append(f"kaggle_api:{k_err}")
                else:
                    raws = collect_stub(cat, per_cat_limits[cat])

            raw_count = len(raws)
            items = [normalize_raw(cat, r) for r in raws]
            items, dropped = apply_dedup(db, items, by_url=bool(cfg.get("dedup", {}).get("by_url", True)))

            # filter expired for contest/activity
            expired_filtered = 0
            if cat in ("contest", "activity"):
                kept: List[Item] = []
                for it in items:
                    if it.deadline:
                        dt = parse_date_basic(it.deadline)
                        if dt and dt < datetime.now(timezone.utc):
                            it.status = "expired"
                            expired_filtered += 1
                            continue
                    kept.append(it)
                items = kept

            score_items(cfg, items)
            items_by_cat[cat] = items
            stats[cat] = {
                "raw": raw_count,
                "dedup_dropped": int(dropped),
                "expired_filtered": int(expired_filtered),
                "kept": len(items),
                "new": sum(1 for i in items if i.is_new),
            }

        selected = pick_top1_per_category(db, cfg, items_by_cat)

        # quality gate: min score per category
        min_score = cfg.get("selection", {}).get("min_score", {})
        for cat, it in list(selected.items()):
            thr = float(min_score.get(cat, 0.0))
            if (it.match_score or 0.0) < thr:
                better = [x for x in items_by_cat.get(cat, []) if (x.match_score or 0.0) >= thr]
                if better:
                    selected[cat] = sorted(better, key=lambda x: (-(x.is_new), -(x.match_score or 0.0)))[0]
                else:
                    # try history
                    hist = db.history_candidates(cat, int(cfg.get("staleness", {}).get("max_days_active", 30)), limit=10)
                    picked = None
                    for h in hist:
                        try:
                            ms = float(h.get("match_score") or 0.0)
                        except Exception:
                            ms = 0.0
                        if ms >= thr:
                            picked = h
                            break
                    if picked:
                        selected[cat] = Item(
                            item_id=picked["item_id"],
                            category=picked["category"],
                            title=picked["title"],
                            url=picked["url"],
                            source=picked["source"],
                            company_or_org=picked.get("company_or_org"),
                            summary=picked.get("summary"),
                            requirements=picked.get("requirements"),
                            location=picked.get("location"),
                            work_mode=picked.get("work_mode"),
                            deadline=picked.get("deadline"),
                            title_en=picked.get("title_en"),
                            title_zh=picked.get("title_zh"),
                            summary_en=picked.get("summary_en"),
                            summary_zh=picked.get("summary_zh"),
                            tags=(picked.get("tags") or "").split(",") if picked.get("tags") else [],
                            is_new=False,
                            status=picked.get("status", "active"),
                        )
                    else:
                        degraded_notice.append(f"{cat} 匹配度低于阈值")
                        alert_events.append({"type": "Content", "affected": cat, "msg": "匹配度低于阈值"})

        # LLM block generation per selected item
        llm_fail = False
        for cat, it in selected.items():
            try:
                block = generate_llm_block(cfg, it)
                it.llm_block = block
                translate_title_summary(cfg, it)
            except LLMError:
                llm_fail = True
                it.llm_block = None
        if llm_fail:
            degraded_notice.append("LLM 不可用，已使用 Fallback 文本")
            alert_events.append({"type": "LLM", "affected": "比赛/活动/实习", "msg": "LLM 失败或不可用"})

        # deadline reminders
        remind_days = int(cfg.get("deadline", {}).get("remind_days", 14))
        reminders: List[str] = []
        for cat in ("contest", "activity"):
            it = selected.get(cat)
            if it and it.deadline:
                dt = parse_date_basic(it.deadline)
                if dt and is_within_days(dt, remind_days):
                    reminders.append(f"{cat}『{it.title}』临近截止: {it.deadline}")

        # crawl anomalies: zero candidates K days
        zero_k = int(cfg.get("alerts", {}).get("zero_candidates_k", 2))
        for cat in ("contest", "activity", "internship"):
            if stats[cat]["kept"] == 0:
                prevs = db.last_runs(max(0, zero_k - 1))
                zero_chain = 1
                for pr in prevs:
                    try:
                        st = json.loads(pr.get("stats_json") or "{}")
                        if st.get("stats", {}).get(cat, {}).get("kept", 0) == 0:
                            zero_chain += 1
                        else:
                            break
                    except Exception:
                        break
                if zero_chain >= zero_k:
                    degraded_notice.append(f"{cat} 连续{zero_chain}天候选为0，已降级")
                    alert_events.append({"type": "Crawl", "affected": cat, "msg": f"连续{zero_chain}天候选为0"})

        # repetitive duplicates anomaly
        for cat in ("contest", "activity", "internship"):
            raw_c = stats[cat].get("raw", 0)
            drop_c = stats[cat].get("dedup_dropped", 0)
            if raw_c >= 5 and raw_c > 0 and (drop_c / float(raw_c)) >= 0.8:
                degraded_notice.append(f"{cat} 候选重复率过高")
                alert_events.append({"type": "Crawl", "affected": cat, "msg": "重复≥80%"})

        # overview lines
        counts_line = (
            f"候选抓取数量（比赛 {stats['contest'].get('raw',0)} / 活动 {stats['activity'].get('raw',0)} / 实习 {stats['internship'].get('raw',0)}）"
        )
        new_line = (
            f"新增（比赛 {stats['contest'].get('new',0)} / 活动 {stats['activity'].get('new',0)} / 实习 {stats['internship'].get('new',0)}）"
        )
        failures_line = "来源失败页：{}（不展开）".format(len(failed_pages_all)) if failed_pages_all else ""

        notice_parts = []
        if prev_status == RunStatus.FAILED.value:
            notice_parts.append("上次失败")
        if degraded_notice:
            notice_parts.extend(degraded_notice)
        if reminders:
            notice_parts.append("；".join(reminders))
        overview = {
            "status": "degraded" if (degraded_notice or failed_pages_all) else "success",
            "notice": "；".join(notice_parts),
            "counts_line": counts_line,
            "new_line": new_line,
            "failures_line": failures_line,
            "ordering": cfg.get("output", {}).get("display_time_preference", "last_seen"),
        }

        email = render_email(selected, overview)

        if not dry_run:
            try:
                send_email(cfg, email["subject"], email["text"], email["html"])
                db.log_send(run_id, "daily", cfg.get("smtp", {}).get("receiver_email", ""), email["subject"], "success")
            except MailError as e:
                db.log_send(
                    run_id, "daily", cfg.get("smtp", {}).get("receiver_email", ""), email["subject"], "failed", error=str(e)
                )
                alert_events.append({"type": "Run", "affected": "全量", "msg": f"SMTP 失败: {str(e)}"})
                db.update_run(run_id, RunStatus.FAILED, stats_json=None, error_summary=f"mail failed: {str(e)}")
                send_alert(cfg, run_id, "Run", "全量", f"SMTP 失败: {str(e)}", degraded=False)
                return 2
        else:
            print(email["subject"])
            print(email["text"])  # for preview

        # persist candidates
        for cat, items in items_by_cat.items():
            for it in items:
                db.upsert_item(it)

        # finalize run status
        stats_payload = {"stats": stats, "failed_pages": failed_pages_all}
        if degraded_notice or failed_pages_all:
            db.update_run(run_id, RunStatus.DEGRADED, stats_json=json.dumps(stats_payload, ensure_ascii=False))
        else:
            db.update_run(run_id, RunStatus.SUCCESS, stats_json=json.dumps(stats_payload, ensure_ascii=False))

        # separate alerts if enabled
        if alert_events and cfg.get("alerts", {}).get("send_separate_email", True):
            for ev in alert_events:
                send_alert(cfg, run_id, ev["type"], ev["affected"], ev["msg"], degraded=True)
        return 0

    except Exception as e:
        send_alert(cfg, run_id, "Run", "全量", f"异常: {str(e)}", degraded=False)
        db.update_run(run_id, RunStatus.FAILED, stats_json=None, error_summary=str(e))
        return 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not send email; print to stdout")
    args = parser.parse_args()

    if args.once or True:
        code = run_once(dry_run=args.dry_run)
        sys.exit(code)


if __name__ == "__main__":
    main()
