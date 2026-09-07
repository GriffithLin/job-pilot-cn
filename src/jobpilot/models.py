"""列级状态谓词：某阶段完成 = 该阶段负责的列非 NULL。

集中定义，所有阶段与 status 计数板复用；阶段间零直接调用，靠这些谓词衔接。
"""

from __future__ import annotations

from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 待抓详情：已发现、未抓、未被过滤
PENDING_ENRICH = (
    "discovered_at IS NOT NULL AND detail_scraped_at IS NULL AND reject_reason IS NULL"
)

# 待打分：有 JD 全文、未打分（被过滤的不打分）
PENDING_SCORE = "full_description IS NOT NULL AND fit_score IS NULL AND reject_reason IS NULL"


def pending_greet(min_score: int) -> str:
    return (
        f"fit_score >= {int(min_score)} AND greeting IS NULL"
        " AND reject_reason IS NULL"
    )


def pending_tailor(min_score: int) -> str:
    return (
        f"fit_score >= {int(min_score)} AND resume_bullets IS NULL"
        " AND tailor_failed IS NULL AND reject_reason IS NULL"
    )


# 今日待发：打招呼语已生成、未人工发送、未被过滤
PENDING_SEND = (
    "greeting_generated_at IS NOT NULL AND manually_sent_at IS NULL"
    " AND reject_reason IS NULL"
)
