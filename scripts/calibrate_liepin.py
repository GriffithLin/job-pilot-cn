"""猎聘 discover+enrich 校准（无 LLM，不烧 token）。

用法: uv run python -u scripts/calibrate_liepin.py [关键词] [城市] [limit]
0 岗时自动 live dump：记录 XHR URL + 存 HTML，供 selector 诊断。
"""

from __future__ import annotations

import sys
from urllib.parse import quote

from jobpilot import db
from jobpilot.discovery.browser import BrowserSession
from jobpilot.discovery.liepin import CITY_CODES, LiepinDiscoverer
from jobpilot.enrichment.detail import enrich_jobs

kw = sys.argv[1] if len(sys.argv) > 1 else "算子开发"
city = sys.argv[2] if len(sys.argv) > 2 else "上海"
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10

conn = db.connect()
db.init_db(conn)
with BrowserSession("liepin") as session:
    jobs = LiepinDiscoverer().run(session.context, kw, {"cities": [city]}, limit=limit)
    print(f"\n[校准] discover 返回 {len(jobs)} 岗", flush=True)
    for j in jobs[:limit]:
        print(f"  - {j['job_title']} | {j['company']} | {j['city']} "
              f"| {j['salary_raw']} | {j['url'][:70]}", flush=True)
    new = sum(1 for j in jobs if db.upsert_job(conn, j))
    print(f"[校准] 入库新增 {new}", flush=True)

    if not jobs:  # live dump：XHR 全录 + HTML 落盘
        page = session.new_page()
        urls: list[str] = []
        page.on("response", lambda r: urls.append(r.url)
                if ("searchfront" in r.url or "/api/search" in r.url) and len(urls) < 40
                else None)
        page.goto(f"https://www.liepin.com/zhaopin/?key={quote(kw)}&city={CITY_CODES.get(city, '020')}",
                  wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(6_000)
        page.screenshot(path="scripts/_liepin_dump.png")
        with open("scripts/_liepin_dump.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"[dump] HTML/截图已存 scripts/_liepin_dump.*，捕获 XHR {len(urls)} 条:", flush=True)
        for u in urls[:20]:
            print(f"  {u[:150]}", flush=True)
        page.close()
    else:
        n = enrich_jobs(conn, session, "liepin", limit=5)
        print(f"[校准] enrich 成功 {n}/5", flush=True)
        for r in conn.execute(
            "SELECT job_title, company, salary_raw, length(full_description) AS L, "
            "substr(full_description,1,150) AS head FROM jobs "
            "WHERE platform='liepin' AND full_description IS NOT NULL "
            "ORDER BY detail_scraped_at DESC LIMIT 3"
        ):
            print(f"  [JD {r['L']}字] {r['job_title']} | {r['company']} | {r['salary_raw']}",
                  flush=True)
            print(f"    {r['head']}", flush=True)
conn.close()
