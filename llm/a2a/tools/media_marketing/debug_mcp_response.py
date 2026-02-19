"""
调试MCP原始响应 - 查看完整的返回数据
"""

import asyncio
import aiohttp
import json


async def debug_mcp_response():
    mcp_url = "http://127.0.0.1:12306/mcp"

    print("🔍 调试MCP原始响应\n")

    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
        # 步骤1：先初始化session
        print("【步骤1】初始化session")
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "DebugTool",
                    "version": "1.0.0"
                }
            },
            "id": 1
        }

        print("📤 发送initialize请求:")
        print(json.dumps(init_payload, indent=2))
        print()

        headers = {"Accept": "application/json, text/event-stream"}

        async with session.post(mcp_url, json=init_payload, headers=headers, timeout=10) as resp:
            session_id = resp.headers.get('mcp-session-id')
            text = await resp.text()

            print(f"📥 初始化响应状态: {resp.status}")
            print(f"📥 Session ID: {session_id[:8] if session_id else 'N/A'}...")
            print(f"📥 初始化响应内容:")
            print("=" * 80)
            print(text[:500])
            print("=" * 80)
            print()

        if not session_id:
            print("❌ 未获取到session ID，无法继续")
            return

        # 步骤2：获取工具列表
        print("【步骤2】获取工具列表")
        list_payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 2
        }

        print("📤 发送tools/list请求:")
        print(json.dumps(list_payload, indent=2))
        print()

        headers = {
            "mcp-session-id": session_id,
            "Accept": "application/json, text/event-stream"
        }

        async with session.post(mcp_url, json=list_payload, headers=headers, timeout=15) as resp:
            print(f"📥 响应状态: {resp.status}")
            print(f"📥 响应头:")
            for key, value in resp.headers.items():
                print(f"   {key}: {value}")
            print()

            text = await resp.text()
            print(f"📥 响应内容（完整）:")
            print("=" * 80)
            print(text)
            print("=" * 80)
            print()

            # 尝试解析
            print("🔧 尝试解析JSON:")
            try:
                data = json.loads(text)
                print(json.dumps(data, indent=2, ensure_ascii=False))

                # 提取工具列表
                result = data.get("result", {})
                tools = result.get("tools", [])
                print(f"\n✅ 找到 {len(tools)} 个工具:")
                for i, tool in enumerate(tools, 1):
                    name = tool.get("name", "N/A")
                    desc = tool.get("description", "N/A")[:60]
                    print(f"   {i}. {name}: {desc}")

            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                print("\n尝试SSE格式解析:")
                lines = text.split('\n')
                for i, line in enumerate(lines[:10], 1):
                    print(f"   行{i}: {line}")


import sys

# Windows UTF-8修复
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except:
        pass

asyncio.run(debug_mcp_response())
