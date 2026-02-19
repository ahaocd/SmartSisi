import aiohttp
import asyncio
import json
import time
import sys
import re
import traceback
from typing import Dict, Any, List, Optional
import os

async def test_api_discovery():
    """探测可用的API端点和格式"""
    print("\n===== 开始API发现测试 =====")
    base_url = "http://localhost:8001"
    
    # 测试各种可能的API路径
    api_paths = [
        "/a2a/discover",
        "/.well-known/agent.json",
        "/a2a/health"
    ]
    
    async with aiohttp.ClientSession() as session:
        for path in api_paths:
            url = f"{base_url}{path}"
            try:
                print(f"测试API: {url}")
                async with session.get(url, timeout=2) as response:
                    status = response.status
                    try:
                        data = await response.json()
                        print(f"✓ API {path} 可用 (HTTP {status})")
                        print(f"  返回数据: {json.dumps(data, ensure_ascii=False)[:200]}...")
                    except:
                        text = await response.text()
                        print(f"✓ API {path} 可用 (HTTP {status})")
                        print(f"  返回文本: {text[:200]}...")
            except Exception as e:
                print(f"✗ API {path} 不可用: {str(e)}")

async def create_task():
    """创建A2A任务并获取任务ID"""
    print("\n===== 创建任务测试 =====")
    base_url = "http://localhost:8001"
    
    # 尝试多种可能的API路径格式
    jsonrpc_paths = [
        "/a2a/jsonrpc",
        "/jsonrpc",
        "/a2a/invoke/currency"
    ]
    
    task_id = None
    
    async with aiohttp.ClientSession() as session:
        for path in jsonrpc_paths:
            url = f"{base_url}{path}"
            try:
                print(f"尝试创建任务: {url}")
                
                # JSON-RPC请求
                payload = {
                    "jsonrpc": "2.0",
                    "method": "invoke",
                    "params": {"query": "Convert 100 USD to CNY"},
                    "id": f"test_{int(time.time())}"
                }
                
                headers = {"Content-Type": "application/json"}
                
                async with session.post(url, json=payload, headers=headers, timeout=5) as response:
                    status = response.status
                    text = await response.text()
                    print(f"响应状态: HTTP {status}")
                    print(f"响应内容: {text[:200]}...")
                    
                    if status == 200:
                        try:
                            data = json.loads(text)
                            # 检查是否包含task_id
                            result = data.get("result", {})
                            if isinstance(result, dict) and "task_id" in result:
                                task_id = result["task_id"]
                                print(f"✓ 成功创建任务, ID: {task_id}")
                                break
                            else:
                                print("✗ 响应中未包含task_id")
                        except:
                            print("✗ 无法解析JSON响应")
                    elif status == 404:
                        print(f"✗ API路径不存在: {path}")
                    else:
                        print(f"✗ 请求失败: HTTP {status}")
            except Exception as e:
                print(f"✗ 请求异常: {str(e)}")
    
    if not task_id:
        print("⚠ 所有API路径尝试失败，生成模拟任务ID用于测试SSE")
        import uuid
        task_id = str(uuid.uuid4())
        print(f"模拟任务ID: {task_id}")
    
    return task_id

