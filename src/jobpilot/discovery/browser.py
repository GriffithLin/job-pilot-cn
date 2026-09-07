"""Playwright 公共底座：Cookie 持久化、反检测注入、人工暂停统一入口。

单点封装原则：将来 Playwright 被指纹检测时，整体替换 nodriver/patchright
只改这一个文件。
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .. import config

# get_jobs 验证过的口径：硬编码 macOS Chrome 135 UA
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

# 反检测 init script（凭理解重写，非复制）：
# 1) console 方法包装：对象参数脱敏为 {}，缓解 console.table 计时探测
# 2) 包装函数的 toString 伪装为 native code
ANTI_DETECTION_JS = """
(() => {
  if (window.__jpAntiDetect) return;
  window.__jpAntiDetect = true;
  const nativeStr = (name) => `function ${name}() { [native code] }`;
  for (const name of ['table', 'log', 'info', 'warn', 'error', 'debug']) {
    const orig = console[name];
    if (typeof orig !== 'function') continue;
    const wrapped = function (...args) {
      try {
        orig.apply(console, args.map(a => (a && typeof a === 'object') ? {} : a));
      } catch (e) {}
    };
    try {
      wrapped.toString = () => nativeStr(name);
      wrapped.toString.toString = () => nativeStr('toString');
    } catch (e) {}
    console[name] = wrapped;
  }
})();
"""

# 挑战页特征：Boss 滑块 / 登录页，猎聘登录页 + 风控拦截（safe.liepin.com/verifysms）
_CHALLENGE_URL_PATTERNS = (
    "safe/verify", "verify-slider", "signin", "login",
    "safe.liepin.com", "verifysms",
)


def load_cookies(platform: str) -> list[dict] | None:
    """兼容旧格式（纯 cookie 列表）；新格式 storage_state 由 load_storage_state 处理。"""
    p = config.cookies_dir() / f"{platform}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def load_storage_state(platform: str) -> str | None:
    """新格式：Playwright storage_state 文件（cookies + localStorage）。

    猎聘登录态在 localStorage 里，只存 cookies 会丢登录。
    """
    p = config.cookies_dir() / f"{platform}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return str(p) if isinstance(data, dict) and "cookies" in data else None


def save_cookies(context: BrowserContext, platform: str) -> None:
    state = context.storage_state()
    # 猎聘把登录 token 放 sessionStorage（storage_state 不含它），从仍打开的页面补抓
    ss: dict[str, dict[str, str]] = {}
    for page in context.pages:
        try:
            m = re.match(r"https?://([^/]+)", page.url)
            if not m:
                continue
            kv = page.evaluate(
                "() => {const o={}; for (let i=0;i<sessionStorage.length;i++)"
                "{const k=sessionStorage.key(i); o[k]=sessionStorage.getItem(k);} return o;}"
            )
            if kv:
                ss[m.group(1)] = kv
        except Exception:
            continue
    if not ss:  # 没有活页面可抓时保留旧值，避免登录态被空覆盖
        try:
            old = json.loads((config.cookies_dir() / f"{platform}.json")
                             .read_text(encoding="utf-8"))
            ss = old.get("session_storage") or {}
        except Exception:
            pass
    state["session_storage"] = ss
    (config.cookies_dir() / f"{platform}.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )


def has_valid_cookie(platform: str) -> bool:
    return bool(load_cookies(platform))


def _is_challenge(url: str) -> bool:
    return any(pat in url.lower() for pat in _CHALLENGE_URL_PATTERNS)


def pause_if_challenge(page: Page, wait_seconds: int = 600) -> None:
    """检测到滑块/登录页 → 提示 + 等人处理（不自动过滑块）。

    交互终端：等回车；非 TTY（后台任务/定时）：轮询 URL 直到挑战消失，
    超时抛错——绝不能死等 input() 把进程挂死。
    """
    if not _is_challenge(page.url):
        return
    print(f"\n⚠️  检测到验证/登录页（{page.url}），请人工处理…", flush=True)
    if sys.stdin and sys.stdin.isatty():
        try:
            input("处理后按回车继续…")
            return
        except EOFError:
            pass  # 伪 TTY：回车拿不到，落入下方 URL 轮询
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(5)
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
        if not _is_challenge(page.url):
            print("✓ 验证页已通过", flush=True)
            return
    raise RuntimeError(f"等待人工处理验证页超时（{wait_seconds}s）: {page.url}")


class BrowserSession:
    """有头 Chromium + Cookie 回灌；退出时保存 Cookie。"""

    def __init__(self, platform: str, headed: bool = True) -> None:
        self.platform = platform
        self.headed = headed
        self._pw = None
        self._browser = None
        self.context: BrowserContext | None = None

    def __enter__(self) -> "BrowserSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=not self.headed,
            slow_mo=50,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )
        self.context = self._browser.new_context(
            user_agent=UA,
            viewport=None,  # 最大化窗口下不固定 viewport
            storage_state=load_storage_state(self.platform),
        )
        self.context.add_init_script(ANTI_DETECTION_JS)
        # 恢复 sessionStorage：init script 在每个新页面创建时按 origin 回灌
        if state_file := load_storage_state(self.platform):
            try:
                ss = json.loads(Path(state_file).read_text(encoding="utf-8")).get(
                    "session_storage") or {}
            except Exception:
                ss = {}
            if ss:
                self.context.add_init_script(
                    "(() => { const MAP = " + json.dumps(ss) + ";"
                    " const kv = MAP[location.host] || MAP[location.origin];"
                    " if (kv) for (const [k, v] of Object.entries(kv))"
                    " { try { sessionStorage.setItem(k, v); } catch (e) {} } })();"
                )
        if cookies := load_cookies(self.platform):
            self.context.add_cookies(cookies)
        return self

    def __exit__(self, *exc) -> None:
        if self.context is not None:
            try:
                save_cookies(self.context, self.platform)
            except Exception:
                pass
            self.context.close()
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()

    def new_page(self) -> Page:
        assert self.context is not None
        return self.context.new_page()
