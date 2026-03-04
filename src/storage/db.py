from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

from src.models import Item, gen_item_id, RunStatus


DEFAULT_DB_PATH = os.path.join("data", "app.db")


class Database:
    def __init__(self, path: str = DEFAULT_DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                item_id TEXT PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                company_or_org TEXT,
                summary TEXT,
                requirements TEXT,
                location TEXT,
                work_mode TEXT,
                deadline TEXT,
                title_en TEXT,
                title_zh TEXT,
                summary_en TEXT,
                summary_zh TEXT,
                tags TEXT,
                first_seen_time TEXT,
                last_seen_time TEXT,
                is_new INTEGER,
                status TEXT,
                match_score REAL,
                llm_block TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                status TEXT NOT NULL,
                stats_json TEXT,
                error_summary TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS send_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                mail_type TEXT NOT NULL,
                to_addr TEXT,
                subject TEXT,
                status TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_category_status ON items(category, status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_first_seen ON items(first_seen_time);")
        self.conn.commit()

    def upsert_item(self, item: Item):
        tags_str = ",".join(item.tags)
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO items (
                item_id, url, category, title, source, company_or_org, summary,
                requirements, location, work_mode, deadline, title_en, title_zh,
                summary_en, summary_zh, tags, first_seen_time, last_seen_time, is_new,
                status, match_score, llm_block
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                company_or_org=excluded.company_or_org,
                summary=excluded.summary,
                requirements=excluded.requirements,
                location=excluded.location,
                work_mode=excluded.work_mode,
                deadline=excluded.deadline,
                title_en=excluded.title_en,
                title_zh=excluded.title_zh,
                summary_en=excluded.summary_en,
                summary_zh=excluded.summary_zh,
                tags=excluded.tags,
                last_seen_time=excluded.last_seen_time,
                is_new=excluded.is_new,
                status=excluded.status,
                match_score=excluded.match_score,
                llm_block=excluded.llm_block
            ;
            """,
            (
                item.item_id,
                item.url,
                item.category,
                item.title,
                item.source,
                item.company_or_org,
                item.summary,
                item.requirements,
                item.location,
                item.work_mode,
                item.deadline,
                item.title_en,
                item.title_zh,
                item.summary_en,
                item.summary_zh,
                tags_str,
                item.first_seen_time.isoformat(),
                item.last_seen_time.isoformat(),
                1 if item.is_new else 0,
                item.status,
                item.match_score,
                item.llm_block,
            ),
        )
        self.conn.commit()

    def get_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM items WHERE url = ?", (url,))
        row = cur.fetchone()
        if not row:
            return None
        col = [c[0] for c in cur.description]
        return dict(zip(col, row))

    def insert_run(self, status: RunStatus, stats_json: Optional[str] = None, error_summary: Optional[str] = None) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO runs(started_at, status, stats_json, error_summary) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), status.value, stats_json, error_summary),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_run(self, run_id: int, status: RunStatus, stats_json: Optional[str] = None, error_summary: Optional[str] = None) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE runs SET status = ?, stats_json = ?, error_summary = ? WHERE run_id = ?",
            (status.value, stats_json, error_summary, run_id),
        )
        self.conn.commit()

    def last_runs(self, limit: int = 1) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM runs ORDER BY run_id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        col = [c[0] for c in cur.description]
        return [dict(zip(col, r)) for r in rows]

    def log_send(self, run_id: Optional[int], mail_type: str, to_addr: str, subject: str, status: str, error: Optional[str] = None):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO send_log(run_id, mail_type, to_addr, subject, status, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                mail_type,
                to_addr,
                subject,
                status,
                error,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def history_candidates(self, category: str, max_days_active: int, limit: int) -> List[Dict[str, Any]]:
        # Return active items in category sorted by most recent last_seen_time
        cur = self.conn.cursor()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_days_active)).isoformat()
        cur.execute(
            """
            SELECT * FROM items
            WHERE category = ? AND status = 'active' AND first_seen_time >= ?
            ORDER BY last_seen_time DESC
            LIMIT ?
            """,
            (category, cutoff, limit),
        )
        rows = cur.fetchall()
        if not rows:
            return []
        col = [c[0] for c in cur.description]
        return [dict(zip(col, r)) for r in rows]
