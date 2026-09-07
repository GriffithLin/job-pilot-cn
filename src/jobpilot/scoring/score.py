"""打分阶段：resume + JD → SCORE/KEYWORDS/REASONING 纯文本协议。"""

from __future__ import annotations

import re

from .. import config, llm

_PROMPT = (config.PKG_DIR / "prompts" / "score_system.txt").read_text(encoding="utf-8")
_SCORE_RE = re.compile(r"SCORE:\s*(\d+)")
_KEYWORDS_RE = re.compile(r"KEYWORDS:\s*(.+)")
_REASONING_RE = re.compile(r"REASONING:\s*(.+)", re.DOTALL)

RESUME_LIMIT = 3000
JD_LIMIT = 6000


def _persona_block(profile: dict) -> str:
    persona = profile.get("persona", {})
    facts = profile.get("facts", {})
    lines = [
        f"- 姓名：{persona.get('name', '候选人')}（可只称「候选人」）",
        f"- 方向：{persona.get('direction', '')}",
        f"- 年限：{persona.get('tenure_years', '')} 年（{persona.get('tenure_since', '')} 起）",
    ]
    if facts.get("have"):
        lines.append("- 已有：" + "、".join(facts["have"]))
    if facts.get("lack"):
        lines.append("- 明确没有：" + "、".join(facts["lack"]))
    return "\n".join(lines)


def _facts_block(profile: dict) -> str:
    rf = profile.get("resume_facts", {})
    lines = []
    if rf.get("allowed_skills"):
        lines.append("- 确有技能：" + "、".join(rf["allowed_skills"]))
    if rf.get("forbidden_claims"):
        lines.append("- 禁止归到候选人头上的表述：" + "、".join(rf["forbidden_claims"]))
    lines.append("- 简历全文见用户消息，以简历为准")
    return "\n".join(lines)


def parse_score_output(text: str) -> dict:
    """解析 LLM 输出；解析失败 score 记 0（下次 --rescore 可重试）。"""
    m = _SCORE_RE.search(text)
    score = int(m.group(1)) if m else 0
    score = max(1, min(10, score)) if m else 0
    keywords = ""
    reasoning = ""
    if (kw := _KEYWORDS_RE.search(text)):
        keywords = kw.group(1).strip()
    if (rs := _REASONING_RE.search(text)):
        reasoning = rs.group(1).strip().splitlines()[0]
    return {
        "fit_score": score,
        "score_keywords": keywords,
        "score_reasoning": reasoning,
    }


def score_job(client: llm.LLMClient, profile: dict, resume: str,
              job_title: str, company: str, full_description: str) -> dict:
    system = _PROMPT.format(
        persona_block=_persona_block(profile),
        facts_block=_facts_block(profile),
    )
    user = (
        f"===简历===\n{llm.truncate(resume, RESUME_LIMIT)}\n\n"
        f"===职位描述===\n岗位：{job_title}｜公司：{company}\n"
        f"{llm.truncate(full_description, JD_LIMIT)}"
    )
    text = client.chat(system, user, temperature=0.2, max_tokens=500)
    return parse_score_output(text)
