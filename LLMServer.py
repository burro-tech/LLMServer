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

from LLMClient import html_to_markdown

import zmq
import pyperclip
from datetime import datetime

SOCKET_PORT = 7777
PAGE_LOAD_TIMEOUT = 60
OPERATION_TIMEOUT = 1
RESPONSE_TIMEOUT = 600
RETRY_INTERNAL = 60
chrome_driver:webdriver.chrome.webdriver.WebDriver = None

def init_webdriver():
    global chrome_driver
    # 配置Chrome选项（保留用户数据，避免重复登录）
    chrome_options = webdriver.ChromeOptions()
    # 可选：注释掉下面一行，改为可视化模式（方便首次登录）
    # chrome_options.add_argument("--headless=new")  # 无头模式（后台运行）
    # chrome_options.add_argument("--user-data-dir=./chrome_user_data")  # 保存登录状态
    # chrome_options.add_argument("--disable-blink-features=AutomationControlled")  # 避免被检测为自动化工具
    # chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # chrome_options.add_experimental_option('useAutomationExtension', False)
    # chrome_options.add_argument("--window-size=1920,1080")
    # chrome_options.add_argument("--window-position=0,0")
    # chrome_options.add_argument("--start-maximized")
    # chrome_options.add_argument("--disable-background-timer-throttling")
    # chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    # chrome_options.add_argument("--disable-renderer-backgrounding")
    # chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # chrome_options.add_argument("--disable-features=VizDisplayCompositor")

    # 初始化Chrome驱动
    chrome_driver = webdriver.Chrome(
        # service=Service(ChromeDriverManager().install()),
        service=Service(executable_path=r"C:\tools\webdriver\chromedriver_145.exe"),
        options=chrome_options
    )
    chrome_driver.implicitly_wait(10)  # 全局隐式等待
    WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT, poll_frequency=1).until(lambda driver: True)

def login_llm():
    chrome_driver.get("https://chat.deepseek.com/sign_in")
    #选择密码登录选项
    code_login_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
        EC.presence_of_element_located((By.XPATH, "//div[@class='ds-sign-in-form__social-buttons-container']/button[1]")))
    # code_login_e = chrome_driver.find_element(By.XPATH, "//*[contains(text(), '密码登录')]")
    # code_login_e = chrome_driver.find_element(By.XPATH, "//*[contains(text(), '密码登录')]")
    code_login_e.click()
    username_input_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
        EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, '输入手机号')]")))

    # username_input_e = chrome_driver.find_element(By.XPATH, "//input[contains(@placeholder, '输入手机号')]")
    code_input_e = chrome_driver.find_element(By.XPATH, "//input[contains(@placeholder, '输入密码')]")

    username_input_e.send_keys('18138879894')
    time.sleep(OPERATION_TIMEOUT)
    code_input_e.send_keys('agent.2025')
    time.sleep(OPERATION_TIMEOUT)
    login_btn_e = chrome_driver.find_element(By.CLASS_NAME, "ds-atom-button.ds-basic-button.ds-basic-button--primary")
    login_btn_e.click()

def new_chat():
    new_chat_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, ".ds-icon-button.ds-icon-button--l.ds-icon-button--sizing-container:nth-of-type(3)")))
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
    # if chat_body is None:
    max_key = 0
    try:
        # chat_body = _get_chat_body()
        item_key_elements = chrome_driver.find_elements(By.CSS_SELECTOR, f"[data-virtual-list-item-key]")
    except Exception as e:
        print(e, 'no data-virtual-list-item-key elements')
        return max_key
    # min_key = 9999
    for element in item_key_elements:
        key = int(element.get_attribute("data-virtual-list-item-key"))
        max_key = key if abs(max_key) < abs(key) else max_key

    if max_key < 0:
        try:
            retry_e = chrome_driver.find_element(By.CLASS_NAME,
                                                 "ds-icon-button.ds-icon-button--s.ds-icon-button--sizing-container")
            sleep(RESPONSE_TIMEOUT/2)
            retry_e.click()
            time.sleep(OPERATION_TIMEOUT)
            max_key = check_staus(True)
        except Exception as e:
            print(e)
            if not recheck:
                list_e = chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list")
                chrome_driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_e)
                time.sleep(OPERATION_TIMEOUT)
                max_key = check_staus(True)
            if max_key < 0:
                print(f'May get limited access. {datetime.now().strftime("%d-%H%M%S")}')
                with open(f'./llm_response/chat body {datetime.now().strftime("%H%M%S")}.html', 'w',
                          encoding='utf8') as f:
                    f.write(chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list-visible-items").get_property(
                        "innerHTML"))
                for i in range(1, 3):
                    time.sleep(10)
                    with open(f'./llm_response/chat body {datetime.now().strftime("%H%M%S")}.html', 'w',
                              encoding='utf8') as f:
                        f.write(chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list-visible-items").get_property(
                            "innerHTML"))

    return max_key


