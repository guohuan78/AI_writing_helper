# -*- encoding:utf-8 -*- 
import json
import webbrowser
import os

from qgui import CreateQGUI,MessageBox

from qgui.notebook_tools import InputBox, BaseButton, HorizontalToolsCombine,CheckButton,BaseButton,RadioButton
from qgui.manager import QStyle

import wenxin_api
from wenxin_api.tasks.free_qa import FreeQA
from wenxin_api.tasks.text_generation import TextGeneration
from wenxin_api.tasks.composition import Composition
from wenxin_api.tasks.summarization import Summarization
from wenxin_api.tasks.couplet import Couplet

# 创建主界面
q_gui = CreateQGUI(title="AI写作外挂",
                   tab_names=["Key","续写","病句","作文","摘要","古诗","对联","改写","词语","押韵","组词"],
                   style=QStyle.lumen)

q_gui.set_navigation_about(author="郭睆（huàn）",
                           version="1.3.2",
                           github_url="https://github.com/guohuan78",
                           bilibili_url="https://space.bilibili.com/518491096?spm_id_from=333.1007.0.0",
                           blog_url="https://guohuan78.github.io/"
                        )

q_gui.set_navigation_info(title="使用方式", info="右侧文本框中填写\n标签页可选择功能")

q_gui.set_navigation_info(title="注意事项", info='''
1.先填写Key才可使用
2.有时请求返回需要较长时间，请耐心等待
3.如遇错误，先检查是否正确填写Key，再次请求可能成功，仍错误可联系作者
4.每个账号的Key单日调用上限为200次，总调用上限为2000次，此限制为所调用的文心大模型本身的限制（它也太扣了点）作者也无能为力。
5.此软件免费，欢迎赞赏
''')

# 运行按钮对应函数
def click_run_custom(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": args["续写输入框"].get(),
    "seq_len": args["续写输入框最多字数"].get(),
    "topp": 0.8,
    "penalty_score": 1.2,
    "min_dec_len": args["续写输入框最少字数"].get(),
    "min_dec_penalty_text": "",
    "is_unidirectional": 1,
    "task_prompt": "SENT",
    "mask_type": "sentence"
    }
    rst = TextGeneration.create(**payload)
    print(rst["result"])

def click_run_correction(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": '改正下面文本中的错误：\"' + args["病句输入框"].get() + '\"',
    "seq_len": 64,
    "topp": 0.0,
    "penalty_score": 1.2,
    "min_dec_len": 1,
    "min_dec_penalty_text": "",
    "is_unidirectional": 0,
    "task_prompt": "Correction",
    "mask_type": "sentence"
    }
    rst = FreeQA.create(**payload)
    print(rst["result"])

def click_run_zuowen(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": '作文题目：' + args["作文输入框"].get() + '\n体裁：' + args["RadioButton"].get() + '\n内容：',
    "seq_len": args["作文输入框最多字数"].get(),
    "topp": 0.8,
    "penalty_score": 1.2,
    "min_dec_len": args["作文输入框最少字数"].get(),
    "min_dec_penalty_text": "[gEND]",
    "is_unidirectional": 0,
    "task_prompt": "zuowen",
    "mask_type": "paragraph"
    }
    rst = Composition.create(**payload)
    print(rst["result"])

def click_run_summarization(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": '请给下面这段话写一句摘要：“' + args["摘要输入框"].get() + '”',
    "seq_len": 512,
    "topp": 0.0,
    "penalty_score": 1.0,
    "min_dec_len": 4,
    "min_dec_penalty_text": "",
    "is_unidirectional": 0,
    "task_prompt": "Text2Annotation",
    "mask_type": "sentence"
    }
    rst = Summarization.create(**payload)
    print(rst["result"])


def click_run_poetry(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": '古诗续写：' + args["古诗输入框"].get(),
    "seq_len": args["古诗输入框最多字数"].get(),
    "topp": 0.8,
    "penalty_score": 1.0,
    "min_dec_len": args["古诗输入框最少字数"].get(),
    "min_dec_penalty_text": "",
    "is_unidirectional": 1,
    "task_prompt": "SENT",
    "mask_type": "sentence"
    }
    rst = TextGeneration.create(**payload)
    print(rst["result"])

def click_run_couplet(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": '上联:' + args["对联输入框"].get() + ' 下联:',
    "seq_len": 32,
    "topp": 0.8,
    "penalty_score": 1.0,
    "min_dec_len": 1,
    "min_dec_penalty_text": "",
    "is_unidirectional": 1,
    "task_prompt": "couplet",
    "mask_type": "sentence"
    }
    rst = Couplet.create(**payload)
    print(rst["result"])

def click_run_rewrite(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": '“' + args["改写输入框"].get() + '”换种表达，意思不变：',
    "seq_len": 64,
    "topp": 0.0,
    "penalty_score": 1.0,
    "min_dec_len": 1,
    "min_dec_penalty_text": "",
    "is_unidirectional": 1,
    "task_prompt": "Paraphrasing",
    "mask_type": "sentence"
    }
    rst = FreeQA.create(**payload)
    print(rst["result"])

