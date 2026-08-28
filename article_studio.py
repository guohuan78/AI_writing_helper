# -*- encoding:utf-8 -*-
"""公众号推文创作台：选题 → 标题 → 大纲 → 逐段成稿 → 摘要 → 导出 Markdown。

导出的带 YAML front matter 的 Markdown 可直接交给 wechat-publisher
（https://github.com/guohuan78/wechat-publisher）自动排版、存草稿、审批、发表。
"""
import datetime
import json
import os
import re
import shutil
import subprocess

import gradio as gr

import corpus
from providers import PROVIDERS, LLMError, chat, chat_stream, resolve_base_url

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(BASE_DIR, "prompts")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
REF_URL = "https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e"
PREVIEW_HTML = os.path.join(BASE_DIR, "preview.html")

_DETECTED_PUBLISHER = "D:/coding/wechat-publisher" if os.path.isdir("D:/coding/wechat-publisher") else ""
DEFAULT_CONFIG = {"api_keys": {}, "provider": "orcarouter", "base_url": "", "model": "",
                  "author": "", "output_dir": "articles", "publisher_dir": _DETECTED_PUBLISHER}


def load_config():
    merged = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            merged.update({k: cfg.get(k, v) for k, v in DEFAULT_CONFIG.items()})
            if cfg.get("api_key") and not merged.get("api_keys"):
                merged["api_keys"] = {"orcarouter": cfg["api_key"]}
        except (OSError, ValueError):
            pass
    return merged


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_prompt(name):
    with open(os.path.join(PROMPT_DIR, name + ".json"), "r", encoding="utf-8") as f:
        tpl = json.load(f)
    return tpl["system"], tpl["user_template"]


def stream_text(prompt_name, api_key, model, temperature, max_tokens=2048,
                provider="orcarouter", base_url="", **variables):
    """按模板流式生成，yield 已累积文本；出错时把错误信息附在尾部后停止。"""
    system, user_template = load_prompt(prompt_name)
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user_template.format(**variables)}]
    text = ""
    try:
        for chunk in chat_stream(messages, api_key, model=model, provider=provider,
                                 base_url=base_url, max_tokens=max_tokens,
                                 temperature=temperature):
            text += chunk
            yield text
    except LLMError as e:
        if e.code in ("bad_key", "no_key"):
            yield text + "\n\n> ⚠️ 请先在「设置」中填写有效的 API Key"
        elif e.code == "rate_limit":
            yield text + "\n\n> ⚠️ 请求过于频繁或额度不足，请稍后重试"
        else:
            yield text + "\n\n> ⚠️ 调用失败：" + str(e)


def strip_warnings(text):
    return "\n".join(l for l in text.splitlines()
                     if not l.strip().startswith("> ⚠️")).rstrip()


def warning_message(text):
    """从流式输出中提取警告内容，无警告返回 None。"""
    m = re.search(r"> ⚠️ (.+)", text or "")
    return m.group(1).strip() if m else None


def parse_topics(text):
    items = []
    for line in text.splitlines():
        m = re.match(r"^\d+[\.、\)）]\s*(.+)$", line.strip())
        if m:
            items.append(m.group(1).replace("**", "").strip())
    return [i for i in items if i]


def parse_titles(text):
    pairs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^[\[【（(]?(悬念式|数字式|观点式|反差式)[\]】）)]?\s*[:：、]?\s*(.+)$", line)
        if m:
            pairs.append(("【" + m.group(1) + "】" + m.group(2).strip(), m.group(2).strip()))
            continue
        m2 = re.match(r"^([\-\*]|\d+[\.、\)）])\s*(.+)$", line)
        if m2 and len(m2.group(2)) > 4:
            pairs.append((m2.group(2).strip(), m2.group(2).strip()))
    return pairs


def parse_sections(outline_text):
    sections = []
    for line in outline_text.splitlines():
        line = line.strip()
        if line and re.match(r"^(#{1,4}\s|[\-\*]\s|\d+[\.、\)）])", line):
            sections.append(line)
    return sections or ([outline_text.strip()] if outline_text.strip() else [])


def safe_filename(title):
    name = re.sub(r'[\\/:*?"<>|\r\n]', "", title).strip()
    name = re.sub(r"\s+", "-", name)
    return name[:24] or "untitled"


