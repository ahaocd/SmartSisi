"""
感谢北京中科大脑神经算法工程师张聪聪提供funasr集成代码
"""
from threading import Thread
import websocket
import json
import time
import ssl
import _thread as thread

from core import wsa_server
from utils import config_util as cfg
from utils import util

class FunASR:
    # 初始化
    def __init__(self, username):
        self.__URL = "ws://{}:{}".format(cfg.local_asr_ip, cfg.local_asr_port)
        self.__ws = None
        self.__connected = False
        self.__frames = []
        self.__state = 0
        self.__closing = False
        self.__task_id = ''
        self.done = False
        self.finalResults = ""
        self.__reconnect_delay = 1
        self.__reconnecting = False
        self.username = username
        self.started = True
        # 🎯 新增：音频上下文数据
        self.audio_context = None

    
    # 收到websocket消息的处理
    def on_message(self, ws, message):
        try:
            self.done = True

            # 🎯 新增：处理音频上下文数据
            try:
                import json
                # 尝试解析JSON格式的音频上下文数据
                message_data = json.loads(message)
                if isinstance(message_data, dict) and message_data.get("type") == "audio_analysis":
                    # 这是增强的音频分析数据
                    self.finalResults = message_data.get("text", "")
                    self.audio_context = message_data.get("audio_context", {})
                    util.log(1, f"[FunASR] 收到音频上下文数据: {len(self.audio_context)} 项")
                    # 🔥 修复：只处理JSON数据，忽略后续的纯文本重复消息
                    self.__json_processed = True
                else:
                    # 普通文本消息
                    self.finalResults = message
                    self.audio_context = None
            except (json.JSONDecodeError, TypeError):
                # 🔥 修复：如果已经处理过JSON数据，忽略纯文本重复消息
                if hasattr(self, '_FunASR__json_processed') and self.__json_processed:
                    util.log(1, f"[FunASR] 跳过重复的纯文本消息: {message[:20]}...")
                    return
                # 不是JSON格式，按普通文本处理
                self.finalResults = message
                self.audio_context = None

            if wsa_server.get_web_instance().is_connected(self.username):
                wsa_server.get_web_instance().add_cmd({"panelMsg": self.finalResults, "Username" : self.username})
            if wsa_server.get_instance().is_connected(self.username):
                content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': self.finalResults}, 'Username' : self.username}
                wsa_server.get_instance().add_cmd(content)

        except Exception as e:
            print(e)

        if self.__closing:
            try:
                self.__ws.close()
            except Exception as e:
                print(e)

    # 收到websocket错误的处理
    def on_close(self, ws, code, msg):
        self.__connected = False
        # util.printInfo(1, self.username, f"### CLOSE:{msg}")
        self.__ws = None

    # 收到websocket错误的处理
    def on_error(self, ws, error):
        self.__connected = False
        # util.printInfo(1, self.username, f"### error:{error}")
        self.__ws = None

    #重连
    def __attempt_reconnect(self):
        if not self.__reconnecting:
            self.__reconnecting = True
            # util.log(1, "尝试重连funasr...")
            while not self.__connected:
                time.sleep(self.__reconnect_delay)
                self.start()
                self.__reconnect_delay *= 2  
            self.__reconnect_delay = 1  
            self.__reconnecting = False


    # 收到websocket连接建立的处理
    def on_open(self, ws):
        self.__connected = True

        def run(*args):
            while self.__connected:
                try:
                    if len(self.__frames) > 0:
                        frame = self.__frames[0]

                        self.__frames.pop(0)
                        if type(frame) == dict:
                            ws.send(json.dumps(frame))
                        elif type(frame) == bytes:
                            ws.send(frame, websocket.ABNF.OPCODE_BINARY)
                        # print('发送 ------> ' + str(type(frame)))
                except Exception as e:
                    print(e)
                time.sleep(0.04)

        thread.start_new_thread(run, ())

    def get_audio_context(self):
        """🔥 新增：获取音频上下文数据的方法"""
        return self.audio_context

    def recognize_file(self, file_path: str) -> str:
        """🔥 新增：识别音频文件的方法"""
        try:
            # 重置状态
            self.done = False
            self.finalResults = ""
            self.audio_context = None

            # 确保连接
            if not self.__connected:
                self.start()
                # 等待连接建立
                import time
                timeout = 10  # 10秒超时
                start_time = time.time()
                while not self.__connected and (time.time() - start_time) < timeout:
                    time.sleep(0.1)

                if not self.__connected:
                    util.log(2, f"[FunASR] WebSocket连接超时")
                    return ""

            # 发送文件路径到ASR_server (JSON格式)
            if self.__ws and self.__connected:
                util.log(1, f"[FunASR] 发送音频文件路径: {file_path}")
                # 🔥 修复：ASR_server期望JSON格式 {"url": "xxx"}
                self.__ws.send(json.dumps({"url": file_path}))

                # 等待处理完成
                timeout = 30  # 30秒超时
                start_time = time.time()
                while not self.done and (time.time() - start_time) < timeout:
                    time.sleep(0.1)

                if self.done:
                    util.log(1, f"[FunASR] 识别完成: {self.finalResults}")
                    return self.finalResults
                else:
                    util.log(2, f"[FunASR] 识别超时")
                    return ""
            else:
                util.log(2, f"[FunASR] WebSocket未连接")
                return ""

        except Exception as e:
            util.log(2, f"[FunASR] 文件识别失败: {e}")
            return ""

    def __connect(self):
        self.finalResults = ""
        self.done = False
        self.__frames.clear()
        websocket.enableTrace(False)
        self.__ws = websocket.WebSocketApp(self.__URL, on_message=self.on_message,on_close=self.on_close,on_error=self.on_error)
        self.__ws.on_open = self.on_open

        self.__ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def add_frame(self, frame):
        self.__frames.append(frame)

    def send(self, buf):
        self.__frames.append(buf)

    def send_url(self, url):
        frame = {'url' : url}
        self.__ws.send(json.dumps(frame))

    def start(self):
        Thread(target=self.__connect, args=[]).start()
        # 增强：传递热词（唤醒/休眠短语）给ASR，提高命中率
        try:
            from utils import config_util as cfg
            wake_words = cfg.config['source'].get('wake_word', '')
            sleep_phrases = cfg.config['source'].get('sleep_phrases', [])
            hotwords = [w.strip() for w in wake_words.split(',') if w.strip()]
            if sleep_phrases:
                hotwords.extend([str(x).strip() for x in sleep_phrases if str(x).strip()])
        except Exception:
            hotwords = []

        data = {
                'vad_need':False,
                'state':'StartTranscription',
                'hotwords': hotwords
        }
        self.add_frame(data)

    def end(self):
        if self.__connected:
            try:
                for frame in self.__frames:
                    self.__frames.pop(0)
                    if type(frame) == dict:
                        self.__ws.send(json.dumps(frame))
                    elif type(frame) == bytes:
                        self.__ws.send(frame, websocket.ABNF.OPCODE_BINARY)
                self.__frames.clear()
                frame = {'vad_need':False,'state':'StopTranscription'}
                self.__ws.send(json.dumps(frame))
            except Exception as e:
                print(e)
        self.__closing = True

    def get_audio_context(self):
        """🎯 获取音频上下文数据"""
        return getattr(self, 'audio_context', None)
