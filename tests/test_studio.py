# -*- encoding:utf-8 -*-
"""创作台端到端测试：导出契约、排版预览、送审与审批状态机（真实 CLI 调用）。

联动测试需要本机存在 wechat-publisher 项目（默认 D:/coding/wechat-publisher，
可用环境变量 WECHAT_PUBLISHER_DIR 覆盖），其中送审测试会调用真实 CLI 存一条
标题带【测试】标记的草稿并停留在 pending 状态，等待人工在后台核对处理。
"""
import os

import pytest

import article_studio as studio

PUBLISHER_DIR = os.environ.get("WECHAT_PUBLISHER_DIR", "D:/coding/wechat-publisher")

pytestmark = pytest.mark.skipif(
    not os.path.isfile(os.path.join(PUBLISHER_DIR, "src", "cli.js")),
    reason="本机没有 wechat-publisher 项目")


def _export(tmp_path):
    return studio.export_article(
        "【测试】创作台送审链路验证", "端到端测试",
        "## 小标题\n\n这是一段用于验证创作台到公众号送审链路的正文，停留在待审批状态等待人工核对。",
        str(tmp_path))


def test_export_front_matter(tmp_path):
    path = _export(tmp_path)
    text = open(path, encoding="utf-8").read()
    assert text.startswith("---\ntitle: 【测试】创作台送审链路验证\nauthor: 端到端测试\ncover: auto\n---")


def test_render_preview_real(tmp_path):
    path = _export(tmp_path)
    proc = studio.run_publisher(["render", path, "-o", str(tmp_path / "preview.html")],
                                PUBLISHER_DIR, 60)
    assert proc.returncode == 0, proc.stderr
    html = open(tmp_path / "preview.html", encoding="utf-8").read()
    assert "创作台送审链路验证" in html
    assert "<body" in html


def test_parse_draft_output():
    assert studio.parse_draft_output("草稿已保存,进入待审批状态:\n  ID: ab12cd34") == ("new", "ab12cd34")
    assert studio.parse_draft_output("内容未变化,已有记录 [ab12cd34] 状态=pending") == ("duplicate", "ab12cd34")
    assert studio.parse_draft_output("nothing here") == (None, None)


def test_run_publisher_config_errors(tmp_path):
    with pytest.raises(studio.PublisherError):
        studio.run_publisher(["list"], "", 5)
    with pytest.raises(studio.PublisherError):
        studio.run_publisher(["list"], str(tmp_path), 5)


def test_draft_and_status_real(tmp_path):
    """真实送审一条【测试】草稿，经 list 回显确认 pending，内容重复时走复用分支。"""
    path = _export(tmp_path)
    proc = studio.run_publisher(["draft", path], PUBLISHER_DIR, 240)
    kind, draft_id = studio.parse_draft_output(proc.stdout)
    assert kind in ("new", "duplicate"), (proc.stdout + proc.stderr)[-500:]

    lst = studio.run_publisher(["list"], PUBLISHER_DIR, 30)
    assert lst.returncode == 0, lst.stderr
    assert draft_id in lst.stdout

    if kind == "duplicate":
        dup_line = [l for l in lst.stdout.splitlines() if draft_id in l][0]
        assert "pending" in dup_line or "approved" in dup_line