def export_article(title, author, body, output_dir):
    front = ["---", "title: " + title]
    if author.strip():
        front.append("author: " + author.strip())
    front.append("cover: auto")
    article = "\n".join(front) + "\n---\n\n" + body.strip() + "\n"
    out = output_dir.strip() or "articles"
    os.makedirs(out, exist_ok=True)
    filename = datetime.date.today().strftime("%Y%m%d") + "-" + safe_filename(title) + ".md"
    path = os.path.join(out, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(article)
    return path


# ---- wechat-publisher 联动 ----

class PublisherError(Exception):
    pass


def run_publisher(args, publisher_dir, timeout=120):
    """在 wechat-publisher 项目目录运行 CLI，返回 CompletedProcess。"""
    cwd = (publisher_dir or "").strip()
    if not cwd:
        raise PublisherError("未配置 wechat-publisher 项目路径，请在「设置」中填写")
    if not os.path.isfile(os.path.join(cwd, "src", "cli.js")):
        raise PublisherError("目录下没找到 src/cli.js，请确认填写的是 wechat-publisher 项目路径")
    node = shutil.which("node")
    if not node:
        raise PublisherError("未找到 node，请先安装 Node.js 并加入 PATH")
    try:
        return subprocess.run([node, "src/cli.js"] + args, cwd=cwd, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise PublisherError("命令超时（%d 秒）：%s" % (timeout, " ".join(args)))


def parse_draft_output(stdout):
    """从 draft 命令输出解析 (kind, id)：kind 为 new / duplicate / None。"""
    m = re.search(r"ID:\s*([0-9a-f]{8})", stdout)
    if m:
        return "new", m.group(1)
    m = re.search(r"已有记录 \[([0-9a-f]{8})\]", stdout)
    if m:
        return "duplicate", m.group(1)
    return None, None


def _absolute_export_path(state):
    """CLI 在 wechat-publisher 目录里执行，相对导出路径必须先转绝对路径。"""
    path = state["export_path"]
    return path if os.path.isabs(path) else os.path.abspath(path)


def render_preview(publisher_dir, state):
    state = dict(state)
    if not state.get("export_path"):
        raise gr.Error("请先在第 6 步导出 Markdown")
    try:
        proc = run_publisher(["render", _absolute_export_path(state), "-o", PREVIEW_HTML], publisher_dir, 60)
    except PublisherError as e:
        raise gr.Error(str(e))
    if proc.returncode != 0:
        raise gr.Error("渲染失败：" + (proc.stderr.strip() or proc.stdout.strip())[-300:])
    with open(PREVIEW_HTML, "r", encoding="utf-8") as f:
        html = f.read()
    gr.Info("排版预览已生成")
    return html


def send_draft(publisher_dir, state):
    state = dict(state)
    if not state.get("export_path"):
        raise gr.Error("请先在第 6 步导出 Markdown")
    try:
        proc = run_publisher(["draft", _absolute_export_path(state)], publisher_dir, 240)
    except PublisherError as e:
        raise gr.Error(str(e))
    kind, draft_id = parse_draft_output(proc.stdout)
    if kind == "new":
        state["draft_id"] = draft_id
        gr.Info("草稿已保存，记录 ID：" + draft_id)
        return ("草稿已保存，记录 ID：`%s`\n\n"
                "下一步：到公众号后台草稿箱核对排版，然后运行 `approve %s` 审批、`publish %s` 发表。"
                % (draft_id, draft_id, draft_id)), state
    if kind == "duplicate":
        state["draft_id"] = draft_id
        gr.Info("内容未变化，复用已有记录 " + draft_id)
        return "内容未变化，复用已有记录：`%s`（状态见「刷新发表状态」）。" % draft_id, state
    raise gr.Error("送审失败：" + ((proc.stderr.strip() or proc.stdout.strip())[-300:]))


def refresh_status(publisher_dir):
    try:
        proc = run_publisher(["list"], publisher_dir, 30)
    except PublisherError as e:
        raise gr.Error(str(e))
    text = (proc.stdout.strip() or proc.stderr.strip()) or "暂无记录。"
    if proc.returncode != 0:
        raise gr.Error("查询失败：" + text[-300:])
    return "```\n" + text + "\n```"


# ---- 语料库、润色与封面 ----

def corpus_stats_text():
    s = corpus.stats()
    return "文章 %d 篇 · 选题记录 %d 条" % (s["articles"], s["topics"])


def add_corpus_article(title, text):
    if not title.strip() or not text.strip():
        raise gr.Error("标题和正文都需要填写")
    corpus.add_article(title, text)
    gr.Info("已导入语料库")
    return corpus_stats_text(), "", ""


def fill_rewrite(state):
    if not state.get("body"):
        raise gr.Error("正文尚未生成")
    return state["body"]


def gen_rewrites(rewrite_text, strength, api_key, model, provider, base_url):
    if not rewrite_text.strip():
        raise gr.Error("请先在第 4 步生成正文，或直接把要改写的文字填入输入框")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    system, user_template = load_prompt("rewrite")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user_template.format(
                    text=rewrite_text.strip(), strength=int(strength))}]
    versions = []
    try:
        for _ in range(3):
            out = chat(messages, api_key, model=model, provider=provider,
                       base_url=base_url, max_tokens=6000, temperature=0.85)
            versions.append(out.strip())
    except LLMError as e:
        raise gr.Error("调用失败：" + str(e))
    return versions[0], versions[1], versions[2]


