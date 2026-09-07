"""LLM 客户端：双协议（OpenAI 兼容 / Anthropic）+ 重试 + 截断 + JSON 提取。

base_url 含 `/api/plan`（火山 Agent Plan）时走 Anthropic Messages 协议，
否则走 OpenAI chat completions。plan 上的 doubao 模型是 thinking 模型，
会先思考再输出——预算放大、只取 text block。
"""

from __future__ import annotations

import json
import re
import time

from . import config

_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # 秒，指数退避基数

# thinking 模型：思考本身吃 token，预算至少给这么多
_ANTHROPIC_MIN_BUDGET = 2500


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self) -> None:
        base_url, api_key, model = config.llm_settings()
        self.model = model
        self._anthropic = "/api/plan" in base_url
        if self._anthropic:
            from anthropic import Anthropic

            self._aclient = Anthropic(base_url=base_url, api_key=api_key, timeout=300)
        else:
            from openai import OpenAI

            self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=300)

    def chat(self, system: str, user: str, temperature: float = 0.2,
             max_tokens: int = 2000) -> str:
        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                text = (self._chat_anthropic(system, user, temperature, max_tokens)
                        if self._anthropic
                        else self._chat_openai(system, user, temperature, max_tokens))
                if not text:
                    raise LLMError("模型返回空内容")
                return text
            except LLMError:
                raise
            except Exception as e:  # 网络/限流等瞬态错误
                last_err = e
                time.sleep(_RETRY_BACKOFF ** (attempt + 1))
        raise LLMError(f"LLM 调用重试 {_MAX_RETRIES} 次仍失败: {last_err}")

    def _chat_openai(self, system: str, user: str, temperature: float,
                     max_tokens: int) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _chat_anthropic(self, system: str, user: str, temperature: float,
                        max_tokens: int) -> str:
        # plan 上的 thinking 模型只支持默认温度，不传 temperature
        resp = self._aclient.messages.create(
            model=self.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=max(max_tokens * 3, _ANTHROPIC_MIN_BUDGET),
        )
        texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "\n".join(texts).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…（已截断）"


def extract_json(text: str) -> dict | list:
    """从 LLM 输出中提取第一个 JSON 对象/数组（容忍 ```json 围栏与前后废话）。"""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == opener:
                depth += 1
            elif cleaned[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:i + 1])
                    except json.JSONDecodeError:
                        break
        break
    raise LLMError(f"无法从输出中解析 JSON: {text[:200]}")
