import json
import os
import sys
import threading
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
import cairosvg

from LLMClient import html_to_markdown

import zmq
import pyperclip
from datetime import datetime
from filelock import FileLock

from logger import init_logger, logger

LOCK_FILE = r"C:\Users\Administrator\AppData\Local\Temp\clipboard.lock"  # Windows

SOCKET_PORT = 9993#1111
PAGE_LOAD_TIMEOUT = 60
OPERATION_TIMEOUT = 1
RESPONSE_TIMEOUT = 600
RETRY_INTERNAL = 60
chrome_driver:webdriver.chrome.webdriver.WebDriver

title_map = {SOCKET_PORT:'test_Server', 7777:'1Server', 9992:'2Server', 9993:'3Server', 9994:'4Server', 6666:'CorrTuning Server', 9981:'Super_Server', 8888:'DB_Server'}

DEBUG_MODE = False
pause_event = threading.Event()   # set=运行中，clear=暂停
pause_event.set()                 # 初始为运行状态
lock = threading.Lock()
def command_thread():
    global DEBUG_MODE
    while True:
        try:
            cmd = input("命令(debug, nodebug): ").strip().lower()
        except EOFError:
            continue

        if cmd == "debug":
            print("收到调试模式命令")
            pause_event.set()  # 唤醒主线程以便退出
            with lock:
                DEBUG_MODE = True
        elif cmd == "nodebug":
            print("收到取消调试模式命令")
            with lock:
                DEBUG_MODE = False
        else:
            print("未知命令")

from enum import Enum

class Status(Enum):
    OK = 1
    NO_REPLY = 0      # 没有回复
    NEED_NEW_CHAT = -1 # 需要新建对话
    NEED_RESEND = -2   # 需要重发
    IN_NEW_CHAT = -3   # 在新对话中

def init_webdriver():
    global chrome_driver
    # 配置Chrome选项（保留用户数据，避免重复登录）
    chrome_options = webdriver.ChromeOptions()

    # 初始化Chrome驱动
    chrome_driver = webdriver.Chrome(
        #service=Service(ChromeDriverManager().install()),
        service=Service(executable_path=r"C:\tools\webdriver\chromedriver_158.exe"), # C:\Users\Administrator\.cache\selenium\chromedriver\win64
        options=chrome_options
    )
    chrome_driver.implicitly_wait(10)  # 全局隐式等待
    WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT, poll_frequency=1).until(lambda driver: True)

def set_title_size(port=None):
    size = chrome_driver.get_window_size()
    width = max(size.get('width', 0), 880)  #变动窗口大小，使得svg的位置刷新以便匹配
    height = max(size.get('height', 0), 500)
    if (width, height) == (size.get('width', 0), size.get('height', 0)):
        width -= 100
    chrome_driver.set_window_size(width, height)
    if port in title_map:
        try:
            chrome_driver.execute_script(f"document.title = '{title_map[port]}'")
        except Exception as e:
            pass

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
    logger.info(f'Finding {target_svg}')
    set_title_size()
    dpr = chrome_driver.execute_script("return window.devicePixelRatio")  #切换显示器
    MATCH_THRESHOLD = 0.75  # 匹配特征点阈值（越大越严格，图标小设5-15即可）
    COMFIRM_THRESHOLD = 0.99

    template_img = cv2.imread(target_svg, cv2.IMREAD_GRAYSCALE)

    try:
        list_e = chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list")
        chrome_driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_e)
    except Exception as e:
        pass

    full_page_screenshot_bytes = chrome_driver.get_screenshot_as_png()
    full_img = Image.open(io.BytesIO(full_page_screenshot_bytes)).convert('L')
    with lock:
        if DEBUG_MODE:
            full_img.save('test_full_image.png')
    all_svg_elements = chrome_driver.find_elements(By.XPATH, '//*[local-name()="svg"]')

    match_results = []
    for svg in all_svg_elements:
        if not svg.is_displayed() or svg.location['x'] < 0 or svg.location['y'] < 0:
            continue
        xy1 = round(svg.location['x']*dpr), round(svg.location['y']*dpr)
        xy2 = xy1[0]+svg.size['width']*dpr, xy1[1]+svg.size['height']*dpr
        image = full_img.crop(xy1+xy2)
        current_img = np.array(image)
        with lock:
            if DEBUG_MODE:
                image.save(f'svg{xy1}.png')
        # ===================== 模板匹配核心（无特征点，永不报错） =====================
        # 缩放模板适配当前SVG大小
        current_height, current_width = current_img.shape[:2]
        scaled_template = cv2.resize(template_img, (current_width, current_height))

        # 计算匹配度
        result = cv2.matchTemplate(current_img, scaled_template, cv2.TM_CCOEFF_NORMED)
        similarity = cv2.minMaxLoc(result)[1]  # 相似度 0~1
        match_results.append((svg, similarity))
        with lock:
            if DEBUG_MODE:
                logger.info(f"SVG {xy1} → 匹配相似度：{round(similarity, 2)}")
        if similarity > COMFIRM_THRESHOLD:
            logger.info(f'{xy1}高相似度：{similarity}, 直接返回')
            return svg

    # 5. 找到匹配度最高的SVG
    target_svg = None
    if match_results:
        # 按匹配分数降序排序，取第一名
        match_results.sort(key=lambda x: x[1], reverse=True)
        best_svg, best_score = match_results[0]

        if best_score >= MATCH_THRESHOLD:
            logger.info(f"✅ 找到目标SVG！最佳匹配分数：{best_score}")
            target_svg = best_svg
        else:
            logger.info(f"❌ 匹配度不足（最低阈值：{MATCH_THRESHOLD}），未找到目标图形")

    # 6. 对目标SVG执行操作（示例）
    return target_svg


