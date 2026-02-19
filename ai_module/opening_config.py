"""
统一的开场白配置和管理
"""
import random
import os
import time
from utils import util

class OpeningStatements:
    # 基础开场白
    DEFAULT = [
        "那就让本座为你保驾护航！",
        "就让本座打开天眼。好好看看。",
        "那就让本座来看看！",
        "让本座为你揭开谜底！",
        "本座这就为你探个究竟！",
        "且让我来看看这奇妙的世界！"
    ]
    
    # 命令类型开场白
    COMMANDS = {
        "long_term": [
            "让本座细细观察...",
            "且让本座看个仔细...",
            "本座这就查看..."
        ],
        "short_term": [
            "那就让本座为你保驾护航...",
            "本座且看一眼...",
            "让本座瞧瞧..."
        ],
        "stop": [
            "本座收回天眼...",
            "好，不看了...",
            "本座闭目..."
        ]
    }
    
    # 场景特定开场白
    SCENES = {
        "人物": [
            "让本座看看是谁...",
            "且看何人在此...",
            "本座瞧瞧..."
        ],
        "动作": [
            "看看在做什么...",
            "且观其动作...",
            "本座瞧瞧..."
        ],
        "表情": [
            "看看什么表情...",
            "且观其神态...",
            "本座瞧瞧..."
        ],
        "服装": [
            "看看穿着如何...",
            "且观其装束...",
            "本座瞧瞧..."
        ]
    }

class OpeningManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OpeningManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._cache = {}
            self.tts = None  # 延迟初始化 TTS
            self._audio_cache = {}  # 音频缓存
            util.log(1, "[初始化] 开场白管理器初始化完成")
    
    def _init_tts(self):
        """延迟初始化 TTS"""
        if self.tts is None:
            from tts.siliconflow_tts import Speech
            self.tts = Speech()
            if not self.tts.connect():
                util.log(1, "[错误] TTS 初始化失败")
                return False
            return True
        return True

    def get_opening(self, command_type=None, scene_type=None):
        """获取开场白文本"""
        try:
            if command_type:
                pool = OpeningStatements.COMMANDS.get(command_type, OpeningStatements.DEFAULT)
            elif scene_type:
                pool = OpeningStatements.SCENES.get(scene_type, OpeningStatements.DEFAULT)
            else:
                pool = OpeningStatements.DEFAULT
                
            text = random.choice(pool)
            util.log(1, f"[开场白] 选择开场白: {text}")
            return text
            
        except Exception as e:
            util.log(1, f"[开场白] 获取开场白失败: {str(e)}")
            return "让本座看看..."

    def is_opening_statement(self, text):
        """判断文本是否是开场白"""
        try:
            # 检查默认开场白
            if text in OpeningStatements.DEFAULT:
                return True
                
            # 检查命令类型开场白
            for command_type in OpeningStatements.COMMANDS:
                if text in OpeningStatements.COMMANDS[command_type]:
                    return True
                    
            # 检查场景特定开场白
            for scene_type in OpeningStatements.SCENES:
                if text in OpeningStatements.SCENES[scene_type]:
                    return True
                    
            return False
            
        except Exception as e:
            util.log(1, f"[开场白] 判断开场白失败: {str(e)}")
            return False

    def get_opening_with_audio(self, command_type=None, scene_type=None):
        """获取开场白文本和对应的音频"""
        try:
            # 获取开场白文本
            text = self.get_opening(command_type, scene_type)
            
            # 生成缓存文件名
            cache_file = f'./samples/opening_{hash(text)}_opening.wav'
            
            # 检查缓存
            if os.path.exists(cache_file):
                util.log(1, f"[开场白] 使用缓存音频: {cache_file}")
                return text, cache_file
            
            # 初始化 TTS
            if not self._init_tts():
                return text, None
            
            # 生成音频
            audio_path = self.tts.to_sample(text, style="lyrical")  # 使用抒情风格
            
            if audio_path:
                # 重命名为缓存文件
                try:
                    if os.path.exists(cache_file):
                        os.remove(cache_file)
                    os.rename(audio_path, cache_file)
                    util.log(1, f"[开场白] 生成新音频: {cache_file}")
                    return text, cache_file
                except Exception as e:
                    util.log(1, f"[开场白] 文件重命名失败: {str(e)}")
                    return text, audio_path
            
            return text, None
            
        except Exception as e:
            util.log(1, f"[开场白] 获取开场白音频失败: {str(e)}")
            return text, None

    def cleanup_cache(self):
        """清理过期的音频缓存"""
        try:
            cache_dir = './samples'
            if not os.path.exists(cache_dir):
                return
                
            current_time = time.time()
            for file in os.listdir(cache_dir):
                if file.startswith('opening_'):
                    file_path = os.path.join(cache_dir, file)
                    # 检查文件修改时间，超过7天的删除
                    if current_time - os.path.getmtime(file_path) > 7 * 24 * 3600:
                        try:
                            os.remove(file_path)
                            util.log(1, f"[开场白] 清理过期缓存: {file}")
                        except Exception as e:
                            util.log(1, f"[开场白] 清理缓存失败: {str(e)}")
                            
        except Exception as e:
            util.log(1, f"[开场白] 清理缓存异常: {str(e)}") 