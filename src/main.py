from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List

from src.config import load_config
from src.storage.db import Database
from src.models import Item, RunStatus
from src.collector.stub import collect as collect_stub
from src.parser.normalizer import normalize_raw
from src.dedup import apply_dedup
from src.scorer import score_items
from src.selector import pick_top1_per_category
from src.renderer import render_email
from src.mailer import send_email, MailError
from src.llm import generate_llm_block, LLMError
from src.alerts import send_alert


def run_once(dry_run: bool = False) -> int:
    cfg = load_config()
    db = Database()
    run_id = db.insert_run(RunStatus.SUCCESS, stats_json=None, error_summary=None)
    degraded_notice: List[str] = []

    try:
        limits = cfg.get("limits", {})
        per_cat_limits = {
            "contest": int(limits.get("contest_candidates", 15)),
            "activity": int(limits.get("activity_candidates", 15)),
            "internship": int(limits.get("internship_candidates", 30)),
        }

        items_by_cat: Dict[str, List[Item]] = {"contest": [], "activity": [], "internship": []}
        # M1/M2: stub collectors (fixtures)
        for cat in items_by_cat.keys():
            raws = collect_stub(cat, per_cat_limits[cat])
            items = [normalize_raw(cat, r) for r in raws]
            items, _ = apply_dedup(db, items, by_url=bool(cfg.get("dedup", {}).get("by_url", True)))
            score_items(cfg, items)
            items_by_cat[cat] = items

        selected = pick_top1_per_category(db, cfg, items_by_cat)

        # LLM block generation per selected item
        llm_fail = False
        for cat, it in selected.items():
            try:
                block = generate_llm_block(cfg, it)
                it.llm_block = block
            except LLMError as e:
                llm_fail = True
                it.llm_block = None
        if llm_fail:
            degraded_notice.append("LLM 不可用，已使用 Fallback 文本")

        overview = {"status": "degraded" if degraded_notice else "success", "notice": "; ".join(degraded_notice)}
        email = render_email(selected, overview)

        if not dry_run:
            try:
                send_email(cfg, email["subject"], email["text"], email["html"])
                db.log_send(run_id, "daily", cfg.get("smtp", {}).get("receiver_email", ""), email["subject"], "success")
            except MailError as e:
                db.log_send(run_id, "daily", cfg.get("smtp", {}).get("receiver_email", ""), email["subject"], "failed", error=str(e))
                # try to send alert via alert channel (could be same smtp though)
                send_alert(cfg, run_id, "Run", "全量", f"SMTP 失败: {str(e)}", degraded=False)
                db.insert_run(RunStatus.FAILED, stats_json=None, error_summary=f"mail failed: {str(e)}")
                return 2
        else:
            print(email["subject"])
            print(email["text"])  # for preview

        # persist selected and candidates
        for cat, items in items_by_cat.items():
            for it in items:
                db.upsert_item(it)

        if degraded_notice:
            db.insert_run(RunStatus.DEGRADED, stats_json=json.dumps({"notice": degraded_notice}, ensure_ascii=False))
            send_alert(cfg, run_id, "LLM", "比赛/活动/实习", "; ".join(degraded_notice), degraded=True)
        else:
            db.insert_run(RunStatus.SUCCESS, stats_json=None)
        return 0

    except Exception as e:
        send_alert(cfg, run_id, "Run", "全量", f"异常: {str(e)}", degraded=False)
        db.insert_run(RunStatus.FAILED, stats_json=None, error_summary=str(e))
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

