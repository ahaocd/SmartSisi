"""
ASR引擎管理器 - 统一的语音识别接口
支持FunASR、阿里云NLS等多种ASR引擎
"""

import os
import sys
import logging
from typing import Optional, Union
from utils import config_util as cfg

# 配置日志
logger = logging.getLogger(__name__)

class ASREngine:
    """ASR引擎基类"""
    
    def __init__(self):
        self.engine_type = None
        self.initialized = False
    
    def recognize(self, audio_data: bytes) -> str:
        """识别音频数据"""
        raise NotImplementedError
    
    def recognize_file(self, file_path: str) -> str:
        """识别音频文件"""
        raise NotImplementedError

class FunASREngine(ASREngine):
    """FunASR引擎实现"""
    
    def __init__(self):
        super().__init__()
        self.engine_type = "funasr"
        self.funasr_client = None
        self._initialize()
    
    def _initialize(self):
        """初始化FunASR引擎"""
        try:
            from .funasr import FunASR
            self.funasr_client = FunASR("User")
            self.initialized = True
            logger.info("✅ FunASR引擎初始化成功")
        except Exception as e:
            logger.error(f"❌ FunASR引擎初始化失败: {e}")
            self.initialized = False
    
    def recognize(self, audio_data: bytes) -> str:
        """识别音频数据"""
        if not self.initialized:
            return ""
        
        try:
            # 将音频数据保存为临时文件
            import tempfile
            import wave
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                # 写入WAV文件头和数据
                with wave.open(temp_file.name, 'wb') as wav_file:
                    wav_file.setnchannels(1)  # 单声道
                    wav_file.setsampwidth(2)  # 16位
                    wav_file.setframerate(16000)  # 16kHz采样率
                    wav_file.writeframes(audio_data)
                
                # 使用文件识别
                result = self.recognize_file(temp_file.name)

                # 🎯 修复：不删除临时文件，让主程序统一清理
                # os.unlink(temp_file.name)  # 注释掉，避免音频分析时文件不存在
                
                return result
                
        except Exception as e:
            logger.error(f"❌ FunASR音频识别失败: {e}")
            return ""
    
    def recognize_file(self, file_path: str) -> str:
        """识别音频文件"""
        if not self.initialized:
            return ""
        
        try:
            if not os.path.exists(file_path):
                logger.warning(f"⚠️ 音频文件不存在: {file_path}")
                return ""
            
            # 使用FunASR客户端识别
            if hasattr(self.funasr_client, 'recognize_file'):
                result = self.funasr_client.recognize_file(file_path)
            else:
                # 备用方法：通过WebSocket发送文件
                result = self._recognize_via_websocket(file_path)
            
            logger.info(f"✅ FunASR识别结果: {result}")
            return result if result else ""
            
        except Exception as e:
            logger.error(f"❌ FunASR文件识别失败: {e}")
            return ""
    
    def _recognize_via_websocket(self, file_path: str) -> str:
        """通过WebSocket识别音频文件"""
        try:
            # 这里应该实现WebSocket客户端逻辑
            # 连接到FunASR服务器 (127.0.0.1:10197)
            import websockets
            import asyncio
            import json
            
            async def recognize_async():
                uri = f"ws://{cfg.local_asr_ip}:{cfg.local_asr_port}"
                
                try:
                    async with websockets.connect(uri) as websocket:
                        # 发送音频文件路径或数据
                        message = {
                            "type": "recognize_file",
                            "file_path": file_path
                        }
                        await websocket.send(json.dumps(message))
                        
                        # 接收识别结果
                        response = await websocket.recv()
                        result_data = json.loads(response)
                        
                        return result_data.get("text", "")
                        
                except Exception as e:
                    logger.error(f"❌ WebSocket识别失败: {e}")
                    return ""
            
            # 运行异步识别
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(recognize_async())
            loop.close()
            
            return result
            
        except Exception as e:
            logger.error(f"❌ WebSocket识别异常: {e}")
            return ""

class AliNLSEngine(ASREngine):
    """阿里云NLS引擎实现"""
    
    def __init__(self):
        super().__init__()
        self.engine_type = "ali"
        self.ali_client = None
        self._initialize()
    
    def _initialize(self):
        """初始化阿里云NLS引擎"""
        try:
            from .ali_nls import ALiNls
            self.ali_client = ALiNls()
            self.initialized = True
            logger.info("✅ 阿里云NLS引擎初始化成功")
        except Exception as e:
            logger.error(f"❌ 阿里云NLS引擎初始化失败: {e}")
            self.initialized = False
    
    def recognize(self, audio_data: bytes) -> str:
        """识别音频数据"""
        if not self.initialized:
            return ""
        
        try:
            # 阿里云NLS的音频识别逻辑
            result = self.ali_client.recognize(audio_data)
            return result if result else ""
        except Exception as e:
            logger.error(f"❌ 阿里云NLS音频识别失败: {e}")
            return ""
    
    def recognize_file(self, file_path: str) -> str:
        """识别音频文件"""
        if not self.initialized:
            return ""
        
        try:
            # 读取文件并识别
            with open(file_path, 'rb') as f:
                audio_data = f.read()
            return self.recognize(audio_data)
        except Exception as e:
            logger.error(f"❌ 阿里云NLS文件识别失败: {e}")
            return ""

# 全局ASR引擎实例
_asr_engine: Optional[ASREngine] = None

def get_asr_engine() -> ASREngine:
    """获取ASR引擎实例"""
    global _asr_engine
    
    if _asr_engine is None:
        # 根据配置选择ASR引擎
        asr_mode = getattr(cfg, 'ASR_mode', 'funasr')
        
        logger.info(f"🎤 正在初始化ASR引擎: {asr_mode}")
        
        if asr_mode == "funasr":
            _asr_engine = FunASREngine()
        elif asr_mode == "ali":
            _asr_engine = AliNLSEngine()
        else:
            logger.warning(f"⚠️ 未知的ASR模式: {asr_mode}，使用FunASR作为默认")
            _asr_engine = FunASREngine()
        
        if not _asr_engine.initialized:
            logger.error("❌ ASR引擎初始化失败，语音识别功能不可用")
    
    return _asr_engine

def reset_asr_engine():
    """重置ASR引擎（用于配置更改后重新初始化）"""
    global _asr_engine
    _asr_engine = None
    logger.info("🔄 ASR引擎已重置")

# 兼容性函数
def recognize_audio(audio_data: bytes) -> str:
    """识别音频数据（兼容性函数）"""
    engine = get_asr_engine()
    return engine.recognize(audio_data)

def recognize_audio_file(file_path: str) -> str:
    """识别音频文件（兼容性函数）"""
    engine = get_asr_engine()
    return engine.recognize_file(file_path)
