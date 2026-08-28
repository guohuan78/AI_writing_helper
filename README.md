# AI写作外挂 · 公众号推文创作台

[![Powered by OrcaRouter](https://img.shields.io/badge/Powered_by-OrcaRouter-2563eb)](https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e)

面向公众号作者的推文创作工具：从选题到成稿的一条生产线，在网页里完成选题、标题、大纲、逐段成稿和摘要，导出带 YAML front matter 的 Markdown，可直接交给 [wechat-publisher](https://github.com/guohuan78/wechat-publisher) 自动排版、存草稿、审批、发表。

## 创作流程

1. **选题**：输入主题，一次生成 6 个切入角度，每个配一句钩子；已用过的角度会自动避开。
2. **标题**：按悬念式/数字式/观点式/反差式生成 8 个候选，单选定稿。
3. **大纲**：生成段落级大纲，可直接编辑，成稿按修改后的大纲进行。
4. **成稿**：按大纲逐段流式生成，边写边出字；语料库有存货时自动注入文风参考。
5. **润色重写**：全文或选段按改写强度（1-5 档）生成 3 个版本并排对比，选一版替换正文。
6. **摘要与封面**：按公众号摘要栏 120 字上限生成摘要，附 3 条封面图创意。
7. **导出**：落盘 `导出目录/日期-标题.md`，front matter 含 `title`/`author`/`cover`，文章自动进入语料库。
8. **预览与送审**：调用 wechat-publisher 预览公众号排版、存草稿送审、回显审批状态。

## 语料库与文风

`corpus.db`（SQLite，本地文件）存两类数据：已发表文章与选题历史。成稿时按字符 bigram 相关度检索最相关的两篇，以「文风参考（只模仿语气与节奏，不引用内容）」注入正文提示词，让文字更像你写的；再次生成选题时，同一主题下已用过的角度会注入「避开」清单。「语料库」折叠区可手动导入过往文章，导出 Markdown 的文章自动入库。

## 模型服务：OrcaRouter

Powered by [OrcaRouter](https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e)——本软件由 OrcaRouter 提供模型服务，通过官方 OpenAI SDK 指向 OrcaRouter 的 OpenAI 兼容接口调用大模型：一个 API 接入所有主流模型，内置自适应路由与故障转移，支持自带密钥（BYOK），按官方价格计费、零加价。通过推荐链接注册，本项目维护者将获得所推荐工作区后续消费额 5% 的返利。

项目内的接入代码见 `orcarouter_provider.py`，核心写法：

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.orcarouter.ai/v1",
    api_key="sk-orca-YOUR_KEY",  # Get key at https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e
)
```

## 运行

`python` 3.10 及以上。

```
pip install -r requirements.txt
python article_studio.py
```

浏览器自动打开创作台。首次使用：

1. 点击[推荐链接](https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e)注册 OrcaRouter，在[控制台](https://www.orcarouter.ai/console)创建 API Key（`sk-orca-` 开头）。
2. 展开页面顶部「设置」，填入 API Key，可按需修改模型（默认 `orcarouter/auto`）与作者名，点击「保存设置」。设置明文保存在本目录 `config.json`，谨防泄露。

Prompt 模板外置在 `prompts/` 目录（选题/标题/大纲/正文/摘要各一个 JSON），改模板即可调整各环节的生成风格。

## 对接 wechat-publisher

「设置」里填 wechat-publisher 项目路径（本机存在 `D:\coding\wechat-publisher` 时自动识别），第 6 步即可在创作台内完成串联：

1. **排版预览**：调用 wechat-publisher 的 `render`，页面内直接查看公众号排版效果。
2. **送审**：调用 `draft`，把导出的 Markdown 存为公众号草稿，页面回显记录 ID；内容未变化时自动复用已有记录。
3. **刷新发表状态**：调用 `list`，回显审批状态机中的全部记录（pending → approved → published）。

审批与发表按 wechat-publisher 的人工闸门在命令行执行：

```
node src/cli.js approve <id>   # 公众号后台草稿箱核对排版后审批
node src/cli.js publish <id>   # 发表，管理员扫码确认
```

## 测试

```
pip install pytest
python -m pytest tests/
```

测试覆盖导出契约、排版预览、送审输出解析与配置错误路径，以及语料库的入库/检索/选题历史与全部 prompt 模板的占位符契约；其中 `test_draft_and_status_real` 会真实调用 wechat-publisher 存一条标题带【测试】标记的草稿并停留在待审批状态，等待人工在后台核对处理（内容未变化时自动走复用分支，不会重复建草稿）。

## 桌面版（初版）

仓库同时保留初版的通用写作桌面工具：入口 `AI_writing_helper.py`，基于 tkinter（依赖 `qgui==0.6.3`），运行方式见仓库历史文档。

## 开发团队

`1.x` 版本为 郭睆 一人

`2.x` 版本 徐继尧 加入