def adopt_version(v1, v2, v3, choice, state):
    state = dict(state)
    picked = {"版本一": v1, "版本二": v2, "版本三": v3}.get(choice)
    if picked is None or not picked.strip():
        raise gr.Error("请先生成改写版本并选择其一")
    state["body"] = picked.strip()
    gr.Info("正文已替换为" + choice)
    return state["body"], state


def gen_cover(api_key, model, provider, base_url, state):
    if not state.get("body"):
        raise gr.Error("请先生成正文")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    system, user_template = load_prompt("cover")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user_template.format(
                    title=state["title"], digest=state["body"][:300])}]
    try:
        out = chat(messages, api_key, model=model, provider=provider,
                   base_url=base_url, max_tokens=2000, temperature=0.9)
    except LLMError as e:
        raise gr.Error("调用失败：" + str(e))
    return out.strip()


# ---- 工作流模式 ----

def switch_mode(mode):
    """返回自动模式卡片与 7 个交互步骤卡片的显隐更新。"""
    auto = "自动" in (mode or "")
    return [gr.update(visible=auto)] + [gr.update(visible=not auto)] * 7


def auto_pipeline(auto_topic, auto_audience, api_key, model, provider, base_url,
                  author, output_dir, progress=gr.Progress()):
    """无人干预流水线：选题→标题→大纲→成稿→摘要→封面→导出，结果回填交互步骤。"""
    topic = (auto_topic or "").strip()
    if not topic:
        raise gr.Error("请先填写主题")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    audience = (auto_audience or "").strip() or "公众号读者"
    state = {"topic": topic, "audience": audience, "angle": None, "title": None,
             "body": None, "summary": None}
    log_lines = []
    blank_radio = gr.update(choices=[], value=None)
    cur = {"log": "", "topics_md": "", "topics_radio": blank_radio, "titles_md": "",
           "titles_radio": blank_radio, "outline": "", "body": "", "summary": "",
           "cover": "", "path": ""}

    def emit(**kw):
        cur.update(kw)
        return (cur["log"], cur["topics_md"], cur["topics_radio"], cur["titles_md"],
                cur["titles_radio"], cur["outline"], cur["body"], cur["summary"],
                cur["cover"], cur["path"], dict(state))

    def note(msg):
        log_lines.append(msg)
        cur["log"] = "\n\n".join(log_lines)
        return cur["log"]

    yield emit(log=note("⏳ ① 生成切入角度…"))

    used = corpus.past_angles(topic)
    text = ""
    for partial in stream_text("topics", api_key, model, 0.9, 3000, topic=topic,
                               audience=audience,
                               avoid="\n".join("- " + a for a in used) or "（无）",
                               provider=provider, base_url=base_url):
        text = partial
        yield emit(topics_md=partial)
    warn = warning_message(text)
    if warn:
        raise gr.Error(warn)
    angles = parse_topics(text)
    if not angles:
        raise gr.Error("选题生成失败：" + (strip_warnings(text)[-300:] or "模型无返回"))
    state["angle"] = angles[0]
    progress(0.2, desc="标题")
    yield emit(topics_md=text, topics_radio=gr.update(choices=angles, value=angles[0]),
               log=note("✅ ① 选定角度：%s\n\n⏳ ② 生成标题候选…" % state["angle"]))

    text = ""
    for partial in stream_text("titles", api_key, model, 0.95, 3000, topic=topic,
                               angle=state["angle"], provider=provider, base_url=base_url):
        text = partial
        yield emit(titles_md=partial)
    warn = warning_message(text)
    if warn:
        raise gr.Error(warn)
    pairs = parse_titles(text)
    if not pairs:
        raise gr.Error("标题生成失败：" + (strip_warnings(text)[-300:] or "模型无返回"))
    state["title"] = pairs[0][1]
    state["title_map"] = dict(pairs)
    progress(0.35, desc="大纲")
    yield emit(titles_md=text,
               titles_radio=gr.update(choices=[d for d, _ in pairs],
                                      value=[d for d, _ in pairs][0]),
               log=note("✅ ② 选定标题：%s\n\n⏳ ③ 生成大纲…" % state["title"]))

    outline = ""
    for partial in stream_text("outline", api_key, model, 0.7, 4000, title=state["title"],
                               angle=state["angle"], audience=audience,
                               provider=provider, base_url=base_url):
        outline = partial
        yield emit(outline=partial)
    warn = warning_message(outline)
    if warn:
        raise gr.Error(warn)
    state["outline"] = outline
    sections = parse_sections(outline)
    hits = corpus.search_articles(topic + "\n" + outline, k=2)
    if hits:
        style_block = "文风参考（只模仿语气与节奏，不引用其中内容）：\n" + "\n---\n".join(
            "《%s》：%s" % (h["title"], h["body"][:400].replace("\n", " ")) for h in hits)
    else:
        style_block = "（语料库暂无参考文章，按自然的风格写。）"
    progress(0.45, desc="逐段成稿")
    yield emit(outline=outline,
               log=note("✅ ③ 大纲完成，共 %d 段\n\n⏳ ④ 逐段成稿（%s）…" % (
                   len(sections),
                   "命中 %d 篇文风参考" % len(hits) if hits else "语料库暂无参考")))

    body = ""
    for i, section in enumerate(sections):
        progress(0.45 + 0.35 * (i + 1) / max(len(sections), 1),
                 desc="第 %d/%d 段" % (i + 1, len(sections)))
        joiner = "\n\n" if body else ""
        section_text = ""
        for partial in stream_text("body", api_key, model, 0.7, 10000, title=state["title"],
                                   angle=state["angle"], audience=audience, outline=outline,
                                   section=section, style_block=style_block,
                                   provider=provider, base_url=base_url):
            section_text = partial
            yield emit(body=joiner + partial)
        body += joiner + section_text
    state["body"] = strip_warnings(body)
    progress(0.85, desc="摘要与封面")
    yield emit(body=body, log=note("✅ ④ 成稿完成（%d 字）\n\n⏳ ⑤ 生成摘要与封面创意…"
                                   % len(state["body"])))

    summary = ""
    for partial in stream_text("summary", api_key, model, 0.4, 1500, title=state["title"],
                               body=state["body"], provider=provider, base_url=base_url):
        summary = partial
        yield emit(summary=partial)
    warn = warning_message(summary)
    if warn:
        raise gr.Error(warn)
    state["summary"] = summary
    system, user_template = load_prompt("cover")
    try:
        cover = chat([{"role": "system", "content": system},
                      {"role": "user", "content": user_template.format(
                          title=state["title"], digest=state["body"][:300])}],
                     api_key, model=model, provider=provider, base_url=base_url,
                     max_tokens=400, temperature=0.9).strip()
    except LLMError as e:
        cover = "封面创意生成失败：" + str(e)

    path = export_article(state["title"], author, state["body"], output_dir)
    corpus.add_article(state["title"], state["body"])
    corpus.record_topic(topic, state["angle"], state["title"])
    saved = load_config()
    saved["author"] = author.strip()
    saved["output_dir"] = output_dir.strip()
    save_config(saved)
    progress(1.0, desc="完成")
    yield emit(summary=summary, cover=cover, path=path,
               log=note("✅ ⑤ 摘要与封面完成\n\n✅ ⑥ 已导出：%s\n\n"
                        "🎉 全流程结束。切回「交互模式」可对任一环节微调后重新导出。" % path))
    gr.Info("自动成稿完成：" + path)


