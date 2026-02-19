#!/usr/bin/env python
"""
测试SEO元数据提取和图片上传功能
"""

import os
import sys
import re

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试内容 - 模拟实际的markdown内容
TEST_CONTENT = """# 绕过Google账号注册二维码验证的完整解决方案

![](/static/screenshots/screenshot_000_d135e41b-5a04-4405-bbce-9e3d4dad3abc.jpg)

## 问题背景：Google账号注册的新限制

近年来，Google加强了账号注册的安全验证机制。

![](/static/screenshots/screenshot_001_f92ac36d-19f3-43ee-bcfb-388738de4f40.jpg)

### 风控升级解析

Google的风控系统经历了多重升级。

---

---SEO-METADATA---
seo_title: 绕过Google注册二维码验证的3种有效方法
seo_description: 详细教程教你如何使用安卓模拟器绕过Google账号注册的二维码验证，包含环境配置、IP设置和高级技巧，成功率100%。
focus_keyword: Google注册二维码验证
keywords: Google账号注册,二维码验证,蓝叠模拟器,虚拟环境,Google风控,账号注册限制,海外IP
---END-SEO---"""


def test_seo_extraction():
    """测试SEO元数据提取"""
    print("=" * 60)
    print("测试SEO元数据提取")
    print("=" * 60)
    
    # 导入提取函数
    from app.routers.wordpress import extract_seo_metadata
    
    clean_content, seo_data = extract_seo_metadata(TEST_CONTENT)
    
    print("\n提取的SEO数据:")
    for key, value in seo_data.items():
        print(f"  {key}: {value}")
    
    print(f"\n清理后内容是否包含SEO块: {'---SEO-METADATA---' in clean_content}")
    print(f"清理后内容是否包含---END-SEO---: {'---END-SEO---' in clean_content}")
    
    if '---SEO-METADATA---' not in clean_content and seo_data.get('seo_title'):
        print("\n✓ SEO提取测试通过!")
        return True
    else:
        print("\n✗ SEO提取测试失败!")
        print(f"\n清理后内容末尾:\n{clean_content[-200:]}")
        return False


def test_image_pattern():
    """测试图片路径匹配"""
    print("\n" + "=" * 60)
    print("测试图片路径匹配")
    print("=" * 60)
    
    # 测试各种图片格式
    test_cases = [
        '![](/static/screenshots/screenshot_000_xxx.jpg)',
        '![alt text](/static/screenshots/screenshot_001_yyy.jpg)',
        '![](static/screenshots/screenshot_002_zzz.jpg)',
        'http://localhost:8483/static/screenshots/screenshot_003_aaa.jpg',
        '<img src="/static/screenshots/screenshot_004_bbb.jpg">',
    ]
    
    # 使用与wordpress_publisher.py相同的模式
    patterns = [
        r'!\[[^\]]*\]\((?:http://(?:localhost|127\.0\.0\.1):\d+)?/?static/screenshots/([^"\'\)\s]+)\)',
        r'(?:http://(?:localhost|127\.0\.0\.1):\d+)?/static/screenshots/([^"\'\)\s]+)',
        r'src=["\'](?:http://(?:localhost|127\.0\.0\.1):\d+)?/?static/screenshots/([^"\'\s]+)["\']',
    ]
    
    all_pass = True
    for test in test_cases:
        found = False
        for pattern in patterns:
            matches = re.findall(pattern, test)
            if matches:
                print(f"✓ 匹配成功: {test}")
                print(f"  提取的文件名: {matches}")
                found = True
                break
        if not found:
            print(f"✗ 匹配失败: {test}")
            all_pass = False
    
    # 测试实际内容
    print("\n测试实际内容中的图片提取:")
    all_filenames = set()
    for pattern in patterns:
        matches = re.findall(pattern, TEST_CONTENT)
        all_filenames.update(matches)
    
    print(f"提取到的图片文件名: {all_filenames}")
    
    if len(all_filenames) >= 2:
        print("\n✓ 图片匹配测试通过!")
        return True
    else:
        print("\n✗ 图片匹配测试失败!")
        return False


def test_full_publish_flow():
    """测试完整发布流程（不实际发布）"""
    print("\n" + "=" * 60)
    print("测试完整发布流程")
    print("=" * 60)
    
    from dotenv import load_dotenv
    load_dotenv()
    
    from app.services.wordpress_publisher import create_publisher_from_env
    from app.routers.wordpress import extract_seo_metadata, convert_image_urls, remove_screenshot_placeholders
    
    # 1. 提取SEO
    content, seo_data = extract_seo_metadata(TEST_CONTENT)
    print(f"1. SEO提取: {seo_data.get('seo_title', 'N/A')}")
    
    # 2. 转换图片URL
    backend_url = "http://localhost:8483"
    content = convert_image_urls(content, backend_url)
    print(f"2. 图片URL转换完成")
    
    # 3. 移除截图占位符
    content = remove_screenshot_placeholders(content)
    print(f"3. 截图占位符移除完成")
    
    # 4. 创建发布器
    publisher = create_publisher_from_env()
    print(f"4. 发布器创建成功, 站点: {publisher.config.site_url}")
    
    # 5. 测试图片处理（不实际上传）
    print(f"5. 内容中的图片路径:")
    img_pattern = r'!\[[^\]]*\]\(([^)]+)\)'
    images = re.findall(img_pattern, content)
    for img in images:
        print(f"   - {img}")
    
    print("\n✓ 完整流程测试通过!")
    return True


if __name__ == "__main__":
    print("BiliNote WordPress 发布功能测试")
    print("=" * 60)
    
    results = []
    
    # 测试SEO提取
    results.append(("SEO提取", test_seo_extraction()))
    
    # 测试图片匹配
    results.append(("图片匹配", test_image_pattern()))
    
    # 测试完整流程
    try:
        results.append(("完整流程", test_full_publish_flow()))
    except Exception as e:
        print(f"\n完整流程测试出错: {e}")
        results.append(("完整流程", False))
    
    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print(f"\n总体结果: {'全部通过!' if all_passed else '存在失败项'}")
