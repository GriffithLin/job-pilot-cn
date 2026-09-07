"""打招呼语生成：≤60 字 + 静态回退兜底。"""

from __future__ import annotations

from .. import config, llm

_PROMPT = (config.PKG_DIR / "prompts" / "greet_system.txt").read_text(encoding="utf-8")
MAX_LEN = 60

_GREET_FALLBACK = (
    "您好，我是{name}，{tenure}算子开发经验，主做{direction_summary}，"
    "有量化性能成果。方便的话想发一份详细简历您看看。"
)


def _fallback(profile: dict) -> str:
    persona = profile.get("persona", {})
    return _GREET_FALLBACK.format(
        name=persona.get("name", "候选人"),
        tenure=persona.get("greet_tenure", f"{persona.get('tenure_years', 1)} 年"),
        direction_summary=persona.get("direction_summary", "大模型算子优化"),
    )


def _valid(text: str) -> bool:
    return bool(text) and len(text.strip()) <= MAX_LEN and "false" not in text.lower()


def generate_greeting(client: llm.LLMClient, profile: dict, resume: str,
                      job: dict) -> dict:
    """返回 {greeting, greeting_fallback}。LLM 两次仍超长 → 静态回退。"""
    persona = profile.get("persona", {})
    system = _PROMPT
    base_user = (
        f"===候选人===\n{persona.get('name', '候选人')}，"
        f"{persona.get('tenure_years', 1)} 年"
        f"{persona.get('direction', '算子开发')}经验。\n"
        f"===岗位===\n{job.get('job_title', '')}｜{job.get('company', '')}\n"
        f"===命中点===\n{job.get('score_keywords', '')}"
        f"（评分理由：{job.get('score_reasoning', '')}）"
    )
    user = base_user
    for round_no in range(2):
        try:
            text = client.chat(system, user, temperature=0.5, max_tokens=200).strip()
        except llm.LLMError:
            break
        if _valid(text):
            return {"greeting": text, "greeting_fallback": 0}
        if round_no == 0:
            # 带上失败样例重试一次
            user = base_user + f"\n\n（上次输出「{text}」超过 {MAX_LEN} 字或格式不对，请严格 ≤{MAX_LEN} 字重写）"
    return {"greeting": _fallback(profile), "greeting_fallback": 1}