# ---- 界面事件 ----

def gen_topics(topic, audience, api_key, model, provider, base_url, state):
    if not topic.strip():
        raise gr.Error("请先填写主题")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    state = dict(state)
    state.update({"topic": topic.strip(), "audience": audience.strip(),
                  "angle": None, "title": None, "body": None, "summary": None})
    used = corpus.past_angles(state["topic"])
    if used:
        gr.Info("该主题已有 %d 条历史角度，已要求避开" % len(used))
    text = ""
    for partial in stream_text("topics", api_key, model, 0.9, 3000,
                               topic=state["topic"],
                               audience=state["audience"] or "公众号读者",
                               avoid="\n".join("- " + a for a in used) or "（无）",
                               provider=provider, base_url=base_url):
        text = partial
        yield partial, gr.update(choices=[], value=None), state
    state["topics_raw"] = text
    yield text, gr.update(choices=parse_topics(text), value=None), state


def select_angle(angle, state):
    state = dict(state)
    state["angle"] = angle
    return state


def gen_titles(api_key, model, provider, base_url, state):
    state = dict(state)
    if not state.get("angle"):
        raise gr.Error("请先在第一步选择一个切入角度")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    text = ""
    for partial in stream_text("titles", api_key, model, 0.95, 3000,
                               topic=state.get("topic", ""), angle=state["angle"],
                               provider=provider, base_url=base_url):
        text = partial
        yield partial, gr.update(choices=[], value=None), state
    pairs = parse_titles(text)
    state["title_map"] = {d: p for d, p in pairs}
    yield text, gr.update(choices=[d for d, _ in pairs], value=None), state


