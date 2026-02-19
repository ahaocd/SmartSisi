"""
正确上传 IndexTTS-2 音色
"""
import requests, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from voice_clone_flask import get_config, LEGACY_CONFIG

config = get_config()
API_KEY = config['tts'].get('api_key') or LEGACY_CONFIG.get('siliconflow_api_key', '')
BASE_URL = config['tts'].get('base_url', 'https://api.siliconflow.cn/v1')

# 你的音频和文本
AUDIO_FILE = r"E:\liusisi\1月23日_compressed.mp3"
REF_TEXT = "邪祟赶挡路,看我表笔劈碎你,严肃,宁神!最后一步不能错,红线对准眉心!法袍已正,剑诀已捏,红线连着手腕的温度,表笔间闪着冷光,现在,跟着我念,滑音,细腔里常见从高音滑到低音的下滑音,试试这样,绫罗飘起遮住日罗西，奏一回断肠的古曲"

print(f"✅ 音频文件: {AUDIO_FILE}")
print(f"✅ 参考文本: {REF_TEXT[:50]}...")

headers = {"Authorization": f"Bearer {API_KEY}"}

# 关键：上传时指定 model=IndexTeam/IndexTTS-2
print("\n" + "="*60)
print("上传音色到 IndexTTS-2")
print("="*60)

with open(AUDIO_FILE, 'rb') as f:
    files = {"file": f}
    data = {
        "model": "IndexTeam/IndexTTS-2",  # 关键！
        "customName": "liusisi-index-20250123",
        "text": REF_TEXT
    }
    
    print("⏳ 上传中...")
    resp = requests.post(
        f"{BASE_URL}/uploads/audio/voice",
        headers=headers,
        files=files,
        data=data,
        timeout=60,
        proxies={"http": None, "https": None}
    )
    
    print(f"状态码: {resp.status_code}")
    
    if resp.status_code == 200:
        result = resp.json()
        voice_uri = result.get('uri', '')
        print(f"✅ 上传成功！")
        print(f"   URI: {voice_uri}")
        
        # 立即测试
        print("\n" + "="*60)
        print("测试 IndexTTS-2")
        print("="*60)
        
        test_text = "一个AI配音成本降低100倍的办法"
        print(f"测试文本: {test_text}")
        
        payload = {
            "model": "IndexTeam/IndexTTS-2",
            "input": test_text,
            "voice": "",
            "references": [
                {
                    "audio": voice_uri,
                    "text": REF_TEXT
                }
            ],
            "response_format": "mp3",
            "sample_rate": 32000,
            "speed": 1.0,
            "max_tokens": 2048
        }
        
        headers2 = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        print("⏳ 生成中...")
        resp2 = requests.post(
            f"{BASE_URL}/audio/speech",
            headers=headers2,
            json=payload,
            timeout=60,
            proxies={"http": None, "https": None}
        )
        
        if resp2.status_code == 200:
            output_file = Path(__file__).parent / "voice_clones" / "test_index_success.mp3"
            with open(output_file, 'wb') as f:
                f.write(resp2.content)
            print(f"✅ IndexTTS-2 成功！")
            print(f"   音频大小: {len(resp2.content)} 字节")
            print(f"   保存位置: {output_file}")
        else:
            print(f"❌ IndexTTS-2 失败: {resp2.text}")
    else:
        print(f"❌ 上传失败: {resp.text}")
