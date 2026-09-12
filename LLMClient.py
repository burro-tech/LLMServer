import json
import zmq
from bs4 import BeautifulSoup
import html2text

# from HtmlParser import html_to_markdown

# from LLMServer import SOCKET_PORT
SOCKET_PORT = 1111


def html_to_markdown(html_content):
    """
    将HTML文本转换为Markdown格式
    :param html_content: 待转换的HTML字符串（支持多行、复杂标签）
    :return: 格式化后的Markdown字符串
    """
    # 解析HTML，使用html.parser避免额外依赖
    soup = BeautifulSoup(html_content, "html.parser")

    # ========== 新增：移除class='code-info-button-text'的所有元素 ==========
    # 找到所有class为code-info-button-text的元素并移除
    for unwanted_elem in soup.find_all(class_='md-code-block-banner-wrap'):
        unwanted_elem.decompose()  # 从DOM树中彻底删除该元素
    clean_html_content = str(soup)
    # 创建HTML转Markdown的转换器实例
    converter = html2text.HTML2Text()

    # 核心参数配置（根据需求调整）
    converter.ignore_links = False  # 不忽略<a>链接标签（保留Markdown链接语法）
    converter.ignore_images = False  # 不忽略<img>图片标签（保留Markdown图片语法）
    converter.ignore_emphasis = False  # 不忽略<b>/<i>等强调标签（保留粗体/斜体）
    converter.body_width = 0  # 取消行宽限制（避免Markdown文本自动换行）
    converter.links_each_paragraph = True  # 链接按段落独立展示，提升可读性
    converter.skip_internal_links = False  # 不跳过内部链接（如<a href="#top">）

    # 执行转换
    markdown_content = converter.handle(clean_html_content)

    # 可选：清理多余的空行（优化格式）
    markdown_content = "\n".join([line.strip() for line in markdown_content.split("\n") if line.strip()])

    return markdown_content


def create_request(prompt, deepthink=True, connect_internet=False, cmd=''):
    return json.dumps({'prompt': prompt,'deepthink':deepthink, 'connect_internet':connect_internet, 'cmd':cmd})


class LLMClient:
    def __init__(self, port = SOCKET_PORT):
        # port = 7777
        self.socket = zmq.Context().socket(zmq.REQ)
        self.socket.connect(f"tcp://localhost:{port}")

    def send(self, prompt, deepthink=True, connect_internet=False, cmd=''):
        request_json = create_request(prompt, deepthink=deepthink, connect_internet=connect_internet, cmd=cmd)
        self.socket.send_json(request_json)
        response = self.socket.recv_json()
        return response


#Compatible API with openai
class openai:
    class OpenAI(LLMClient):
        def __init__(self, base_url, api_key):
            super().__init__()

        @property
        def chat(self):
            return self

        @property
        def completions(self):
            return self

        def __create(self, model, messages, temperature=None, stream=None, max_tokens=0):
            contents = ''
            for message in messages:
                contents += message['content']
            html_response = json.loads(self.send(contents))['response']
            # soup = BeautifulSoup(html_response, 'html.parser')
            # text_response = soup.get_text()
            text_response = html_to_markdown(html_response)
            compatible_response = {"id": "cmpl-1305b94c570f447fbde3180560736287", "object": "chat.completion",
                                   "created": 1698999575, "model": "kimi-k2-turbo-preview",
                                   "choices": [{"index": 0, "message": {"role": "assistant", "content": text_response},
                                                "finish_reason": 'stop'}]}
            return compatible_response

        def create(self, model, messages, temperature=None, stream=None, max_tokens=0):
            return self.__create(model, messages, temperature, stream, max_tokens)


    class AsyncOpenAI(OpenAI):
        async def create(self, model, messages, temperature=None, stream=None, max_tokens=0):
            return super().__create(model, messages, temperature, stream, max_tokens)