def select_title(display, state):
    state = dict(state)
    state["title"] = state.get("title_map", {}).get(display, display)
    return state


def gen_outline(api_key, model, provider, base_url, state):
    state = dict(state)
    if not state.get("title"):
        raise gr.Error("请先在第二步选定标题")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    text = ""
    for partial in stream_text("outline", api_key, model, 0.7, 4000,
                               title=state["title"], angle=state["angle"],
                               audience=state.get("audience") or "公众号读者",
                               provider=provider, base_url=base_url):
        text = partial
        yield partial, state
    yield text, state


def gen_body(outline_text, api_key, model, provider, base_url, state):
    state = dict(state)
    if not state.get("title"):
        raise gr.Error("请先完成标题选择")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    outline = outline_text.strip()
    if not outline:
        raise gr.Error("大纲为空，请先生成大纲")
    state["outline"] = outline
    hits = corpus.search_articles((state.get("topic") or "") + "\n" + outline, k=2)
    if hits:
        style_block = "文风参考（只模仿语气与节奏，不引用其中内容）：\n" + "\n---\n".join(
            "《%s》：%s" % (h["title"], h["body"][:400].replace("\n", " ")) for h in hits)
    else:
        style_block = "（语料库暂无参考文章，按自然的风格写。）"
    sections = parse_sections(outline)
    progress = gr.Progress()
    body = ""
    for i, section in enumerate(sections):
        progress((i + 1) / len(sections), desc="第 %d/%d 段" % (i + 1, len(sections)))
        section_text = ""
        joiner = "\n\n" if body else ""
        for partial in stream_text("body", api_key, model, 0.7, 10000,
                                   title=state["title"], angle=state["angle"],
                                   audience=state.get("audience") or "公众号读者",
                                   outline=outline, section=section,
                                   style_block=style_block,
                                   provider=provider, base_url=base_url):
            section_text = partial
            yield joiner + partial, state
        body += joiner + section_text
    state["body"] = strip_warnings(body)
    yield body, state


def gen_summary(api_key, model, provider, base_url, state):
    state = dict(state)
    if not state.get("body"):
        raise gr.Error("请先生成正文")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    text = ""
    for partial in stream_text("summary", api_key, model, 0.4, 1500,
                               title=state["title"], body=state["body"],
                               provider=provider, base_url=base_url):
        text = partial
        yield partial, state
    state["summary"] = text
    yield text, state


def do_export(author, output_dir, state):
    state = dict(state)
    if not state.get("title") or not state.get("body"):
        raise gr.Error("请先完成正文生成")
    path = export_article(state["title"], author, state["body"], output_dir)
    corpus.add_article(state["title"], state["body"])
    corpus.record_topic(state.get("topic", ""), state.get("angle", ""), state["title"])
    cfg = load_config()
    cfg["author"] = author.strip()
    cfg["output_dir"] = output_dir.strip()
    save_config(cfg)
    gr.Info("已导出：" + path)
    return path, state


def on_provider_change(provider_key):
    """切换供应商：载入该供应商已保存的 Key，带出官方地址与默认模型。"""
    info = PROVIDERS.get(provider_key, {})
    saved_key = load_config().get("api_keys", {}).get(provider_key, "")
    if info.get("console"):
        console = "在 [%s](%s) 创建 Key" % (info["console_name"], info["console"])
    else:
        console = "填入任意 OpenAI 兼容服务的地址与对应 Key"
    return saved_key, info.get("default_model", ""), info.get("base_url", ""), console


