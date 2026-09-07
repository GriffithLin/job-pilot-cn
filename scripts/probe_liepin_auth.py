"""猎聘 auth 真源裁决：恢复 state 后首页 UI 是否登录 + IndexedDB 枚举。"""
import json

from jobpilot.discovery.browser import BrowserSession

with BrowserSession("liepin") as session:
    page = session.new_page()
    page.goto("https://www.liepin.com", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(8_000)
    text = page.locator("body").inner_text()
    print("登录/注册 出现:", "登录/注册" in text, flush=True)
    # 登录后导航一般出现「消息」「简历」等词
    for kw in ("消息", "我的简历", "已投递", "退出"):
        print(f"含「{kw}」:", kw in text, flush=True)
    idx = text.find("首页")
    print("导航片段:", repr(text[max(0, idx-20):idx+120]), flush=True)

    print("=== document.cookie（非 httpOnly）===", flush=True)
    print(page.evaluate("() => document.cookie")[:400], flush=True)

    print("=== IndexedDB 数据库 ===", flush=True)
    try:
        dbs = page.evaluate("() => indexedDB.databases()")
        print(json.dumps(dbs, ensure_ascii=False), flush=True)
    except Exception as e:
        print("枚举失败:", e, flush=True)
    page.close()
