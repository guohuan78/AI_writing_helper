# -*- encoding:utf-8 -*-
"""公众号推文创作台：选题 → 标题 → 大纲 → 逐段成稿 → 摘要 → 导出 Markdown。

导出的带 YAML front matter 的 Markdown 可直接交给 wechat-publisher
（https://github.com/guohuan78/wechat-publisher）自动排版、存草稿、审批、发表。
"""
import datetime
import json
import os
import re

import gradio as gr

from orcarouter_provider import DEFAULT_MODEL, chat_stream

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(BASE_DIR, "prompts")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
REF_URL = "https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e"

DEFAULT_CONFIG = {"api_key": "", "model": DEFAULT_MODEL, "author": "", "output_dir": "articles"}


def load_config():
    merged = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            merged.update({k: cfg.get(k, v) for k, v in DEFAULT_CONFIG.items()})
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


def stream_text(prompt_name, api_key, model, temperature, max_tokens=2048, **variables):
    """按模板流式生成，yield 已累积文本；出错时把错误信息附在尾部后停止。"""
    system, user_template = load_prompt(prompt_name)
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user_template.format(**variables)}]
    text = ""
    try:
        for chunk in chat_stream(messages, api_key, model=model,
                                 max_tokens=max_tokens, temperature=temperature):
            text += chunk
            yield text
    except OrcaRouterError as e:
        if e.code in ("bad_key", "no_key"):
            yield text + "\n\n> ⚠️ 请先在「设置」中填写有效的 API Key"
        elif e.code == "rate_limit":
            yield text + "\n\n> ⚠️ 请求过于频繁或额度不足，请稍后重试"
        else:
            yield text + "\n\n> ⚠️ 调用失败：" + str(e)


def strip_warnings(text):
    return "\n".join(l for l in text.splitlines()
                     if not l.strip().startswith("> ⚠️")).rstrip()


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


# ---- 界面事件 ----

def gen_topics(topic, audience, api_key, model, state):
    if not topic.strip():
        raise gr.Error("请先填写主题")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    state = dict(state)
    state.update({"topic": topic.strip(), "audience": audience.strip(),
                  "angle": None, "title": None, "body": None, "summary": None})
    text = ""
    for partial in stream_text("topics", api_key, model, 0.9, 800,
                               topic=state["topic"],
                               audience=state["audience"] or "公众号读者"):
        text = partial
        yield partial, gr.update(choices=[], value=None), state
    state["topics_raw"] = text
    yield text, gr.update(choices=parse_topics(text), value=None), state


def select_angle(angle, state):
    state = dict(state)
    state["angle"] = angle
    return state


def gen_titles(api_key, model, state):
    state = dict(state)
    if not state.get("angle"):
        raise gr.Error("请先在第一步选择一个切入角度")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    text = ""
    for partial in stream_text("titles", api_key, model, 0.95, 600,
                               topic=state.get("topic", ""), angle=state["angle"]):
        text = partial
        yield partial, gr.update(choices=[], value=None), state
    pairs = parse_titles(text)
    state["title_map"] = {d: p for d, p in pairs}
    yield text, gr.update(choices=[d for d, _ in pairs], value=None), state


def select_title(display, state):
    state = dict(state)
    state["title"] = state.get("title_map", {}).get(display, display)
    return state


def gen_outline(api_key, model, state):
    state = dict(state)
    if not state.get("title"):
        raise gr.Error("请先在第二步选定标题")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    text = ""
    for partial in stream_text("outline", api_key, model, 0.7, 900,
                               title=state["title"], angle=state["angle"],
                               audience=state.get("audience") or "公众号读者"):
        text = partial
        yield partial, state
    yield text, state


def gen_body(outline_text, api_key, model, state):
    state = dict(state)
    if not state.get("title"):
        raise gr.Error("请先完成标题选择")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    outline = outline_text.strip()
    if not outline:
        raise gr.Error("大纲为空，请先生成大纲")
    state["outline"] = outline
    sections = parse_sections(outline)
    progress = gr.Progress()
    body = ""
    for i, section in enumerate(sections):
        progress((i + 1) / len(sections), desc="第 %d/%d 段" % (i + 1, len(sections)))
        section_text = ""
        joiner = "\n\n" if body else ""
        for partial in stream_text("body", api_key, model, 0.7, 2000,
                                   title=state["title"], angle=state["angle"],
                                   audience=state.get("audience") or "公众号读者",
                                   outline=outline, section=section):
            section_text = partial
            yield joiner + partial, state
        body += joiner + section_text
    state["body"] = strip_warnings(body)
    yield body, state


