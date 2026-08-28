# -*- encoding:utf-8 -*-
"""多供应商模型接入。

统一走 OpenAI 兼容协议（官方 SDK），按供应商解析 API 地址，
切换供应商只需换 Key 与 base_url，调用代码完全一致。
各供应商接入参数以其官方文档为准：
- OrcaRouter: https://docs.orcarouter.ai
- StepFun: https://platform.stepfun.com（推理模型用 /step_plan/v1 路径）
- 智谱 GLM: https://docs.bigmodel.cn/cn/guide/develop/openai/introduction
- Kimi: https://platform.kimi.ai/docs/guide/migrating-from-openai-to-kimi
"""
from openai import (APIConnectionError, APIStatusError, AuthenticationError,
                    OpenAI, RateLimitError)

REQUEST_TIMEOUT = 120


class LLMError(Exception):
    """模型调用/配置异常。code: no_key / config / bad_key / rate_limit / network / http / format。"""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


PROVIDERS = {
    "orcarouter": {
        "label": "OrcaRouter（一个 Key 调全部模型）",
        "base_url": "https://api.orcarouter.ai/v1",
        "default_model": "orcarouter/auto",
        "console": "https://www.orcarouter.ai/console",
        "console_name": "OrcaRouter 控制台",
    },
    "stepfun": {
        "label": "StepFun 阶跃星辰",
        "base_url": "https://api.stepfun.com/v1",
        "default_model": "step-2-16k",
        "console": "https://platform.stepfun.com",
        "console_name": "阶跃星辰开放平台",
    },
    "glm": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4.6",
        "console": "https://open.bigmodel.cn",
        "console_name": "智谱 BigModel 平台",
    },
    "kimi": {
        "label": "Kimi 月之暗面",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k2-0905-preview",
        "console": "https://platform.kimi.ai",
        "console_name": "Kimi 开放平台",
    },
    "custom": {
        "label": "自定义（OpenAI 兼容地址）",
        "base_url": "",
        "default_model": "",
        "console": "",
        "console_name": "",
    },
}


def resolve_base_url(provider, base_url=""):
    """显式地址优先，其次供应商默认地址；自定义供应商必须显式给出。"""
    if (base_url or "").strip():
        return base_url.strip()
    info = PROVIDERS.get(provider)
    if not info:
        raise LLMError("未知供应商：%s" % provider, code="config")
    if not info["base_url"]:
        raise LLMError("请先在「设置」中填写自定义 API 地址", code="config")
    return info["base_url"]


def resolve_model(provider, model=""):
    if (model or "").strip():
        return model.strip()
    info = PROVIDERS.get(provider)
    if not info or not info["default_model"]:
        raise LLMError("请先在「设置」中填写模型名", code="config")
    return info["default_model"]


_ERROR_TYPES = (AuthenticationError, RateLimitError, APIConnectionError, APIStatusError)


def _client(api_key, base_url):
    if not api_key:
        raise LLMError("缺少 API Key", code="no_key")
    return OpenAI(base_url=base_url, api_key=api_key,
                  timeout=REQUEST_TIMEOUT, max_retries=0)


def _wrap(e):
    if isinstance(e, AuthenticationError):
        return LLMError("API Key 无效", code="bad_key")
    if isinstance(e, RateLimitError):
        return LLMError("请求过于频繁或额度不足", code="rate_limit")
    if isinstance(e, APIConnectionError):
        return LLMError("网络异常：" + str(e), code="network")
    if isinstance(e, APIStatusError):
        return LLMError("调用失败 HTTP " + str(e.status_code) + "：" + str(e), code="http")
    return LLMError("调用失败：" + str(e), code="http")


def _messages(prompt):
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    return prompt


def chat(prompt, api_key, model="", provider="orcarouter", base_url="",
         max_tokens=512, temperature=0.7):
    """非流式调用，返回完整回复文本。"""
    url = resolve_base_url(provider, base_url)
    real_model = resolve_model(provider, model)
    client = _client(api_key, url)
    try:
        resp = client.chat.completions.create(
            model=real_model, messages=_messages(prompt),
            max_tokens=max_tokens, temperature=temperature)
    except _ERROR_TYPES as e:
        raise _wrap(e) from e
    try:
        return resp.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        raise LLMError("返回格式异常", code="format")


def chat_stream(prompt, api_key, model="", provider="orcarouter", base_url="",
                max_tokens=2048, temperature=0.7):
    """流式调用，逐段 yield 回复文本。"""
    url = resolve_base_url(provider, base_url)
    real_model = resolve_model(provider, model)
    client = _client(api_key, url)
    try:
        stream = client.chat.completions.create(
            model=real_model, messages=_messages(prompt),
            max_tokens=max_tokens, temperature=temperature, stream=True)
    except _ERROR_TYPES as e:
        raise _wrap(e) from e
    try:
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is not None and delta.content:
                yield delta.content
    except _ERROR_TYPES as e:
        raise _wrap(e) from e
