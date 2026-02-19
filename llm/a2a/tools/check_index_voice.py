"""
检查 IndexTTS-2 上传的音色详情
"""
import requests, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from voice_clone_flask import get_config, LEGACY_CONFIG

config = get_config()
API_KEY = config['tts'].get('api_key') or LEGACY_CONFIG.get('siliconflow_api_key', '')
BASE_URL = config['tts'].get('base_url', 'https://api.siliconflow.cn/v1')

headers = {"Authorization": f"Bearer {API_KEY}"}

resp = requests.get(f"{BASE_URL}/audio/voice/list", headers=headers, timeout=30, proxies={"http": None, "https": None})

if resp.status_code == 200:
    voices = resp.json().get('result', [])
    
    print("查找 IndexTTS-2 音色...")
    for v in voices:
        if 'index' in v.get('customName', '').lower():
            print(f"\n音色: {v.get('customName')}")
            print(f"  URI: {v.get('uri')}")
            print(f"  模型: {v.get('model', 'N/A')}")
            print(f"  文本: {v.get('text', '')[:50]}...")
            print(f"  URL: {v.get('url', 'N/A')}")
            print(f"  audioUrl: {v.get('audioUrl', 'N/A')}")
            print(f"  所有字段:")
            for key, value in v.items():
                if key not in ['customName', 'uri', 'model', 'text']:
                    print(f"    {key}: {value}")
else:
    print(f"❌ 失败: {resp.text}")