class SSEClient:
    """简单的SSE客户端，用于解析SSE流"""
    
    def __init__(self, url):
        self.url = url
        self.buffer = ""
        self.event_count = 0
        self.last_event_time = time.time()
    
    async def connect(self):
        """连接到SSE流"""
        print(f"\n开始连接SSE: {self.url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                # 尝试多种请求头组合
                headers_options = [
                    {"Accept": "text/event-stream"},
                    {"Accept": "*/*"},
                    {}  # 空headers作为后备选项
                ]
                
                for headers in headers_options:
                    print(f"正在尝试连接... (请求头: {headers})")
                    
                    try:
                        # 设置更灵活的超时
                        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=30)
                        
                        async with session.get(self.url, headers=headers, timeout=timeout) as response:
                            status = response.status
                            content_type = response.headers.get("Content-Type", "")
                            
                            print(f"连接状态: HTTP {status}")
                            print(f"响应头: Content-Type={content_type}")
                            
                            if status != 200:
                                text = await response.text()
                                print(f"连接失败: HTTP {status}, 内容: {text[:200]}...")
                                continue
                            
                            # 检查是标准SSE格式还是非标准格式
                            is_standard_sse = "text/event-stream" in content_type
                            
                            if not is_standard_sse:
                                print(f"⚠ 警告: 内容类型不是SSE格式: {content_type}，尝试作为常规JSON处理")
                                
                                # 处理非SSE标准的JSON响应
                                text = await response.text()
                                try:
                                    data = json.loads(text)
                                    print(f"从非SSE响应解析JSON: {json.dumps(data, ensure_ascii=False)[:200]}...")
                                    self.event_count = 1
                                    print("✓ 非标准SSE响应处理成功")
                                    return True
                                except json.JSONDecodeError:
                                    print(f"⚠ 非SSE响应不是有效的JSON: {text[:100]}...")
                            else:
                                print(f"SSE连接成功建立, 开始接收事件...")
                                self.event_count = 0
                                self.last_event_time = time.time()
                                
                                # 接收SSE数据流
                                async for line in response.content:
                                    line_str = line.decode('utf-8')
                                    
                                    # 处理行数据
                                    await self._process_sse_line(line_str)
                                    
                                    # 更新最后事件时间
                                    self.last_event_time = time.time()
                                    
                                    # 如果收到10个事件或等待10秒，则停止
                                    if self.event_count >= 10 or (time.time() - start_time) > 30:
                                        print(f"测试完成: 收到{self.event_count}个事件，耗时{time.time() - start_time:.2f}秒")
                                        break
                                
                                print(f"共接收到 {self.event_count} 个事件")
                                return True
                    except aiohttp.ClientError as e:
                        print(f"连接错误: {str(e)}")
                    except asyncio.TimeoutError:
                        print(f"连接超时，尝试下一个请求头选项")
                    except Exception as e:
                        print(f"连接异常: {str(e)}")
                        print(traceback.format_exc())
        except Exception as e:
            print(f"SSE测试异常: {str(e)}")
            print(traceback.format_exc())
        
        return False
    
    async def _process_sse_line(self, line):
        """处理SSE行数据"""
        # 如果是数据行
        if line.startswith('data: '):
            self.event_count += 1
            data_str = line[6:].strip()
            print(f"\n事件 #{self.event_count} (接收时间: {time.strftime('%H:%M:%S')})")
            
            try:
                # 解析JSON数据
                data = json.loads(data_str)
                formatted_json = json.dumps(data, indent=2, ensure_ascii=False)
                print(f"SSE数据: {formatted_json}")
                
                # 分析事件类型
                event_type = "未知"
                
                # 如果是心跳
                if isinstance(data, dict) and data.get("type") == "heartbeat":
                    event_type = "心跳"
                # 如果是连接建立
                elif isinstance(data, dict) and data.get("type") == "connection_established":
                    event_type = "连接建立"
                # 如果是JSON-RPC响应格式
                elif "jsonrpc" in data:
                    if "error" in data:
                        event_type = f"错误: {data['error'].get('message', '未知错误')}" if isinstance(data['error'], dict) else f"错误: {data['error']}"
                    elif "result" in data:
                        result = data["result"]
                        if isinstance(result, dict):
                            # 检查任务状态
                            if "status" in result and isinstance(result["status"], dict):
                                state = result["status"].get("state", "unknown")
                                is_final = result.get("final", False)
                                event_type = f"任务状态: {state}, 最终: {is_final}"
                            
                            # 检查是否有产物
                            has_artifacts = "artifacts" in result and isinstance(result["artifacts"], list) and len(result["artifacts"]) > 0
                            if has_artifacts:
                                artifact_count = len(result["artifacts"])
                                event_type += f", 产物数量: {artifact_count}"
                
                print(f"事件类型: {event_type}")
            except json.JSONDecodeError:
                print(f"无效的JSON数据: {data_str}")
            except Exception as e:
                print(f"处理事件异常: {str(e)}")
        # 空行或注释行
        elif line.strip() == '' or line.startswith(':'):
            pass
        # 其他行
        else:
            print(f"未识别的SSE行: {line.strip()}")

async def test_sse_subscription(task_id):
    """测试SSE订阅"""
    print("\n===== SSE订阅测试 =====")
    base_url = "http://localhost:8001"
    
    # 尝试多种SSE端点格式
    sse_paths = [
        f"/a2a/task/subscribe/{task_id}",
        f"/a2a/task/currency/subscribe/{task_id}"
    ]
    
    for path in sse_paths:
        url = f"{base_url}{path}"
        print(f"\n测试SSE端点: {url}")
        
        # 创建SSE客户端并连接
        client = SSEClient(url)
        success = await client.connect()
        
        if success:
            print(f"✓ SSE端点 {path} 测试成功，共接收到 {client.event_count} 个事件")
        else:
            print(f"✗ SSE端点 {path} 测试失败")

async def test_transit_station():
    """测试中转站功能"""
    print("\n===== 中转站功能测试 =====")
    
    try:
        # 修复导入路径问题
        import sys
        import os
        
        # 添加父目录到路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        root_dir = os.path.dirname(parent_dir)
        
        if root_dir not in sys.path:
            sys.path.append(root_dir)
            print(f"已添加目录到Python路径: {root_dir}")
        
        # 导入中转站
        from llm.transit_station import get_transit_station
        transit = get_transit_station()
        
        print("✓ 成功导入中转站模块")
        
        # 测试添加中间状态
        transit.add_intermediate_state("这是一条测试中间状态消息", "测试来源")
        print("✓ 成功添加中间状态")
        
        # 检查中间状态列表
        if hasattr(transit, 'intermediate_states') and transit.intermediate_states:
            print(f"✓ 中间状态列表包含 {len(transit.intermediate_states)} 条状态")
            print(f"  首条状态: {transit.intermediate_states[0][:50]}...")
        else:
            print("✗ 中间状态列表为空")
        
        # 检查Sisi核心实例
        if hasattr(transit, 'sisi_core') and transit.sisi_core:
            print("✓ 中转站已注册Sisi核心实例")
        else:
            print("⚠ 中转站未注册Sisi核心实例，可能无法播放TTS")
            
        # 注意：这里不调用process_final_result，避免实际执行TTS
        print("提示: TTS播放功能需在实际环境中测试")
        
        return True
    except Exception as e:
        print(f"✗ 中转站测试失败: {str(e)}")
        print(traceback.format_exc())
        return False

async def main():
    print("=== A2A服务器连接测试 ===")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 测试API发现
    await test_api_discovery()
    
    # 2. 创建任务
    task_id = await create_task()
    
    # 3. 测试SSE订阅
    if task_id:
        await test_sse_subscription(task_id)
    
    # 4. 测试中转站功能
    await test_transit_station()
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    asyncio.run(main()) 