def save_settings(provider, base_url, api_key, model, author, output_dir, publisher_dir):
    cfg = load_config()
    keys = dict(cfg.get("api_keys") or {})
    keys[provider] = api_key.strip()
    cfg.update({"provider": provider, "base_url": base_url.strip(), "model": model.strip(),
                "api_keys": keys, "author": author.strip(),
                "output_dir": output_dir.strip(), "publisher_dir": publisher_dir.strip()})
    save_config(cfg)
    gr.Info("设置已保存：%s 的 Key 已单独保存" % PROVIDERS.get(provider, {}).get("label", provider))


cfg = load_config()

CUSTOM_CSS = """
.gradio-container {max-width: 920px !important; margin: 0 auto !important;}
footer {display: none !important;}
#hero {margin: 10px 0 6px;}
#hero h1 {font-size: 1.7em; font-weight: 700; margin: 0; letter-spacing: .5px;
  background: linear-gradient(90deg, #4f46e5, #0ea5e9);
  -webkit-background-clip: text; background-clip: text; color: transparent;}
#hero p {color: #64748b; margin: 6px 0 0; font-size: .95em;}
#hero a {color: #4f46e5; text-decoration: none; font-weight: 600;}
.card {background: var(--background-fill-primary, #fff);
  border: 1px solid var(--border-color-primary, #e2e8f0);
  border-radius: 16px; padding: 18px 22px 20px; margin: 0 0 14px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, .06);}
.step-h h2 {margin: 0 0 10px; font-size: 1.08rem; font-weight: 700; line-height: 1.25;
  border-left: 4px solid var(--color-accent, #6366f1); padding-left: 10px;}
.step-note p {color: var(--body-text-color-subdued, #64748b); font-size: .9em; margin: -4px 0 10px;}
"""

STUDIO_THEME = gr.themes.Soft(
    primary_hue="indigo", secondary_hue="sky", neutral_hue="slate",
    font=["system-ui", "Segoe UI", "Microsoft YaHei", "PingFang SC", "sans-serif"])

