"""pipeline 编排：discover → enrich → score → greet → tailor → report。

幂等性来自列级状态机：任何阶段崩溃，重跑 `jp run` 即续传，无需断点文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import config, db, models, report
from .llm import LLMClient, LLMError


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class RunOptions:
    platforms: list[str] = field(default_factory=lambda: ["boss", "liepin"])
    max_per_search: int = 20
    skip_discover: bool = False
    skip_browser: bool = False  # 只跑离线阶段（score/greet/tailor/report）


@dataclass
class RunResult:
    errors: dict[str, str] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)


def run_pipeline(opts: RunOptions) -> RunResult:
    conn = db.connect()
    db.init_db(conn)
    result = RunResult()
    profile = config.load_profile()
    resume = config.load_resume()
    min_score = profile.get("preferences", {}).get("min_score_to_greet", 6)

    # ---- 浏览器阶段（discover + enrich，同一上下文内完成，登录态共享）----
    if not opts.skip_browser:
        try:
            _run_browser_stages(conn, opts, result)
        except Exception as e:  # 浏览器层崩溃不阻塞离线阶段
            result.errors["browser"] = str(e)
    # ---- 离线阶段（score → greet → tailor → report）----
    client = None
    try:
        client = LLMClient()
    except Exception as e:
        result.errors["llm"] = str(e)

    if client is not None:
        _run_score(conn, client, profile, resume, result)
        _run_greet(conn, client, profile, resume, min_score, result)
        _run_tailor(conn, client, profile, resume, min_score, result)

    try:
        path = report.generate_report(conn)
        result.stats["report"] = str(path)
    except Exception as e:
        result.errors["report"] = str(e)

    return result


def _run_browser_stages(conn, opts: RunOptions, result: RunResult) -> None:
    from .discovery.browser import BrowserSession
    from .discovery.boss import BossDiscoverer
    from .discovery.liepin import LiepinDiscoverer
    from .enrichment.detail import enrich_jobs

    searches = config.load_searches()
    discoverers = {"boss": BossDiscoverer(), "liepin": LiepinDiscoverer()}

    for platform in opts.platforms:
        if platform not in discoverers:
            continue
        conf = searches.get(platform, {})
        keywords = conf.get("keywords", [])
        if not keywords:
            result.errors[f"discover:{platform}"] = "searches.yaml 无关键词"
            continue

        with BrowserSession(platform) as session:
            if not opts.skip_discover:
                for kw in keywords:
                    try:
                        jobs = discoverers[platform].run(
                            session.context, kw, conf, limit=opts.max_per_search
                        )
                        new = sum(1 for j in jobs if db.upsert_job(conn, j))
                        result.stats[f"discover:{platform}:{kw}"] = new
                    except Exception as e:
                        result.errors[f"discover:{platform}:{kw}"] = str(e)
            # enrich 与 discover 同一浏览器会话，避免重复扫码
            try:
                n = enrich_jobs(conn, session, platform, limit=opts.max_per_search)
                result.stats[f"enrich:{platform}"] = n
            except Exception as e:
                result.errors[f"enrich:{platform}"] = str(e)


def _run_score(conn, client: LLMClient, profile: dict, resume: str,
               result: RunResult) -> None:
    from .scoring import score as score_mod

    rows = db.fetch(conn, models.PENDING_SCORE, order="ORDER BY discovered_at ASC")
    done = 0
    for r in rows:
        try:
            out = score_mod.score_job(
                client, profile, resume, r["job_title"], r["company"],
                r["full_description"] or "",
            )
            db.update_columns(
                conn, r["url"], scored_at=_now(),
                fit_score=out["fit_score"],
                score_keywords=out["score_keywords"],
                score_reasoning=out["score_reasoning"],
            )
            done += 1
        except LLMError as e:
            result.errors[f"score:{r['url']}"] = str(e)
    result.stats["scored"] = done


def _run_greet(conn, client: LLMClient, profile: dict, resume: str,
               min_score: int, result: RunResult) -> None:
    from .scoring.greet import generate_greeting

    rows = db.fetch(conn, models.pending_greet(min_score),
                    order="ORDER BY fit_score DESC")
    done = 0
    for r in rows:
        try:
            out = generate_greeting(client, profile, resume, dict(r))
            db.update_columns(
                conn, r["url"], greeting_generated_at=_now(),
                greeting=out["greeting"],
                greeting_fallback=out["greeting_fallback"],
            )
            done += 1
        except LLMError as e:
            result.errors[f"greet:{r['url']}"] = str(e)
    result.stats["greeted"] = done


def _run_tailor(conn, client: LLMClient, profile: dict, resume: str,
                min_score: int, result: RunResult) -> None:
    from .scoring.tailor import tailor_job

    rows = db.fetch(conn, models.pending_tailor(min_score),
                    order="ORDER BY fit_score DESC")
    done = 0
    for r in rows:
        try:
            out = tailor_job(client, profile, resume, dict(r))
            if "resume_bullets" in out:
                import json

                db.update_columns(
                    conn, r["url"], tailored_at=_now(),
                    resume_bullets=json.dumps(out["resume_bullets"], ensure_ascii=False),
                )
            else:
                db.update_columns(
                    conn, r["url"], tailored_at=_now(),
                    tailor_failed=out["tailor_failed"],
                )
            done += 1
        except LLMError as e:
            result.errors[f"tailor:{r['url']}"] = str(e)
    result.stats["tailored"] = done
