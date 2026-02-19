#!/usr/bin/env python
"""查询WordPress分类和文章信息"""

import requests
from dotenv import load_dotenv
import os

load_dotenv()

WP_URL = os.getenv("WORDPRESS_URL", "https://www.xasia.cc")
WP_USER = os.getenv("WORDPRESS_USER", "67859543")
WP_PASS = os.getenv("WORDPRESS_APP_PASSWORD", "XqXt bHFX rwL3 M5kc rDqd HXD2")

session = requests.Session()
session.trust_env = False

print("=" * 60)
print("WordPress 分类列表")
print("=" * 60)

try:
    r = session.get(f"{WP_URL}/wp-json/wp/v2/categories", timeout=10)
    categories = r.json()
    for c in categories:
        print(f"  ID: {c['id']:3d} | 名称: {c['name']:10s} | 别名: {c['slug']:20s} | 文章数: {c['count']}")
except Exception as e:
    print(f"获取分类失败: {e}")

print("\n" + "=" * 60)
print("最近发布的文章 (最新10篇)")
print("=" * 60)

try:
    r = session.get(f"{WP_URL}/wp-json/wp/v2/posts", params={"per_page": 10, "status": "any"}, auth=(WP_USER, WP_PASS), timeout=10)
    posts = r.json()
    for p in posts:
        status = "已发布" if p['status'] == 'publish' else "草稿"
        title = p['title']['rendered'][:30] + "..." if len(p['title']['rendered']) > 30 else p['title']['rendered']
        print(f"  ID: {p['id']:5d} | 状态: {status:4s} | 标题: {title}")
        print(f"         链接: {p['link']}")
except Exception as e:
    print(f"获取文章失败: {e}")

print("\n" + "=" * 60)
print("标签列表")
print("=" * 60)

try:
    r = session.get(f"{WP_URL}/wp-json/wp/v2/tags", params={"per_page": 20}, timeout=10)
    tags = r.json()
    for t in tags:
        print(f"  ID: {t['id']:3d} | 名称: {t['name']:15s} | 文章数: {t['count']}")
except Exception as e:
    print(f"获取标签失败: {e}")