with gr.Blocks(title="公众号推文创作台") as demo:
    gr.HTML('<div id="hero"><h1>AI 写作外挂 · 公众号推文创作台</h1>'
            '<p>选题 → 标题 → 大纲 → 逐段成稿 → 润色 → 摘要导出 → 排版送审，一条流水线到草稿箱'
            '　·　模型服务 <a href="https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e" '
            'target="_blank">OrcaRouter</a> / StepFun / GLM / Kimi（OpenAI 兼容，设置里切换）</p></div>')
    app_state = gr.State({})

    mode_radio = gr.Radio(choices=["🖐 交互模式（逐步选择）", "🤖 自动模式（一键成稿）"],
                          value="🖐 交互模式（逐步选择）", label="工作模式",
                          info="自动模式：角度与标题取第一候选，一键跑到导出；交互模式：每一步自己选。")

    with gr.Group(elem_classes=["card"], visible=False) as auto_card:
        gr.Markdown("## 🤖 自动模式", elem_classes=["step-h"])
        gr.Markdown("填主题后一键跑完整条流水线，日志实时显示进度；完成后切回「交互模式」，"
                    "所有结果已回填到各步骤，可继续手动微调。", elem_classes=["step-note"])
        auto_topic = gr.Textbox(label="主题", placeholder="今天想写什么：一个词、一件事、一条新闻都行")
        auto_audience = gr.Textbox(label="目标读者与口吻（可选）", placeholder="例：刚入行的产品经理，口语一点")
        auto_btn = gr.Button("🚀 一键成稿", variant="primary")
        auto_log = gr.Markdown()

    with gr.Accordion("设置", open=False):
        provider_box = gr.Dropdown(choices=[(info["label"], key) for key, info in PROVIDERS.items()],
                                   value=cfg.get("provider", "orcarouter"), label="模型供应商",
                                   info="OrcaRouter 一个 Key 即可调用 GLM、Kimi、Qwen 等全部模型，也可直连各供应商官方接口")
        baseurl_box = gr.Textbox(
            label="API 地址（OpenAI 兼容）",
            value=cfg.get("base_url") or PROVIDERS.get(cfg.get("provider", "orcarouter"), {}).get("base_url", ""),
            info="切换供应商时自动填入官方地址，可修改")
        key_box = gr.Textbox(label="API Key（当前供应商）", type="password",
                             value=cfg.get("api_keys", {}).get(cfg.get("provider", "orcarouter"), ""),
                             info="每个供应商的 Key 分开保存在 config.json 的 api_keys 中，明文谨防泄露")
        _provider_info = PROVIDERS.get(cfg.get("provider", "orcarouter"), {})
        console_md = gr.Markdown(
            ("在 [%s](%s) 创建 Key" % (_provider_info["console_name"], _provider_info["console"]))
            if _provider_info.get("console") else "填入任意 OpenAI 兼容服务的地址与对应 Key",
            elem_classes=["step-note"])
        model_box = gr.Textbox(
            label="模型",
            value=cfg.get("model") or _provider_info.get("default_model", ""),
            info="以所选平台的模型列表为准，可直接改名")
        author_box = gr.Textbox(label="作者名（可选）", value=cfg["author"],
                                info="写入文章 front matter 的 author 字段")
        outdir_box = gr.Textbox(label="导出目录", value=cfg["output_dir"],
                                info="本地目录或 wechat-publisher 项目的 articles 路径")
        pubdir_box = gr.Textbox(label="wechat-publisher 项目路径", value=cfg["publisher_dir"],
                                info="用于排版预览与一键送审，例如 D:\\coding\\wechat-publisher")
        save_btn = gr.Button("保存设置")

    with gr.Accordion("语料库（文风学习）", open=False):
        gr.Markdown("导入已发表的文章作为文风参考，成稿时自动检索最相关的两篇；导出 Markdown 的文章会自动入库，"
                    "选题历史也会记录用于避开旧角度。")
        with gr.Row():
            corpus_title = gr.Textbox(label="文章标题", scale=1)
            corpus_stats = gr.Textbox(label="语料库现状", value=corpus_stats_text(), interactive=False, scale=1)
        corpus_text = gr.Textbox(label="文章正文", lines=6)
        with gr.Row():
            corpus_add_btn = gr.Button("导入文章")
            corpus_stats_btn = gr.Button("刷新统计")

    with gr.Group(elem_classes=["card"]) as card1:
        gr.Markdown("## 1 · 选题", elem_classes=["step-h"])
        topic_box = gr.Textbox(label="主题", placeholder="今天想写什么：一个词、一件事、一条新闻都行")
        audience_box = gr.Textbox(label="目标读者与口吻（可选）", placeholder="例：刚入行的产品经理，口语一点")
        topics_btn = gr.Button("生成切入角度", variant="primary")
        topics_md = gr.Markdown()
        topics_radio = gr.Radio(label="选定一个切入角度", choices=[])

    with gr.Group(elem_classes=["card"]) as card2:
        gr.Markdown("## 2 · 标题", elem_classes=["step-h"])
        titles_btn = gr.Button("生成标题候选")
        titles_md = gr.Markdown()
        titles_radio = gr.Radio(label="选定标题", choices=[])

    with gr.Group(elem_classes=["card"]) as card3:
        gr.Markdown("## 3 · 大纲", elem_classes=["step-h"])
        gr.Markdown("生成后可以直接在文本框里修改，成稿按修改后的大纲进行。", elem_classes=["step-note"])
        outline_btn = gr.Button("生成大纲")
        outline_box = gr.Textbox(label="段落级大纲", lines=6)

    with gr.Group(elem_classes=["card"]) as card4:
        gr.Markdown("## 4 · 逐段成稿", elem_classes=["step-h"])
        body_btn = gr.Button("按大纲逐段生成", variant="primary")
        body_md = gr.Markdown()

    with gr.Group(elem_classes=["card"]) as card5:
        gr.Markdown("## 5 · 润色重写", elem_classes=["step-h"])
        gr.Markdown("把要改写的文字填入下方（「填入正文」可带入成稿全文），生成 3 个版本后选一版替换正文。",
                    elem_classes=["step-note"])
        rewrite_fill_btn = gr.Button("填入正文")
        rewrite_input = gr.Textbox(label="待改写文字", lines=6)
        strength_slider = gr.Slider(1, 5, step=1, value=3, label="改写强度",
                                    info="1=只修语病用词，3=换句式结构，5=深度重写")
        rewrite_btn = gr.Button("生成 3 个改写版本", variant="primary")
        with gr.Row():
            rewrite_v1 = gr.Textbox(label="版本一", lines=5)
            rewrite_v2 = gr.Textbox(label="版本二", lines=5)
            rewrite_v3 = gr.Textbox(label="版本三", lines=5)
        rewrite_choice = gr.Radio(label="采用哪个版本", choices=["版本一", "版本二", "版本三"])
        rewrite_adopt_btn = gr.Button("替换正文")

    with gr.Group(elem_classes=["card"]) as card6:
        gr.Markdown("## 6 · 摘要与导出", elem_classes=["step-h"])
        summary_btn = gr.Button("生成摘要")
        summary_box = gr.Textbox(label="摘要（公众号摘要栏上限 120 字，发表时粘贴使用）", lines=3)
        cover_btn = gr.Button("生成封面创意")
        cover_box = gr.Textbox(label="封面创意（3 条）", lines=3)
        export_btn = gr.Button("导出 Markdown", variant="primary")
        export_path = gr.Textbox(label="导出位置", interactive=False)

    with gr.Group(elem_classes=["card"]) as card7:
        gr.Markdown("## 7 · 预览与送审", elem_classes=["step-h"])
        gr.Markdown("联动 [wechat-publisher](https://github.com/guohuan78/wechat-publisher)：预览公众号排版效果，"
                    "送审后由那边的人工审批闸门把关（pending → 人工核对 → approve → publish 扫码发表）。",
                    elem_classes=["step-note"])
        preview_btn = gr.Button("排版预览")
        preview_html = gr.HTML()
        draft_btn = gr.Button("送审：存草稿待审批", variant="primary")
        draft_md = gr.Markdown()
        status_btn = gr.Button("刷新发表状态")
        status_md = gr.Markdown()

    topics_btn.click(gen_topics, [topic_box, audience_box, key_box, model_box,
                                  provider_box, baseurl_box, app_state],
                     [topics_md, topics_radio, app_state])
    topics_radio.change(select_angle, [topics_radio, app_state], [app_state])
    titles_btn.click(gen_titles, [key_box, model_box, provider_box, baseurl_box, app_state],
                     [titles_md, titles_radio, app_state])
    titles_radio.change(select_title, [titles_radio, app_state], [app_state])
    outline_btn.click(gen_outline, [key_box, model_box, provider_box, baseurl_box, app_state],
                      [outline_box, app_state])
    body_btn.click(gen_body, [outline_box, key_box, model_box, provider_box, baseurl_box, app_state],
                   [body_md, app_state])
    summary_btn.click(gen_summary, [key_box, model_box, provider_box, baseurl_box, app_state],
                      [summary_box, app_state])
    export_btn.click(do_export, [author_box, outdir_box, app_state], [export_path, app_state])
    save_btn.click(save_settings, [provider_box, baseurl_box, key_box, model_box,
                                   author_box, outdir_box, pubdir_box], None)
    provider_box.change(on_provider_change, [provider_box],
                        [key_box, model_box, baseurl_box, console_md])
    preview_btn.click(render_preview, [pubdir_box, app_state], [preview_html])
    draft_btn.click(send_draft, [pubdir_box, app_state], [draft_md, app_state])
    status_btn.click(refresh_status, [pubdir_box], [status_md])
    corpus_add_btn.click(add_corpus_article, [corpus_title, corpus_text],
                         [corpus_stats, corpus_text, corpus_title])
    corpus_stats_btn.click(lambda: corpus_stats_text(), None, [corpus_stats])
    rewrite_fill_btn.click(fill_rewrite, [app_state], [rewrite_input])
    rewrite_btn.click(gen_rewrites, [rewrite_input, strength_slider, key_box, model_box,
                                     provider_box, baseurl_box],
                      [rewrite_v1, rewrite_v2, rewrite_v3])
    rewrite_adopt_btn.click(adopt_version, [rewrite_v1, rewrite_v2, rewrite_v3, rewrite_choice, app_state],
                            [body_md, app_state])
    cover_btn.click(gen_cover, [key_box, model_box, provider_box, baseurl_box, app_state],
                    [cover_box])
    mode_radio.change(switch_mode, [mode_radio],
                      [auto_card, card1, card2, card3, card4, card5, card6, card7])
    auto_btn.click(auto_pipeline,
                   [auto_topic, auto_audience, key_box, model_box, provider_box, baseurl_box,
                    author_box, outdir_box],
                   [auto_log, topics_md, topics_radio, titles_md, titles_radio,
                    outline_box, body_md, summary_box, cover_box, export_path, app_state])

if __name__ == "__main__":
    demo.launch(inbrowser=True, css=CUSTOM_CSS, theme=STUDIO_THEME)
