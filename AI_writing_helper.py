# -*- encoding:utf-8 -*-
import datetime
import json
import os
import time
import webbrowser
from qgui.manager import QStyle
from qgui.notebook_tools import InputBox, HorizontalToolsCombine, CheckButton, BaseButton, RadioButton
from orcarouter_provider import chat, OrcaRouterError, DEFAULT_MODEL
from qgui import CreateQGUI, MessageBox

# 创建主界面
q_gui = CreateQGUI(title="AI写作外挂",
                   tab_names=["Key", "续写", "病句", "作文", "摘要", "古诗", "对联", "改写", "词语", "押韵", "组词"],
                   style=QStyle.lumen)
q_gui.set_navigation_about(author="郭睆（huàn）\n        徐继尧",
                           version="2.2.0",
                           github_url="https://github.com/guohuan78",
                           bilibili_url="https://space.bilibili.com/518491096?spm_id_from=333.1007.0.0",
                           blog_url="https://guohuan78.github.io/"
                           )
q_gui.set_navigation_info(title="使用方式", info="根据提示填写文本框\n标签页可选择功能\n点并始执行等待结果生成")
q_gui.set_navigation_info(title="注意事项", info='''
1.务必先填写key再选择功能
2.有时调用需要较长时间，开始执行按钮变灰表示正在调用，请耐心等待。
3.QQ交流群：344389127
4.模型调用会消耗 OrcaRouter 账户余额，请留意用量与额度。
5.软件完全免费，欢迎赞赏。
''')


