"""猎聘 discoverer：搜索页 XHR 拦截 jobCardList + AntD 分页。

XHR JSON 无字体反爬问题，比 DOM 解析稳。
"""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import quote

from .base import BaseDiscoverer

LIEPIN_HOME = "https://www.liepin.com"

# 猎聘城市代码（部分）
CITY_CODES = {
    "北京": "010", "上海": "020", "深圳": "050090",
    "广州": "050020", "杭州": "070020", "成都": "280020",
    "南京": "060020", "苏州": "060080", "武汉": "170020",
    "西安": "270020", "合肥": "150020",
}

# 拦截的 XHR 接口（排除 -cond-init 初始化请求）
XHR_MARKER = "com.liepin.searchfront4c.pc-search-job"

LOCATORS = {
    "next_page": "li.ant-pagination-next",
    "page_disabled": "ant-pagination-disabled",
}


class LiepinDiscoverer(BaseDiscoverer):
    platform = "liepin"

    def build_url(self, keyword: str, city: str, conf: dict) -> str:
        code = conf.get("city_codes", {}).get(city) or CITY_CODES.get(city, "010")
        return f"{LIEPIN_HOME}/zhaopin/?key={quote(keyword)}&city={code}"

    def run(self, context, keyword: str, conf: dict,
            limit: int = 20) -> list[dict[str, Any]]:
        cities = conf.get("cities", ["北京"])
        raw: list[dict[str, Any]] = []
        # 多城平分配额（同 boss.py：避免排前面的城市吃光配额饿死后面城市）
        per_city = limit if len(cities) <= 1 else max(4, limit // len(cities))
        for city in cities:
            raw.extend(self._scrape_city(context, keyword, city, conf, per_city))
        # 按 jobId/link 去重（多城市多页可能重复）
        seen: set[str] = set()
        deduped = []
        for j in raw:
            key = j.get("url") or j.get("job_title", "")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(j)
        return self._finalize(deduped, keyword, limit)

    def _scrape_city(self, context, keyword: str, city: str, conf: dict,
                     limit: int) -> list[dict[str, Any]]:
        from .browser import pause_if_challenge

        captured: list[dict] = []
        page = context.new_page()

        def on_response(resp):
            if XHR_MARKER not in resp.url or "-cond-init" in resp.url:
                return
            try:
                data = resp.json()
            except Exception:
                return
            # 2026-09 实测嵌套：flag → data → data → jobCardList（比旧文档多一层 data）
            cards = ((data.get("data") or {}).get("data") or {}).get("jobCardList") or []
            captured.extend(cards)

        try:
            page.on("response", on_response)
            page.goto(self.build_url(keyword, city, conf),
                      wait_until="domcontentloaded", timeout=60_000)
            pause_if_challenge(page)
            time.sleep(random.uniform(2, 4))

            # AntD 分页：点「下一页」直到禁用或抓够
            max_pages = conf.get("max_pages", 3)
            for _ in range(max_pages):
                if len(captured) >= limit:
                    break
                next_btn = page.locator(LOCATORS["next_page"]).first
                try:
                    cls = next_btn.get_attribute("class") or ""
                    if LOCATORS["page_disabled"] in cls:
                        break
                    next_btn.click()
                    time.sleep(random.uniform(3, 5))
                except Exception:
                    break

            return [self._map_card(c, keyword) for c in captured]
        finally:
            page.close()

    def _map_card(self, card: dict, keyword: str) -> dict[str, Any]:
        """jobCardList 条目 → jobs 表行。字段名以 2026-09 实测为准。"""
        job = card.get("job") or {}
        comp = card.get("comp") or {}
        rec = card.get("recruiter") or {}

        link = job.get("link") or ""
        if link and not str(link).startswith("http"):
            link = LIEPIN_HOME + str(link)
        salary_raw = str(job.get("salary") or "") or None
        parsed = _parse_liepin_salary(salary_raw)
        # dq 形如「上海-浦东新区」（- 分隔，非 ·）
        dq = str(job.get("dq") or "").split("-")
        tags = [str(t) for t in (job.get("labels") or []) if t]
        if job.get("requireWorkYears"):
            tags.append(str(job["requireWorkYears"]))
        if job.get("requireEduLevel"):
            tags.append(str(job["requireEduLevel"]))

        return {
            "url": link or f"liepin:{job.get('jobId') or job.get('title')}",
            "apply_url": link or None,
            "job_title": job.get("title") or "",
            "company": comp.get("compName") or "",
            "city": dq[0].strip(),
            "district": dq[1].strip() if len(dq) > 1 else "",
            "salary_raw": salary_raw,
            "salary_min": parsed[0] if parsed else None,
            "salary_max": parsed[1] if parsed else None,
            "salary_months": 12,
            "job_tags": str(tags) or None,
            # 猎聘卡片仍展示 HR 信息（imShowText 如「2月前活跃」）
            "hr_name": rec.get("recruiterName") or "",
            "hr_title": rec.get("recruiterTitle") or "",
            "hr_active": rec.get("imShowText") or "",
        }


def _parse_liepin_salary(raw: str) -> tuple[int, int, int] | None:
    import re

    m = re.match(r"^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)([KkWw万])", (raw or "").strip())
    if not m:
        return None
    lo, hi = float(m.group(1)), float(m.group(2))
    if m.group(3) in ("W", "w", "万"):  # 万/月 → K
        lo, hi = lo * 10, hi * 10
    return (int(min(lo, hi)), int(max(lo, hi)), 12)
