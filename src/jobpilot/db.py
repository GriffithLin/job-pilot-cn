"""SQLite 数据总线：单表 jobs + WAL + upsert/查询辅助。

阶段间只通过本表交互（列级状态机，谓词见 models.py），
模块边界铁律：discovery/enrichment 只写 discover/enrich 列，
scoring 只写 score/greet/tailor 列，禁止跨模块直接调用。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  url            TEXT PRIMARY KEY,
  platform       TEXT NOT NULL CHECK(platform IN ('boss','liepin')),

  -- discover
  job_title      TEXT,
  company        TEXT,
  city           TEXT,
  district       TEXT,
  salary_raw     TEXT,
  salary_min     INTEGER,
  salary_max     INTEGER,
  salary_months  INTEGER,
  job_tags       TEXT,
  hr_name        TEXT,
  hr_title       TEXT,
  hr_active      TEXT,
  search_source  TEXT,
  discovered_at  TEXT,

  -- enrich
  full_description TEXT,
  apply_url      TEXT,
  detail_scraped_at TEXT,
  enrich_error   TEXT,
  enrich_attempts INTEGER DEFAULT 0,

  -- 过滤（纯代码规则淘汰，不进 LLM）
  reject_reason  TEXT,
  rejected_at    TEXT,

  -- score
  fit_score      INTEGER,
  score_keywords TEXT,
  score_reasoning TEXT,
  scored_at      TEXT,

  -- greet
  greeting       TEXT,
  greeting_fallback INTEGER DEFAULT 0,
  greeting_generated_at TEXT,

  -- tailor
  resume_bullets TEXT,
  tailor_failed  TEXT,
  tailored_at    TEXT,

  -- 人工回路
  manually_sent_at TEXT,
  human_notes    TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(fit_score) WHERE fit_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_pending_score
  ON jobs(full_description) WHERE full_description IS NOT NULL AND fit_score IS NULL;
"""

_DISCOVER_COLUMNS = {
    "url", "platform", "job_title", "company", "city", "district",
    "salary_raw", "salary_min", "salary_max", "salary_months", "job_tags",
    "hr_name", "hr_title", "hr_active", "search_source", "discovered_at",
}
ALLOWED_COLUMNS = _DISCOVER_COLUMNS | {
    "full_description", "apply_url", "detail_scraped_at", "enrich_error", "enrich_attempts",
    "reject_reason", "rejected_at",
    "fit_score", "score_keywords", "score_reasoning", "scored_at",
    "greeting", "greeting_fallback", "greeting_generated_at",
    "resume_bullets", "tailor_failed", "tailored_at",
    "manually_sent_at", "human_notes",
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_job(conn: sqlite3.Connection, job: dict[str, Any]) -> bool:
    """插入岗位行；url 冲突则忽略。返回 True 表示新增。"""
    cols = {k: v for k, v in job.items() if k in ALLOWED_COLUMNS and v is not None}
    bad = set(job) - ALLOWED_COLUMNS
    if bad:
        raise ValueError(f"未知列: {bad}")
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    try:
        conn.execute(f"INSERT INTO jobs ({names}) VALUES ({marks})", tuple(cols.values()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def fetch(conn: sqlite3.Connection, where: str = "1=1", params: Iterable = (),
          order: str = "ORDER BY discovered_at DESC") -> list[sqlite3.Row]:
    cur = conn.execute(f"SELECT * FROM jobs WHERE {where} {order}", tuple(params))
    return cur.fetchall()


def update_columns(conn: sqlite3.Connection, url: str, **cols: Any) -> None:
    bad = set(cols) - ALLOWED_COLUMNS
    if bad:
        raise ValueError(f"未知列: {bad}")
    if not cols:
        return
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE jobs SET {sets} WHERE url = ?", (*cols.values(), url))
    conn.commit()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    """jp status 的计数板数据源。"""
    q = lambda sql, p=(): (conn.execute(sql, tuple(p)).fetchone() or [0])[0]  # noqa: E731
    return {
        "总岗位": q("SELECT COUNT(*) FROM jobs"),
        "待抓详情": q(
            "SELECT COUNT(*) FROM jobs WHERE discovered_at IS NOT NULL"
            " AND detail_scraped_at IS NULL AND reject_reason IS NULL"
        ),
        "已过滤": q("SELECT COUNT(*) FROM jobs WHERE reject_reason IS NOT NULL"),
        "待打分": q(
            "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
            " AND fit_score IS NULL AND reject_reason IS NULL"
        ),
        "已打分": q("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"),
        "高分岗(≥7)": q("SELECT COUNT(*) FROM jobs WHERE fit_score >= 7"),
        "待发清单": q(
            "SELECT COUNT(*) FROM jobs WHERE greeting_generated_at IS NOT NULL"
            " AND manually_sent_at IS NULL AND reject_reason IS NULL"
        ),
        "已人工发送": q("SELECT COUNT(*) FROM jobs WHERE manually_sent_at IS NOT NULL"),
    }