# 历史记录
def history_write(input_text: str, action: str, output_text: str):
    file = open("history.txt", "a", encoding='utf-8')
    file.write(
        datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S") + ' 操作："' + action + '" 输入："' + input_text + '" 输出："' + output_text + '"\n\n')


# 清屏
def clear_desktop(event):
    q_gui.notebook.text_area.configure(state="normal")
    q_gui.notebook.text_area.delete("1.0", "end")
    q_gui.notebook.text_area.configure(state="disable")
    print("控制台连接成功\n")


# 调用api与异常处理
def run(payload, args, have_num, action):
    history_save(args=args)
    global synonym, antonym, interpretation, words_error
    words_error = False
    if action == "近义词" or action == "反义词" or action == "释义":
        if not args["词语输入框"].get():
            print("请填写输入内容\n")
            words_error = True
            return
        if not args["词语输入框"].get().find("%") == -1:
            print('输入内容不合法，请检查文本是否带有"%"\n')
            words_error = True
            return
    else:
        if not args[action + "输入框"].get():
            print("请填写输入内容\n")
            return
        if not args[action + "输入框"].get().find("%") == -1:
            print('输入内容不合法，请检查文本是否带有"%"\n')
            return
    if have_num:
        if not args[action + "输入框最多字数"].get().isdigit():
            print("请检查最多字数\n")
            return
        if not args[action + "输入框最少字数"].get().isdigit():
            print("请检查最少字数\n")
            return
        if int(args[action + "输入框最少字数"].get()) < 1:
            print("最少字数必须大于等于1\n")
            return
        if int(args[action + "输入框最多字数"].get()) > 1000:
            print("最多字数必须小于等于1000\n")
            return
        if int(args[action + "输入框最多字数"].get()) < 1:
            print("最多字数必须小于等于1000\n")
            return
        if int(args[action + "输入框最多字数"].get()) < int(args[action + "输入框最少字数"].get()):
            print("最少字数必须小于等于最大生成长度\n")
            return
    prompt = payload["text"]
    if have_num:
        prompt = prompt + '\n字数要求：不少于' + args[action + "输入框最少字数"].get() + '字。'
    max_tokens = int(int(payload["seq_len"]) * 1.5) + 16
    api_key = args["API Key"].get()
    model = args["模型"].get().strip() or DEFAULT_MODEL
    try:
        result = chat(prompt, api_key, model=model, max_tokens=max_tokens,
                      temperature=payload.get("temperature", 0.7))
    except OrcaRouterError as e:
        if e.code == "rate_limit":
            time.sleep(1)
            try:
                result = chat(prompt, api_key, model=model, max_tokens=max_tokens,
                              temperature=payload.get("temperature", 0.7))
            except OrcaRouterError as retry_error:
                print("调用过于频繁，请稍后重试，错误信息：" + str(retry_error) + "\n")
                words_error = True
                return
        elif e.code == "bad_key" or e.code == "no_key":
            print("请检查key\n")
            words_error = True
            return
        else:
            print("未知错误，请联系开发者，错误信息：" + str(e) + "\n")
            words_error = True
            return
    else:
        if action == "近义词" or action == "反义词" or action == "释义":
            if action == "近义词":
                synonym = result.strip()
                print("词语 " + action + " " + synonym + "\n")
            if action == "反义词":
                antonym = result.strip()
                print("词语 " + action + " " + antonym + "\n")
            if action == "释义":
                interpretation = result.strip()
                print("词语 " + action + " " + interpretation + "\n")
        else:
            print(action + " " + result + "\n")
            history_write(input_text=args[action + "输入框"].get(), output_text=result, action=action)


# 运行按钮对应函数
# 续写
def click_run_custom(args: dict):
    payload = {
        "text": args["续写输入框"].get() + '\n\n（接着上面的内容继续写，不要重复原文。）',
        "seq_len": args["续写输入框最多字数"].get(),
        "temperature": 0.8
    }
    run(payload, args, True, "续写")


# 病句
def click_run_correction(args: dict):
    payload = {
        "text": '改正下面文本中的错误：\"' + args["病句输入框"].get() + '\"',
        "seq_len": 64,
        "temperature": 0.2
    }
    run(payload, args, False, "病句")


# 作文
def click_run_zuowen(args: dict):
    payload = {
        "text": '作文题目：' + args["作文输入框"].get() + '\n体裁：' + args["RadioButton"].get() + '\n内容：',
        "seq_len": args["作文输入框最多字数"].get(),
        "temperature": 0.8
    }
    run(payload, args, True, "作文")


# 摘要
def click_run_summarization(args: dict):
    payload = {
        "text": '请给下面这段话写一句摘要：“' + args["摘要输入框"].get() + '”',
        "seq_len": 512,
        "temperature": 0.2
    }
    run(payload, args, False, "摘要")


# 古诗
def click_run_poetry(args: dict):
    payload = {
        "text": '古诗续写：' + args["古诗输入框"].get(),
        "seq_len": args["古诗输入框最多字数"].get(),
        "temperature": 0.8
    }
    run(payload, args, True, "古诗")


# 对联
def click_run_couplet(args: dict):
    payload = {
        "text": '上联:' + args["对联输入框"].get() + ' 下联:',
        "seq_len": 32,
        "temperature": 0.8
    }
    run(payload, args, False, "对联")


# 改写
def click_run_rewrite(args: dict):
    payload = {
        "text": '“' + args["改写输入框"].get() + '”换种表达，意思不变：',
        "seq_len": 64,
        "temperature": 0.2
    }
    run(payload, args, False, "改写")


# 词语
def click_run_words(args: dict):
    global word
    if args["CheckButton-近义词"].get() == '1':
        payload = {
            "text": '“' + args["词语输入框"].get() + '”的近义词是：',
            "seq_len": 16,
            "temperature": 0.2
        }
        run(payload, args, False, "近义词")
        if words_error:
            return
    if args["CheckButton-反义词"].get() == '1':
        payload = {
            "text": '“' + args["词语输入框"].get() + '”的反义词是：',
            "seq_len": 16,
            "temperature": 0.2
        }
        run(payload, args, False, "反义词")
        if words_error:
            return
    if args["CheckButton-释义"].get() == '1':
        payload = {
            "text": '“' + args["词语输入框"].get() + '”的释义是：',
            "seq_len": 32,
            "temperature": 0.2
        }
        run(payload, args, False, "释义")
        if words_error:
            return
    word = ""
    if args["CheckButton-近义词"].get() == '0' and args["CheckButton-反义词"].get() == '0' and args[
        "CheckButton-释义"].get() == '0':
        print("您没有选中任何一个需要的功能，请点击需要的功能前的方框。\n")
    else:
        if args["CheckButton-近义词"].get() == '1':
            word = '近义词："' + synonym + '" '
        if args["CheckButton-反义词"].get() == '1':
            word = word + '反义词："' + antonym + '" '
        if args["CheckButton-释义"].get() == '1':
            word = word + '释义："' + interpretation + '" '
        history_write(input_text=args["词语输入框"].get(), output_text=word, action="词语")

# 押韵
def click_run_rhyme(args: dict):
    payload = {
        "text": '问题：与“' + args["押韵输入框"].get() + '”字押韵的字有哪些？回答：很多，比如：',
        "seq_len": 16,
        "temperature": 0.2
    }
    run(payload, args, False, "押韵")


# 组词
def click_run_rhyme_words(args: dict):
    payload = {
        "text": '问题：含“' + args["组词输入框"].get() + '”字的词语有哪些？回答：',
        "seq_len": 32,
        "temperature": 0.2
    }
    run(payload, args, False, "组词")


def orca_callback(event):
    webbrowser.open_new("https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e")


def wechatpay_callback(event):
    q_gui.print_image("images/wechatpay.png")


def key_save(args: dict):
    history_save(args)
    print("保存成功！\n")


def history_save(args: dict):
    history = {
        "API Key": args["API Key"].get(),
        "模型": args["模型"].get(),
        "continue_text": args["续写输入框"].get(),
        "continue_text_max": args["续写输入框最多字数"].get(),
        "continue_text_min": args["续写输入框最少字数"].get(),
        "grammatically_wrong_sentence_text": args["病句输入框"].get(),
        "composition_text": args["作文输入框"].get(),
        "composition_type": args["RadioButton"].get(),
        "composition_text_max": args["作文输入框最多字数"].get(),
        "composition_text_min": args["作文输入框最少字数"].get(),
        "summary_text": args["摘要输入框"].get(),
        "poetry_text": args["古诗输入框"].get(),
        "poetry_text_max": args["古诗输入框最多字数"].get(),
        "poetry_text_min": args["古诗输入框最少字数"].get(),
        "couplet_text": args["对联输入框"].get(),
        "rewrite_text": args["改写输入框"].get(),
        "word_text": args["词语输入框"].get(),
        "word_text_synonym": args["CheckButton-近义词"].get(),
        "word_text_antonym": args["CheckButton-反义词"].get(),
        "word_text_paraphrase": args["CheckButton-释义"].get(),
        "rhyme_text": args["押韵输入框"].get(),
        "group_words_text": args["组词输入框"].get(),
        "version": "2.2.0"
    }
    history = json.dumps(history)
    f = open('history.json', 'w')
    f.write(history)
    f.close()


def get_history(key, text):
    if os.path.exists('history.json'):
        f = open('history.json', 'r')
        content = f.read()
        history = json.loads(content)
        return history[key]
    else:
        return text


def get_API_Key():
    if os.path.exists('history.json'):
        f = open('history.json', 'r')
        content = f.read()
        history = json.loads(content)
        return history['API Key']
    else:
        MessageBox.info('''
本软件通过 OrcaRouter 调用大模型，需要填写 API Key 方可使用。
将自动为您打开 OrcaRouter 网站，注册并登录后，在控制台创建 API Key（sk-orca- 开头）。
复制 API Key，填写到软件中方可使用。
保存 key 以后将不会出现此弹窗。
''')
        webbrowser.open_new("https://www.orcarouter.ai/ref/ref_b183ab1e01f1ab2c8e0e")
        return None


def get_Model():
    if os.path.exists('history.json'):
        f = open('history.json', 'r')
        content = f.read()
        history = json.loads(content)
        return history.get('模型', DEFAULT_MODEL)
    else:
        return DEFAULT_MODEL


def start_history(event):
    try:
        os.startfile("history.txt")
    except Exception:
        print("找不到历史记录，请运行后重试，如仍有错误可联系作者")


def print_QQ(event):
    print("QQ交流群：344389127\n")


# 创建控制台元素
# Key 获取 API Key
clear_desktop("")
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="API Key", label_info="API Key", default=get_API_Key()),
     BaseButton(bind_func=orca_callback, text="获取 OrcaRouter Key")],
    text="点击右方按钮进入 OrcaRouter，注册后在控制台创建 API Key（sk-orca- 开头），填入左侧输入框。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="模型", label_info="模型", default=get_Model()),
     BaseButton(bind_func=key_save, text="保存key")],
    text="模型默认 orcarouter/auto（自动选择），也可填写 qwen/qwen3-max、z-ai/glm-5、kimi/kimi-k2.5 等。点击右方按钮可以保存设置，明文存储在同级目录 history.json中，谨防泄露。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [BaseButton(bind_func=start_history, text="查看历史记录"),
     BaseButton(bind_func=wechatpay_callback, text="赞赏作者"),
     BaseButton(bind_func=print_QQ, text="QQ群"),
     BaseButton(bind_func=clear_desktop, text="清屏")]))
