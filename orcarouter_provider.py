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


def chat(prompt: str, api_key: str, model: str = DEFAULT_MODEL,
         max_tokens: int = 512, temperature: float = 0.7) -> str:
    """调用 /v1/chat/completions，返回模型回复文本。"""
    if not api_key:
        raise OrcaRouterError("缺少 API Key", code="no_key")
    client = OpenAI(base_url=ORCAROUTER_BASE_URL, api_key=api_key,
                    timeout=REQUEST_TIMEOUT, max_retries=0)
    try:
        resp = client.chat.completions.create(
            model=model or DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except AuthenticationError as e:
        raise OrcaRouterError("API Key 无效", code="bad_key") from e
    except RateLimitError as e:
        raise OrcaRouterError("请求过于频繁或额度不足", code="rate_limit") from e
    except APIConnectionError as e:
        raise OrcaRouterError("网络异常：" + str(e), code="network") from e
    except APIStatusError as e:
        raise OrcaRouterError("调用失败 HTTP " + str(e.status_code) + "：" + str(e), code="http") from e
    try:
        return resp.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        raise OrcaRouterError("返回格式异常", code="format")
