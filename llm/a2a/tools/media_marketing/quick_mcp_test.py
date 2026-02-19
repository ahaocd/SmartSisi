"""
快速MCP测试 - 使用现有的Chrome进程测试工具

前提：
1. Chrome已经在运行（你日常使用的Chrome，已登录抖音）
2. mcp-chrome扩展已安装并启用

不需要：
- 启动新的Chrome
- 配置复杂的session
"""

import asyncio
import aiohttp
import json
from typing import List, Dict


async def quick_test_mcp_chrome():
    """快速测试mcp-chrome是否可用"""

    mcp_url = "http://127.0.0.1:12306/mcp"

    print("=" * 80)
    print("🔍 MCP工具快速检测")
    print("=" * 80)
    print()

    # 1. 测试连接
    print("【1】测试mcp-chrome连接...")
    try:
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
            # 简单的健康检查请求
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 1
            }

            async with session.post(mcp_url, json=payload, timeout=5) as resp:
                if resp.status in [200, 400, 500]:
                    print("   ✅ mcp-chrome服务正在运行")
                    text = await resp.text()

                    # 尝试解析工具列表
                    try:
                        data = json.loads(text)
                        tools = data.get("result", {}).get("tools", [])
                        tool_names = [t.get("name") for t in tools if isinstance(t, dict)]

                        print(f"\n【2】可用工具列表（共 {len(tool_names)} 个）")
                        for i, name in enumerate(tool_names, 1):
                            print(f"   {i}. {name}")

                        print(f"\n【3】三个策略的关键工具检查")

                        # 策略1：发表评论
                        print("\n   ▶️ 策略1：发表评论")
                        has_navigate = any(n in tool_names for n in ["chrome_navigate", "navigate"])
                        has_click = any(n in tool_names for n in ["chrome_click_element", "chrome_click", "click"])
                        has_type = any(n in tool_names for n in ["chrome_fill_or_select", "chrome_type", "type"])

                        print(f"      导航工具: {'✅' if has_navigate else '❌'}")
                        print(f"      点击工具: {'✅' if has_click else '❌'}")
                        print(f"      输入工具: {'✅' if has_type else '❌'}")
                        print(f"      结论: {'✅ 可执行' if (has_navigate and has_click and has_type) else '❌ 缺少工具'}")

                        # 策略2和3：需要JS执行
                        print("\n   ▶️ 策略2：回复评论（需要JS执行）")
                        print("   ▶️ 策略3：访问主页分析（需要JS执行）")

                        js_tools = [
                            "chrome_inject_script",
                            "chrome_eval",
                            "chrome_execute_script",
                            "evaluateJavascript",
                            "eval"
                        ]

                        found_js_tool = None
                        for js_tool in js_tools:
                            if js_tool in tool_names:
                                found_js_tool = js_tool
                                break

                        if found_js_tool:
                            print(f"      JS执行工具: ✅ {found_js_tool}")
                            print(f"      结论: ✅ 策略2和策略3可执行")
                            print(f"      📌 代码需要更新：将 'chrome_inject_script' 改为 '{found_js_tool}'")
                        else:
                            print(f"      JS执行工具: ❌ 未找到")
                            print(f"      结论: ❌ 策略2和策略3无法执行")
                            print(f"      📌 建议：使用playwright MCP作为备用")

                        print(f"\n【4】关于playwright MCP")
                        print(f"   - playwright可以与mcp-chrome共存")
                        print(f"   - mcp-chrome: 控制你的Chrome（保留登录）")
                        print(f"   - playwright: 独立浏览器（需重新登录）")
                        print(f"   - 📌 优先mcp-chrome，playwright备用")

                        print(f"\n【5】关于MCP的'本地模型'")
                        print(f"   - MCP不包含AI模型！")
                        print(f"   - MCP = 浏览器控制协议（类似Selenium）")
                        print(f"   - 真正的AI在system.conf（GLM-4.1V用于OCR）")

                        # 保存结果
                        result = {
                            "service_running": True,
                            "tools_count": len(tool_names),
                            "tools": tool_names,
                            "strategy1_available": has_navigate and has_click and has_type,
                            "strategy2_3_available": found_js_tool is not None,
                            "js_tool_name": found_js_tool
                        }

                        from pathlib import Path
                        report_file = Path(__file__).parent / "mcp_tools_result.json"
                        report_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(f"\n💾 结果已保存: {report_file}")

                        return result

                    except json.JSONDecodeError:
                        print("   ⚠️ 响应格式不是标准JSON，可能是SSE格式")
                        print(f"   原始响应: {text[:200]}...")
                else:
                    print(f"   ❌ 连接失败，状态码: {resp.status}")
                    return None

    except aiohttp.ClientConnectorError as e:
        print(f"   ❌ 无法连接到mcp-chrome服务")
        print(f"   错误: {e}")
        print()
        print("   可能的原因：")
        print("   1. mcp-chrome扩展未安装或未启用")
        print("   2. Chrome未启动")
        print("   3. 扩展端口不是12306")
        print()
        print("   解决方法：")
        print("   1. 打开Chrome，访问 chrome://extensions")
        print("   2. 确认mcp-chrome扩展已启用")
        print("   3. 或运行主程序，它会自动启动")
        return None
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return None

    print()
    print("=" * 80)


async def main():
    import sys

    # Windows UTF-8编码
    if sys.platform == 'win32':
        try:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        except:
            pass

    result = await quick_test_mcp_chrome()

    if not result:
        print("\n❌ 测试未完成")
        print("\n建议：先运行主程序一次，让它启动Chrome和mcp-chrome服务")
        print("命令：python douyin_marketing_agent_tool.py")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n用户中断")
