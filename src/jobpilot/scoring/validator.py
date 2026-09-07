"""确定性校验器（纯代码、非 LLM）：tailor 产出的防虚构守门员。

规则（三层：数字 / 公司名 / 表述）：
1. 输出中出现的所有数字必须在白名单内 —— 白名单 = profile.resume_facts.real_metrics
   + 简历原文里出现过的数字（确定性提取，两者都是事实）
2. 公司名只允许 profile.resume_facts.preserved_companies 里的占位
3. 禁词表（forbidden_claims）+ 年限只允许 profile.resume_facts.real_tenure 的口径
"""

from __future__ import annotations

import re

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_TENURE_RE = re.compile(r"(\d+)\s*年|([一两二三四五六七八九十])\s*年")

# 没在公司待过就写上公司名 = 虚构（可被 profile.resume_facts.company_blocklist 覆盖）
_DEFAULT_COMPANY_BLOCKLIST = [
    "英伟达", "NVIDIA", "AMD", "华为", "海思", "寒武纪", "地平线",
    "百度", "字节", "阿里", "腾讯", "美团", "昇腾", "沐曦", "燧原", "壁仞",
]


def _allowed_numbers(profile: dict, resume: str) -> set[str]:
    rf = profile.get("resume_facts", {})
    corpus = "\n".join(rf.get("real_metrics", [])) + "\n" + resume
    return set(_NUM_RE.findall(corpus))


def validate_tailor_output(text: str, profile: dict, resume: str) -> list[str]:
    """返回错误列表；空列表 = 通过。"""
    errors: list[str] = []
    rf = profile.get("resume_facts", {})

    # 1. 数字白名单
    allowed = _allowed_numbers(profile, resume)
    for num in _NUM_RE.findall(text):
        if num not in allowed:
            errors.append(f"出现白名单外的数字「{num}」（疑似虚构量化结果）")

    # 2. 公司名：只允许占位/白名单公司
    preserved = rf.get("preserved_companies", [])
    blocklist = rf.get("company_blocklist", _DEFAULT_COMPANY_BLOCKLIST)
    for name in blocklist:
        if name in text and not any(p in text for p in preserved):
            errors.append(f"出现未任职过的公司名「{name}」")
            break

    # 3. 禁词
    for word in rf.get("forbidden_claims", []):
        if word in text:
            errors.append(f"禁用表述「{word}」")

    # 4. 年限
    tenure_years = profile.get("persona", {}).get("tenure_years", 1)
    for m in _TENURE_RE.finditer(text):
        arabic, cn = m.group(1), m.group(2)
        if arabic is not None and int(arabic) != tenure_years:
            errors.append(f"年限「{m.group(0)}」与真实年限 {tenure_years} 年不符")
        elif cn is not None and cn != "一":
            errors.append(f"年限「{m.group(0)}」与真实年限 {tenure_years} 年不符")

    # 5. LLM 泄漏语
    for leak in ("I apologize", "i am sorry", "here is", "以下是修改", "抱歉"):
        if leak.lower() in text.lower():
            errors.append(f"LLM 泄漏语「{leak}」")
            break

    return errors