# 续写
q_gui.add_notebook_tool(
    InputBox(name="续写输入框", label_info="请输入文本", default=get_history("continue_text", "烟把黑夜烫了一个洞，"), tab_index=1))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [],
    tab_index=1,
    text="字数输入为整数，介于1到1000之间，字数越多所需时间越久，同时可能出现重复内容。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="续写输入框最多字数", label_info="最多字数", default=get_history("continue_text_max", "128"), tab_index=1),
     BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=1))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="续写输入框最少字数", label_info="最少字数", default=get_history("continue_text_min", "1")),
     BaseButton(bind_func=click_run_custom)],
    tab_index=1))
# 病句
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="病句输入框", label_info="请输入病句",
              default=get_history("grammatically_wrong_sentence_text", "我们提倡节约用水,反对豪无节制地用水,浪废水资源地行为。")),
     BaseButton(bind_func=click_run_correction)],
    tab_index=2,
    text="框内输入病句，点击开始执行，控制台会返回改错后的句子。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=2))
# 作文
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="作文输入框", label_info="请输入题目", default=get_history("composition_text", "理想"))],
    tab_index=3,
    text="框内输入作文的标题，点击开始执行，控制台会返回生成的作文。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [RadioButton(["记叙文", "议论文", "说明文", "应用文", "读后感", "日记"])],
    tab_index=3,
    text="请选择所需的作文体裁。"))

