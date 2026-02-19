#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Suno API 配置文件
存储 API 密钥和基础 URL 等配置信息 - 按照官方文档更新
"""

import os

# 不再使用dotenv加载环境变量
# from dotenv import load_dotenv
# load_dotenv()

# API 密钥 - 使用官方文档提供的密钥
API_KEY = os.getenv("SUNO_API_KEY", "sk-rYH5680dd44lS4VEnFWPOy7Q0xm1Sgtxo4DSeaHwLPjF9mTl")

# API 基础 URL - 使用官方文档提供的URL
BASE_URL = os.getenv("SUNO_BASE_URL", "https://api.openxs.top")

# 结果保存路径 - 修改为SmartSisi项目的qa/random_generation_music目录
# 从当前位置 (SmartSisi/llm/a2a/tools/sisimusic) 向上4级到SmartSisi根目录，然后进入qa/random_generation_music
RANDOM_GENERATION_MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../qa/random_generation_music")
SAVE_DIR = os.getenv("SUNO_SAVE_DIR", os.path.abspath(RANDOM_GENERATION_MUSIC_DIR))

# 确保保存目录存在
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# 官方文档支持的模型版本
SUPPORTED_MODELS = {
    "v3.0": "chirp-v3.0",
    "v3.5": "chirp-v3.5", 
    "v4.0": "chirp-v4",
    "v4.5": "chirp-auk"
}

# 默认使用v4.5模型
DEFAULT_MODEL = "chirp-auk"
