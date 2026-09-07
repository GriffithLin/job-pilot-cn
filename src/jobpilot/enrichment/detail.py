"""Enrich 阶段：抓 JD 全文。

Boss：优先走详情 API（/wapi/zpgeek/job/detail.json 服务端 JSON，
无字体反爬），DOM 兜底；猎聘：详情页 DOM 直接抓。
"""

from __future__ import annotations

import random
import time
from typing import Any

from .. import db, models
from ..discovery.browser import BrowserSession

BOSS_HOME = "https://www.zhipin.com"

# Boss 详情 API（列表页点击卡片时触发）
BOSS_DETAIL_API = "**/wapi/zpgeek/job/detail.json*"

# JD 正文候选选择器（平台改版时逐个尝试，取第一个命中的）
BOSS_JD_SELECTORS = [
    "div.job-sec-text",
    "div.job-detail-section",
    "div[class*='job-sec']",
]
LIEPIN_JD_SELECTORS = [
    # 2026-09 实测：<section class="job-intro-container"><dl class="paragraph">
    "section.job-intro-container",
    "dd.job-intro-container",
    "div[class*='job-description']",
]


def enrich_jobs(conn, session: BrowserSession, platform: str,
                limit: int = 20) -> int:
    """抓取待 enrich 岗位的 JD 全文；返回成功数。"""
    rows = db.fetch(
        conn,
        f"{models.PENDING_ENRICH} AND platform = ? AND enrich_attempts < 3",
        [platform],
        order="ORDER BY discovered_at ASC",
    )[:limit]
    done = 0
    for r in rows:
        try:
            desc = (_enrich_boss(session, r) if platform == "boss"
                    else _enrich_liepin(session, r))
            if desc:
                db.update_columns(
                    conn, r["url"],
                    full_description=desc,
                    apply_url=r["apply_url"] or r["url"],
                    detail_scraped_at=models.now_iso(),
                    enrich_attempts=(r["enrich_attempts"] or 0) + 1,
                )
                done += 1
            else:
                db.update_columns(
                    conn, r["url"],
                    enrich_error="未找到 JD 正文（选择器可能过期）",
                    enrich_attempts=(r["enrich_attempts"] or 0) + 1,
                )
        except Exception as e:
            db.update_columns(
                conn, r["url"],
                enrich_error=str(e)[:200],
                enrich_attempts=(r["enrich_attempts"] or 0) + 1,
            )
        time.sleep(random.uniform(2, 4))
    return done


def _extract_text(page, selectors: list[str], min_len: int = 50) -> str:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count():
            text = "\n".join(t.strip() for t in loc.all_text_contents() if t.strip())
            if len(text) >= min_len:
                return text
    return ""


def _enrich_boss(session: BrowserSession, row: Any) -> str:
    """打开 Boss 详情页：API 拦截优先（列表页点击触发的 detail.json 不一定
    在直接打开详情页时出现，超时即降级 DOM 抓取）。"""
    from ..discovery.browser import pause_if_challenge

    page = session.new_page()
    try:
        url = row["apply_url"] or row["url"]
        if not url.startswith("http"):
            url = BOSS_HOME + url
        desc = ""
        try:
            with page.expect_response(BOSS_DETAIL_API, timeout=10_000) as resp_info:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            data = resp_info.value.json()
            zpData = (data.get("zpData") or {}).get("jobInfo") or {}
            desc = (zpData.get("postDescription")
                    or zpData.get("jobDescription") or "")
        except Exception:
            page.wait_for_load_state("domcontentloaded", timeout=30_000)
        pause_if_challenge(page)
        if len(desc) < 50:
            desc = _extract_text(page, BOSS_JD_SELECTORS)
        return desc
    finally:
        page.close()


def _enrich_liepin(session: BrowserSession, row: Any) -> str:
    from ..discovery.browser import pause_if_challenge

    page = session.new_page()
    try:
        url = row["apply_url"] or row["url"]
        if not url.startswith("http"):
            return ""
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        pause_if_challenge(page)
        # 2026-09：详情页是 React SPA，正文水合需数秒——轮询等选择器命中
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            desc = _extract_text(page, LIEPIN_JD_SELECTORS)
            if desc:
                return desc
            time.sleep(1.5)
        return ""
    finally:
        page.close()