q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="作文输入框最多字数", label_info="最多字数", default=get_history("composition_text_max", "520")),
     BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=3,
    text="字数输入为整数，介于1到1000之间，字数越多所需时间越久。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="作文输入框最少字数", label_info="最少字数", default=get_history("composition_text_min", "128")),
     BaseButton(bind_func=click_run_zuowen)],
    tab_index=3))
# 摘要
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="摘要输入框", label_info="请输入文本",
              default=get_history("summary_text", '外媒7月18日报道，阿联酋政府当日证实该国将建设首个核电站，以应对不断上涨的用电需求。'
                                                  '分析称阿联酋作为世界第三大石油出口国，更愿意将该能源用于出口，而非发电。'
                                                  '首座核反应堆预计在2017年运行。cntv李婉然编译报道')),
     BaseButton(bind_func=click_run_summarization)],
    tab_index=4,
    text="框内输入需要生成摘要的文本，点击开始执行，控制台会返回生成的摘要。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=4))
# 古诗
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="古诗输入框", label_info="请输入文本", default=get_history("poetry_text", "小小黄花尔许愁，"))],
    tab_index=5,
    text="框内输入古诗的开头，点击开始执行，控制台会返回生成的古诗续写内容。若生成结果不理想可尝试在文本后加逗号。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [],
    tab_index=5,
    text="字数输入为整数，介于1到1000之间，字数越多所需时间越久，同时可能出现非古诗正文内容。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="古诗输入框最多字数", label_info="最多字数", default=get_history("poetry_text_max", "64")),
     BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=5))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="古诗输入框最少字数", label_info="最少字数", default=get_history("poetry_text_min", "1")),
     BaseButton(bind_func=click_run_poetry)],
    tab_index=5))
# 对联
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="对联输入框", label_info="请输入上联", default=get_history("couplet_text", "风云三尺剑")),
     BaseButton(bind_func=click_run_couplet)],
    tab_index=6,
    text="框内输入上联，点击开始执行，控制台会返回生成的下联。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=6))
# 改写
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="改写输入框", label_info="请输入文本", default=get_history("rewrite_text", "蓝色性格的人如何还击别人？")),
     BaseButton(bind_func=click_run_rewrite)],
    tab_index=7,
    text="框内输入需要改写的文本，点击开始执行，控制台会返回生成的意思相近的改写结果，论文狗降重利器！"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=7))
# 词语
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="词语输入框", label_info="请输入词语", default=get_history("word_text", "还击")),
     BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=8))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [CheckButton(options=[("近义词", int(get_history("word_text_synonym", 1))),
                          ("反义词", int(get_history("word_text_antonym", 1))),
                          ("释义", int(get_history("word_text_paraphrase", 1)))]),
     BaseButton(bind_func=click_run_words)],
    tab_index=8,
    text="需要该词语的 近义词/反义词/释义 在相应的框前打对勾"))
# 押韵
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="押韵输入框", label_info="请输入一个字", default=get_history("rhyme_text", "花")),
     BaseButton(bind_func=click_run_rhyme)],
    tab_index=9,
    text="框内输入需要押韵的字，点击开始执行，控制台会返回与这个字押韵的字。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=9))
# 组词
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="组词输入框", label_info="请输入一个字", default=get_history("group_words_text", "华")),
     BaseButton(bind_func=click_run_rhyme_words)],
    tab_index=10,
    text="框内输入需要组词的字，点击开始执行，控制台会返回含这个字的词语"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [BaseButton(bind_func=clear_desktop, text="清屏")],
    tab_index=10))
q_gui.run()