def click_run_words(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    synonym = ''
    antonym = ''
    interpretation = ''
    if args["CheckButton-近义词"].get() == '1':
        print("近义词 ",end = '')
        payload={
        "text": '“' + args["词语输入框"].get() + '”的近义词是：',
        "seq_len": 16,
        "topp": 0.0,
        "penalty_score": 1.0,
        "min_dec_len": 1,
        "min_dec_penalty_text": "",
        "is_unidirectional": 1,
        "task_prompt": "QA_Closed_book",
        "mask_type": "word"
        }
        rst = FreeQA.create(**payload)
        print(rst["result"])
        synonym = rst["result"]
    if args["CheckButton-反义词"].get() == '1':
        print("反义词 ",end = '')
        payload={
        "text": '“' + args["词语输入框"].get() + '”的反义词是：',
        "seq_len": 16,
        "topp": 0.0,
        "penalty_score": 1.0,
        "min_dec_len": 1,
        "min_dec_penalty_text": "",
        "is_unidirectional": 1,
        "task_prompt": "QA_Closed_book",
        "mask_type": "word"
        }
        rst = FreeQA.create(**payload)
        print(rst["result"])
        antonym = rst["result"]
    if args["CheckButton-释义"].get() == '1':
        print("释义 ",end = '')
        payload={
        "text": '“' + args["词语输入框"].get() + '”的释义是：',
        "seq_len": 32,
        "topp": 0.0,
        "penalty_score": 1.0,
        "min_dec_len": 1,
        "min_dec_penalty_text": "",
        "is_unidirectional": 1,
        "task_prompt": "QA_Closed_book",
        "mask_type": "paragraph"
        }
        rst = FreeQA.create(**payload)
        print(rst["result"])
        interpretation = rst["result"]
    if args["CheckButton-近义词"].get() == '1':
        print("\n近义词：" + synonym)
    if args["CheckButton-反义词"].get() == '1':
        print("\n反义词：" + antonym)
    if args["CheckButton-释义"].get() == '1':
        print("\n释义：" + interpretation)
    if args["CheckButton-近义词"].get() == '0' and args["CheckButton-反义词"].get() == '0' and args["CheckButton-释义"].get() == '0':
        print("您没有选中任何一个需要的功能，请点击需要的功能前的方框。")

def click_run_rhyme(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": '问题：与“' + args["押韵输入框"].get() + '”字押韵的字有哪些？回答：很多，比如：',
    "seq_len": 16,
    "topp": 0.0,
    "penalty_score": 1.2,
    "min_dec_len": 1,
    "min_dec_penalty_text": "",
    "is_unidirectional": 0,
    "task_prompt": "QA_Closed_book",
    "mask_type": "word"
    }
    rst = FreeQA.create(**payload)
    print(rst["result"])

def click_run_rhyme_words(args: dict):
    wenxin_api.ak = args["API Key"].get()
    wenxin_api.sk = args["Secret Key"].get()
    payload={
    "text": '问题：含“' + args["组词输入框"].get() + '”字的词语有哪些？回答：',
    "seq_len": 32,
    "topp": 0.0,
    "penalty_score": 1.2,
    "min_dec_len": 1,
    "min_dec_penalty_text": "",
    "is_unidirectional": 0,
    "task_prompt": "QA_Closed_book",
    "mask_type": "word"
    }
    rst = FreeQA.create(**payload)
    print(rst["result"])

def yanggu_callback(event):
    webbrowser.open_new("https://wenxin.baidu.com/moduleApi/ernie3")

def wechatpay_callback(event):
    q_gui.print_image("images/wechatpay.png")

def key_save(args: dict):
    key = {
        "API Key": args["API Key"].get(),
        "Secret Key": args["Secret Key"].get()
    }
    key = json.dumps(key)
    f = open('key.json', 'w')
    f.write(key)
    f.close()
    print("保存成功！")

def get_API_Key():
    if os.path.exists('key.json'):
        f = open('key.json', 'r')
        content = f.read()
        key = json.loads(content)
        return key['API Key']
    else:
        MessageBox.info('''
本软件依赖文心大模型，需要申请 key 并填写方可使用，申请免费。
将自动为您打开申请网站，请点击网站右上方“登录”，登录百度账号。
鼠标移动到右上角头像，点击“查看AK/SK",点击“创建API key”。
复制 API Key 和 Secret Key，填写到软件中方可使用。
保存 key 以后将不会出现此弹窗。
''')
        webbrowser.open_new("https://wenxin.baidu.com/moduleApi/ernie3")
        return None

def get_Secret_Key():
    if os.path.exists('key.json'):
        f = open('key.json', 'r')
        content = f.read()
        key = json.loads(content)
        return key['Secret Key']
    else:
        return None

# 创建控制台元素
# Key 获取 API Key 和 Secret Key
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="API Key", label_info="API Key", default=get_API_Key()),
    BaseButton(bind_func=yanggu_callback, text="文心大模型")],
    text="点击右方按钮进入文心大模型，网站右上方登录百度账号，点击“查看AK/SK”获取API Key Secret Key。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="Secret Key", label_info="Secret Key", default=get_Secret_Key()),
    BaseButton(bind_func=key_save, text="保存key")],
    text="为避免每次打开软件都需要重复输入key，点击右方按钮可以保存key，明文存储在同级目录 key.json，谨防泄露。"))
