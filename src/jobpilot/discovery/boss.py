"""Boss 直聘 discoverer：搜索页滚动采集 + 薪资字体反爬解码。

选择器集中在 LOCATORS，平台改版只改这里。
"""

from __future__ import annotations

import random
import re
import time
from typing import Any
from urllib.parse import quote

from .base import BaseDiscoverer

BOSS_HOME = "https://www.zhipin.com"

# 常用城市代码（Boss 的 city 参数），更多城市在 searches.yaml 里用 code: 覆盖
CITY_CODES = {
    "北京": "101010100", "上海": "101020100", "深圳": "101280600",
    "广州": "101280100", "杭州": "101210100", "成都": "101270100",
    "南京": "101190100", "苏州": "101190400", "武汉": "101200100",
    "西安": "101110100", "合肥": "101220100",
}

# 薪资字体反爬：PUA 私有区字符 → 数字。
# 2026-09 实测段为 U+E031-E03A（kanzhun 字体）；get_jobs 时代的 E8F0-E8F9 一并保留
SALARY_FONT = {chr(0xE8F0 + i): str(i) for i in range(10)}
SALARY_FONT.update({chr(0xE031 + i): str(i) for i in range(10)})

# 2026-09 实测的列表页结构：
# - 薪资是 span.job-salary（旧文档写的 span.salary 已不存在）
# - span.company-name 已下线，公司名装在 span.boss-name 里
# - HR 名/头衔/活跃度不再展示在列表卡片上
LOCATORS = {
    "job_card": "ul.rec-job-list li.job-card-box",
    "job_name": "a.job-name",
    "salary": "span.job-salary",
    "company_name": "span.boss-name",
    "company_location": "span.company-location",
    "tag_list": "ul.tag-list li",
}

_SALARY_RE = re.compile(r"^(\d+)-(\d+)[Kk](?:·(\d+)薪)?$")


def decode_salary_font(text: str) -> str:
    """私有区反爬字符 → 正常数字。"""
    return "".join(SALARY_FONT.get(ch, ch) for ch in text)


def parse_salary(raw: str) -> tuple[int, int, int] | None:
    """'25-45K·16薪' → (25, 45, 16)；解析失败返回 None。"""
    if not raw:
        return None
    m = _SALARY_RE.match(raw.strip())
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    months = int(m.group(3)) if m.group(3) else 12
    return (min(lo, hi), max(lo, hi), months)


class BossDiscoverer(BaseDiscoverer):
    platform = "boss"

    def build_url(self, keyword: str, city: str, conf: dict) -> str:
        code = conf.get("city_codes", {}).get(city) or CITY_CODES.get(city, "101010100")
        params = f"query={quote(keyword)}&city={code}"
        if salary := conf.get("boss_salary", ""):
            params += f"&salary={salary}"
        return f"{BOSS_HOME}/web/geek/jobs?{params}"

    def run(self, context, keyword: str, conf: dict,
            limit: int = 20) -> list[dict[str, Any]]:
        cities = conf.get("cities", ["北京"])
        raw: list[dict[str, Any]] = []
        # 多城平分配额：原来「攒够 limit*2 就停」会让排前面的城市吃光配额，
        # 后面的城市被整体跳过——五城场景必须每城都有产出
        per_city = limit if len(cities) <= 1 else max(4, limit // len(cities))
        for city in cities:
            raw.extend(self._scrape_city(context, keyword, city, conf, per_city))
        return self._finalize(raw, keyword, limit)

    def _scrape_city(self, context, keyword: str, city: str, conf: dict,
                     limit: int) -> list[dict[str, Any]]:
        from .browser import pause_if_challenge

        page = context.new_page()
        # 单卡字段缺失时 locator 自动等待默认 30s 会拖垮整批，压到 2s
        page.set_default_timeout(2_000)
        try:
            url = self.build_url(keyword, city, conf)
            print(f"[boss] 打开 {url}", flush=True)
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            print(f"[boss] 页面加载完成，当前 URL: {page.url}", flush=True)
            pause_if_challenge(page)
            page.wait_for_selector(LOCATORS["job_card"], timeout=30_000)
            print(f"[boss] 卡片列表已出现，开始滚动加载（目标 {min(limit, 30)}）", flush=True)
            self._scroll_to_bottom(page, target=min(limit, 30))
            count = page.locator(LOCATORS["job_card"]).count()
            print(f"[boss] 滚动完成，共 {count} 张卡片，开始提取", flush=True)
            return self._extract_cards(page, keyword)
        finally:
            page.close()

    def _scroll_to_bottom(self, page, target: int, max_rounds: int = 20) -> None:
        """增量滚动：卡片数 3 轮不变 → 触底。"""
        stable = 0
        last_count = 0
        for _ in range(max_rounds):
            page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            time.sleep(random.uniform(0.8, 1.6))
            count = page.locator(LOCATORS["job_card"]).count()
            if count == last_count:
                stable += 1
                if stable >= 3 or count >= target:
                    break
            else:
                stable = 0
            last_count = count
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

    def _extract_cards(self, page, keyword: str) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        failed = 0
        cards = page.locator(LOCATORS["job_card"]).all()
        for card in cards:
            try:
                jobs.append(self._extract_one(card, keyword))
            except Exception:
                failed += 1  # 单卡失败不拖垮整批
        if failed:
            print(f"[boss] {failed}/{len(cards)} 张卡片提取失败已跳过", flush=True)
        return [j for j in jobs if j]

    def _extract_one(self, card, keyword: str) -> dict[str, Any] | None:
        if card.locator(LOCATORS["job_name"]).count() == 0:
            return None  # 广告/推荐卡没有岗位链接
        href = card.locator(LOCATORS["job_name"]).first.get_attribute("href") or ""
        if not href or "job_detail" not in href:
            return None
        url = href if href.startswith("http") else BOSS_HOME + href
        url = url.split("?")[0]  # 去掉安全参数，做规范化主键

        def _text(sel: str) -> str:
            loc = card.locator(sel)
            return loc.first.text_content().strip() if loc.count() else ""

        salary_raw = decode_salary_font(_text(LOCATORS["salary"]))
        parsed = parse_salary(salary_raw)
        tags = [t.strip() for t in
                card.locator(LOCATORS["tag_list"]).all_text_contents() if t.strip()]

        location = [p.strip() for p in _text(LOCATORS["company_location"]).split("·")]
        return {
            "url": url,
            "job_title": _text(LOCATORS["job_name"]),
            "company": _text(LOCATORS["company_name"]),
            "city": location[0] if location else "",
            "district": location[1] if len(location) > 1 else "",  # 如「浦东新区」
            "salary_raw": salary_raw,
            "salary_min": parsed[0] if parsed else None,
            "salary_max": parsed[1] if parsed else None,
            "salary_months": parsed[2] if parsed else None,
            "job_tags": tags and str(tags) or None,  # JSON 数组字符串
            "hr_name": "",   # 列表卡片已不再展示 HR 名/头衔/活跃度
            "hr_title": "",
            "hr_active": "",
        }
