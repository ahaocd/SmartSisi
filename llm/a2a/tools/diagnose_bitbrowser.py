"""
比特浏览器诊断工具
检查比特浏览器是否正常运行并列出所有环境
"""
import requests
import json
import sys

def check_bitbrowser_connection():
    """检查比特浏览器连接"""
    print("=" * 80)
    print("🔍 比特浏览器诊断工具")
    print("=" * 80)
    print()
    
    # 测试端口
    test_ports = [54345, 54346, 35471, 50325]
    api_url = None
    
    print("📡 正在测试API端口...")
    for port in test_ports:
        url = f"http://127.0.0.1:{port}/browser/list"
        print(f"   尝试端口 {port}...", end=" ")
        try:
            response = requests.post(
                url, 
                json={"page": 0, "pageSize": 10}, 
                timeout=3
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    print(f"✅ 连接成功！")
                    api_url = f"http://127.0.0.1:{port}"
                    break
                else:
                    print(f"❌ API返回错误: {data.get('msg')}")
            else:
                print(f"❌ HTTP {response.status_code}")
        except requests.exceptions.ConnectionError:
            print("❌ 连接失败")
        except Exception as e:
            print(f"❌ 异常: {e}")
    
    print()
    
    if not api_url:
        print("=" * 80)
        print("❌ 无法连接到比特浏览器！")
        print("=" * 80)
        print()
        print("⚠️  请检查以下问题：")
        print("1. 比特浏览器客户端是否已启动")
        print("2. 比特浏览器版本是否支持API（需要专业版）")
        print("3. 防火墙是否阻止了本地连接")
        print("4. API服务是否在设置中开启")
        print()
        print("💡 解决方案：")
        print("1. 打开比特浏览器客户端")
        print("2. 进入设置 -> API设置")
        print("3. 确保「本地API服务」已开启")
        print("4. 记下API端口号（通常是54345）")
        print()
        return None
    
    print("=" * 80)
    print(f"✅ 比特浏览器连接成功！")
    print(f"   API地址: {api_url}")
    print("=" * 80)
    print()
    
    return api_url

def list_environments(api_url):
    """列出所有环境"""
    print("📋 正在获取环境列表...")
    print()
    
    try:
        url = f"{api_url}/browser/list"
        response = requests.post(
            url,
            json={"page": 0, "pageSize": 100},
            timeout=10
        )
        data = response.json()
        
        if not data.get('success'):
            print(f"❌ 获取失败: {data.get('msg')}")
            return []
        
        browsers = data.get('data', {}).get('list', [])
        
        print("=" * 80)
        print(f"找到 {len(browsers)} 个浏览器环境")
        print("=" * 80)
        print()
        
        if not browsers:
            print("⚠️  未找到任何环境！")
            print()
            print("💡 请在比特浏览器中创建至少3个环境：")
            print("1. 打开比特浏览器客户端")
            print("2. 点击「新建浏览器」")
            print("3. 设置名称（建议包含 'xiaohongshu' 或 'xhs'）")
            print("4. 重复3次，创建3个环境")
            return []
        
        # 显示所有环境
        for i, browser in enumerate(browsers, 1):
            env_id = browser.get('id')
            env_name = browser.get('name', '未命名')
            env_remark = browser.get('remark', '')
            
            print(f"{i}. 【{env_name}】")
            print(f"   ID: {env_id}")
            if env_remark:
                print(f"   备注: {env_remark}")
            
            # 检查是否匹配小红书
            name_lower = env_name.lower()
            if 'xiaohongshu' in name_lower or 'xhs' in name_lower or '小红书' in env_name:
                print(f"   ✅ 匹配小红书环境")
            else:
                print(f"   ⚠️  建议将名称改为包含 'xiaohongshu' 或 'xhs'")
            print()
        
        # 筛选小红书环境
        print("=" * 80)
        print("🔍 筛选小红书专用环境...")
        print("=" * 80)
        print()
        
        xhs_browsers = []
        for browser in browsers:
            name_lower = browser.get('name', '').lower()
            if 'xiaohongshu' in name_lower or 'xhs' in name_lower or '小红书' in browser.get('name', ''):
                xhs_browsers.append(browser)
        
        if xhs_browsers:
            print(f"✅ 找到 {len(xhs_browsers)} 个小红书环境：")
            print()
            for i, browser in enumerate(xhs_browsers, 1):
                print(f"{i}. 【{browser.get('name')}】")
                print(f"   ID: {browser.get('id')}")
                print()
            
            if len(xhs_browsers) >= 3:
                print("✅ 环境数量充足（≥3个），可以开始自动发布！")
            else:
                print(f"⚠️  建议创建至少3个小红书环境（当前只有{len(xhs_browsers)}个）")
        else:
            print("⚠️  未找到专用小红书环境")
            print()
            print("将使用前3个环境（如果有）：")
            for i, browser in enumerate(browsers[:3], 1):
                print(f"{i}. 【{browser.get('name')}】 ID: {browser.get('id')}")
            print()
            print("💡 建议：将这些环境重命名为包含 'xiaohongshu' 或 'xhs'")
        
        print()
        print("=" * 80)
        
        return xhs_browsers if xhs_browsers else browsers[:3]
    
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_open_browser(api_url, browser_id):
    """测试打开浏览器"""
    print()
    print("=" * 80)
    print(f"🧪 测试打开浏览器: {browser_id}")
    print("=" * 80)
    print()
    
    try:
        url = f"{api_url}/browser/open"
        response = requests.post(
            url,
            json={"id": browser_id},
            timeout=30
        )
        data = response.json()
        
        if data.get('success'):
            print("✅ 浏览器启动成功！")
            print(f"   WebSocket: {data.get('data', {}).get('ws')}")
            print(f"   HTTP端口: {data.get('data', {}).get('http')}")
            print()
            print("⚠️  请手动关闭该浏览器窗口，或等待自动关闭")
            return True
        else:
            print(f"❌ 启动失败: {data.get('msg')}")
            return False
    
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False

def main():
    """主函数"""
    # 1. 检查连接
    api_url = check_bitbrowser_connection()
    if not api_url:
        return
    
    # 2. 列出环境
    browsers = list_environments(api_url)
    if not browsers:
        return
    
    # 3. 询问是否测试
    print()
    print("=" * 80)
    print("💡 下一步操作")
    print("=" * 80)
    print()
    print("诊断完成！你可以：")
    print("1. 在每个环境中手动登录小红书一次（重要！）")
    print("2. 运行主程序: python xiaohongshu_auto_upload_tool.py")
    print()
    
    # 可选：测试打开第一个浏览器
    test_choice = input("是否测试打开第一个环境？(y/n): ").strip().lower()
    if test_choice == 'y':
        test_open_browser(api_url, browsers[0].get('id'))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        import traceback
        traceback.print_exc()

