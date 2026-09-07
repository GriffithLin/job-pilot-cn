"""猎聘详情页探针 v2：等水合 + 记录详情页 XHR 找 detail API 。"""
import sys
import time

from jobpilot.discovery.browser import BrowserSession

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.liepin.com/job/1984026851.shtml"

with BrowserSession("liepin") as session:
    page = session.new_page()
    apis = []
    page.on("response", lambda r: apis.append(r.url)
            if "api-c.liepin.com" in r.url and len(apis) < 30 else None)
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    # 轮询等正文：body 文本 > 100 字即认为水合完成
    deadline = time.time() + 25
    text = ""
    while time.time() < deadline:
        page.wait_for_timeout(2_000)
        try:
            text = page.locator("body").inner_text()
        except Exception:
            text = ""
        if len(text.strip()) > 100:
            break
    print(f"等待后 body 文本 {len(text)} 字", flush=True)
    print("前 400 字:", text[:400].replace(chr(10), " | "), flush=True)
    with open("scripts/_liepin_detail.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("XHR api-c.liepin.com:", len(apis), flush=True)
    for u in apis[:15]:
        print(" ", u[:140], flush=True)
    page.close()
