"""猎聘登录态地面真相：首页 UI / detail 跳转 / 运行时 cookie 全记录。"""
from jobpilot.discovery.browser import BrowserSession

with BrowserSession("liepin") as session:
    page = session.new_page()

    print("=== 1) 首页 www.liepin.com ===", flush=True)
    page.goto("https://www.liepin.com", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(6_000)
    text = page.locator("body").inner_text()
    print("含「登录/注册」连体:", "登录/注册" in text, flush=True)
    print("含单独「注册」:", "注册" in text, flush=True)
    print("含单独「登录」:", "登录" in text, flush=True)
    idx = text.find("登录")
    print("登录 上下文:", repr(text[max(0, idx-40):idx+60]) if idx >= 0 else "无", flush=True)

    print("=== 2) 详情页 /job/1984026851.shtml ===", flush=True)
    page.goto("https://www.liepin.com/job/1984026851.shtml",
              wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8_000)
    print("最终 URL:", page.url[:120], flush=True)
    t2 = page.locator("body").inner_text()
    print("body 字数:", len(t2), flush=True)
    print("前 200 字:", t2[:200].replace(chr(10), " | "), flush=True)

    print("=== 3) 详情页 /a/79339065.shtml 变体 ===", flush=True)
    page.goto("https://www.liepin.com/a/79339065.shtml",
              wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8_000)
    print("最终 URL:", page.url[:120], flush=True)
    t3 = page.locator("body").inner_text()
    print("body 字数:", len(t3), "| 前 200 字:", t3[:200].replace(chr(10), " | "), flush=True)

    print("=== 4) 运行时 cookie 名 ===", flush=True)
    print(sorted({c["name"] for c in session.context.cookies()}), flush=True)
    page.close()