q_gui.add_notebook_tool(BaseButton(bind_func=wechatpay_callback, text="赞赏作者"))

# 续写
q_gui.add_notebook_tool(InputBox(name="续写输入框", label_info="请输入文本", default="烟把黑夜烫了一个洞，",tab_index = 1))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [],
    tab_index=1,
    text="字数输入为整数，介于1到1000之间，字数越多所需时间越久，同时可能出现重复内容。"))
q_gui.add_notebook_tool(InputBox(name="续写输入框最多字数", label_info="最多字数", default="128",tab_index = 1))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="续写输入框最少字数", label_info="最少字数", default="1"),
     BaseButton(bind_func=click_run_custom)],
     tab_index = 1))
# 病句
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="病句输入框", label_info="请输入病句", default="我们提倡节约用水,反对豪无节制地用水,浪废水资源地行为。"),
    BaseButton(bind_func=click_run_correction)],
    tab_index = 2,
    text = "框内输入病句，点击开始执行，控制台会返回改错后的句子。"))
# 作文
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="作文输入框", label_info="请输入题目", default="理想")],
    tab_index = 3,
    text = "框内输入作文的标题，点击开始执行，控制台会返回生成的作文。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [RadioButton(["记叙文", "议论文", "说明文", "应用文", "读后感","日记"])],
    tab_index = 3,
    text = "请选择所需的作文体裁。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="作文输入框最多字数", label_info="最多字数", default="512")],
    tab_index=3,
    text="字数输入为整数，介于1到1000之间，字数越多所需时间越久。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="作文输入框最少字数", label_info="最少字数", default="128"),
     BaseButton(bind_func=click_run_zuowen)],
     tab_index = 3))
# 摘要
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="摘要输入框", label_info="请输入文本", default='外媒7月18日报道，阿联酋政府当日证实该国将建设首个核电站，以应对不断上涨的用电需求。分析称阿联酋作为世界第三大石油出口国，更愿意将该能源用于出口，而非发电。首座核反应堆预计在2017年运行。cntv李婉然编译报道'),
    BaseButton(bind_func=click_run_summarization)],
    tab_index = 4,
    text = "框内输入需要生成摘要的文本，点击开始执行，控制台会返回生成的摘要。"))
# 古诗
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="古诗输入框", label_info="请输入文本", default="小小黄花尔许愁，")],
    tab_index = 5,
    text = "框内输入古诗的开头，点击开始执行，控制台会返回生成的古诗续写内容。若生成结果不理想可尝试在文本后加逗号。"))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [],
    tab_index=5,
    text="字数输入为整数，介于1到1000之间，字数越多所需时间越久，同时可能出现非古诗正文内容。"))
q_gui.add_notebook_tool(InputBox(name="古诗输入框最多字数", label_info="最多字数", default="64",tab_index = 5))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="古诗输入框最少字数", label_info="最少字数", default="1"),
     BaseButton(bind_func=click_run_poetry)],
     tab_index = 5))
# 对联
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="对联输入框", label_info="请输入上联", default="风云三尺剑"),
    BaseButton(bind_func=click_run_couplet)],
    tab_index = 6,
    text = "框内输入上联，点击开始执行，控制台会返回生成的下联。"))
# 改写
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="改写输入框", label_info="请输入文本", default="蓝色性格的人如何还击别人？"),
    BaseButton(bind_func=click_run_rewrite)],
    tab_index = 7,
    text = "框内输入需要改写的文本，点击开始执行，控制台会返回生成的意思相近的改写结果，论文狗降重利器！"))
# 词语
q_gui.add_notebook_tool(InputBox(name="词语输入框", label_info="请输入词语", default="还击",tab_index = 8))
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [CheckButton(options=[("近义词", 1), ("反义词", 1), ("释义", 1)]),
    BaseButton(bind_func=click_run_words)],
    tab_index = 8,
    text = "需要该成语的 近义词/反义词/释义 在相应的框前打对勾"))
# 押韵
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="押韵输入框", label_info="请输入一个字", default="花"),
    BaseButton(bind_func=click_run_rhyme)],
    tab_index = 9,
    text = "框内输入需要押韵的字，点击开始执行，控制台会返回与这个字押韵的字。"))
# 组词
q_gui.add_notebook_tool(HorizontalToolsCombine(
    [InputBox(name="组词输入框", label_info="请输入一个字", default="华"),
    BaseButton(bind_func=click_run_rhyme_words)],
    tab_index = 10,
    text = "框内输入需要组词的字，点击开始执行，控制台会返回含这个字的词语"))


q_gui.run()
