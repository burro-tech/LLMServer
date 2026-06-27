import json
import sys
import time
from code import interact
from time import sleep

from selenium import webdriver
from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import io
from PIL import Image
import cv2
import numpy as np

from LLMClient import html_to_markdown

import zmq
import pyperclip
from datetime import datetime
from filelock import FileLock
LOCK_FILE = r"C:\Users\Administrator\AppData\Local\Temp\clipboard.lock"  # Windows

SOCKET_PORT = 9991
PAGE_LOAD_TIMEOUT = 60
OPERATION_TIMEOUT = 1
RESPONSE_TIMEOUT = 600
RETRY_INTERNAL = 60
chrome_driver:webdriver.chrome.webdriver.WebDriver

def init_webdriver():
    global chrome_driver
    # 配置Chrome选项（保留用户数据，避免重复登录）
    chrome_options = webdriver.ChromeOptions()

    # 初始化Chrome驱动
    chrome_driver = webdriver.Chrome(
        # service=Service(ChromeDriverManager().install()),
        service=Service(executable_path=r"C:\tools\webdriver\chromedriver_148.exe"), # C:\Users\Administrator\.cache\selenium\chromedriver\win64
        options=chrome_options
    )
    chrome_driver.implicitly_wait(10)  # 全局隐式等待
    WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT, poll_frequency=1).until(lambda driver: True)

def find_element_by_text(text, precise=True):
    es = chrome_driver.find_elements(By.XPATH, f"//*[contains(text(),{text})]")
    for e in es:
        if e.is_displayed():
            if precise and e.text == text:
                return e
            elif not precise:
                return e
    return None

def find_element_by_svg(target_svg):
    # -------------------------- 【配置区：修改这里即可】 --------------------------
    # TEMPLATE_PATH = "svg_new.png"  # 你提前截好的目标SVG模板图
    print(f'Finding {target_svg}')
    MATCH_THRESHOLD = 0.8  # 匹配特征点阈值（越大越严格，图标小设5-15即可）

    template_img = cv2.imread(target_svg, cv2.IMREAD_GRAYSCALE)
    template_height, template_width = template_img.shape[:2]

    all_svg = chrome_driver.find_elements(By.XPATH, '//*[local-name()="svg"]')
    # 存储匹配结果：(SVG元素, 匹配分数)
    match_results = []
    # 4. 遍历所有SVG，进行图像特征匹配
    for index, svg in enumerate(all_svg):
        # 跳过隐藏的SVG（避免空白图干扰）
        if not svg.is_displayed():
            continue

        try:
            # 步骤1：SVG截图 → 转成OpenCV可识别的灰度图
            png_bytes = svg.screenshot_as_png  # SVG截图字节流
            image = Image.open(io.BytesIO(png_bytes)).convert('L')  # 转灰度图
            current_img = np.array(image)

            #screenshot_as_png会导致滑动条滚动，导致看不到retry按钮
            list_e = chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list")
            chrome_driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_e)
            time.sleep(OPERATION_TIMEOUT/2)

            # ===================== 模板匹配核心（无特征点，永不报错） =====================
            # 缩放模板适配当前SVG大小
            current_height, current_width = current_img.shape[:2]
            scaled_template = cv2.resize(template_img, (current_width, current_height))

            # 计算匹配度
            result = cv2.matchTemplate(current_img, scaled_template, cv2.TM_CCOEFF_NORMED)
            similarity = cv2.minMaxLoc(result)[1]  # 相似度 0~1

            match_results.append((svg, similarity))
            print(f"SVG {index + 1} → 匹配相似度：{round(similarity, 2)}")

        except Exception as e:
            print(f"SVG {index + 1} 处理失败：{str(e)}")

    # 5. 找到匹配度最高的SVG
    target_svg = None
    if match_results:
        # 按匹配分数降序排序，取第一名
        match_results.sort(key=lambda x: x[1], reverse=True)
        best_svg, best_score = match_results[0]

        if best_score >= MATCH_THRESHOLD:
            print(f"\n✅ 找到目标SVG！最佳匹配分数：{best_score}")
            target_svg = best_svg
        else:
            print(f"\n❌ 匹配度不足（最低阈值：{MATCH_THRESHOLD}），未找到目标图形")

    # 6. 对目标SVG执行操作（示例）
    return target_svg