def send_prompt(prompt, last_message_id, chat_body):
    limited_chat = False

    chat_input_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, "//textarea[contains(@placeholder, '发送消息')]")))
    # chat_input_e.send_keys(prompt)  #无法处理换行
    # chat_input_e.clear()  #无效
    chat_input_e.click()
    time.sleep(OPERATION_TIMEOUT)
    pyperclip.copy(prompt)
    ActionChains(chrome_driver).key_down(Keys.CONTROL).send_keys('a').send_keys('v').key_up(Keys.CONTROL).perform()
    time.sleep(OPERATION_TIMEOUT)
    chat_input_e.send_keys(Keys.ENTER)
    time.sleep(OPERATION_TIMEOUT)
    limited_message_id = -(last_message_id + 2)
    time.sleep(10)

    return (last_message_id + 2), chat_body, limited_chat

def chat_with_llm(prompt, message_id, chat_body):
    response_content = 'failed'

    try:
        # if chat_body is None:
        chat_body = _get_chat_body()
        response_e = WebDriverWait(chat_body, RESPONSE_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"[data-virtual-list-item-key='{message_id}']")))

        buttons_e = WebDriverWait(response_e, RESPONSE_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, "ds-flex")))

        response_content_e = WebDriverWait(response_e, RESPONSE_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".ds-message>.ds-markdown")))
        # response_content = response_content_e.get_attribute('outerHTML')
        # response_content = response_content_e.get_property('outerHTML')
        last_content = response_e.get_property('innerHTML')

        while True:
            time.sleep(10)
            #response_e = chat_body.find_element(By.CSS_SELECTOR, f"[data-virtual-list-item-key='{new_message_id}']")
            content = response_e.get_property('innerHTML')
            #有可能在思考，导致response_content_e一直是空的，所以要用response_e来做比较
            with open(f'./llm_response/llm response new.html', 'w',
                      encoding='utf8') as f:
                f.write(content)
            with open(f'./llm_response/llm response.html', 'w',
                      encoding='utf8') as f:
                f.write(last_content)

            if last_content == content:
                #response_content_e = response_e.find_element(By.CSS_SELECTOR, ".ds-message>.ds-markdown")
                response_content = html_to_markdown(response_content_e.get_property('innerHTML'))
                if len(response_content) == 0:
                    continue
                break
            else:
                last_content = content

        response_content = response_content_e.get_property('innerHTML')
        with open(f'./llm_response/llm response {datetime.now().strftime("%H%M%S")}.html', 'w', encoding='utf8') as f:
            f.write(response_content)
    except Exception as e:
        chat_body = _get_chat_body()
        print(e)
    try:
        continue_button_e = buttons_e.find_element(By.CLASS_NAME,
                                                   "ds-atom-button.ds-basic-button.ds-basic-button--outlined")
        continue_button_e.click()
        time.sleep(OPERATION_TIMEOUT)
        chat_with_llm(prompt, message_id, chat_body)
    except Exception as e:
        print(e)

    return response_content, chat_body


if __name__ == '__main__':
    port = SOCKET_PORT
    args = sys.argv[1:]
    if len(args) > 0:
        port = int(args[0])
    socket = zmq.Context().socket(zmq.REP)
    socket.bind(f"tcp://*:{port}")  # 绑定到所有接口的5555端口

    init_webdriver()
    login_llm()
    # set_llm()
    # message_id, chat_body = prepare_chat()
    chat_body = None
    need_init = True
    while True:
        if need_init:
            set_llm()
            # message_id, chat_body = prepare_chat()
            need_init = False

        if socket.poll(None, zmq.POLLIN):
            request = json.loads(socket.recv_json())
            prompt = request['prompt']
            cmd = request['cmd']
            need_send = 'reget' not in cmd
            response_content = 'failed'
            try:
                while True:
                    message_id = check_staus()
                    if message_id < 0 or (message_id == 0 and 'complete prompt' not in cmd):
                        response_content = 'new chat'
                        new_chat()
                        need_init = True
                        break
                    if need_send:
                        message_id, chat_body, limited = send_prompt(prompt, message_id, chat_body)
                        need_send = False
                        continue
                    response_content, chat_body = chat_with_llm(prompt, message_id, chat_body)
                    break
                #
                # if message_id == 0 and 'complete prompt' not in cmd:
                #     response_content = 'new chat'
                #     need_init = True
                #     continue


                    #
                    # else:
                    #     if 'reget' in cmd:
                    #         response_content, chat_body = chat_with_llm(prompt, message_id, chat_body)
                    #     else:
                    #         message_id, chat_body, limited = send_prompt(prompt, message_id, chat_body)
                    #         if limited:
                    #             response_content = 'new chat'
                    #             new_chat()
                    #             need_init = True
                    #             continue
                    #             # set_llm()
                    #             # message_id, chat_body = prepare_chat()
                    #             # chat_body, limited = send_prompt(prompt, message_id, chat_body)
                    #         else:
                    #             response_content, chat_body = chat_with_llm(prompt, message_id, chat_body)
                    #             break
            except Exception as e:
                print(e)
            # socket.send_json(chat_with_llm(request))
            socket.send_json(json.dumps({'response': response_content}))
            # if message_id >= 100:
            #     break
        # new_chat()