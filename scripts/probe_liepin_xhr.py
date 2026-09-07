"""猎聘 XHR body 探针：看 pc-search-job 新 JSON 结构 + city=020 是否真过滤了上海。"""
import json
from urllib.parse import quote

from jobpilot.discovery.browser import BrowserSession

with BrowserSession("liepin") as session:
    page = session.new_page()
    page.set_default_timeout(5_000)
    bodies = []

    def on_resp(r):
        if "pc-search-job" in r.url and "-cond-init" not in r.url:
            try:
                bodies.append(r.json())
            except Exception as e:
                bodies.append({"_err": str(e), "_url": r.url})

    page.on("response", on_resp)
    page.goto(f"https://www.liepin.com/zhaopin/?key={quote('算子开发')}&city=020",
              wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8_000)

    cards = page.locator("div.job-card-pc-container").count()
    texts = page.locator(
        "div.job-card-pc-container a[data-nick='job-detail-job-info']").all_inner_texts()
    sh = sum(1 for t in texts if "上海" in t)
    print(f"DOM 卡片 {cards}，job-info 链接 {len(texts)}，其中含上海 {sh}", flush=True)
    for t in texts[:3]:
        print("  ---", t.replace("\n", " | ")[:120], flush=True)

    print(f"XHR bodies {len(bodies)}", flush=True)
    if bodies:
        with open("scripts/_liepin_xhr.json", "w", encoding="utf-8") as f:
            json.dump(bodies[0], f, ensure_ascii=False, indent=1)
        d = bodies[0]
        print("top keys:", list(d.keys()), flush=True)
        dd = d.get("data")
        if isinstance(dd, dict):
            print("data keys:", list(dd.keys())[:25], flush=True)
    page.close()
