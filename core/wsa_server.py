from asyncio import AbstractEventLoop

import websockets
import asyncio
import json
from abc import abstractmethod
from websockets.legacy.server import Serve

from utils import util
from scheduler.thread_manager import MyThread
import time
import os

class MyServer:
    def __init__(self, host='0.0.0.0', port=10000):
        self.lock = asyncio.Lock()
        self._host = host  # ip
        self._port = port  # 端口号
        self._listCmd = []  # 要发送的信息的列表
        self._clients = list()  # 改为protected属性
        self._server: Serve = None
        self._event_loop: AbstractEventLoop = None
        self._running = True
        self._pending = None
        self.isConnect = False
        self.TIMEOUT = 3  # 设置任何超时时间为 3 秒
        self._tasks = {}  # 记录任务和开始时间的字典
        self._last_message = None  # 记录最后一条消息
        self._heartbeat_interval = 60  # 心跳间隔（秒）
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 5  # 重连延迟（秒）
        self._message_counter = 0  # 消息计数器
        self._audio_playing = False  # 语音播放状态
        self._last_audio_time = 0  # 上次语音播放时间

    def clean_message(self, message):
        """清理消息内容，避免重复编码"""
        if isinstance(message, str):
            return message.strip().replace('\x00', '')
        elif isinstance(message, dict):
            return {k: self.clean_message(v) for k, v in message.items()}
        elif isinstance(message, list):
            return [self.clean_message(v) for v in message]
        return message

    # 接收处理
    async def __consumer_handler(self, websocket, path):
        """处理接收到的消息"""
        username = None
        output_setting = None
        try:
            async for message in websocket:
                await asyncio.sleep(0.01)
                try:
                    # 清理消息中的空字节
                    if isinstance(message, str):
                        message = message.encode('utf-8', errors='ignore').decode('utf-8').replace('\x00', '')
                    elif isinstance(message, bytes):
                        message = message.decode('utf-8', errors='ignore').replace('\x00', '')
                        
                    data = json.loads(message)
                    username = data.get("Username")
                    output_setting = data.get("Output")
                except json.JSONDecodeError:
                    util.log(1, f"无效的JSON消息: {message[:100]}")  # 只记录前100个字符
                    continue
                    
                if username or output_setting:
                    remote_address = websocket.remote_address
                    unique_id = f"{remote_address[0]}:{remote_address[1]}"
                    async with self.lock:
                        for i in range(len(self._clients)):
                            if self._clients[i]["id"] == unique_id:
                                if username:
                                    self._clients[i]["username"] = username
                                if output_setting:
                                    self._clients[i]["output"] = output_setting   
                await self.__consumer(message)
        except websockets.exceptions.ConnectionClosedError:
            await self.remove_client(websocket)
        except Exception as e:
            util.log(1, f"消息处理异常: {str(e)}")
            await self.remove_client(websocket)

    def get_client_output(self, username):
        clients_with_username = [c for c in self._clients if c.get("username") == username]
        if not clients_with_username:
            return False
        for client in clients_with_username:
            output = client.get("output", 1)
            if output != 0 and output != '0':
                return True 
        return False

    # 发送处理        
    async def __producer_handler(self, websocket, path):
        while self._running:
            await asyncio.sleep(0.01)
            if len(self._listCmd) > 0:
                message = await self.__producer()
                if message:
                    try:
                        # 处理消息前先检查语音状态
                        if isinstance(message, dict):
                            data = message
                        else:
                            data = json.loads(message) if isinstance(message, str) else message
                        
                        # 添加语音状态检查
                        if 'audio_status' in data:
                            if data['audio_status'] == 'busy':
                                util.log(1, "语音系统正忙，跳过当前消息")
                                continue
                        
                        username = data.get("Username", "User")
                        
                        # 消息预处理
                        processed_message = self.on_send_handler(data)
                        if processed_message is None:
                            continue
                            
                        async with self.lock:
                            if len(self._clients) == 0:
                                continue
                            
                            if username == "User":
                                wsclients = [c["websocket"] for c in self._clients]
                                for client in wsclients:
                                    try:
                                        await asyncio.wait_for(client.send(json.dumps(processed_message)), timeout=self.TIMEOUT)
                                    except asyncio.TimeoutError:
                                        util.log(1, f"发送消息超时: {username}")
                                        await self.remove_client(client)
                                    except Exception as e:
                                        util.log(1, f"发送消息异常: {str(e)}")
                                        await self.remove_client(client)
                            else:
                                target_clients = [c["websocket"] for c in self._clients if c.get("username") == username]
                                if not target_clients:
                                    continue
                                    
                                for client in target_clients:
                                    try:
                                        await asyncio.wait_for(client.send(json.dumps(processed_message)), timeout=self.TIMEOUT)
                                    except asyncio.TimeoutError:
                                        util.log(1, f"发送消息超时: {username}")
                                        await self.remove_client(client)
                                    except Exception as e:
                                        util.log(1, f"发送消息异常: {str(e)}")
                                        await self.remove_client(client)
                                        
                    except Exception as e:
                        util.log(1, f"消息处理异常: {str(e)}")
                        continue

    # 发送消息（设置超时）
    async def send_message_with_timeout(self, client, message, username, timeout=3):
        try:
            await asyncio.wait_for(self.send_message(client, message, username), timeout=timeout)
        except asyncio.TimeoutError:
            util.printInfo(1, "User" if username is None else username, f"发送消息超时: 用户名 {username}")
        except websockets.exceptions.ConnectionClosed as e:
            # 从客户端列表中移除已断开的连接
            await self.remove_client(client)
            util.printInfo(1, "User" if username is None else username, f"WebSocket 连接关闭: {e}")

    # 发送消息
    async def send_message(self, client, message, username):
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed as e:
            # 从客户端列表中移除已断开的连接
            await self.remove_client(client)
            util.printInfo(1, "User" if username is None else username, f"WebSocket 连接关闭: {e}")

                
    async def __handler(self, websocket, path):
        """处理WebSocket连接"""
        try:
            # 等待连接建立
            await websocket.ping()
            
            remote_address = websocket.remote_address
            unique_id = f"{remote_address[0]}:{remote_address[1]}"
            
            async with self.lock:
                self._clients.append({
                    "id": unique_id, 
                    "websocket": websocket, 
                    "username": "User",
                    "connected_time": time.time()
                })
                self.isConnect = True
            
            if isinstance(self, TestServer):
                await self.add_client(websocket)
            
            self.on_connect_handler()
            
            # 创建消息处理任务
            consumer_task = asyncio.create_task(self.__consumer_handler(websocket, path))
            producer_task = asyncio.create_task(self.__producer_handler(websocket, path))
            heartbeat_task = asyncio.create_task(self.__heartbeat(websocket))
            
            # 等待任务完成
            try:
                done, pending = await asyncio.wait(
                    [consumer_task, producer_task, heartbeat_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # 取消未完成的任务
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                        
            except Exception as e:
                util.log(1, f"任务处理异常: {str(e)}")
                
        except websockets.exceptions.ConnectionClosed:
            util.log(1, "连接已关闭")
        except Exception as e:
            util.log(1, f"连接处理异常: {str(e)}")
        finally:
            # 清理连接
            await self.remove_client(websocket)

    async def __consumer(self, message):
        """处理接收到的消息"""
        try:
            # 清理并验证消息
            cleaned_message = self.clean_message(message)
            if cleaned_message is None:
                return
                
            # 检查消息类型和状态
            if isinstance(cleaned_message, dict):
                # 处理语音相关状态
                if cleaned_message.get('type') == 'play_finished':
                    # 停止当前语音播放
                    self._audio_playing = False
                    self._last_audio_time = time.time()
                    util.log(1, "收到播放结束事件")
                elif cleaned_message.get('type') == 'play_start':
                    # 开始新的语音播放
                    self._audio_playing = True
                    self._last_audio_time = time.time()
                        
            # 调用消息处理器
            self.on_revice_handler(cleaned_message)
        except Exception as e:
            util.log(1, f"消息处理异常: {str(e)}")

    async def __producer(self):
        """处理要发送的消息"""
        if len(self._listCmd) > 0:
            message = self._listCmd.pop(0)
            try:
                # 清理消息内容
                cleaned_message = self.clean_message(message)
                
                # 处理语音相关消息
                if isinstance(cleaned_message, dict):
                    # 检查是否是播放结束消息
                    if cleaned_message.get('type') == 'play_finished':
                        self._audio_playing = False
                        return cleaned_message

                    self._message_counter += 1
                    msg_id = f"{time.time()}_{self._message_counter}"
                    cleaned_message['_msg_id'] = msg_id
                    
                    # 处理语音播放状态
                    if 'audio' in cleaned_message or 'text' in cleaned_message:
                        # 检查上次播放是否超时
                        if self._audio_playing and time.time() - self._last_audio_time > 10:
                            util.log(1, "检测到语音播放超时，重置状态")
                            self._audio_playing = False

                        # 如果正在播放，返回None以跳过此消息
                        if self._audio_playing:
                            util.log(1, f"语音正在播放中，跳过消息: {cleaned_message.get('text', '')}")
                            return None

                        # 设置为播放状态
                        self._audio_playing = True
                        self._last_audio_time = time.time()
                        cleaned_message['audio_control'] = {
                            'timestamp': time.time(),
                            'msg_id': msg_id,
                            'status': 'playing'
                        }
                
                return cleaned_message
            except Exception as e:
                util.log(1, f"消息处理异常: {str(e)}")
                return None
        return None
        
    async def remove_client(self, websocket):
        """移除客户端连接"""
        async with self.lock:
            # 移除指定的客户端
            self._clients = [c for c in self._clients if c["websocket"] != websocket]
            
            # 更新连接状态
            if len(self._clients) == 0:
                self.isConnect = False
                util.log(1, "所有客户端已断开连接")
            
            # 调用关闭处理器
            self.on_close_handler()

    def is_connected(self, username):
        if username is None:
            username = "User"
        if len(self._clients) == 0:
            return False
        clients = [c for c in self._clients if c["username"] == username]
        if len(clients) > 0:
            return True
        return False


    # 子类实现：服务端接收消息后的处理逻辑
    @abstractmethod
    def on_revice_handler(self, message):
        pass

    # 子类实现：客户端连接后的处理逻辑
    @abstractmethod
    def on_connect_handler(self):
        pass
    
    # 子类实现：服务端发送消息前的处理逻辑
    @abstractmethod
    def on_send_handler(self, message):
        return message

    # 子类实现：客户端断开连接后的处理逻辑
    @abstractmethod
    def on_close_handler(self):
        pass

    # 创建server
    def __connect(self):
        """创建服务器"""
        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)
        self._isExecute = True
        if self._server:
            util.log(1, 'server already exist')
            return
        
        async def start_server():
            # websockets>=12 asyncio server calls handler(connection) (no `path` arg).
            # Use legacy server API here to keep our handler(websocket, path) compatible.
            self._server = await websockets.legacy.server.serve(self.__handle_connection, self._host, self._port)
            util.log(1, f'WebSocket server started on {self._host}:{self._port}')
        
        self._event_loop.run_until_complete(start_server())
        self._event_loop.run_forever()

    # 往要发送的命令列表中，添加命令
    def add_cmd(self, cmd):
        """添加命令到消息队列"""
        try:
            if len(self._clients) == 0:
                return
            
            # 检查是否是结束播放的消息
            if isinstance(cmd, dict) and cmd.get('type') == 'play_finished':
                self._audio_playing = False
                self._last_audio_time = time.time()
                return

            # 检查是否是重复命令
            cmd_str = json.dumps(cmd) if isinstance(cmd, dict) else str(cmd)
            if hasattr(self, '_last_cmd') and self._last_cmd == cmd_str:
                return
            
            self._last_cmd = cmd_str
            
            # 处理语音消息
            if isinstance(cmd, dict):
                if "Username" not in cmd:
                    cmd["Username"] = "User"
                    
                # 添加语音状态检查
                if ('audio' in cmd or 'text' in cmd) and not cmd.get('type') == 'play_finished':
                    # 检查是否需要等待前一个语音完成
                    if self._audio_playing:
                        # 记录日志
                        util.log(1, f"语音正在播放，跳过消息: {cmd.get('text', '')}")
                        return
                    
                    # 更新语音状态
                    self._audio_playing = True
                    self._last_audio_time = time.time()
            
            self._listCmd.append(cmd)
            
        except Exception as e:
            util.log(1, f"添加消息到队列失败: {str(e)}")

    # 开启服务
    def start_server(self):
        MyThread(target=self.__connect).start()

    # 关闭服务
    async def stop_server(self):
        """停止服务器"""
        self._running = False
        self.isConnect = False
        if self._server is None:
            return
        try:
            # 等待 WebSocket 服务器关闭
            if self._server:
                await self._server.wait_closed()  # 确保关闭服务器
            if self._event_loop and not self._event_loop.is_closed():
                self._event_loop.stop()
                self._event_loop.close()
            self._server = None
            self._clients = []
            util.log(1, "WebSocket server stopped.")
        except Exception as e:
            util.log(1, f"停止服务器时出错: {str(e)}")
            if hasattr(self, '_server') and self._server:
                self._server = None
            self._clients = []

    async def __heartbeat(self, websocket):
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await websocket.ping()
            except Exception as e:
                util.log(1, f"心跳检测失败: {str(e)}")
                await self.remove_client(websocket)
                break

    async def __handle_connection(self, websocket, path):
        try:
            heartbeat_task = asyncio.create_task(self.__heartbeat(websocket))
            await self.__handler(websocket, path)
        except websockets.exceptions.ConnectionClosed:
            util.log(1, "连接已关闭，尝试重连...")
            await self.__attempt_reconnect()
        except Exception as e:
            util.log(1, f"连接处理异常: {str(e)}")
        finally:
            heartbeat_task.cancel()

    async def __attempt_reconnect(self):
        if self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            await asyncio.sleep(self._reconnect_delay)
            util.log(1, f"尝试重连 ({self._reconnect_attempts}/{self._max_reconnect_attempts})...")
            try:
                self.start_server()
                self._reconnect_attempts = 0
            except Exception as e:
                util.log(1, f"重连失败: {str(e)}")
        else:
            util.log(1, "达到最大重连次数，停止重连")
            self._running = False


#ui端server
class WebServer(MyServer):
    def __init__(self, host='0.0.0.0', port=10003):
        super().__init__(host, port)

    def on_revice_handler(self, message):
        try:
            if isinstance(message, dict):
                # 处理所有消息
                panel_msg = {
                    "type": "user_input",
                    "content": message.get('userInput', ''),
                    "username": message.get("Username", "User")
                }
                web_instance = get_web_instance()
                if web_instance:
                    web_instance.add_cmd({
                        "panelReply": panel_msg,
                        "Username": message.get("Username", "User")
                    })
        except Exception as e:
            util.log(1, f"消息处理异常: {str(e)}")
    
    def on_connect_handler(self):
        self.add_cmd({"panelMsg": "使用提示：SmartSisi可以独立使用，启动数字人将自动对接。"})

    def on_send_handler(self, message):
        try:
            if isinstance(message, dict):
                return message
            if isinstance(message, str):
                return json.loads(message)
            return None
        except Exception as e:
            util.log(1, f"Web服务器消息处理失败: {str(e)}")
            return None

    def on_close_handler(self):
        pass

#数字人端server
class HumanServer(MyServer):
    def __init__(self, host='0.0.0.0', port=10002):
        super().__init__(host, port)
        self._audio_queue = []  # 语音消息队列
        self._current_audio = None  # 当前播放的语音
        self._audio_lock = asyncio.Lock()  # 语音操作锁
        self._auto_play_interval = 180  # 自动播放间隔（3分钟）
        self._last_auto_play_time = time.time()  # 上次自动播放时间
        self._auto_play_enabled = True  # 自动播放开关
        self._last_interaction_time = time.time()  # 上次交互时间
        self._interaction_cooldown = 180  # 交互冷却时间（3分钟）
        self._busy_message_sent = False  # 是否已发送忙碌消息
        self._scene_description_mode = False  # 场景描述模式
        self._scene_messages = []  # 场景描述消息队列
        self._tts_timeout = 10  # TTS超时时间（秒）
        self._max_audio_length = 15  # 最大音频长度（秒）
        self._max_text_length = 100  # 单次合成最大文本长度
        self._cache_dir = './samples'  # 缓存目录
        self._is_opening_audio = False  # 是否正在播放开场白

    def _get_cache_filename(self, text, is_opening=False):
        """统一的缓存文件名生成方法"""
        if is_opening:
            return os.path.join(self._cache_dir, f'opening_{hash(text)}_opening.wav')
        return os.path.join(self._cache_dir, f'sample-{int(time.time() * 1000)}.wav')

    def on_revice_handler(self, message):
        """处理接收到的消息"""
        try:
            if isinstance(message, dict):
                # 更新交互时间
                current_time = time.time()
                self._last_interaction_time = current_time
                
                # 检查是否是场景描述相关消息
                if message.get('type') == 'scene_start':
                    self._scene_description_mode = True
                    self._scene_messages = []
                elif message.get('type') == 'scene_end':
                    self._scene_description_mode = False
                
                # 处理语音播放完成事件
                if message.get('audio_event') == 'complete':
                    self._audio_playing = False
                    self._current_audio = None
                    self._busy_message_sent = False  # 重置忙碌消息标志
                    self._is_opening_audio = False  # 重置开场白状态
                    
                    # 如果在场景描述模式下，继续播放队列中的场景消息
                    if self._scene_description_mode and self._scene_messages:
                        next_message = self._scene_messages.pop(0)
                        self.add_cmd(next_message)
                    else:
                        asyncio.create_task(self._process_audio_queue())
                        
                # 处理语音播放开始事件
                elif message.get('audio_event') == 'start':
                    self._audio_playing = True
                    self._current_audio = message.get('audio_id')
                    if message.get('is_opening'):
                        self._is_opening_audio = True
                        
        except Exception as e:
            util.log(1, f"消息处理异常: {str(e)}")

    async def _process_audio_queue(self):
        """处理语音队列"""
        try:
            async with self._audio_lock:
                if not self._audio_playing and self._audio_queue:
                    next_audio = self._audio_queue.pop(0)
                    self._audio_playing = True
                    self._current_audio = next_audio.get('audio_id')
                    self.add_cmd(next_audio)
                    util.log(1, f"开始播放队列中的语音: {self._current_audio}")
        except Exception as e:
            util.log(1, f"处理语音队列异常: {str(e)}")

    def on_connect_handler(self):
        """连接建立时的处理"""
        web_server_instance = get_web_instance()
        web_server_instance.add_cmd({"is_connect": self.isConnect})
        # 重置语音状态
        self._audio_playing = False
        self._current_audio = None
        self._audio_queue.clear()

    def on_send_handler(self, message):
        """发送消息前的处理"""
        try:
            if not self.isConnect:
                return None

            current_time = time.time()
            
            if isinstance(message, dict):
                # 检查是否是开场白
                is_opening = message.get('type', '').startswith('opening_')
                
                # 处理语音消息
                if 'text' in message or 'audio' in message:
                    # 生成缓存文件名
                    cache_file = self._get_cache_filename(message.get('text', ''), is_opening)
                    
                    # 检查缓存
                    if is_opening and os.path.exists(cache_file):
                        message['audio_file'] = cache_file
                        message['is_opening'] = True
                        util.log(1, f"使用开场白缓存: {cache_file}")
                    
                    # 检查文本长度
                    text = message.get('text', '')
                    if len(text) > self._max_text_length:
                        segments = self._split_text(text)
                        if segments:
                            message['text'] = segments[0]
                            for segment in segments[1:]:
                                self._scene_messages.append({
                                    'text': segment,
                                    'type': 'text_segment',
                                    'audio_id': f"segment_{time.time()}_{self._message_counter}"
                                })
                    
                    # 生成唯一的语音ID
                    message['audio_id'] = f"audio_{time.time()}_{self._message_counter}"
                    
                    # 添加TTS控制参数
                    message['tts_config'] = {
                        'timeout': self._tts_timeout,
                        'max_length': self._max_audio_length
                    }
                    
                    # 检查是否是场景描述消息
                    is_scene = message.get('type', '').startswith('scene_')
                    
                    # 检查是否是自动播放消息
                    is_auto_play = message.get('auto_play', False)
                    
                    if self._audio_playing:
                        if is_scene:
                            self._scene_messages.append(message)
                            util.log(1, f"场景描述消息加入队列: {message.get('text', '')}")
                            return None
                        elif not is_auto_play and not self._busy_message_sent:
                            self._busy_message_sent = True
                            return {
                                'text': '我正在说话，请稍等一下...',
                                'audio_id': f"busy_{time.time()}",
                                'type': 'busy_notification'
                            }
                        return None
                    else:
                        self._audio_playing = True
                        self._current_audio = message['audio_id']
                        if is_auto_play:
                            self._last_auto_play_time = current_time
                        if is_opening:
                            self._is_opening_audio = True
                        util.log(1, f"直接播放语音: {message['audio_id']}")
                
                # 添加语音状态信息
                message['audio_status'] = {
                    'playing': self._audio_playing,
                    'current_audio': self._current_audio,
                    'queue_size': len(self._audio_queue),
                    'scene_queue_size': len(self._scene_messages),
                    'auto_play_enabled': self._auto_play_enabled,
                    'is_busy': self._busy_message_sent,
                    'scene_mode': self._scene_description_mode,
                    'is_opening': self._is_opening_audio
                }
            
            return message
        except Exception as e:
            util.log(1, f"消息发送处理异常: {str(e)}")
            return message

    def _split_text(self, text):
        """将长文本分段"""
        if not text:
            return []
            
        # 按标点符号分段
        segments = []
        current_segment = ""
        
        # 分段标点符号
        split_chars = ['。', '！', '？', '；', '.', '!', '?', ';']
        
        for char in text:
            current_segment += char
            if char in split_chars and len(current_segment) >= 20:  # 最小分段长度
                segments.append(current_segment)
                current_segment = ""
                
        # 处理剩余文本
        if current_segment:
            segments.append(current_segment)
            
        return segments

    def on_close_handler(self):
        """连接关闭时的处理"""
        web_server_instance = get_web_instance()
        web_server_instance.add_cmd({"is_connect": self.isConnect})
        # 清理语音状态
        self._audio_playing = False
        self._current_audio = None
        self._audio_queue.clear()
        self._scene_messages.clear()
        self._scene_description_mode = False
        # 重置自动播放状态
        self._auto_play_enabled = True
        self._last_auto_play_time = time.time()
        self._busy_message_sent = False  # 重置忙碌消息标志

#测试
class TestServer(MyServer):
    def __init__(self, host='0.0.0.0', port=10000):
        super().__init__(host, port)
        self.received_messages = []
        self.connection_events = []
        self.disconnection_events = []
        self._test_clients = []  # 本地测试客户端列表
        self._audio_queue = []  # 语音消息队列

    def on_revice_handler(self, message):
        """记录接收到的消息"""
        try:
            if isinstance(message, str):
                try:
                    message = json.loads(message)
                except json.JSONDecodeError:
                    pass  # 保持原始字符串格式
                    
            # 处理语音相关消息
            if isinstance(message, dict) and 'audio_command' in message:
                if message['audio_command'] == 'stop':
                    self._audio_playing = False
                    util.log(1, "停止语音播放")
                elif message['audio_command'] == 'start':
                    self._audio_playing = True
                    util.log(1, "开始语音播放")
                    
            self.received_messages.append({
                'time': time.time(),
                'message': message
            })
            print(f"收到消息: {json.dumps(message, ensure_ascii=False) if isinstance(message, dict) else message}")
        except Exception as e:
            util.log(1, f"消息处理异常: {str(e)}")
    
    def on_connect_handler(self):
        """记录连接事件"""
        try:
            self.connection_events.append({
                'time': time.time(),
                'client_count': len(self._clients)  # 使用父类的_clients
            })
            print(f"连接已建立，当前客户端数: {len(self._clients)}")
        except Exception as e:
            util.log(1, f"连接处理异常: {str(e)}")
    
    def on_send_handler(self, message):
        """处理发送消息"""
        try:
            timestamp = time.time()
            
            # 检查语音状态
            if self._audio_playing and isinstance(message, dict):
                if 'text' in message or 'audio' in message:
                    # 如果正在播放语音，将新的语音消息加入队列
                    self._audio_queue.append(message)
                    return None
            
            if isinstance(message, dict):
                message['send_time'] = timestamp
                # 添加语音状态
                message['audio_status'] = 'busy' if self._audio_playing else 'ready'
                return message
            elif isinstance(message, str):
                try:
                    msg_dict = json.loads(message)
                    msg_dict['send_time'] = timestamp
                    msg_dict['audio_status'] = 'busy' if self._audio_playing else 'ready'
                    return msg_dict
                except:
                    return f"{message} (sent at {timestamp})"
            return message
        except Exception as e:
            util.log(1, f"消息发送处理异常: {str(e)}")
            return message
    
    def on_close_handler(self):
        """记录断开连接事件"""
        try:
            self.disconnection_events.append({
                'time': time.time(),
                'remaining_clients': len(self._clients)  # 使用父类的_clients
            })
            print(f"连接已断开，剩余客户端数: {len(self._clients)}")
        except Exception as e:
            util.log(1, f"断开连接处理异常: {str(e)}")

    def get_stats(self):
        """获取服务器统计信息"""
        return {
            'received_messages': len(self.received_messages),
            'connections': len(self.connection_events),
            'disconnections': len(self.disconnection_events),
            'active_clients': len(self._clients),  # 使用父类的_clients
            'is_connected': self.isConnect
        }

    async def add_client(self, websocket):
        """添加客户端"""
        if websocket not in self._test_clients:
            self._test_clients.append(websocket)

    async def remove_client(self, websocket):
        """移除客户端时清理语音状态"""
        if websocket in self._test_clients:
            self._test_clients.remove(websocket)
            self._audio_playing = False
            self._audio_queue.clear()
        await super().remove_client(websocket)

    def process_audio_queue(self):
        """处理语音队列"""
        if not self._audio_playing and self._audio_queue:
            next_message = self._audio_queue.pop(0)
            self._audio_playing = True
            self.add_cmd(next_message)
            

#单例

__instance: MyServer = None
__web_instance: MyServer = None


def new_instance(host='0.0.0.0', port=10002) -> MyServer:
    global __instance
    if __instance is None:
        __instance = HumanServer(host, port)
    return __instance


def new_web_instance(host='0.0.0.0', port=10003) -> MyServer:
    global __web_instance
    if __web_instance is None:
        __web_instance = WebServer(host, port)
    return __web_instance


def get_instance() -> MyServer:
    return __instance


def get_web_instance() -> MyServer:
    return __web_instance

if __name__ == '__main__':
    testServer = TestServer(host='0.0.0.0', port=10000)
    testServer.start_server()
