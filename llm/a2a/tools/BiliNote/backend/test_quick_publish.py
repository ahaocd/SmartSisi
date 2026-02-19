"""快速测试批量发布功能"""
import requests
import json

API_BASE = "http://localhost:8483"

def test_batch_publish():
    """测试批量生成+发布"""
    print("=" * 60)
    print("测试批量生成+发布")
    print("=" * 60)
    
    # 测试视频
    video_url = "https://www.youtube.com/watch?v=P3E2Ff8DeFo"
    
    # 先获取模型列表
    print("\n1. 获取模型列表...")
    resp = requests.get(f"{API_BASE}/api/model_list")
    result = resp.json()
    models = result.get('data', [])
    print(f"   可用模型: {[m['model_name'] for m in models]}")
    
    if not models:
        print("   ❌ 没有可用模型!")
        return
    
    # 优先选择 deepseek 或 gpt-4o-mini
    model = None
    for m in models:
        if 'deepseek' in m['model_name'].lower() or 'gpt-4o-mini' in m['model_name'].lower():
            model = m
            break
    if not model:
        model = models[0]
    print(f"   使用模型: {model['model_name']} (provider: {model['provider_id']})")
    
    # 发起批量请求
    print(f"\n2. 发起批量生成+发布请求...")
    print(f"   视频: {video_url}")
    
    payload = {
        "video_urls": [video_url],
        "platform": "youtube",
        "quality": "medium",
        "model_name": model['model_name'],
        "provider_id": model['provider_id'],
        "format": ["screenshot", "seo"],
        "style": "normal",
        "extras": "",
        "auto_publish": True
    }
    
    print(f"   请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    resp = requests.post(
        f"{API_BASE}/api/batch_generate_publish",
        json=payload,
        timeout=300
    )
    
    print(f"\n3. 响应状态: {resp.status_code}")
    result = resp.json()
    print(f"   响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
    
    if result.get('status') == 'started':
        print("\n✅ 批量任务已启动!")
        print("   后台正在处理，请查看后端日志...")
    else:
        print(f"\n❌ 启动失败: {result}")

if __name__ == "__main__":
    test_batch_publish()
