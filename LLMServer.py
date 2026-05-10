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
from filelock import FileLock
LOCK_FILE = r"C:\Users\Administrator\AppData\Local\Temp\clipboard.lock"  # Windows

SOCKET_PORT = 7777
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
    new_chat_e = chrome_driver.find_elements(By.CLASS_NAME, "ds-icon-button.ds-icon-button--l.ds-icon-button--sizing-container")[2]
    if not new_chat_e.is_displayed():
        new_chat_e = chrome_driver.find_elements(By.CLASS_NAME,"ds-icon-button.ds-icon-button--xl.ds-icon-button--sizing-container")[1]

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
        print(e, 'no data-virtual-list-item-key elements')
        return max_key

    for element in item_key_elements:
        key = int(element.get_attribute("data-virtual-list-item-key"))
        max_key = key if abs(max_key) < abs(key) else max_key
    print(f'max_key = {max_key}')
    if max_key < 0:
        try:
            print('处理重试异常')
            retry_e = chrome_driver.find_element(By.CLASS_NAME,
                                                 "ds-icon-button.ds-icon-button--s.ds-icon-button--sizing-container")
            sleep(RESPONSE_TIMEOUT/2)
            retry_e.click()
            time.sleep(RETRY_INTERNAL)
            max_key = check_staus(True)
        except Exception as e:
            print(e)
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
                print('处理思考已停止异常')
                buttons = buttons_e.find_elements(By.CLASS_NAME,
                                                  "ds-icon-button.ds-icon-button--m.ds-icon-button--sizing-container")
                buttons[1].click()
                time.sleep(OPERATION_TIMEOUT)
                # chat_with_llm(message_id) message id 会改变
        except Exception as e:
            print(e)
    try:
        print('处理长输出异常，点击继续输出')
        continue_button_e = buttons_e.find_element(By.CLASS_NAME,
                                                   "ds-atom-button.ds-basic-button.ds-basic-button--outlined")
        continue_button_e.click()
        time.sleep(OPERATION_TIMEOUT)
        chat_with_llm(message_id)
    except Exception as e:
        print(e)

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