def find_element_by_svg2(target_svg):
    # -------------------------- 【配置区：修改这里即可】 --------------------------
    # TEMPLATE_PATH = "svg_new.png"  # 你提前截好的目标SVG模板图
    logger.info(f'Finding {target_svg}')
    MATCH_THRESHOLD = 0.75  # 匹配特征点阈值（越大越严格，图标小设5-15即可）
    COMFIRM_THRESHOLD = 0.99

    template_img = cv2.imread(target_svg, cv2.IMREAD_GRAYSCALE)
    template_height, template_width = template_img.shape[:2]

    all_svg = chrome_driver.find_elements(By.XPATH, '//*[local-name()="svg"]')
    # 存储匹配结果：(SVG元素, 匹配分数)
    match_results = []
    list_e = None
    try:
        list_e = chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list")
    except Exception as e:
        pass

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
            # image.save(f'SVG{index + 1}.png', format='PNG')

            #screenshot_as_png会导致滑动条滚动，导致看不到retry按钮
            if list_e is not None:
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
            logger.info(f"SVG {index + 1} → 匹配相似度：{round(similarity, 2)}")
            if similarity > COMFIRM_THRESHOLD:
                logger.info(f'高相似度：{similarity}, 直接返回')
                return svg

        except Exception as e:
            logger.info(f"SVG {index + 1} 处理失败：{str(e)}")

    # 5. 找到匹配度最高的SVG
    target_svg = None
    if match_results:
        # 按匹配分数降序排序，取第一名
        match_results.sort(key=lambda x: x[1], reverse=True)
        best_svg, best_score = match_results[0]

        if best_score >= MATCH_THRESHOLD:
            logger.info(f"\n✅ 找到目标SVG！最佳匹配分数：{best_score}")
            target_svg = best_svg
        else:
            logger.info(f"\n❌ 匹配度不足（最低阈值：{MATCH_THRESHOLD}），未找到目标图形")

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

    username_input_e.send_keys('18922839345')  #18138879894
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
    chat_body = _get_chat_body()
    if chat_body is None:
        return
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
    interact_items_e = None
    try:
        interact_items_e = WebDriverWait(chrome_driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, "ds-virtual-list-visible-items")))
        logger.info('获取到chatbody')
    except Exception as e:
        logger.info('未获取到chatbody，可能处于新页面')
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
        logger.info('获取含key元素')
        item_key_elements = chrome_driver.find_elements(By.CSS_SELECTOR, f"[data-virtual-list-item-key]")
    except Exception as e:
        logger.info('[data-virtual-list-item-key] 查找异常，返回0')
        return Status.NO_REPLY, max_key

    # for element in item_key_elements:
    #     key = int(element.get_attribute("data-virtual-list-item-key"))
    #     max_key = key if abs(max_key) <= abs(key) else max_key
    if len(item_key_elements) > 0:
        max_key = int(item_key_elements[-1].get_attribute("data-virtual-list-item-key"))
    else:
        logger.info('no data-virtual-list-item-key elements，返回0')
        return Status.NO_REPLY, max_key

    logger.info(f'max_key = {max_key}')
    if max_key < 0:
        # try:
        try:
            list_e = chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list")
            chrome_driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_e)
        except Exception as e:
            logger.info('下拉到最底部时发生异常')
        logger.info('开始处理异常')
        logger.info('1. 判定是否需要开启新对话')

        # retry_e = chrome_driver.find_element(By.CLASS_NAME,
        #                                      "ds-icon-button.ds-icon-button--s.ds-icon-button--sizing-container")
        last_response_text = ''
        try:
            last_response_text = chrome_driver.find_element(By.CLASS_NAME, f"ds-virtual-list-visible-items").text[-15:]
        except Exception as e:
            logger.info('Find ds-virtual-list-visible-items failed.')

        if '请开启新对话' in last_response_text:
            logger.info('达到对话长度上限')
            return Status.NEED_NEW_CHAT, max_key

        logger.info('2. 判定消息是否发送成功')
        if '消息未能发送' in last_response_text:
            logger.info('消息未能发送')
            return Status.NEED_RESEND, max_key

        logger.info('3. 判定是否需要重试')
        retry_e = find_element_by_svg(r'./svg_retry.png')
        if retry_e is not None:
            sleep(RESPONSE_TIMEOUT / 2)
            retry_e.click()
            time.sleep(RETRY_INTERNAL)
        _, max_key = check_staus(True)

        # except Exception as e:
        #     print('无重试异常')
        #     if not recheck:
        #         print('获取scrollable元素')
        #         list_e = chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list")
        #         chrome_driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_e)
        #         time.sleep(OPERATION_TIMEOUT)
        #         max_key = check_staus(True)
        #     if max_key < 0:
        #         try:
        #             if '请开启新对话' in chrome_driver.find_element(By.CLASS_NAME, f"ds-virtual-list-visible-items").text[-15:]:
        #                 print('达到对话长度上限')
        #                 return max_key
        #         except Exception as e:
        #             print(e)
        #
        #         print(f'May still loading. {datetime.now().strftime("%d-%H%M%S")}')
        #         with open(f'./llm_response/chat body {datetime.now().strftime("%H%M%S")}.html', 'w',
        #                   encoding='utf8') as f:
        #             f.write(chrome_driver.find_element(By.CLASS_NAME, "ds-virtual-list-visible-items").get_property(
        #                 "innerHTML"))
        #         time.sleep(RETRY_INTERNAL)
        #         max_key = check_staus(True)
    logger.info(f'返回 max_key = {max_key}')
    return Status.OK, max_key


