# -*- encoding:utf-8 -*-
"""个人语料库：文风学习素材与选题历史的本地 SQLite 存储。

两张表：
- articles  已发表/导入的文章，成稿时按字符 bigram 相关度检索作风格参考；
- topics    主题-角度-标题的选用历史，再次生成选题时用于避开旧角度。
"""
import os
import re
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "corpus.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS articles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS topics(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        angle TEXT NOT NULL,
        title TEXT,
        created_at TEXT NOT NULL)""")
    return conn


def add_article(title, body):
    with _conn() as conn:
        conn.execute("INSERT INTO articles(title, body, created_at) VALUES(?,?,?)",
                     (title.strip(), body.strip(),
                      datetime.now().isoformat(timespec="seconds")))


def list_articles():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT title, body, created_at FROM articles ORDER BY id DESC").fetchall()
    return [{"title": t, "body": b, "created_at": c} for t, b, c in rows]


def record_topic(topic, angle, title=None):
    if not topic.strip() or not angle.strip():
        return
    with _conn() as conn:
        conn.execute("INSERT INTO topics(topic, angle, title, created_at) VALUES(?,?,?,?)",
                     (topic.strip(), angle.strip(),
                      (title or "").strip() or None,
                      datetime.now().isoformat(timespec="seconds")))


def past_angles(topic, limit=20):
    """同一主题下已用过的切入角度，最新的在前，自动去重。"""
    if not topic.strip():
        return []
    with _conn() as conn:
        rows = conn.execute(
            "SELECT angle FROM topics WHERE topic = ? ORDER BY id DESC LIMIT ?",
            (topic.strip(), limit)).fetchall()
    seen, out = set(), []
    for (angle,) in rows:
        if angle not in seen:
            seen.add(angle)
            out.append(angle)
    return out


def _bigrams(text):
    text = re.sub(r"\s+", "", text or "")
    if not text:
        return set()
    if len(text) == 1:
        return {text}
    return {text[i:i + 2] for i in range(len(text) - 1)}


def search_articles(query, k=2, snippet_len=400):
    """按字符 bigram 重合度检索最相关的 k 篇文章，返回带 score 的列表。"""
    q = _bigrams(query)
    if not q:
        return []
    scored = []
    for art in list_articles():
        overlap = len(q & _bigrams(art["title"] + " " + art["body"][:2000]))
        if overlap:
            scored.append((overlap, art))
    scored.sort(key=lambda pair: -pair[0])
    return [dict(art, score=score) for score, art in scored[:k]]


def stats():
    with _conn() as conn:
        articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        topics = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
    return {"articles": articles, "topics": topics}
