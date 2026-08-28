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
