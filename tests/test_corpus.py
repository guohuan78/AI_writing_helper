# -*- encoding:utf-8 -*-
"""语料库与模板契约测试（离线，不调用模型）。"""
import pytest

import article_studio as studio
import corpus


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "DB_PATH", str(tmp_path / "corpus.db"))


def test_article_search_by_bigram_overlap():
    corpus.add_article("内核内存回收漫谈", "LRU 链表与页面回收的实践笔记，聊聊回收水位线怎么算。")
    corpus.add_article("手冲咖啡入门", "水温研磨度与粉水比，一杯好咖啡的三要素。")
    hits = corpus.search_articles("内存回收 水位线 实践", k=1)
    assert len(hits) == 1
    assert hits[0]["title"] == "内核内存回收漫谈"
    assert hits[0]["score"] > 0


def test_search_empty_query_returns_empty():
    corpus.add_article("标题", "正文")
    assert corpus.search_articles("   ") == []


def test_stats_and_recency_order():
    corpus.add_article("A", "正文A")
    corpus.add_article("B", "正文B")
    arts = corpus.list_articles()
    assert arts[0]["title"] == "B"
    s = corpus.stats()
    assert s["articles"] == 2 and s["topics"] == 0


def test_topic_history_dedup_and_skip_empty():
    corpus.record_topic("AI 写作", "从工具史切入", None)
    corpus.record_topic("AI 写作", "从工具史切入", "标题一")
    corpus.record_topic("AI 写作", "反常识：写得越快越好", None)
    corpus.record_topic("  ", "空主题不记录", None)
    corpus.record_topic("AI 写作", "  ", None)
    assert corpus.past_angles("AI 写作") == ["反常识：写得越快越好", "从工具史切入"]
    assert corpus.past_angles("别的主题") == []


def test_prompt_templates_format():
    """全部模板的占位符必须与代码传参一致，format 不抛 KeyError/IndexError。"""
    studio.load_prompt("topics")[1].format(topic="t", audience="a", avoid="- x")
    studio.load_prompt("titles")[1].format(topic="t", angle="a")
    studio.load_prompt("outline")[1].format(title="t", angle="a", audience="a")
    studio.load_prompt("body")[1].format(title="t", angle="a", audience="a",
                                         outline="o", style_block="s", section="c")
    studio.load_prompt("summary")[1].format(title="t", body="b")
    studio.load_prompt("rewrite")[1].format(text="x", strength=3)
    studio.load_prompt("cover")[1].format(title="t", digest="d")
