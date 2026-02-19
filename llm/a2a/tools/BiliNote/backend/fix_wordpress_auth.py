#!/usr/bin/env python3
"""
修复WordPress认证问题
"""

import json
import requests
import logging
import base64

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WordPress配置
WORDPRESS_URL = "https://xasia.cc"
WORDPRESS_USER = "67859543"
WORDPRESS_APP_PASSWORD = "XqXt bHFX rwL3 M5kc rDqd HXD2"
API_BASE = f"{WORDPRESS_URL}/wp-json/wp/v2"

def test_different_auth_methods():
    """测试不同的认证方式"""
    session = requests.Session()
    session.trust_env = False
    
    # 方法1: Basic Auth (标准方式)
    logger.info("=== 测试方法1: Basic Auth ===")
    try:
        response = session.get(
            f"{API_BASE}/users/me",
            auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
            timeout=10
        )
        logger.info(f"Basic Auth状态码: {response.status_code}")
        logger.info(f"Basic Auth响应: {response.text[:200]}")
    except Exception as e:
        logger.error(f"Basic Auth失败: {e}")
    
    # 方法2: Authorization Header
    logger.info("\n=== 测试方法2: Authorization Header ===")
    try:
        credentials = base64.b64encode(f"{WORDPRESS_USER}:{WORDPRESS_APP_PASSWORD}".encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json"
        }
        response = session.get(
            f"{API_BASE}/users/me",
            headers=headers,
            timeout=10
        )
        logger.info(f"Auth Header状态码: {response.status_code}")
        logger.info(f"Auth Header响应: {response.text[:200]}")
    except Exception as e:
        logger.error(f"Auth Header失败: {e}")
    
    # 方法3: 使用www子域名
    logger.info("\n=== 测试方法3: 使用www子域名 ===")
    try:
        www_api_base = "https://www.xasia.cc/wp-json/wp/v2"
        response = session.get(
            f"{www_api_base}/users/me",
            auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
            timeout=10
        )
        logger.info(f"WWW域名状态码: {response.status_code}")
        logger.info(f"WWW域名响应: {response.text[:200]}")
        
        if response.status_code == 200:
            logger.info("✅ 使用www子域名认证成功！")
            return www_api_base
    except Exception as e:
        logger.error(f"WWW域名失败: {e}")
    
    # 方法4: 测试Cookie认证
    logger.info("\n=== 测试方法4: Cookie认证 ===")
    try:
        # 先登录获取cookie
        login_data = {
            "username": WORDPRESS_USER,
            "password": WORDPRESS_APP_PASSWORD
        }
        login_response = session.post(
            f"{WORDPRESS_URL}/wp-login.php",
            data=login_data,
            timeout=10
        )
        logger.info(f"登录状态码: {login_response.status_code}")
        
        # 使用cookie访问API
        response = session.get(f"{API_BASE}/users/me", timeout=10)
        logger.info(f"Cookie认证状态码: {response.status_code}")
        logger.info(f"Cookie认证响应: {response.text[:200]}")
    except Exception as e:
        logger.error(f"Cookie认证失败: {e}")
    
    return None

def test_post_with_correct_auth(api_base):
    """使用正确的认证方式测试POST"""
    if not api_base:
        logger.error("没有找到有效的API端点")
        return
    
    session = requests.Session()
    session.trust_env = False
    
    logger.info(f"\n=== 使用正确认证测试POST: {api_base} ===")
    
    # 测试数据
    post_data = {
        "title": "认证测试文章",
        "content": "这是一个测试认证的文章",
        "status": "draft",
        "categories": [8]  # 使用指南分类
    }
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = session.post(
            f"{api_base}/posts",
            json=post_data,
            auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
            headers=headers,
            timeout=30
        )
        
        logger.info(f"POST状态码: {response.status_code}")
        logger.info(f"POST响应头: {dict(response.headers)}")
        logger.info(f"POST响应内容: {response.text[:500]}")
        
        if response.status_code == 201:
            result = response.json()
            logger.info(f"✅ 文章创建成功！ID: {result.get('id')}")
            logger.info(f"文章链接: {result.get('link')}")
            return True
        elif response.status_code == 200:
            try:
                result = response.json()
                if isinstance(result, dict) and "id" in result:
                    logger.info(f"✅ 文章创建成功！ID: {result.get('id')}")
                    return True
                else:
                    logger.warning("POST返回200但格式不正确")
            except:
                logger.warning("POST返回200但无法解析JSON")
        else:
            logger.error(f"POST失败: {response.status_code}")
            
    except Exception as e:
        logger.error(f"POST请求异常: {e}")
    
    return False

def main():
    """主函数"""
    logger.info("开始WordPress认证修复测试")
    
    # 测试不同认证方式
    correct_api_base = test_different_auth_methods()
    
    # 如果找到正确的认证方式，测试POST
    if correct_api_base:
        test_post_with_correct_auth(correct_api_base)
    else:
        logger.error("❌ 所有认证方式都失败了")
        logger.info("可能的解决方案：")
        logger.info("1. 检查应用密码是否正确")
        logger.info("2. 检查用户是否有发布权限")
        logger.info("3. 检查WordPress REST API是否启用")
        logger.info("4. 检查服务器防火墙设置")

if __name__ == "__main__":
    main()