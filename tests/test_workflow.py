# -*- encoding:utf-8 -*-
"""双模式工作流测试（离线）：模式显隐切换与自动流水线的入参校验。"""
import pytest

import gradio as gr

import article_studio as studio


def test_switch_mode_toggles_visibility():
    ups = studio.switch_mode("🤖 自动模式（一键成稿）")
    assert ups[0]["visible"] is True
    assert all(u["visible"] is False for u in ups[1:])

    ups = studio.switch_mode("🖐 交互模式（逐步选择）")
    assert ups[0]["visible"] is False
    assert all(u["visible"] is True for u in ups[1:])

    ups = studio.switch_mode("")
    assert ups[0]["visible"] is False
    assert all(u["visible"] is True for u in ups[1:])


def test_auto_pipeline_input_validations():
    with pytest.raises(gr.Error):
        next(studio.auto_pipeline("   ", "", "sk-orca-x", "orcarouter/auto",
                                  "orcarouter", "", "", "articles"))
    with pytest.raises(gr.Error):
        next(studio.auto_pipeline("主题", "", "", "orcarouter/auto",
                                  "orcarouter", "", "", "articles"))


def test_stream_text_surfaces_llm_errors(monkeypatch):
    """回归：底层调用报错时 stream_text 应给出友好警告，而不是自身崩溃。"""
    import providers

    def broken_stream(*args, **kwargs):
        raise providers.LLMError("API Key 无效", code="bad_key")
        yield  # pragma: no cover

    monkeypatch.setattr(studio, "chat_stream", broken_stream)
    out = list(studio.stream_text("topics", "sk-x", "m", 0.9,
                                  topic="t", audience="a", avoid="（无）"))
    assert out and "⚠️" in out[-1] and "API Key" in out[-1]
    assert studio.warning_message(out[-1]) == "请先在「设置」中填写有效的 API Key"


def test_warning_message_helper():
    assert studio.warning_message("正文\n\n> ⚠️ 请求过于频繁") == "请求过于频繁"
    assert studio.warning_message("没有警告的内容") is None