def login_llm():
    chrome_driver.get("https://chat.deepseek.com/sign_in")
    #选择密码登录选项
    # code_login_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
    #     EC.presence_of_element_located((By.XPATH, "//div[@class='ds-sign-in-form__social-buttons-container']/button[1]")))
    # code_login_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
    #     EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '密码登录')]")))
    # code_login_e = chrome_driver.find_element(By.XPATH, "//*[contains(text(), '密码登录')]")
    # code_login_e = chrome_driver.find_element(By.XPATH, "//*[contains(text(), '密码登录')]")
    # code_login_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
    #     EC.presence_of_element_located((By.CLASS_NAME, "ds-button.ds-button--primary.ds-button--text.ds-button--capsule.ds-button--m.ds-button--icon-relative-m.ds-button--underlined.ds-sign-in-form__social-link")))

    _ = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
        EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'密码登录')]")))
    code_login_e = find_element_by_text('密码登录')
    code_login_e.click()
    username_input_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
        EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, '输入手机号')]")))

    # username_input_e = chrome_driver.find_element(By.XPATH, "//input[contains(@placeholder, '输入手机号')]")
    code_input_e = chrome_driver.find_element(By.XPATH, "//input[contains(@placeholder, '输入密码')]")

    username_input_e.send_keys('18138879894')
    time.sleep(OPERATION_TIMEOUT)
    code_input_e.send_keys('agent.2025')
    time.sleep(OPERATION_TIMEOUT)
    # login_btn_e = chrome_driver.find_element(By.CLASS_NAME, "ds-button.ds-button--primary.ds-button--filled.ds-button--capsule.ds-button--xl.ds-button--icon-relative-m.ds-button--min-width")
    login_btn_e = find_element_by_text('登录')
    login_btn_e.click()

def new_chat():
    # new_chat_e = chrome_driver.find_elements(By.CLASS_NAME, "ds-icon-button.ds-icon-button--l.ds-icon-button--sizing-container")[2]
    # if not new_chat_e.is_displayed():
    #     new_chat_e = chrome_driver.find_elements(By.CLASS_NAME,"ds-icon-button.ds-icon-button--xl.ds-icon-button--sizing-container")[1]
    new_chat_e = find_element_by_svg(r'./svg_new.png')
    new_chat_e.click()
    time.sleep(OPERATION_TIMEOUT)

def set_llm(deepthink=True, internet=True):
    #深度思考
    r1_choice_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, ".ds-toggle-button")))
    #联网
    internet_choice_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, ".ds-toggle-button:nth-of-type(2)")))

    if deepthink != ('selected' in r1_choice_e.get_attribute("class")):
        r1_choice_e.click()
        time.sleep(OPERATION_TIMEOUT)

    if internet != ('selected' in internet_choice_e.get_attribute("class")):
        internet_choice_e.click()
        time.sleep(OPERATION_TIMEOUT)

def _get_chat_body():
    print('获取chatbody')
    interact_items_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
        EC.presence_of_element_located((By.CLASS_NAME, "ds-virtual-list-visible-items")))
    return interact_items_e

def prepare_chat(is_new_chat=True):
    message_id = 0
    if is_new_chat:
        return message_id, None
    interact_items_e = _get_chat_body()
    WebDriverWait(interact_items_e, RESPONSE_TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-virtual-list-item-key]")))
    messages_e = interact_items_e.find_elements(By.CSS_SELECTOR, "[data-virtual-list-item-key]")
    for message_e in messages_e:
        message_id = max(int(message_e.get_attribute("data-virtual-list-item-key")), message_id)

    return message_id, interact_items_e

def check_staus(recheck=False):
    max_key = 0
    try:
        print('获取含key元素')
        item_key_elements = chrome_driver.find_elements(By.CSS_SELECTOR, f"[data-virtual-list-item-key]")
    except Exception as e:
        print('no data-virtual-list-item-key elements，返回0')
        return max_key

    for element in item_key_elements:
        key = int(element.get_attribute("data-virtual-list-item-key"))
        max_key = key if abs(max_key) < abs(key) else max_key
    print(f'max_key = {max_key}')
    if max_key < 0:
        try:
            print('处理重试异常')
            # retry_e = chrome_driver.find_element(By.CLASS_NAME,
            #                                      "ds-icon-button.ds-icon-button--s.ds-icon-button--sizing-container")
            retry_e = find_element_by_svg(r'./svg_retry.png')
            sleep(RESPONSE_TIMEOUT/2)
            retry_e.click()
            time.sleep(RETRY_INTERNAL)
            max_key = check_staus(True)
        except Exception as e:
            print('无重试异常')
            if not recheck:
                print('获取scrollable元素')
                list_e = chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list")
                chrome_driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_e)
                time.sleep(OPERATION_TIMEOUT)
                max_key = check_staus(True)
            if max_key < 0:
                try:
                    if '请开启新对话' in chrome_driver.find_element(By.CLASS_NAME, f"ds-virtual-list-visible-items").text[-15:]:
                        print('达到对话长度上限')
                        return max_key
                except Exception as e:
                    print(e)

                print(f'May still loading. {datetime.now().strftime("%d-%H%M%S")}')
                with open(f'./llm_response/chat body {datetime.now().strftime("%H%M%S")}.html', 'w',
                          encoding='utf8') as f:
                    f.write(chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list-visible-items").get_property(
                        "innerHTML"))
                time.sleep(RETRY_INTERNAL)
                max_key = check_staus(True)
    print(f'返回 max_key = {max_key}')
    return max_key


