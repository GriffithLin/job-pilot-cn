"""jp 命令行入口。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import config, db, models, report
from .llm import LLMClient, LLMError

app = typer.Typer(help="JobPilot-CN：半自动国内求职 agent ")
console = Console()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@app.command()
def init() -> None:
    """初始化 ~/.jobpilot-cn/ 运行时目录与数据库。"""
    config.runtime_dir()
    conn = db.connect()
    db.init_db(conn)
    conn.close()
    console.print(f"[green]✓[/] 已初始化 {config.runtime_dir()}")
    if not config.profile_path().exists():
        console.print("下一步：uv run python scripts/build_profile.py --resume <简历md路径>")
    if not (config.runtime_dir() / ".env").exists():
        console.print("下一步：复制 .env.example 为 .env 并填入 LLM 配置")
    console.print("然后：jp login boss / jp login liepin 扫码登录")


@app.command()
def status() -> None:
    """各阶段计数板。"""
    conn = db.connect()
    db.init_db(conn)
    table = Table(title="JobPilot 状态")
    table.add_column("阶段")
    table.add_column("数量", justify="right")
    for k, v in db.counts(conn).items():
        table.add_row(k, str(v))
    conn.close()
    console.print(table)


@app.command()
def login(platform: str = typer.Argument(..., help="boss 或 liepin")):
    """打开浏览器扫码登录，持久化 Cookie（约一周有效）。"""
    if platform not in ("boss", "liepin"):
        raise typer.Exit("platform 只能是 boss 或 liepin")
    from .discovery.browser import BrowserSession, save_cookies

    home = {"boss": "https://www.zhipin.com", "liepin": "https://www.liepin.com"}[platform]
    with BrowserSession(platform) as session:
        page = session.new_page()
        page.goto(home, wait_until="domcontentloaded", timeout=60_000)
        console.print("[yellow]请在浏览器中完成扫码登录[/]（猎聘为微信扫码）…")
        console.print("[dim]窗口保持打开：登录态会自动持续保存，用完直接关掉浏览器窗口即退出[/]")
        import time

        logged_in = False
        tick = 0
        while True:
            time.sleep(5)
            tick += 1
            closed = False
            try:
                closed = not session.context.pages
            except Exception:
                closed = True  # 浏览器进程已被关掉
            if not logged_in:
                if platform == "boss":
                    names = {c["name"] for c in session.context.cookies()}
                    logged_in = bool(names & {"wt2", "wt", "bst"})
                else:
                    # 双证据防假阳性：登录/注册消失 且 出现任一登录后导航词
                    try:
                        text = page.locator("body").inner_text(timeout=2_000)
                        logged_in = bool(text) and "登录/注册" not in text and any(
                            kw in text for kw in ("消息", "我的简历", "退出")
                        )
                    except Exception:
                        pass
                if logged_in:
                    console.print("[green]✓[/] 检测到登录态，已保存；浏览器留给你继续用")
            # 登录后每次落盘；未登录也每 30s 兜底存（检测失误也不丢态）
            if logged_in or closed or tick % 6 == 0:
                try:
                    save_cookies(session.context, platform)
                except Exception:
                    pass
            if closed:
                break
    console.print(f"[green]✓[/] Cookie 已保存到 {config.cookies_dir() / f'{platform}.json'}")


@app.command()
def discover(
    platform: str = typer.Option("all", help="boss / liepin / all"),
    max_jobs: int = typer.Option(20, "--max", help="每个关键词抓取上限"),
) -> None:
    """抓取岗位列表入库（含纯代码过滤）。"""
    from .pipeline import RunOptions, run_pipeline

    platforms = ["boss", "liepin"] if platform == "all" else [platform]
    result = run_pipeline(RunOptions(platforms=platforms, max_per_search=max_jobs))
    _print_result(result)


@app.command()
def enrich(platform: str = typer.Option("all"), limit: int = typer.Option(20)) -> None:
    """抓取 JD 全文（需登录态）。"""
    from .enrichment.detail import enrich_jobs
    from .discovery.browser import BrowserSession

    conn = db.connect()
    db.init_db(conn)
    platforms = ["boss", "liepin"] if platform == "all" else [platform]
    for p in platforms:
        with BrowserSession(p) as session:
            n = enrich_jobs(conn, session, p, limit=limit)
        console.print(f"[green]✓[/] {p}: 抓到 JD {n} 条")
    conn.close()


@app.command()
def score(rescore: bool = typer.Option(False, help="重试打分失败的（score=0）")):
    """LLM 打分。"""
    from .pipeline import RunOptions, run_pipeline

    conn = db.connect()
    db.init_db(conn)
    if rescore:
        conn.execute(
            "UPDATE jobs SET fit_score = NULL, scored_at = NULL WHERE fit_score = 0"
        )
        conn.commit()
    conn.close()
    result = run_pipeline(RunOptions(platforms=[], skip_browser=True))
    _print_result(result)


@app.command(name="report")
def report_cmd() -> None:
    """生成今日待发清单。"""
    conn = db.connect()
    db.init_db(conn)
    path = report.generate_report(conn)
    conn.close()
    console.print(f"[green]✓[/] 报告已生成: {path}")


@app.command()
def run(
    max_jobs: int = typer.Option(20, "--max", help="每关键词抓取上限"),
    skip_discover: bool = typer.Option(False, help="跳过抓取（仍会 enrich + 离线阶段）"),
    skip_browser: bool = typer.Option(False, help="只跑离线阶段（打分/生成/报告）"),
    platform: str = typer.Option("all"),
) -> None:
    """全流程：discover → enrich → score → greet → tailor → report（幂等，可重跑）。"""
    from .pipeline import RunOptions, run_pipeline

    platforms = ["boss", "liepin"] if platform == "all" else [platform]
    result = run_pipeline(RunOptions(
        platforms=platforms, max_per_search=max_jobs,
        skip_discover=skip_discover, skip_browser=skip_browser,
    ))
    _print_result(result)


@app.command()
def sent(
    url: Optional[str] = typer.Argument(None, help="岗位 URL（省略则交互式逐条确认）"),
    note: str = typer.Option("", help="备注"),
    interactive: bool = typer.Option(False, "--interactive", "-i"),
) -> None:
    """人工发送后回记状态。"""
    conn = db.connect()
    db.init_db(conn)
    if url:
        db.update_columns(conn, url, manually_sent_at=_now(), human_notes=note or None)
        console.print("[green]✓[/] 已记录")
    else:
        rows = db.fetch(conn, models.PENDING_SEND, order="ORDER BY fit_score DESC")
        if not rows:
            console.print("没有待发岗位；先 jp run 生成")
        for r in rows:
            console.print(
                f"[{r['fit_score']}] {r['job_title']} · {r['company']}"
            )
            ans = typer.prompt("已发送? [y/N/q退出]", default="n")
            if ans.lower() == "q":
                break
            if ans.lower() == "y":
                n = typer.prompt("备注（可空）", default="")
                db.update_columns(
                    conn, r["url"], manually_sent_at=_now(),
                    human_notes=n or None,
                )
    conn.close()


@app.command(name="check-jd")
def check_jd(jd_file: Path = typer.Argument(..., help="JD 文本文件（md/txt）")):
    """离线校准工具：对单个 JD 跑 score + greet + tailor，不走数据库。"""
    profile = config.load_profile()
    resume = config.load_resume()
    jd_text = jd_file.read_text(encoding="utf-8")
    client = LLMClient()

    from .scoring.score import score_job
    from .scoring.greet import generate_greeting
    from .scoring.tailor import tailor_job

    job = {"job_title": jd_file.stem, "company": "（离线校准）",
           "full_description": jd_text}
    try:
        s = score_job(client, profile, resume, job["job_title"], job["company"], jd_text)
        console.print(f"\n[bold]SCORE[/]: {s['fit_score']}/10")
        console.print(f"[bold]KEYWORDS[/]: {s['score_keywords']}")
        console.print(f"[bold]REASONING[/]: {s['score_reasoning']}\n")
        job.update(s)
        g = generate_greeting(client, profile, resume, job)
        tag = "（静态回退）" if g["greeting_fallback"] else ""
        console.print(f"[bold]打招呼语[/]{tag}:\n  {g['greeting']}\n")
        t = tailor_job(client, profile, resume, job)
        if "resume_bullets" in t:
            console.print("[bold]定制要点[/]:")
            for b in t["resume_bullets"]:
                console.print(f"  {b}")
        else:
            console.print(f"[red]定制失败[/]: {t['tailor_failed']}")
    except LLMError as e:
        console.print(f"[red]LLM 调用失败[/]: {e}")


def _print_result(result) -> None:
    if result.stats:
        table = Table(title="执行统计")
        table.add_column("项")
        table.add_column("值", justify="right")
        for k, v in result.stats.items():
            table.add_row(k, str(v))
        console.print(table)
    if result.errors:
        console.print("[red]错误（不影响其他阶段，重跑 jp run 可续传）:[/]")
        for k, v in result.errors.items():
            console.print(f"  [red]·[/] {k}: {v[:200]}")


def main() -> None:
    app()
