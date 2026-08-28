# -*- encoding:utf-8 -*-
"""多供应商接入测试（离线）：注册表、地址/模型解析、错误码与 base_url 传递。"""
import pytest

import providers


def test_registry_integrity():
    for key, info in providers.PROVIDERS.items():
        assert info.get("label")
        assert "default_model" in info
        if key != "custom":
            assert info["base_url"].startswith("https://")
            assert info["console"].startswith("https://")


def test_resolve_base_url():
    assert providers.resolve_base_url("orcarouter") == "https://api.orcarouter.ai/v1"
    assert providers.resolve_base_url("stepfun") == "https://api.stepfun.com/v1"
    assert providers.resolve_base_url("glm") == "https://open.bigmodel.cn/api/paas/v4"
    assert providers.resolve_base_url("kimi") == "https://api.moonshot.cn/v1"
    assert providers.resolve_base_url("kimi", "http://localhost:8000/v1") == "http://localhost:8000/v1"
    with pytest.raises(providers.LLMError):
        providers.resolve_base_url("custom", "  ")
    with pytest.raises(providers.LLMError):
        providers.resolve_base_url("nope", "")


def test_resolve_model():
    assert providers.resolve_model("stepfun", "") == "step-2-16k"
    assert providers.resolve_model("glm", "") == "glm-4.6"
    assert providers.resolve_model("kimi", " kimi-k2-turbo-preview ") == "kimi-k2-turbo-preview"
    with pytest.raises(providers.LLMError):
        providers.resolve_model("custom", "")


def test_missing_key_error_code():
    with pytest.raises(providers.LLMError) as ei:
        providers.chat("hi", "", provider="stepfun")
    assert ei.value.code == "no_key"


def test_custom_without_model_error_code():
    with pytest.raises(providers.LLMError) as ei:
        providers.chat("hi", "sk-x", model="", provider="custom",
                       base_url="http://127.0.0.1:9/v1")
    assert ei.value.code == "config"


def test_chat_passes_provider_base_url(monkeypatch):
    """验证引擎把供应商官方地址与默认模型正确传给 OpenAI SDK（离线 mock）。"""
    captured = {}

    class _Msg:
        content = "ok"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kw):
            captured["payload"] = kw
            return _Resp()

    class FakeClient:
        def __init__(self, base_url=None, api_key=None, timeout=None, max_retries=None):
            captured["base_url"] = str(base_url)
            captured["api_key"] = api_key
            self.chat = type("Chat", (), {})()
            self.chat.completions = _Completions()

    monkeypatch.setattr(providers, "OpenAI", FakeClient)
    assert providers.chat("hi", "sk-test", model="", provider="glm") == "ok"
    assert captured["base_url"] == "https://open.bigmodel.cn/api/paas/v4"
    assert captured["payload"]["model"] == "glm-4.6"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hi"}]


# ---- 双协议（OpenAI ChatCompletions → Anthropic Messages）----

import httpx


def _messages_api_400():
    import httpx as _httpx
    from openai import APIStatusError
    request = _httpx.Request("POST", "https://api.stepfun.com/step_plan/v1/chat/completions")
    response = _httpx.Response(400, request=request,
                               json={"error": {"message": "please use the Messages API (/v1/messages) instead",
                                               "type": "request_params_invalid"}})
    return APIStatusError("Error code: 400 - please use the Messages API (/v1/messages) instead",
                          response=response, body=None)


def test_fallback_to_messages_api(monkeypatch):
    captured = {}

    class _Completions:
        def create(self, **kw):
            raise _messages_api_400()

    class FakeClient:
        def __init__(self, base_url=None, api_key=None, timeout=None, max_retries=None):
            self.chat = type("Chat", (), {})()
            self.chat.completions = _Completions()

    class FakeResp:
        status_code = 200
        text = '{"content":[{"type":"text","text":"来自 Messages 协议"}]}'
        def json(self):
            return {"content": [{"type": "text", "text": "来自 Messages 协议"}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResp()

    monkeypatch.setattr(providers, "OpenAI", FakeClient)
    monkeypatch.setattr(providers.httpx, "post", fake_post)
    providers._protocol_cache.clear()

    out = providers.chat("hi", "sk-test", model="step-explore", provider="custom",
                         base_url="https://api.stepfun.com/step_plan/v1")
    assert out == "来自 Messages 协议"
    assert captured["url"] == "https://api.stepfun.com/step_plan/v1/messages"
    assert captured["json"]["model"] == "step-explore"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["headers"]["x-api-key"] == "sk-test"
    key = ("https://api.stepfun.com/step_plan/v1", "step-explore")
    assert providers._protocol_cache[key] == "anthropic"
    # 协议已记住：再次调用直接走 Messages，不再触碰 OpenAI 客户端
    out2 = providers.chat("again", "sk-test", model="step-explore", provider="custom",
                          base_url="https://api.stepfun.com/step_plan/v1")
    assert out2 == "来自 Messages 协议"
    providers._protocol_cache.clear()


def test_messages_stream_parses_sse(monkeypatch):
    captured = {}

    class FakeStreamResp:
        status_code = 200
        def iter_lines(self):
            return iter([
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"你"}}',
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"好"}}',
                'data: {"type":"message_stop"}',
                '',
            ])

    class _Ctx:
        def __init__(self, resp):
            self._resp = resp
        def __enter__(self):
            return self._resp
        def __exit__(self, *args):
            return False

    def fake_stream(method, url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Ctx(FakeStreamResp())

    monkeypatch.setattr(providers.httpx, "stream", fake_stream)
    out = "".join(providers.messages_chat_stream(
        "https://api.stepfun.com/step_plan/v1", "sk-test", "step-explore",
        [{"role": "system", "content": "系统提示"},
         {"role": "user", "content": "你好"}]))
    assert out == "你好"
    assert captured["url"] == "https://api.stepfun.com/step_plan/v1/messages"
    assert captured["json"]["system"] == "系统提示"
    assert captured["json"]["stream"] is True


def test_messages_error_mapping(monkeypatch):
    class FakeResp:
        status_code = 401
        text = '{"error": "unauthorized"}'

    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: FakeResp())
    with pytest.raises(providers.LLMError) as ei:
        providers.messages_chat("https://x/v1", "bad-key", "m",
                                [{"role": "user", "content": "hi"}])
    assert ei.value.code == "bad_key"