def send_prompt(prompt):
    logger.info('获取输入框元素')
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

    time.sleep(2)  # DEEPSEEK改成长文本转为附件的形式，附件上传需要时间
    chat_input_e.send_keys(Keys.ENTER)
    #防止超时还未上传完的情况发生
    try:
        prompt_file_btn = chrome_driver.find_element(By.XPATH, '//button[normalize-space()="粘贴原文至输入框"]')
        logger.info('未发送成功')
        prompt_file_btn.click()
        time.sleep(OPERATION_TIMEOUT)
        chat_input_e.send_keys(Keys.ENTER)
    except Exception as e:
        pass

    time.sleep(OPERATION_TIMEOUT)

    time.sleep(10)


def chat_with_llm(message_id):
    response_content = 'failed'

    try:
        chat_body = _get_chat_body()
        logger.info(f'获取message id={message_id} 的元素，{RESPONSE_TIMEOUT}s后超时')
        response_e = WebDriverWait(chat_body, RESPONSE_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"[data-virtual-list-item-key='{message_id}']")))
        logger.info(f'获取ds-flex，{RESPONSE_TIMEOUT}s后超时')
        buttons_e = WebDriverWait(response_e, RESPONSE_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, "ds-flex")))
        logger.info(f'获取文本元素，{RESPONSE_TIMEOUT}s后超时')
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
            # with open(f'./llm_response/llm response new.html', 'w',
            #           encoding='utf8') as f:
            #     f.write(content)
            # with open(f'./llm_response/llm response.html', 'w',
            #           encoding='utf8') as f:
            #     f.write(last_content)

            if last_content == content:
                logger.info('前后两次获取的内容一致')
                response_content = html_to_markdown(response_content_e.get_property('innerHTML'))
                if len(response_content) == 0:
                    logger.info('有效内容为空')
                    continue
                break
            else:
                logger.info('前后两次获取的内容不一致，内容生成中')
                last_content = content

        # response_content = response_content_e.get_property('innerHTML')
        # with open(f'./llm_response/llm response {datetime.now().strftime("%H%M%S")}.html', 'w', encoding='utf8') as f:
        #     f.write(response_content)
    except Exception as e:
        logger.info(e)
        try:
            text = response_e.text
            if '已停止' in text[:3]:
                logger.info('尝试处理思考已停止异常')
                # buttons = buttons_e.find_elements(By.CLASS_NAME,
                #                                   "ds-icon-button.ds-icon-button--m.ds-icon-button--sizing-container")
                # buttons[1].click()

                button = find_element_by_svg(r'./svg_retry2.png')
                button.click()
                time.sleep(OPERATION_TIMEOUT)
                # chat_with_llm(message_id) message id 会改变
        except Exception as e:
            logger.info('无思考已停止异常')
        try:
            retry_btn = chrome_driver.find_element(By.XPATH, '//span[@class="ds-button__content" and contains(text(),"重试")]')
            retry_btn.click()
            time.sleep(OPERATION_TIMEOUT)
        except Exception as e:
            logger.info('无重试异常')
    try:
        logger.info('尝试处理长输出异常，点击继续输出')
        # continue_button_e = buttons_e.find_element(By.CLASS_NAME,
        #                                            "ds-atom-button.ds-basic-button.ds-basic-button--outlined")
        continue_button_e = buttons_e.find_element(By.XPATH, "//*[text()='继续生成']")
        continue_button_e.click()
        time.sleep(OPERATION_TIMEOUT)
        chat_with_llm(message_id)
    except Exception as e:
        logger.info('无长输出异常')

    return response_content


