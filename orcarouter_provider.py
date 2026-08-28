# -*- encoding:utf-8 -*-
"""OrcaRouter 模型接入。

通过 OrcaRouter 的 OpenAI 兼容接口调用大模型，
接口文档：https://docs.orcarouter.ai
"""
import requests

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
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    body = {
        "model": model or DEFAULT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        resp = requests.post(ORCAROUTER_BASE_URL + "/chat/completions",
                             headers=headers, json=body, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        raise OrcaRouterError("网络异常：" + str(e), code="network")
    if resp.status_code in (401, 403):
        raise OrcaRouterError("API Key 无效", code="bad_key")
    if resp.status_code == 429:
        raise OrcaRouterError("请求过于频繁或额度不足", code="rate_limit")
    if resp.status_code != 200:
        raise OrcaRouterError("调用失败 HTTP " + str(resp.status_code) + "：" + resp.text[:200], code="http")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise OrcaRouterError("返回格式异常：" + resp.text[:200], code="format")
