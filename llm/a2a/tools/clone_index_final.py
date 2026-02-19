"""
用你的音频和正确文本克隆 IndexTTS-2
"""
import requests, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from voice_clone_flask import get_config, LEGACY_CONFIG

config = get_config()
API_KEY = config['tts'].get('api_key') or LEGACY_CONFIG.get('siliconflow_api_key', '')
BASE_URL = config['tts'].get('base_url', 'https://api.siliconflow.cn/v1')

# 你的音频和正确文本
AUDIO_FILE = r"E:\liusisi\1月23日_compressed.mp3"
REF_TEXT = "邪祟赶挡路,看我表笔劈碎你,严肃,宁神!最后一步不能错,红线对准眉心!法袍已正,剑诀已捏,红线连着手腕的温度,表笔间闪着冷光,现在,跟着我念,滑音,细腔里常见从高音滑到低音的下滑音,试试这样,绫罗飘起遮住日罗西，奏一回断肠的古曲"

print(f"✅ 音频文件: {AUDIO_FILE}")
print(f"✅ 参考文本: {REF_TEXT[:50]}...")
print(f"✅ 文件大小: {Path(AUDIO_FILE).stat().st_size / 1024:.2f} KB")

headers = {"Authorization": f"Bearer {API_KEY}"}

# 步骤1：上传音色
print("\n" + "="*60)
print("步骤1: 上传音色到服务器")
print("="*60)

with open(AUDIO_FILE, 'rb') as f:
    files = {"file": f}
    data = {
        "model": "FunAudioLLM/CosyVoice2-0.5B",
        "customName": "liusisi-geci-20250123",
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
    
    if resp.status_code == 200:
        result = resp.json()
        voice_uri = result.get('uri', '')
        print(f"✅ 上传成功！")
        print(f"   URI: {voice_uri}")
    else:
        print(f"❌ 上传失败: {resp.text}")
        exit(1)

# 步骤2：测试 IndexTTS-2
print("\n" + "="*60)
print("步骤2: 测试 IndexTTS-2")
print("="*60)

test_texts = [
    "一个AI配音成本降低100倍的办法",
    "今天天气真好，适合出去走走",
    "Hello, this is a test of English speech"
]

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

for i, test_text in enumerate(test_texts, 1):
    print(f"\n测试 {i}: {test_text}")
    
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
    
    try:
        print("   ⏳ 生成中...")
        resp = requests.post(
            f"{BASE_URL}/audio/speech",
            headers=headers,
            json=payload,
            timeout=60,
            proxies={"http": None, "https": None}
        )
        
        if resp.status_code == 200:
            output_file = Path(__file__).parent / "voice_clones" / f"test_index_final_{i}.mp3"
            with open(output_file, 'wb') as f:
                f.write(resp.content)
            print(f"   ✅ 成功！")
            print(f"   音频大小: {len(resp.content)} 字节")
            print(f"   保存位置: {output_file}")
        else:
            print(f"   ❌ 失败: {resp.text}")
    except Exception as e:
        print(f"   ❌ 错误: {e}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
print(f"""
✅ 音色已上传: {voice_uri}
✅ 参考文本: {REF_TEXT[:50]}...

如果 IndexTTS-2 还是失败，说明：
1. 你的音频是歌曲（有旋律），IndexTTS-2 不支持
2. 需要录制普通说话的音频（不是唱歌）
3. CosyVoice2 可以正常使用你的音色
""")
