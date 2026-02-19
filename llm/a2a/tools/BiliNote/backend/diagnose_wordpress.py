#!/usr/bin/env python3
"""
WordPress API 诊断脚本
"""

import json
import requests
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WordPress配置
WORDPRESS_URL = "https://xasia.cc"
WORDPRESS_USER = "67859543"
WORDPRESS_APP_PASSWORD = "XqXt bHFX rwL3 M5kc rDqd HXD2"
API_BASE = f"{WORDPRESS_URL}/wp-json/wp/v2"
AUTH = (WORDPRESS_USER, WORDPRESS_APP_PASSWORD)

def test_api_endpoints():
    """测试各种API端点"""
    session = requests.Session()
    session.trust_env = False
    
    tests = [
        ("WordPress根目录", f"{WORDPRESS_URL}/wp-json/"),
        ("API根目录", f"{API_BASE}/"),
        ("文章端点GET", f"{API_BASE}/posts?per_page=1"),
        ("用户信息", f"{API_BASE}/users/me"),
        ("分类信息", f"{API_BASE}/categories"),
    ]
    
    for name, url in tests:
        try:
            logger.info(f"\n=== 测试 {name} ===")
            logger.info(f"URL: {url}")
            
            response = session.get(url, auth=AUTH, timeout=10)
            logger.info(f"状态码: {response.status_code}")
            logger.info(f"响应头: {dict(response.headers)}")
            logger.info(f"响应内容: {response.text[:300]}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.info(f"JSON类型: {type(data)}")
                    if isinstance(data, list):
                        logger.info(f"列表长度: {len(data)}")
                    elif isinstance(data, dict):
                        logger.info(f"字典键: {list(data.keys())[:5]}")
                except:
                    logger.info("非JSON响应")
            
        except Exception as e:
            logger.error(f"请求失败: {e}")

def test_post_methods():
    """测试不同的POST方法"""
    session = requests.Session()
    session.trust_env = False
    
    # 简单的测试数据
    test_data = {
        "title": "API测试文章",
        "content": "这是一个测试文章",
        "status": "draft"
    }
    
    methods = [
        ("application/json", test_data),
        ("application/x-www-form-urlencoded", test_data),
    ]
    
    for content_type, data in methods:
        try:
            logger.info(f"\n=== 测试POST方法: {content_type} ===")
            
            headers = {
                "Content-Type": content_type,
                "Accept": "application/json"
            }
            
            if content_type == "application/json":
                response = session.post(
                    f"{API_BASE}/posts",
                    json=data,
                    auth=AUTH,
                    headers=headers,
                    timeout=30
                )
            else:
                response = session.post(
                    f"{API_BASE}/posts",
                    data=data,
                    auth=AUTH,
                    headers=headers,
                    timeout=30
                )
            
            logger.info(f"状态码: {response.status_code}")
            logger.info(f"响应头: {dict(response.headers)}")
            logger.info(f"响应内容: {response.text[:500]}")
            
            if response.status_code in [200, 201]:
                try:
                    result = response.json()
                    logger.info(f"响应类型: {type(result)}")
                    if isinstance(result, dict):
                        logger.info(f"文章ID: {result.get('id', '未找到')}")
                        logger.info(f"文章状态: {result.get('status', '未知')}")
                    elif isinstance(result, list):
                        logger.info(f"返回列表长度: {len(result)}")
                except Exception as e:
                    logger.error(f"JSON解析失败: {e}")
            
        except Exception as e:
            logger.error(f"POST请求失败: {e}")

def test_authentication():
    """测试认证"""
    session = requests.Session()
    session.trust_env = False
    
    logger.info("\n=== 测试认证 ===")
    
    # 测试无认证
    try:
        response = session.get(f"{API_BASE}/posts?per_page=1", timeout=10)
        logger.info(f"无认证访问: {response.status_code}")
    except Exception as e:
        logger.error(f"无认证请求失败: {e}")
    
    # 测试错误认证
    try:
        response = session.get(
            f"{API_BASE}/posts?per_page=1", 
            auth=("wrong", "credentials"),
            timeout=10
        )
        logger.info(f"错误认证访问: {response.status_code}")
    except Exception as e:
        logger.error(f"错误认证请求失败: {e}")
    
    # 测试正确认证
    try:
        response = session.get(
            f"{API_BASE}/posts?per_page=1", 
            auth=AUTH,
            timeout=10
        )
        logger.info(f"正确认证访问: {response.status_code}")
        
        # 测试用户信息
        user_response = session.get(f"{API_BASE}/users/me", auth=AUTH, timeout=10)
        logger.info(f"用户信息状态码: {user_response.status_code}")
        if user_response.status_code == 200:
            user_data = user_response.json()
            logger.info(f"用户ID: {user_data.get('id')}")
            logger.info(f"用户名: {user_data.get('username')}")
            logger.info(f"用户角色: {user_data.get('roles', [])}")
            logger.info(f"用户权限: {user_data.get('capabilities', {}).keys()}")
        
    except Exception as e:
        logger.error(f"正确认证请求失败: {e}")

def main():
    """主函数"""
    logger.info("开始WordPress API诊断")
    
    test_api_endpoints()
    test_authentication()
    test_post_methods()
    
    logger.info("\n=== 诊断完成 ===")

if __name__ == "__main__":
    main()