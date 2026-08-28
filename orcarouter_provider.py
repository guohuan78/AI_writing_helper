# -*- encoding:utf-8 -*-
"""OrcaRouter 模型接入。

使用官方 OpenAI SDK 指向 OrcaRouter 的 OpenAI 兼容接口。
接口文档：https://docs.orcarouter.ai
推荐链接：https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e
"""
from openai import (APIConnectionError, APIStatusError, AuthenticationError,
                    OpenAI, RateLimitError)

ORCAROUTER_BASE_URL = "https://api.orcarouter.ai/v1"
DEFAULT_MODEL = "orcarouter/auto"
REQUEST_TIMEOUT = 120


class OrcaRouterError(Exception):
    """调用异常。code 用于上层区分处理：no_key / bad_key / rate_limit / network / http / format。"""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def _client(api_key):
    if not api_key:
        raise OrcaRouterError("缺少 API Key", code="no_key")
    return OpenAI(base_url=ORCAROUTER_BASE_URL, api_key=api_key,
                  timeout=REQUEST_TIMEOUT, max_retries=0)


def _messages(prompt):
    """字符串快捷形式转成单条 user 消息，列表原样透传。"""
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    return prompt


def _wrap(e):
    if isinstance(e, AuthenticationError):
        return OrcaRouterError("API Key 无效", code="bad_key")
    if isinstance(e, RateLimitError):
        return OrcaRouterError("请求过于频繁或额度不足", code="rate_limit")
    if isinstance(e, APIConnectionError):
        return OrcaRouterError("网络异常：" + str(e), code="network")
    if isinstance(e, APIStatusError):
        return OrcaRouterError("调用失败 HTTP " + str(e.status_code) + "：" + str(e), code="http")
    return OrcaRouterError("调用失败：" + str(e), code="http")


_ERROR_TYPES = (AuthenticationError, RateLimitError, APIConnectionError, APIStatusError)


def chat(prompt, api_key, model=DEFAULT_MODEL, max_tokens=512, temperature=0.7):
    """调用 /v1/chat/completions，返回完整回复文本。"""
    client = _client(api_key)
    try:
        resp = client.chat.completions.create(
            model=model or DEFAULT_MODEL,
            messages=_messages(prompt),
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except _ERROR_TYPES as e:
        raise _wrap(e) from e
    try:
        return resp.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        raise OrcaRouterError("返回格式异常", code="format")


def chat_stream(prompt, api_key, model=DEFAULT_MODEL, max_tokens=2048, temperature=0.7):
    """流式调用 /v1/chat/completions，逐段 yield 回复文本。"""
    client = _client(api_key)
    try:
        stream = client.chat.completions.create(
            model=model or DEFAULT_MODEL,
            messages=_messages(prompt),
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
    except _ERROR_TYPES as e:
        raise _wrap(e) from e
    try:
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is not None and delta.content:
                yield delta.content
    except _ERROR_TYPES as e:
        raise _wrap(e) from e
