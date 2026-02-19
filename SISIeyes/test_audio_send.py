#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试音频发送到ESP32设备
"""

import requests
import time

def test_tone_audio():
    """测试音调播放"""
    esp32_url = "http://172.20.10.2/cmd"  # 你的ESP32 IP
    
    print("🔊 测试音调播放...")
    
    # 测试440Hz音调
    response = requests.post(esp32_url, data="audio:tone:440")
    print(f"440Hz音调: {response.text}")
    
    time.sleep(2)
    
    # 测试880Hz音调
    response = requests.post(esp32_url, data="audio:tone:880")
    print(f"880Hz音调: {response.text}")
    
    time.sleep(2)
    
    # 测试停止
    response = requests.post(esp32_url, data="audio:stop")
    print(f"停止音频: {response.text}")

def test_wav_file():
    """测试WAV文件发送（当前不支持）"""
    print("❌ 当前ESP32不支持WAV文件播放")
    print("   只支持音调播放: audio:tone:频率")

if __name__ == "__main__":
    print("🎵 ESP32音频测试")
    print("=" * 30)
    
    try:
        test_tone_audio()
        test_wav_file()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