if __name__ == '__main__':
    port = 9993
    args = sys.argv[1:]
    if len(args) > 0:
        port = int(args[0])
    socket = zmq.Context().socket(zmq.REP)
    socket.bind(f"tcp://*:{port}")  # 绑定到所有接口的5555端口
    init_logger(f'{os.path.splitext(os.path.basename(__file__))[0]}_{port if port not in title_map else title_map[port]}')
    threading.Thread(target=command_thread, daemon=True).start()

    init_webdriver()
    login_llm()
    input()
    chat_body = None
    need_init = True
    while True:
        set_title_size(port)
        if need_init:
            set_llm()
            need_init = False

        if socket.poll(None, zmq.POLLIN):
            request = json.loads(socket.recv_json())
            prompt = request['prompt']
            cmd = request['cmd']
            need_send = 'reget' not in cmd
            response_content = 'failed'
            logger.info(f'New request with cmd:{cmd} and prompt:{prompt[:30]}')
            try:
                if 'new chat' in cmd:
                    new_chat()
                    need_init = True
                    socket.send_json(json.dumps({'response': 'done'}))
                    continue
                while True:
                    status, message_id = check_staus()
                    if status == Status.NEED_NEW_CHAT or (status == Status.NO_REPLY and 'complete prompt' not in cmd):
                        response_content = 'new chat'
                        if status == Status.NEED_NEW_CHAT:
                            new_chat()
                            need_init = True
                        break
                    if need_send or status == Status.NEED_RESEND:
                        send_prompt(prompt)
                        need_send = False
                        continue
                    response_content = chat_with_llm(message_id)
                    break

            except Exception as e:
                logger.info(e)
            socket.send_json(json.dumps({'response': response_content}))