def send_prompt(prompt):
    print('获取输入框元素')
    chat_input_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, "//textarea[contains(@placeholder, '发送消息')]")))
    # chat_input_e.send_keys(prompt)  #无法处理换行
    # chat_input_e.clear()  #无效
    chat_input_e.click()
    time.sleep(OPERATION_TIMEOUT)

    old_content = pyperclip.paste()
    with FileLock(LOCK_FILE, timeout=10):
        pyperclip.copy(prompt)
        time.sleep(0.1)
        ActionChains(chrome_driver).key_down(Keys.CONTROL).send_keys('a').send_keys('v').key_up(Keys.CONTROL).perform()
        time.sleep(0.1)
        pyperclip.copy(old_content)

    time.sleep(OPERATION_TIMEOUT)
    chat_input_e.send_keys(Keys.ENTER)
    time.sleep(OPERATION_TIMEOUT)

    time.sleep(10)


def chat_with_llm(message_id):
    response_content = 'failed'

    try:
        chat_body = _get_chat_body()
        print(f'获取message id={message_id} 的元素，{RESPONSE_TIMEOUT}s后超时')
        response_e = WebDriverWait(chat_body, RESPONSE_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"[data-virtual-list-item-key='{message_id}']")))
        print(f'获取ds-flex，{RESPONSE_TIMEOUT}s后超时')
        buttons_e = WebDriverWait(response_e, RESPONSE_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, "ds-flex")))
        print(f'获取文本元素，{RESPONSE_TIMEOUT}s后超时')
        response_content_e = WebDriverWait(response_e, RESPONSE_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".ds-message>.ds-markdown")))
        # response_content = response_content_e.get_attribute('outerHTML')
        # response_content = response_content_e.get_property('outerHTML')
        list_e = chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list")
        chrome_driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_e)
        time.sleep(OPERATION_TIMEOUT)

        chrome_driver.save_screenshot(f'./llm_response/chat_with_llm.png')
        last_content = response_e.get_property('innerHTML')

        while True:
            time.sleep(10)
            content = response_e.get_property('innerHTML')
            #有可能在思考，导致response_content_e一直是空的，所以要用response_e来做比较
            with open(f'./llm_response/llm response new.html', 'w',
                      encoding='utf8') as f:
                f.write(content)
            with open(f'./llm_response/llm response.html', 'w',
                      encoding='utf8') as f:
                f.write(last_content)

            if last_content == content:
                print('前后两次获取的内容一致')
                response_content = html_to_markdown(response_content_e.get_property('innerHTML'))
                if len(response_content) == 0:
                    print('有效内容为空')
                    continue
                break
            else:
                print('前后两次获取的内容不一致，内容生成中')
                last_content = content

        response_content = response_content_e.get_property('innerHTML')
        with open(f'./llm_response/llm response {datetime.now().strftime("%H%M%S")}.html', 'w', encoding='utf8') as f:
            f.write(response_content)
    except Exception as e:
        print(e)
        try:
            text = response_e.text
            if '已停止' in text[:3]:
                print('尝试处理思考已停止异常')
                buttons = buttons_e.find_elements(By.CLASS_NAME,
                                                  "ds-icon-button.ds-icon-button--m.ds-icon-button--sizing-container")
                buttons[1].click()
                time.sleep(OPERATION_TIMEOUT)
                # chat_with_llm(message_id) message id 会改变
        except Exception as e:
            print('无思考已停止异常')
    try:
        print('尝试处理长输出异常，点击继续输出')
        continue_button_e = buttons_e.find_element(By.CLASS_NAME,
                                                   "ds-atom-button.ds-basic-button.ds-basic-button--outlined")
        continue_button_e.click()
        time.sleep(OPERATION_TIMEOUT)
        chat_with_llm(message_id)
    except Exception as e:
        print('无长输出异常')

    return response_content


if __name__ == '__main__':
    port = SOCKET_PORT
    args = sys.argv[1:]
    if len(args) > 0:
        port = int(args[0])
    socket = zmq.Context().socket(zmq.REP)
    socket.bind(f"tcp://*:{port}")  # 绑定到所有接口的5555端口

    init_webdriver()
    login_llm()
    chat_body = None
    need_init = True
    while True:
        if need_init:
            set_llm()
            need_init = False

        if socket.poll(None, zmq.POLLIN):
            request = json.loads(socket.recv_json())
            prompt = request['prompt']
            cmd = request['cmd']
            need_send = 'reget' not in cmd
            response_content = 'failed'
            try:
                if 'new chat' in cmd:
                    new_chat()
                    need_init = True
                    socket.send_json(json.dumps({'response': 'done'}))
                    continue
                while True:
                    message_id = check_staus()
                    if message_id < 0 or (message_id == 0 and 'complete prompt' not in cmd):
                        response_content = 'new chat'
                        new_chat()
                        need_init = True
                        break
                    if need_send:
                        send_prompt(prompt)
                        need_send = False
                        continue
                    response_content = chat_with_llm(message_id)
                    break

            except Exception as e:
                print(e)
            socket.send_json(json.dumps({'response': response_content}))
