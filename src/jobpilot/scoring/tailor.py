"""定制简历要点：LLM 只产结构化 JSON，代码组装，validator 守门。"""

from __future__ import annotations

import json

from .. import config, llm
from .validator import validate_tailor_output

_PROMPT = (config.PKG_DIR / "prompts" / "tailor_system.txt").read_text(encoding="utf-8")
MAX_ATTEMPTS = 3


def tailor_job(client: llm.LLMClient, profile: dict, resume: str,
               job: dict) -> dict:
    """返回 {resume_bullets: list[str]} 或 {tailor_failed: str}。"""
    rf = profile.get("resume_facts", {})
    persona = profile.get("persona", {})
    system = _PROMPT.format(
        company_placeholder=rf.get("preserved_companies", ["某公司"])[0],
        tenure=rf.get("real_tenure", f"{persona.get('tenure_years', 1)} 年"),
        forbidden_words="、".join(rf.get("forbidden_claims", [])) or "（无）",
    )

    jd_head = (job.get("full_description") or "")[:2000]
    base_user = (
        f"===简历===\n{llm.truncate(resume, 3000)}\n\n"
        f"===职位描述===\n岗位：{job.get('job_title', '')}｜公司：{job.get('company', '')}\n{jd_head}\n\n"
        f"===命中点===\n{job.get('score_keywords', '')}"
    )

    errors: list[str] = []
    user = base_user
    for attempt in range(MAX_ATTEMPTS):
        try:
            text = client.chat(system, user, temperature=0.3, max_tokens=1500)
            data = llm.extract_json(text)
        except llm.LLMError as e:
            errors.append(str(e))
            user = base_user + f"\n\n（上次输出解析失败：{errors[-1][:150]}。请只输出合法 JSON。）"
            continue

        headline = str(data.get("headline", "")).strip()
        bullets = [str(b).strip() for b in data.get("bullets", []) if str(b).strip()]
        if not bullets:
            errors.append("bullets 为空")
            user = base_user + "\n\n（上次输出没有要点，请按格式重给。）"
            continue

        combined = headline + "\n" + "\n".join(bullets)
        errs = validate_tailor_output(combined, profile, resume)
        if not errs:
            assembled = [f"【{headline}】"] if headline else []
            assembled += [f"- {b}" for b in bullets]
            return {"resume_bullets": assembled}

        errors = errs[-5:]  # 只带最近 5 条，喂回重试
        user = (
            base_user
            + "\n\n以下问题必须避免：\n"
            + "\n".join(f"- {e}" for e in errors)
        )

    return {"tailor_failed": "；".join(errors[:5])}


def bullets_to_text(bullets_json: str) -> str:
    """DB 里存的 JSON 数组 → 报告用的多行文本。"""
    try:
        items = json.loads(bullets_json)
        return "\n".join(items) if isinstance(items, list) else str(items)
    except (json.JSONDecodeError, TypeError):
        return str(bullets_json)
