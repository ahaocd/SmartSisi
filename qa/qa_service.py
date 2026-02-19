#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QA服务模块 - 问答匹配和处理
优化版本：更清晰的代码结构，更好的错误处理
"""

import os
import csv
import difflib
import random
import json
import time
import shlex
import subprocess
import requests
from collections import OrderedDict
from utils import config_util as cfg
from scheduler.thread_manager import MyThread
from utils import util


class QAService:
    """问答服务类 - 处理问答匹配、人设问答、命令执行等"""
    
    def __init__(self):
        """初始化QA服务"""
        # TTS缓存配置
        self.__tts_cache = OrderedDict()
        self.__max_cache_size = 100
        
        # 匹配参数配置
        self.similarity_threshold = 0.7  # 相似度阈值，降低到70%以匹配更多QA变体
        self.contains_bonus = 0.4        # 包含匹配加成
        
        # 从配置读取播放设置
        self.playsound = self._get_play_setting()
        
        # 初始化关键词配置
        self._init_keywords()
        
        util.log(1, f"[QA服务] 初始化完成，播放设置: {self.playsound}")

        # ESP32设备配置
        self.esp32_ip = "172.20.10.2"
        self.esp32_base_url = f"http://{self.esp32_ip}"

    def _get_play_setting(self):
        """安全获取播放设置"""
        try:
            return cfg.config.get('interact', {}).get('playsound', 'true').lower() == 'true'
        except Exception:
            return True  # 默认开启播放

    def get_esp32_photo(self):
        """调用ESP32拍照获取图片（ESP32会自动显示）"""
        try:
            # 调用ESP32拍照接口（ESP32会自动显示到屏幕）
            response = requests.post(f"{self.esp32_base_url}/camera/snap", timeout=10)

            if response.status_code == 200:
                # 保存照片到默认图片文件夹
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                photo_path = f"E:/liusisi/SmartSisi/@image/esp32_music_{timestamp}.jpg"

                # 确保目录存在
                os.makedirs(os.path.dirname(photo_path), exist_ok=True)

                with open(photo_path, 'wb') as f:
                    f.write(response.content)

                util.log(1, f"📸 ESP32拍照成功，已保存: {photo_path}")
                return photo_path
            else:
                util.log(2, f"⚠️ ESP32拍照失败: HTTP {response.status_code}")
                return None

        except Exception as e:
            util.log(2, f"⚠️ ESP32拍照异常: {str(e)}")
            return None

    def _init_keywords(self):
        """初始化关键词配置"""
        # 人设问答关键词
        self.attribute_keyword = [
            [['你叫什么名字', '你的名字是什么'], 'name'],
            [['你是男的还是女的', '你是男生还是女生', '你的性别是什么'], 'gender'],
            [['你今年多大了', '你多大了', '你今年多少岁', '你几岁了'], 'age'],
            [['你的家乡在哪', '你的家乡是什么', '你家在哪', '你住在哪'], 'birth'],
            [['你的生肖是什么', '你属什么'], 'zodiac'],
            [['你是什么座', '你是什么星座', '你的星座是什么'], 'constellation'],
            [['你是做什么的', '你的职业是什么', '你是干什么的'], 'job'],
            [['你的爱好是什么', '你有爱好吗', '你喜欢什么'], 'hobby'],
            [['联系方式', '联系你们', '怎么联系客服', '有没有客服'], 'contact']
        ]

        # 命令关键词
        self.command_keyword = [
            [['关闭', '再见', '你走吧'], 'stop'],
            [['静音', '闭嘴', '我想静静'], 'mute'],
            [['取消静音', '你在哪呢', '你可以说话了'], 'unmute'],
            [['换个性别', '换个声音'], 'changeVoice']
        ]

    def question(self, query_type, text):
        """
        处理问答请求

        Args:
            query_type (str): 查询类型 'qa'/'Persona'/'command'
            text (str): 用户输入文本

        Returns:
            tuple: (答案, 类型)
        """
        if not text or not text.strip():
            return None, None

        text = text.strip()

        # QA服务专注于业务逻辑，打断检测由上层监控器处理

        if query_type == 'qa':
            return self._handle_qa_query(text)
        elif query_type == 'Persona':
            return self._handle_persona_query(text)
        elif query_type == 'command':
            return self._handle_command_query(text)

        return None, None

    # 打断检测方法已移除，由上层监控器处理

    def _load_interrupt_config(self):
        """从music_playlist.json加载打断配置"""
        try:
            import json
            import os

            # 获取music_playlist.json路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "music_playlist.json")

            if not os.path.exists(config_path):
                util.log(2, f"[QA服务] 音乐配置文件不存在: {config_path}")
                return None

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 返回打断关键词配置
            interrupt_keywords = config.get("interrupt_keywords", {})
            if interrupt_keywords:
                util.log(1, f"[QA服务] 成功加载打断关键词配置，包含 {len(interrupt_keywords)} 种类型")
                return interrupt_keywords
            else:
                util.log(2, f"[QA服务] 配置文件中未找到interrupt_keywords")
                return None

        except Exception as e:
            util.log(2, f"[QA服务] 加载打断配置失败: {str(e)}")
            return None

    # 打断响应和决策方法已移除，由上层监控器和打断管理器处理

    def _handle_qa_query(self, text):
        """处理QA查询"""
        qa_file_path = self._get_qa_file_path()
        if not qa_file_path:
            util.log(2, "[QA服务] 无法确定QA文件路径")
            return None, None
            
        answer_dict = self._read_qna(qa_file_path)
        if not answer_dict:
            util.log(2, "[QA服务] QA数据为空")
            return None, None
            
        answer, action = self._get_keyword_match(answer_dict, text, 'qa')
        
        # 执行关联脚本（如果有的话）
        if action and action.strip():
            MyThread(target=self._run_script, args=[action]).start()
            
        # 🎯 修复：返回脚本信息，而不是固定的'qa'
        return answer, action if action else 'qa'

    def _handle_persona_query(self, text):
        """处理人设查询"""
        answer, action = self._get_keyword_match(self.attribute_keyword, text, 'Persona')
        return answer, 'Persona'

    def _handle_command_query(self, text):
        """处理命令查询"""
        answer, action = self._get_keyword_match(self.command_keyword, text, 'command')
        return answer, 'command'

    def _get_qa_file_path(self):
        """获取QA文件路径"""
        # 优先级：qa/qa.csv > 配置文件路径 > 默认路径
        qa_paths = [
            "qa/qa.csv",  # 相对路径
            os.path.join(os.path.dirname(__file__), "qa.csv"),  # 同目录
        ]
        
        # 尝试从配置获取路径
        try:
            if hasattr(cfg, 'system_config') and cfg.system_config.has_section('interact'):
                config_path = cfg.system_config.get('interact', 'qna')
                if config_path:
                    qa_paths.insert(0, config_path)
        except Exception as e:
            util.log(1, f"[QA服务] 读取配置文件路径失败: {e}")
        
        # 查找存在的文件
        for path in qa_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                util.log(1, f"[QA服务] 使用QA文件: {abs_path}")
                return abs_path
                
        util.log(2, f"[QA服务] 未找到QA文件，尝试的路径: {qa_paths}")
        return None

    def _read_qna(self, filename):
        """
        读取问答文件
        
        Args:
            filename (str): QA文件路径
            
        Returns:
            list: 问答数据列表
        """
        qna = []
        
        try:
            with open(filename, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                header = next(reader, None)
                
                if not header:
                    util.log(2, "[QA服务] QA文件为空")
                    return qna
                
                # 验证表头（宽松验证）
                if len(header) < 2:
                    util.log(2, f"[QA服务] QA文件格式错误，表头: {header}")
                    return qna
                
                row_count = 0
                for row in reader:
                    if len(row) < 2 or not row[0].strip() or not row[1].strip():
                        continue
                        
                    # 解析问题（支持逗号分隔）
                    questions = [q.strip() for q in row[0].split(',') if q.strip()]
                    
                    # 解析答案（支持|分隔的多个答案）
                    answers = [a.strip() for a in row[1].split('|') if a.strip()]
                    
                    # 解析脚本
                    script = row[2].strip() if len(row) >= 3 and row[2].strip() else None
                    
                    if questions and answers:
                        qna.append([questions, answers, script])
                        row_count += 1
                
                util.log(1, f"[QA服务] 成功读取 {row_count} 条问答对")
                
        except Exception as e:
            util.log(2, f"[QA服务] 读取QA文件失败: {e}")
            
        return qna

    def _get_keyword_match(self, keyword_dict, text, query_type):
        """
        关键词匹配算法
        
        Args:
            keyword_dict (list): 关键词字典
            text (str): 用户输入
            query_type (str): 查询类型
            
        Returns:
            tuple: (答案, 动作)
        """
        if not keyword_dict:
            return None, None
            
        candidates = []
        
        for qa in keyword_dict:
            if len(qa) < 2:
                continue
                
            for quest in qa[0]:
                similarity = self._calculate_similarity(text, quest)
                
                if similarity >= self.similarity_threshold:
                    action = qa[2] if (query_type == "qa" and len(qa) > 2) else None
                    answers = qa[1]
                    
                    # 选择答案
                    if isinstance(answers, str):
                        answer = answers
                    else:
                        answer = random.choice(answers)
                        
                    candidates.append((similarity, answer, action))

        if not candidates:
            return None, None

        # 按相似度排序，选择最佳匹配
        candidates.sort(key=lambda x: x[0], reverse=True)
        
        # 从前几个候选中随机选择
        max_candidates = max(1, int(len(candidates) * 0.3))
        top_candidates = candidates[:max_candidates]
        chosen = random.choice(top_candidates)
        
        return chosen[1], chosen[2]

    def _calculate_similarity(self, text1, text2):
        """
        计算文本相似度 - 修复版，避免不当的部分匹配
        
        Args:
            text1 (str): 用户输入文本
            text2 (str): QA库中的问题文本
            
        Returns:
            float: 相似度分数
        """
        # 基础相似度
        similarity = difflib.SequenceMatcher(None, text1, text2).quick_ratio()
        
        # 🔥 修复：更严格的匹配策略
        # 1. 完全匹配或高度相似 - 高分
        if text1 == text2 or similarity >= 0.9:
            return 1.0
        
        # 2. 精确包含匹配 - 仅当长度差异合理时才加成
        text1_len = len(text1)
        text2_len = len(text2)
        
        # 避免短词汇被长句子误匹配的问题
        if text2 in text1:  # QA问题包含在用户输入中
            length_ratio = text2_len / text1_len if text1_len > 0 else 0
            # 只有当QA问题占用户输入的足够比例时才加成
            if length_ratio >= 0.5:  # 至少占50%
                similarity += self.contains_bonus
            elif length_ratio >= 0.3 and text2_len >= 3:  # 或者至少3个字符且占30%
                similarity += self.contains_bonus * 0.5
        elif text1 in text2 and text1_len >= 3:  # 用户输入包含在QA问题中
            length_ratio = text1_len / text2_len if text2_len > 0 else 0
            if length_ratio >= 0.7:  # 用户输入至少占QA问题的70%
                similarity += self.contains_bonus * 0.7
            
        return min(similarity, 1.0)  # 确保不超过1.0

    def _run_script(self, action):
        """
        执行脚本命令

        Args:
            action (str): 脚本命令
        """
        try:
            time.sleep(0.1)  # 短暂延迟

            # 如果是Python文件，使用Python解释器执行
            if action.endswith('.py'):
                import sys
                import os

                # 🔥 修复：构建正确的脚本路径
                if action == "motor_control.py":
                    # motor_control.py在项目根目录
                    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), action)
                else:
                    # 其他脚本可能在qa目录
                    script_path = os.path.join(os.path.dirname(__file__), action)

                # 检查脚本是否存在
                if os.path.exists(script_path):
                    args = [sys.executable, script_path]
                    util.log(1, f"[QA服务] 找到脚本: {script_path}")
                else:
                    util.log(2, f"[QA服务] 脚本不存在: {script_path}")
                    return
            else:
                args = shlex.split(action)

            process = subprocess.Popen(args,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     text=True)
            util.log(1, f"[QA服务] 执行脚本: {action}")

        except Exception as e:
            util.log(2, f"[QA服务] 脚本执行失败: {e}")

    def record_qapair(self, question, answer):
        """
        记录问答对到文件
        
        Args:
            question (str): 问题
            answer (str): 答案
        """
        try:
            qa_config = cfg.config.get('interact', {})
            qa_file = qa_config.get('qna')
            
            if not qa_file or not qa_file.endswith('.csv'):
                util.log(1, '[QA服务] 未配置CSV文件，跳过记录')
                return
                
            file_exists = os.path.isfile(qa_file)
            
            with open(qa_file, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                if not file_exists:
                    writer.writerow(['问题', '答案', '脚本'])  # 写入表头
                writer.writerow([question, answer, ''])
                
            util.log(1, f'[QA服务] 问答对已记录: {question[:20]}...')
            
        except Exception as e:
            util.log(2, f'[QA服务] 记录问答对失败: {e}')

    def handle_json_tts_mapping(self, text):
        """
        处理JSON格式的TTS映射（保留兼容性）
        
        Args:
            text (str): 输入文本
            
        Returns:
            dict: TTS参数字典
        """
        try:
            if text.strip().startswith('{') and text.strip().endswith('}'):
                data = json.loads(text)
                return {
                    'text': data.get('text', ''),
                    'params': {
                        'emotion': data.get('emotion', 'normal'),
                        'speed': data.get('speed', 1.0),
                        'pitch': data.get('pitch', 0),
                        'volume': data.get('volume', 1.0)
                    },
                    'is_json': True
                }
            return {'text': text, 'is_json': False}
            
        except json.JSONDecodeError:
            return {'text': text, 'is_json': False}
        except Exception as e:
            util.log(2, f"[QA服务] JSON解析失败: {e}")
            return {'text': text, 'is_json': False}
 