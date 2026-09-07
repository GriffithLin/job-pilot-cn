"""Discoverer 公共基类 + 纯代码过滤链（不进 LLM，省钱）。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .. import config


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def apply_filters(job: dict[str, Any], profile: dict) -> str | None:
    """返回 reject_reason；None = 通过。顺序：标题黑名单 → 日结岗 → HR 不活跃 → 公司黑名单 → 薪资。"""
    prefs = profile.get("preferences", {})
    title = job.get("job_title") or ""

    for pattern in prefs.get("title_blacklist", []):
        if re.search(pattern, title):
            return f"title_blacklist:{pattern}"

    if "元/天" in (job.get("salary_raw") or ""):
        return "daily_wage:日结岗"

    active = job.get("hr_active") or ""
    if active and ("月前活跃" in active or "年前活跃" in active):
        return f"hr_inactive:{active}"

    company = (job.get("company") or "").lower()
    for name in prefs.get("company_blacklist", []):
        if name.lower() in company:
            return f"company_blacklist:{name}"

    if job.get("salary_min") and job.get("salary_max"):
        salary_min_k = prefs.get("salary_min_k")
        if salary_min_k:
            months = job.get("salary_months") or 12
            median = (job["salary_min"] + job["salary_max"]) / 2 * months / 12
            if median < salary_min_k:
                return f"salary_below:{median:.0f}K < {salary_min_k}K"

    return None


class BaseDiscoverer:
    platform: str = ""

    def run(self, context, keyword: str, conf: dict,
            limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _finalize(self, raw_jobs: list[dict[str, Any]], keyword: str,
                  limit: int) -> list[dict[str, Any]]:
        """过滤链 + 公共字段补齐。"""
        profile = config.load_profile()
        jobs: list[dict[str, Any]] = []
        for j in raw_jobs[:limit * 3]:  # 过滤会淘汰一部分，多取一些
            job = {**j, "platform": self.platform, "search_source": keyword}
            reason = apply_filters(job, profile)
            if reason:
                job["reject_reason"] = reason
                job["rejected_at"] = now_iso()
            job.setdefault("discovered_at", now_iso())
            jobs.append(job)
            # 通过过滤的够数即停；被拒的继续收集（报告尾供翻案）
            if len([x for x in jobs if not x.get("reject_reason")]) >= limit:
                pass  # 通过过滤的够数即停，被拒岗继续收集（报告尾供翻案）
        return jobs
