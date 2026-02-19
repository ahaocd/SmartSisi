#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
增强版音乐生成工具 - 解决cowbell重复问题，增加随机性

本文件是音乐工具的增强版，它包含以下改进：
1. 使用随机化的Phonk提示词生成，避免重复内容
2. 添加算命大师和道士元素
3. 支持从对话历史中提取关键词
4. 增加提示词和歌词的随机性
5. 保持与原始MusicGeneratorTool接口兼容

音乐生成模式说明：
- 灵感模式：只使用prompt参数，由AI根据提示词生成完整音乐
- 自定义模式：使用lyrics、title和tags参数，可以精确控制生成内容
- 双重生成模式(dual_generation_with_selective_play)：同时使用灵感和自定义两种模式，选择最佳结果播放
"""

import sys
import os
import importlib.util
import logging
from typing import Dict, List, Any, Optional

# 导入当前目录的模块
try:
    # 使用显式的相对导入
    from .music_integration import get_enhanced_music_params
    enhanced_module_available = True
except ImportError as e:
    enhanced_module_available = False
    print(f"警告: 增强版音乐生成模块导入失败: {str(e)}，将使用原始模块")

# 设置日志
logger = logging.getLogger("music_tool_enhanced")

# 导入原始音乐工具模块
try:
    # 获取当前目录和父目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    # 构建原始music_tool.py的路径
    music_tool_path = os.path.join(parent_dir, 'music_tool.py')
    spec = importlib.util.spec_from_file_location("music_tool", music_tool_path)
    music_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(music_tool)
    
    # 获取原始的音乐生成工具类
    OriginalMusicGeneratorTool = music_tool.MusicGeneratorTool
    original_create_music_now = music_tool.create_music_now
    original_run_music_workflow = music_tool.run_music_workflow
    
    logger.info("成功导入原始音乐工具模块")
except Exception as e:
    logger.error(f"导入原始音乐工具模块失败: {str(e)}")
    raise ImportError(f"无法导入原始音乐工具模块: {str(e)}")

class EnhancedMusicGeneratorTool(OriginalMusicGeneratorTool):
    """增强版音乐生成工具，添加随机性和算命元素"""
    
    def __init__(self, api_key: str = None, *args, **kwargs):
        """初始化增强版音乐生成工具"""
        super().__init__(api_key, *args, **kwargs)
        self.using_enhanced_module = enhanced_module_available
        logger.info(f"初始化增强版音乐生成工具，增强模块可用: {self.using_enhanced_module}")
    
    def _generate_enhanced_phonk_prompt(self, query: str, emotion_state: str = "伤感") -> str:
        """
        生成强化Phonk特征的专业提示词 - 增强版，添加随机性
        
        Args:
            query: 用户查询
            emotion_state: 情感状态
            
        Returns:
            str: 强化Phonk特征的提示词
        """
        # 如果增强模块可用，使用增强模块
        if self.using_enhanced_module:
            try:
                # 获取增强版参数
                enhanced_params = get_enhanced_music_params(
                    query=query,
                    emotion_state=emotion_state,
                    include_fortune=True
                )
                return enhanced_params["prompt"]
            except Exception as e:
                logger.error(f"使用增强模块生成提示词失败: {str(e)}")
                # 失败时回退到原始方法
                return super()._generate_enhanced_phonk_prompt(query, emotion_state)
        else:
            # 使用原始方法
            return super()._generate_enhanced_phonk_prompt(query, emotion_state)
    
    def _generate_simple_lyrics(self, query: str, emotion_state: str = None) -> str:
        """
        从查询和情感状态生成简单的歌词 - 增强版，添加随机性
        
        Args:
            query: 用户查询
            emotion_state: 情感状态
            
        Returns:
            str: 生成的简单歌词
        """
        # 如果增强模块可用，使用增强模块
        if self.using_enhanced_module:
            try:
                # 获取增强版参数
                enhanced_params = get_enhanced_music_params(
                    query=query,
                    emotion_state=emotion_state,
                    include_fortune=True
                )
                return enhanced_params["lyrics"]
            except Exception as e:
                logger.error(f"使用增强模块生成歌词失败: {str(e)}")
                # 失败时回退到原始方法
                return super()._generate_simple_lyrics(query, emotion_state)
        else:
            # 使用原始方法
            return super()._generate_simple_lyrics(query, emotion_state)
    
    def run(self, query: str, task_id: str = None, history: List[Dict] = None, time_info: Dict = None, 
            emotion_state: str = None, mode: str = "dual_generation_with_selective_play", 
            lyrics: str = None, title: str = None, tags: str = None):
        """
        运行音乐生成任务 - 增强版，添加随机性和算命元素
        
        Args:
            query: 用户查询
            task_id: 任务ID，如果为空则自动生成
            history: 对话历史
            time_info: 时间信息
            emotion_state: 情感状态
            mode: 生成模式，可选值：
                  - "inspiration"：灵感模式，只使用prompt参数
                  - "custom"：自定义模式，使用lyrics、title和tags参数
                  - "dual_generation_with_selective_play"：双重生成模式，同时使用两种方式并选择最佳结果
            lyrics: 自定义模式歌词内容
            title: 自定义模式歌曲标题
            tags: 自定义模式风格标签
            
        Returns:
            Dict: 任务信息
        """
        # 如果增强模块可用且没有提供自定义参数，使用增强模块生成参数
        if self.using_enhanced_module and not (lyrics and title and tags):
            try:
                # 获取增强版参数
                enhanced_params = get_enhanced_music_params(
                    query=query,
                    history=history,
                    time_info=time_info,
                    emotion_state=emotion_state,
                    include_fortune=True
                )
                
                # 更新参数
                if not lyrics:
                    lyrics = enhanced_params["lyrics"]
                if not title:
                    title = enhanced_params["title"]
                if not tags:
                    tags = enhanced_params["tags"]
                if not emotion_state:
                    emotion_state = enhanced_params["emotion_state"]
                
                logger.info(f"使用增强版参数: 标题={title}, 歌词长度={len(lyrics)}, 标签={tags[:30]}...")
            except Exception as e:
                logger.error(f"使用增强模块生成参数失败: {str(e)}")
        
        # 调用父类方法处理实际生成
        return super().run(
            query=query,
            task_id=task_id,
            history=history,
            time_info=time_info,
            emotion_state=emotion_state,
            mode=mode,
            lyrics=lyrics,
            title=title,
            tags=tags
        )

# 替代原始的一键生成函数
def enhanced_create_music_now(query: str = "创作一首女声Phonk音乐", wait_timeout: int = 300) -> dict:
    """
    增强版一键音乐生成工作流
    
    输入文本命令，自动完成：生成→轮询→下载→播放
    增加了随机性和算命元素
    
    注意：
    - 灵感模式使用prompt参数（生成提示词），AI完全控制音乐生成
    - 自定义模式使用lyrics（歌词）、title（标题）和tags（标签）参数，更精确控制生成内容
    - 双重生成模式同时使用两种方式并选择最佳结果
    
    Args:
        query: 音乐生成指令，例如："创作一首女声Phonk音乐"
        wait_timeout: 最大等待时间（秒），默认5分钟
        
    Returns:
        dict: 完整结果
    """
    # 创建增强版工具实例
    generator = EnhancedMusicGeneratorTool()
    
    # 启动双重生成任务
    task = generator.run(
        query=query,
        emotion_state="伤感",  # 默认情感
        mode="dual_generation_with_selective_play"
    )
    
    # 后续代码与原始函数相同
    task_id = task.get('task_id')
    if not task_id:
        return {
            "status": "FAILED",
            "error": "任务创建失败"
        }
    
    # 使用原始函数的轮询和等待逻辑
    return original_create_music_now(query, wait_timeout)

# 替代原始的工作流函数
def enhanced_run_music_workflow(query: str, history: List[Dict] = None, 
                               time_info: Dict = None, emotion_state: str = None):
    """
    增强版音乐生成工作流，添加随机性和算命元素
    
    Args:
        query: 用户查询
        history: 对话历史
        time_info: 时间信息
        emotion_state: 情感状态
        
    Returns:
        Dict: 结果信息
    """
    # 创建增强版工具实例
    generator = EnhancedMusicGeneratorTool()
    
    # 启动任务
    task = generator.run(
        query=query,
        history=history,
        time_info=time_info,
        emotion_state=emotion_state,
        mode="dual_generation_with_selective_play"
    )
    
    # 后续代码与原始函数相同
    return original_run_music_workflow(query, history, time_info, emotion_state)

# 导出函数和类
create_music_now = enhanced_create_music_now
run_music_workflow = enhanced_run_music_workflow
MusicGeneratorTool = EnhancedMusicGeneratorTool

# 创建工具函数
def create_tool():
    """创建增强版音乐生成工具实例"""
    return EnhancedMusicGeneratorTool()

# 主函数，用于测试
if __name__ == "__main__":
    print("测试增强版音乐生成工具")
    result = create_music_now("创作一首关于算命大师的Phonk音乐")
    print(f"生成结果: {result['status']}")
    if result.get('downloaded_files'):
        print(f"下载文件: {result['downloaded_files']}")
    if result.get('played_file'):
        print(f"播放文件: {result['played_file']}") 