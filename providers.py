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
import httpx
import json
from openai import (APIConnectionError, APIStatusError, AuthenticationError,
                    OpenAI, RateLimitError)

REQUEST_TIMEOUT = 120
_ANTHROPIC_VERSION = "2023-06-01"
# 进程内协议记忆：(base_url, model) -> "anthropic"。
# 某些模型（如 StepFun 的 step-explore）仅提供 Anthropic Messages 协议，
# 第一次遇到 400 提示后记住，后续调用直接走 /v1/messages。
_protocol_cache = {}


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


# ---- Anthropic Messages 协议（/v1/messages）----

def _messages_endpoint(base_url):
    return base_url.rstrip("/") + "/messages"


def _anthropic_headers(api_key):
    return {"x-api-key": api_key, "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json"}


def _to_anthropic_payload(messages, model, max_tokens, temperature, stream=False):
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
               "messages": [{"role": m["role"], "content": m["content"]}
                            for m in messages if m["role"] != "system"]}
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if stream:
        payload["stream"] = True
    return payload


def _anthropic_error(status_code, text):
    if status_code in (401, 403):
        return LLMError("API Key 无效", code="bad_key")
    if status_code == 429:
        return LLMError("请求过于频繁或额度不足", code="rate_limit")
    return LLMError("调用失败 HTTP %d：%s" % (status_code, (text or "")[:200]), code="http")


def _anthropic_text(data):
    return "".join(block.get("text", "") for block in data.get("content", [])
                   if block.get("type") == "text")


def messages_chat(base_url, api_key, model, messages, max_tokens=512, temperature=0.7):
    """Anthropic Messages 协议非流式调用，返回完整文本。

    思考型模型（返回 thinking 块）可能把 max_tokens 全部耗在思考上、
    没有产出正文（stop_reason=max_tokens）——此时自动加大预算重试一次。
    """
    budget = max_tokens
    for attempt in range(3):
        payload = _to_anthropic_payload(messages, model, budget, temperature)
        try:
            resp = httpx.post(_messages_endpoint(base_url), json=payload,
                              headers=_anthropic_headers(api_key), timeout=REQUEST_TIMEOUT)
        except httpx.HTTPError as e:
            raise LLMError("网络异常：" + str(e), code="network") from e
        if resp.status_code != 200:
            raise _anthropic_error(resp.status_code, resp.text)
        try:
            data = resp.json()
            text = _anthropic_text(data)
        except (ValueError, AttributeError, TypeError):
            raise LLMError("返回格式异常：" + resp.text[:200], code="format")
        if text:
            return text
        if attempt < 2 and data.get("stop_reason") == "max_tokens":
            budget = min(budget * 4, 32000)
            continue
        raise LLMError("模型没有输出正文（思考占用了全部输出预算，已自动加大重试）",
                       code="format")
    raise LLMError("模型没有输出正文", code="format")


def messages_chat_stream(base_url, api_key, model, messages,
                         max_tokens=512, temperature=0.7):
    """Anthropic Messages 协议流式调用，逐段 yield 文本。"""
    payload = _to_anthropic_payload(messages, model, max_tokens, temperature, stream=True)
    try:
        with httpx.stream("POST", _messages_endpoint(base_url), json=payload,
                          headers=_anthropic_headers(api_key), timeout=REQUEST_TIMEOUT) as resp:
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", "replace")
                raise _anthropic_error(resp.status_code, body)
            for line in resp.iter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                except ValueError:
                    continue
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield delta["text"]
                elif event.get("type") == "message_stop":
                    break
    except httpx.HTTPError as e:
        raise LLMError("网络异常：" + str(e), code="network") from e


def _messages_api_required(e):
    """识别「该模型仅支持 Messages API」类 400 错误。"""
    return isinstance(e, APIStatusError) and getattr(e, "status_code", None) == 400 \
        and "/v1/messages" in str(e)


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


def _anthropic_stream_with_rescue(url, api_key, model, messages, max_tokens, temperature):
    """流式输出；若一个字都没吐出（思考烧光预算），退回带自适应重试的非流式。"""
    got = False
    for text in messages_chat_stream(url, api_key, model, messages,
                                     max_tokens, temperature):
        got = True
        yield text
    if not got:
        text = messages_chat(url, api_key, model, messages, max_tokens, temperature)
        if text:
            yield text


def chat(prompt, api_key, model="", provider="orcarouter", base_url="",
         max_tokens=512, temperature=0.7):
    """非流式调用，返回完整回复文本。仅支持 Messages 协议的模型自动切换。"""
    url = resolve_base_url(provider, base_url)
    real_model = resolve_model(provider, model)
    messages = _messages(prompt)
    if _protocol_cache.get((url, real_model)) == "anthropic":
        return messages_chat(url, api_key, real_model, messages, max_tokens, temperature)
    client = _client(api_key, url)
    try:
        resp = client.chat.completions.create(
            model=real_model, messages=messages,
            max_tokens=max_tokens, temperature=temperature)
    except _ERROR_TYPES as e:
        if _messages_api_required(e):
            _protocol_cache[(url, real_model)] = "anthropic"
            return messages_chat(url, api_key, real_model, messages, max_tokens, temperature)
        raise _wrap(e) from e
    try:
        return resp.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        raise LLMError("返回格式异常", code="format")


def chat_stream(prompt, api_key, model="", provider="orcarouter", base_url="",
                max_tokens=2048, temperature=0.7):
    """流式调用，逐段 yield 回复文本。仅支持 Messages 协议的模型自动切换。"""
    url = resolve_base_url(provider, base_url)
    real_model = resolve_model(provider, model)
    messages = _messages(prompt)
    if _protocol_cache.get((url, real_model)) == "anthropic":
        yield from _anthropic_stream_with_rescue(url, api_key, real_model, messages,
                                                 max_tokens, temperature)
        return
    client = _client(api_key, url)
    try:
        stream = client.chat.completions.create(
            model=real_model, messages=messages,
            max_tokens=max_tokens, temperature=temperature, stream=True)
    except _ERROR_TYPES as e:
        if _messages_api_required(e):
            _protocol_cache[(url, real_model)] = "anthropic"
            yield from _anthropic_stream_with_rescue(url, api_key, real_model, messages,
                                                     max_tokens, temperature)
            return
        raise _wrap(e) from e
    try:
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is not None and delta.content:
                yield delta.content
    except _ERROR_TYPES as e:
        raise _wrap(e) from e
