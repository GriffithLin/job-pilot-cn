"""每日待发清单（markdown）：按分数降序，人工复制发送。"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from . import config, models
from .scoring.tailor import bullets_to_text


def generate_report(conn: sqlite3.Connection, report_date: date | None = None) -> Path:
    report_date = report_date or date.today()
    pending = conn.execute(
        f"SELECT * FROM jobs WHERE {models.PENDING_SEND}"
        " ORDER BY fit_score DESC, scored_at ASC"
    ).fetchall()
    rejected = conn.execute(
        "SELECT job_title, company, reject_reason FROM jobs"
        " WHERE reject_reason IS NOT NULL ORDER BY rejected_at DESC LIMIT 50"
    ).fetchall()

    lines: list[str] = [f"# 求职待发清单 · {report_date.isoformat()}", ""]

    total = len(pending)
    hi = sum(1 for r in pending if (r["fit_score"] or 0) >= 7)
    lines += [
        f"今日待发 **{total}** 岗（其中 ≥7 分 {hi} 个）；被过滤 {len(rejected)} 岗（见文末）。",
        "",
        "发送顺序建议：从高往低发；每发一条记得回来 `jp sent --interactive` 回记。",
        "",
    ]

    for r in pending:
        score = r["fit_score"] or 0
        salary = r["salary_raw"] or ""
        lines.append(f"## [{score}] {r['job_title']} · {r['company']} · {salary}")
        lines.append("")
        kw = r["score_keywords"] or ""
        lines.append(f"- **匹配点**: {kw}")
        if r["score_reasoning"]:
            lines.append(f"- **评估**: {r['score_reasoning']}")
        lines.append(f"- **链接**: {r['apply_url'] or r['url']}")
        if r["hr_name"]:
            lines.append(f"- **HR**: {r['hr_name']}（{r['hr_title'] or ''}，{r['hr_active'] or ''}）")
        lines.append("")
        lines.append(f"**打招呼语（复制发送）**{'（⚠️ 静态回退语，建议手改）' if r['greeting_fallback'] else ''}:")
        lines.append("")
        lines.append(f"> {r['greeting']}")
        lines.append("")
        if r["resume_bullets"]:
            lines.append("**定制简历要点**:")
            lines.append("")
            lines.append(bullets_to_text(r["resume_bullets"]))
            lines.append("")
        elif r["tailor_failed"]:
            lines.append(f"⚠️ 定制要点生成失败（人工写）：{r['tailor_failed']}")
            lines.append("")
        lines.append("**发送检查清单**: [ ] 已发  [ ] HR 已回复  [ ] 简历已发")
        lines.append("")
        lines.append("---")
        lines.append("")

    if rejected:
        lines += ["", "## 被过滤岗位（供人工翻案）", ""]
        for r in rejected:
            lines.append(f"- {r['job_title']} · {r['company']} —— {r['reject_reason']}")

    out = config.reports_dir() / f"{report_date.isoformat()}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
