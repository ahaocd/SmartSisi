#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Suno API 测试脚本 - 测试使用chirp-v4模型生成歌曲
"""

import os
import sys
import logging
import json
import argparse

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("suno_test")

# 添加父目录到sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
sys.path.append(current_dir)

# 导入SunoAPI类
from suno_api import SunoAPI

# 默认设置 - 请替换为您自己的API密钥进行测试
DEFAULT_API_KEY = "sk-rYH5680dd44lS4VEnFWPOy7Q0xm1Sgtxo4DSeaHwLPjF9mTl"
DEFAULT_BASE_URL = "https://api.openxs.top"

def test_suno_api_v4(api_key=None, base_url=None, model="chirp-v4"):
    """测试使用chirp-v4模型的Suno API调用"""
    logger.info("开始测试Suno API (%s模型)...", model)
    
    # 创建SunoAPI实例，直接传入API密钥和BASE_URL
    api = SunoAPI(api_key=api_key or DEFAULT_API_KEY, 
                 base_url=base_url or DEFAULT_BASE_URL)
    
    # 修改默认模型
    api.default_model = model
    
    # 测试连接
    logger.info("测试API连接...")
    connection_test = api.test_connection()
    logger.info(f"连接测试结果: {connection_test}")
    
    # 使用灵感模式生成音乐
    logger.info("使用灵感模式生成音乐...")
    inspiration_result = api.generate_music_inspiration(
        description="创作一首简短的轻松欢快的流行歌曲，适合早晨聆听",
        make_instrumental=False,
        mv=model  # 明确指定使用模型
    )
    
    logger.info(f"灵感模式结果状态: {inspiration_result.get('code')}")
    if inspiration_result.get('code') == 'success':
        logger.info("灵感模式音乐生成成功")
        logger.info(f"返回数据: {json.dumps(inspiration_result.get('data'), indent=2)}")
    else:
        logger.error(f"灵感模式生成失败: {inspiration_result.get('message')}")
    
    return inspiration_result

if __name__ == "__main__":
    # 添加命令行参数解析
    parser = argparse.ArgumentParser(description="Suno API 测试工具")
    parser.add_argument("--key", type=str, help="API密钥")
    parser.add_argument("--url", type=str, help="API基础URL")
    parser.add_argument("--model", type=str, default="chirp-v4", help="使用的模型版本")
    args = parser.parse_args()
    
    # 优先使用命令行参数，其次使用环境变量，最后使用默认值
    api_key = args.key or os.environ.get("SUNO_API_KEY", DEFAULT_API_KEY)
    base_url = args.url or os.environ.get("SUNO_BASE_URL", DEFAULT_BASE_URL)
    model = args.model
    
    print(f"使用API密钥: {api_key[:5]}...{api_key[-5:]}")
    print(f"使用基础URL: {base_url}")
    print(f"使用模型: {model}")
    
    result = test_suno_api_v4(api_key, base_url, model)
    print("\n测试完成！")
    print(f"结果状态: {result.get('code')}")
    if result.get('code') != 'success':
        print(f"错误信息: {result.get('message')}") 