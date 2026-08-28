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
        next(studio.auto_pipeline("   ", "", "sk-orca-x", "orcarouter/auto", "", "articles"))
    with pytest.raises(gr.Error):
        next(studio.auto_pipeline("主题", "", "", "orcarouter/auto", "", "articles"))