def gen_summary(api_key, model, state):
    state = dict(state)
    if not state.get("body"):
        raise gr.Error("请先生成正文")
    if not api_key.strip():
        raise gr.Error("请先在「设置」中填写 API Key")
    text = ""
    for partial in stream_text("summary", api_key, model, 0.4, 200,
                               title=state["title"], body=state["body"]):
        text = partial
        yield partial, state
    state["summary"] = text
    yield text, state


def do_export(author, output_dir, state):
    state = dict(state)
    if not state.get("title") or not state.get("body"):
        raise gr.Error("请先完成正文生成")
    path = export_article(state["title"], author, state["body"], output_dir)
    cfg = load_config()
    cfg["author"] = author.strip()
    cfg["output_dir"] = output_dir.strip()
    save_config(cfg)
    gr.Info("已导出：" + path)
    return path, state


def save_settings(api_key, model, author, output_dir):
    save_config({"api_key": api_key.strip(), "model": model.strip(),
                 "author": author.strip(), "output_dir": output_dir.strip()})
    gr.Info("设置已保存到 config.json")


cfg = load_config()

with gr.Blocks(title="公众号推文创作台") as demo:
    gr.Markdown("# AI 写作外挂 · 公众号推文创作台\n"
                "选题 → 标题 → 大纲 → 逐段成稿 → 摘要 → 导出 Markdown，"
                "交给 [wechat-publisher](https://github.com/guohuan78/wechat-publisher) 排版发表。")
    app_state = gr.State({})

    with gr.Accordion("设置", open=False):
        key_box = gr.Textbox(label="OrcaRouter API Key", type="password", value=cfg["api_key"],
                             info="sk-orca- 开头，获取地址：" + REF_URL + "；明文保存在本目录 config.json，谨防泄露")
        model_box = gr.Textbox(label="模型", value=cfg["model"],
                               info="默认 orcarouter/auto（按任务难度自动选型），也可填 qwen/qwen3-max、z-ai/glm-5 等")
        author_box = gr.Textbox(label="作者名（可选）", value=cfg["author"],
                                info="写入文章 front matter 的 author 字段")
        outdir_box = gr.Textbox(label="导出目录", value=cfg["output_dir"],
                                info="本地目录或 wechat-publisher 项目的 articles 路径")
        save_btn = gr.Button("保存设置")

    with gr.Group():
        gr.Markdown("## 1 · 选题")
        topic_box = gr.Textbox(label="主题", placeholder="今天想写什么：一个词、一件事、一条新闻都行")
        audience_box = gr.Textbox(label="目标读者与口吻（可选）", placeholder="例：刚入行的产品经理，口语一点")
        topics_btn = gr.Button("生成切入角度", variant="primary")
        topics_md = gr.Markdown()
        topics_radio = gr.Radio(label="选定一个切入角度", choices=[])

    with gr.Group():
        gr.Markdown("## 2 · 标题")
        titles_btn = gr.Button("生成标题候选")
        titles_md = gr.Markdown()
        titles_radio = gr.Radio(label="选定标题", choices=[])

    with gr.Group():
        gr.Markdown("## 3 · 大纲")
        gr.Markdown("生成后可以直接在文本框里修改，成稿按修改后的大纲进行。")
        outline_btn = gr.Button("生成大纲")
        outline_box = gr.Textbox(label="段落级大纲", lines=6)

    with gr.Group():
        gr.Markdown("## 4 · 逐段成稿")
        body_btn = gr.Button("按大纲逐段生成", variant="primary")
        body_md = gr.Markdown()

    with gr.Group():
        gr.Markdown("## 5 · 摘要与导出")
        summary_btn = gr.Button("生成摘要")
        summary_box = gr.Textbox(label="摘要（公众号摘要栏上限 120 字，发表时粘贴使用）", lines=3)
        export_btn = gr.Button("导出 Markdown", variant="primary")
        export_path = gr.Textbox(label="导出位置", interactive=False)

    topics_btn.click(gen_topics, [topic_box, audience_box, key_box, model_box, app_state],
                     [topics_md, topics_radio, app_state])
    topics_radio.change(select_angle, [topics_radio, app_state], [app_state])
    titles_btn.click(gen_titles, [key_box, model_box, app_state],
                     [titles_md, titles_radio, app_state])
    titles_radio.change(select_title, [titles_radio, app_state], [app_state])
    outline_btn.click(gen_outline, [key_box, model_box, app_state], [outline_box, app_state])
    body_btn.click(gen_body, [outline_box, key_box, model_box, app_state], [body_md, app_state])
    summary_btn.click(gen_summary, [key_box, model_box, app_state], [summary_box, app_state])
    export_btn.click(do_export, [author_box, outdir_box, app_state], [export_path, app_state])
    save_btn.click(save_settings, [key_box, model_box, author_box, outdir_box], None)

if __name__ == "__main__":
    demo.launch(inbrowser=True)
