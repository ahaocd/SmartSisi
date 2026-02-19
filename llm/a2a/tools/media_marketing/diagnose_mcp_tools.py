"""
🔍 MCP工具诊断脚本 - 检查mcp-chrome可用工具和三个策略的可行性

功能：
1. 查询mcp-chrome实际提供的工具列表
2. 测试chrome_inject_script是否存在（及其可能的别名）
3. 验证三个策略的工具依赖
4. 生成诊断报告

使用前提：
- Chrome浏览器已启动（带mcp-chrome扩展）
- mcp-chrome服务正在运行（http://127.0.0.1:12306/mcp）
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPToolsDiagnostic:
    def __init__(self, mcp_url: str = "http://127.0.0.1:12306/mcp"):
        self.mcp_url = mcp_url
        self.session_id = None
        self.available_tools = []

    async def initialize_session(self) -> bool:
        """初始化MCP session"""
        try:
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "MCPToolsDiagnostic",
                            "version": "1.0.0"
                        }
                    },
                    "id": 1
                }

                headers = {"Accept": "application/json, text/event-stream"}

                async with session.post(self.mcp_url, json=payload, headers=headers, timeout=10) as resp:
                    self.session_id = resp.headers.get('mcp-session-id')
                    text = await resp.text()

                    if not self.session_id:
                        logger.error(f"❌ 未获取到session ID")
                        return False

                    logger.info(f"✅ Session初始化成功: {self.session_id[:8]}...")
                    return True
        except Exception as e:
            logger.error(f"❌ Session初始化失败: {e}")
            return False

    async def list_tools(self) -> List[str]:
        """获取工具列表"""
        if not self.session_id:
            if not await self.initialize_session():
                return []

        try:
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": 2
                }
                headers = {
                    "mcp-session-id": self.session_id,
                    "Accept": "application/json, text/event-stream"
                }

                async with session.post(self.mcp_url, json=payload, headers=headers, timeout=15) as resp:
                    text = await resp.text()

                    try:
                        data = json.loads(text)
                        result = data.get("result", {})
                        tools = result.get("tools", [])
                        self.available_tools = [t.get("name") for t in tools if isinstance(t, dict) and "name" in t]
                        return self.available_tools
                    except json.JSONDecodeError:
                        # SSE格式
                        import re
                        matches = re.findall(r'data: ({.*?})\n', text, re.DOTALL)
                        if matches:
                            try:
                                obj = json.loads(matches[-1])
                                result = obj.get("result", {})
                                tools = result.get("tools", [])
                                self.available_tools = [t.get("name") for t in tools if isinstance(t, dict) and "name" in t]
                                return self.available_tools
                            except:
                                return []
                        return []
        except Exception as e:
            logger.error(f"❌ 获取工具列表失败: {e}")
            return []

    def check_strategy_tools(self) -> Dict:
        """检查三个策略所需的工具是否可用"""

        # 三个策略的工具依赖
        strategies = {
            "策略1_发表评论": {
                "description": "在评论框发表评论",
                "required_tools": [
                    ["chrome_navigate", "navigate"],
                    ["chrome_click_element", "chrome_click", "click"],
                    ["chrome_fill_or_select", "chrome_type", "type", "input"],
                ],
                "available": []
            },
            "策略2_回复评论": {
                "description": "回复评论者的评论（需要JS定位）",
                "required_tools": [
                    ["chrome_inject_script", "chrome_eval", "evaluateJavascript", "eval"],
                    ["chrome_fill_or_select", "chrome_type", "type"],
                    ["chrome_keyboard", "keyboard"],
                ],
                "available": []
            },
            "策略3_访问主页分析": {
                "description": "访问用户主页，JS抓取数据",
                "required_tools": [
                    ["chrome_navigate", "navigate"],
                    ["chrome_inject_script", "chrome_eval", "evaluateJavascript", "eval"],
                    ["chrome_keyboard", "keyboard"],
                ],
                "available": []
            }
        }

        # 检查每个策略的工具可用性
        for strategy_name, strategy_info in strategies.items():
            for tool_variants in strategy_info["required_tools"]:
                found = False
                for variant in tool_variants:
                    if variant in self.available_tools:
                        strategy_info["available"].append(variant)
                        found = True
                        break

                if not found:
                    strategy_info["available"].append(f"❌ {tool_variants[0]} (未找到)")

        return strategies

    async def test_inject_script(self, test_url: str = "https://www.douyin.com") -> Dict:
        """测试chrome_inject_script是否可用（尝试所有可能的名称）"""

        # 所有可能的JS执行工具名
        possible_names = [
            "chrome_inject_script",
            "chrome_eval",
            "chrome_execute_script",
            "evaluateJavascript",
            "evaluateJS",
            "eval",
            "execute_script",
            "inject_script"
        ]

        test_results = {}

        for tool_name in possible_names:
            if tool_name not in self.available_tools:
                test_results[tool_name] = "工具不存在"
                continue

            try:
                # 简单的测试脚本：返回页面标题
                test_script = "(() => { return document.title; })()"

                connector = aiohttp.TCPConnector()
                async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                    payload = {
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": {"script": test_script}
                        },
                        "id": 100
                    }
                    headers = {
                        "mcp-session-id": self.session_id,
                        "Accept": "application/json, text/event-stream"
                    }

                    async with session.post(self.mcp_url, json=payload, headers=headers, timeout=10) as resp:
                        text = await resp.text()

                        try:
                            result = json.loads(text)
                            if "error" in result:
                                test_results[tool_name] = f"❌ 错误: {result['error']}"
                            else:
                                test_results[tool_name] = f"✅ 成功"
                        except json.JSONDecodeError:
                            # SSE格式
                            import re
                            matches = re.findall(r'data: ({.*?})\n', text, re.DOTALL)
                            if matches:
                                obj = json.loads(matches[-1])
                                if "error" in obj:
                                    test_results[tool_name] = f"❌ 错误: {obj['error']}"
                                else:
                                    test_results[tool_name] = f"✅ 成功"
                            else:
                                test_results[tool_name] = "❓ 无法解析响应"
            except Exception as e:
                test_results[tool_name] = f"❌ 异常: {str(e)[:50]}"

        return test_results

    async def generate_report(self) -> str:
        """生成诊断报告"""
        report = []
        report.append("=" * 80)
        report.append("🔍 MCP工具诊断报告")
        report.append("=" * 80)
        report.append("")

        # 1. 连接状态
        report.append("【1】MCP连接状态")
        report.append(f"   URL: {self.mcp_url}")
        report.append(f"   Session ID: {self.session_id[:8] if self.session_id else 'N/A'}...")
        report.append(f"   状态: {'✅ 已连接' if self.session_id else '❌ 未连接'}")
        report.append("")

        # 2. 可用工具列表
        report.append(f"【2】可用工具列表（共 {len(self.available_tools)} 个）")
        if self.available_tools:
            for i, tool in enumerate(self.available_tools, 1):
                report.append(f"   {i}. {tool}")
        else:
            report.append("   ❌ 无可用工具")
        report.append("")

        # 3. 三个策略的工具依赖检查
        report.append("【3】三个策略的工具依赖检查")
        strategies = self.check_strategy_tools()
        for strategy_name, strategy_info in strategies.items():
            report.append(f"\n   ▶️ {strategy_name}")
            report.append(f"      描述: {strategy_info['description']}")
            report.append(f"      可用工具:")
            for tool in strategy_info['available']:
                status = "✅" if not tool.startswith("❌") else "❌"
                report.append(f"         {status} {tool}")

            # 判断策略是否可行
            all_available = all(not t.startswith("❌") for t in strategy_info['available'])
            if all_available:
                report.append(f"      结论: ✅ 该策略可执行")
            else:
                report.append(f"      结论: ❌ 缺少必要工具，无法执行")
        report.append("")

        # 4. JS执行工具测试
        report.append("【4】JS执行工具测试（chrome_inject_script及其变体）")
        test_results = await self.test_inject_script()
        for tool_name, result in test_results.items():
            report.append(f"   {tool_name}: {result}")
        report.append("")

        # 5. 关键发现和建议
        report.append("【5】关键发现和建议")

        # 检查是否有JS执行工具
        has_js_tool = any("✅" in result for result in test_results.values())
        if has_js_tool:
            working_tools = [name for name, result in test_results.items() if "✅" in result]
            report.append(f"   ✅ 发现可用的JS执行工具: {', '.join(working_tools)}")
            report.append(f"   📌 建议: 使用 {working_tools[0]} 执行策略2和策略3")
        else:
            report.append(f"   ❌ 未找到可用的JS执行工具")
            report.append(f"   📌 建议: 考虑使用 playwright MCP 作为备用方案")
        report.append("")

        # 检查策略1是否可行
        strategy1 = strategies.get("策略1_发表评论", {})
        if all(not t.startswith("❌") for t in strategy1.get("available", [])):
            report.append(f"   ✅ 策略1（发表评论）: 可执行")
        else:
            report.append(f"   ❌ 策略1（发表评论）: 缺少工具")

        # 检查策略2和策略3
        strategy2 = strategies.get("策略2_回复评论", {})
        strategy3 = strategies.get("策略3_访问主页分析", {})

        if has_js_tool:
            report.append(f"   ✅ 策略2（回复评论）: 可执行（需更新代码使用正确的工具名）")
            report.append(f"   ✅ 策略3（访问主页分析）: 可执行（需更新代码使用正确的工具名）")
        else:
            report.append(f"   ❌ 策略2（回复评论）: 无JS执行工具，无法执行")
            report.append(f"   ❌ 策略3（访问主页分析）: 无JS执行工具，无法执行")

        report.append("")
        report.append("【6】关于 playwright MCP 的说明")
        report.append("   playwright MCP 可以与 mcp-chrome 共存")
        report.append("   - mcp-chrome: 控制你已打开的Chrome浏览器（有登录状态）")
        report.append("   - playwright: 独立启动浏览器（无登录状态，需重新登录）")
        report.append("   📌 建议: 优先使用mcp-chrome（保留登录状态），playwright作为备用")
        report.append("")

        report.append("【7】关于 MCP 的本地模型")
        report.append("   MCP本身不包含AI模型！")
        report.append("   - MCP只是浏览器控制协议（类似Selenium）")
        report.append("   - 所谓'本地模型'指的是mcp-chrome扩展的JS代码")
        report.append("   - 真正的AI模型在你的system.conf配置中（GLM-4.1V用于OCR）")
        report.append("")

        report.append("=" * 80)
        report.append("诊断完成")
        report.append("=" * 80)

        return "\n".join(report)


async def main():
    """主函数"""
    print("\n🚀 开始MCP工具诊断...\n")

    diagnostic = MCPToolsDiagnostic()

    # 1. 初始化session
    if not await diagnostic.initialize_session():
        print("❌ 无法连接到mcp-chrome服务")
        print("请确保：")
        print("1. Chrome浏览器已启动（带--remote-debugging-port=9222）")
        print("2. mcp-chrome扩展已加载")
        print("3. mcp-chrome服务正在运行（http://127.0.0.1:12306/mcp）")
        return

    # 2. 获取工具列表
    print("📋 正在获取工具列表...\n")
    tools = await diagnostic.list_tools()

    if not tools:
        print("❌ 未获取到任何工具")
        return

    # 3. 生成报告
    report = await diagnostic.generate_report()
    print(report)

    # 4. 保存报告到文件
    from pathlib import Path
    report_file = Path(__file__).parent / "mcp_diagnostic_report.txt"
    report_file.write_text(report, encoding="utf-8")
    print(f"\n💾 报告已保存到: {report_file}")


if __name__ == "__main__":
    import sys

    # Windows UTF-8编码修复
    if sys.platform == 'win32':
        try:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        except:
            pass

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
