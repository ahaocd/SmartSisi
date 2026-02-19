"""
A2A服务器主程序入口 - 基于FastAPI实现
"""

import os
import sys
import json
import time
import uuid
import asyncio
import logging
import traceback
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import importlib.util
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from pydantic import BaseModel

# 设置更详细的日志，包括DEBUG级别
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 添加文件日志处理器 - 使用绝对路径
try:
    # 使用绝对路径确保日志文件在正确位置
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        from utils import util
        log_dir = util.ensure_log_dir("a2a")
        log_file_path = os.path.join(log_dir, "a2a_server.log")
    except Exception:
        log_dir = os.path.join(base_dir, "logs", "a2a")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "a2a_server.log")
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'))
    logger.addHandler(file_handler)
    logger.debug("已添加文件日志处理器")
    logger.debug(f"日志文件路径: {log_file_path}")
except Exception as e:
    logger.warning(f"添加文件日志处理器失败: {str(e)}")

# 获取目录信息
script_dir = os.path.dirname(os.path.abspath(__file__))
sisi_dir = os.path.join(script_dir, '..')
root_dir = os.path.join(sisi_dir, '..')
logger.info(f"脚本目录: {script_dir}")
logger.info(f"SmartSisi目录: {sisi_dir}")
logger.info(f"项目根目录: {root_dir}")

# 调整Python路径
sys.path.insert(0, root_dir)  # 项目根目录
sys.path.insert(0, sisi_dir)   # SmartSisi目录
sys.path.insert(0, script_dir) # 脚本目录
logger.info(f"Python路径: {sys.path}")

# 尝试导入SSE工具模块
try:
    from sse_starlette.sse import EventSourceResponse

    # 使用绝对导入而不是相对导入
    try:
        # 尝试从Sisi命名空间导入
        from SmartSisi.llm.a2a.sse_utils import (
            create_sse_response,
            standard_sse_generator,
            create_test_sse_response,
            create_error_response,
            ErrorCode,
            create_task_not_found_response
        )
        logger.info("成功导入SSE工具模块(从Sisi命名空间)")
    except ImportError:
        # 尝试直接导入
        from llm.a2a.sse_utils import (
            create_sse_response,
            standard_sse_generator,
            create_test_sse_response,
            create_error_response,
            ErrorCode,
            create_task_not_found_response
        )
        logger.info("成功导入SSE工具模块(直接导入)")
except Exception as e:
    logger.error(f"导入SSE工具模块失败: {str(e)}")
    logger.error(traceback.format_exc())
    raise

# 创建FastAPI应用
app = FastAPI(
    title="Sisi A2A Server",
    description="Sisi A2A Server based on FastAPI",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("FastAPI应用初始化完成，准备添加路由...")
logger.debug("=== 开始注册路由 ===")

# 添加中间件记录请求
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:32]
    path = request.url.path
    method = request.method

    # 获取Accept头
    accept_header = request.headers.get("accept", "*/*")
    logger.info(f"[{request_id}] 收到请求: {method} {path}")
    logger.info(f"[{request_id}] 请求头: {accept_header}")

    # 正常处理请求
    response = await call_next(request)

    # 记录响应信息
    logger.info(f"[{request_id}] 响应状态: {response.status_code}")

    # 检查是否有Content-Type头
    if "content-type" in response.headers:
        content_type = response.headers["content-type"]
        logger.info(f"[{request_id}] 响应类型: {content_type}")

        # 特别关注SSE请求
        if "text/event-stream" in accept_header or path.endswith("/test_json_to_sse") or "sse" in path.lower():
            logger.info(f"[{request_id}] SSE请求特别关注: 内容类型={content_type}")

    return response

# 注册健康检查路由
@app.get("/a2a/health")
async def health_check():
    """健康检查端点"""
    logger.debug("执行健康检查")
    return {"status": "ok"}
logger.debug("已注册路由: /a2a/health -> health_check")

# 特别重要：最先注册处理旧的特殊SSE端点路由 - 确保高优先级
@app.get("/a2a/task/subscribe/test_json_to_sse")
async def legacy_test_json_to_sse(request: Request):
    """旧的测试端点 - 返回正确的SSE响应"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到旧格式测试请求: test_json_to_sse")
    logger.info(f"[{request_id}] 请求URL: {request.url}")
    logger.info(f"[{request_id}] 请求头: {dict(request.headers)}")
    logger.info(f"[{request_id}] Accept头: {request.headers.get('accept', 'None')}")

    try:
        # 创建一个特殊的测试任务对象
        from datetime import datetime
        test_task = {
            "id": "test_json_to_sse",
            "sessionId": str(uuid.uuid4()),
            "status": {
                "state": "working",
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": "这是测试SSE任务"}]
                },
                "timestamp": datetime.now().isoformat()
            },
            "metadata": {"test": True, "type": "sse_test"}
        }

        # 直接创建SSE响应
        logger.info(f"[{request_id}] 创建SSE响应")

        # 定义一个SSE生成器函数
        async def sse_generator():
            """生成SSE数据"""
            # 发送连接建立事件
            logger.info(f"[{request_id}] 发送连接建立事件")
            yield {"event": "connected", "data": json.dumps({'type': 'connection_established', 'timestamp': time.time()})}

            # 等待一小段时间
            await asyncio.sleep(0.1)

            # 发送任务初始状态
            logger.info(f"[{request_id}] 发送初始状态事件")
            yield {"event": "status", "data": json.dumps({'task': test_task, 'timestamp': time.time()})}

            # 发送几个测试状态更新
            for i in range(3):
                await asyncio.sleep(0.5)
                update_data = {
                    'data': {
                        'jsonrpc': '2.0',
                        'result': {
                            'id': test_task["id"],
                            'progress': (i + 1) * 25,
                            'timestamp': time.time()
                        }
                    },
                    'timestamp': time.time()
                }
                logger.info(f"[{request_id}] 发送状态更新事件 #{i+1}")
                yield {"event": "update", "data": json.dumps(update_data)}

            # 发送完成状态
            await asyncio.sleep(0.5)
            complete_data = {
                'data': {
                    'jsonrpc': '2.0',
                    'result': {
                        'id': test_task["id"],
                        'status': 'completed',
                        'timestamp': time.time()
                    }
                },
                'timestamp': time.time()
            }
            logger.info(f"[{request_id}] 发送完成状态事件")
            yield {"event": "update", "data": json.dumps(complete_data)}

            # 发送完成事件
            await asyncio.sleep(0.5)
            final_data = {
                'task': test_task,
                'final': True,
                'timestamp': time.time()
            }
            logger.info(f"[{request_id}] 发送最终事件")
            yield {"event": "final", "data": json.dumps(final_data)}

        # 使用EventSourceResponse创建SSE响应
        response = EventSourceResponse(
            sse_generator(),
            status_code=200,
            ping=15  # 保持连接的ping间隔
        )

        # 确保响应头正确
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        response.headers["X-Accel-Buffering"] = "no"

        logger.info(f"[{request_id}] 响应头: {dict(response.headers)}")
        logger.info(f"[{request_id}] 返回SSE响应: {type(response).__name__}")

        return response
    except Exception as e:
        logger.error(f"[{request_id}] 处理旧格式测试请求出错: {str(e)}")
        import traceback
        logger.error(f"[{request_id}] 错误详情: {traceback.format_exc()}")

        # 确保错误响应也使用SSE格式
        return create_error_response(ErrorCode.INTERNAL_ERROR, f"处理旧格式测试请求出错: {str(e)}")
logger.debug("已注册路由: /a2a/task/subscribe/test_json_to_sse -> legacy_test_json_to_sse (高优先级路由)")

# 统一的SSE测试端点
@app.get("/a2a/sse-test/{test_type}")
async def a2a_sse_test(test_type: str, request: Request, delay: float = 0.5):
    """统一的SSE测试端点"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到SSE测试请求: {test_type}, 路径: {request.url.path}")
    logger.info(f"[{request_id}] 请求头: {dict(request.headers)}")
    logger.info(f"[{request_id}] Accept头: {request.headers.get('accept', 'None')}")

    # 检查是否是JSON到SSE的特殊测试
    if test_type.lower() in ["json-to-sse", "json_to_sse"]:
        logger.info(f"[{request_id}] 检测到特殊测试类型: {test_type}")

    # 创建SSE响应
    logger.info(f"[{request_id}] 开始创建SSE响应")
    response = create_test_sse_response(test_type, delay)

    # 检查响应类型
    logger.info(f"[{request_id}] 创建SSE响应成功，类型: {type(response).__name__}")
    if hasattr(response, 'headers'):
        logger.info(f"[{request_id}] 创建后的响应头: {dict(response.headers)}")

        # 确保Content-Type正确
        if response.headers.get('content-type') != 'text/event-stream':
            logger.warning(f"[{request_id}] 响应Content-Type不正确: {response.headers.get('content-type')}")
            response.headers['content-type'] = 'text/event-stream'

        logger.info(f"[{request_id}] 响应头设置完成: {dict(response.headers)}")

    logger.info(f"[{request_id}] 测试SSE响应创建成功，类型: {type(response)}")
    return response
logger.debug("已注册路由: /a2a/sse-test/{test_type} -> a2a_sse_test")

# 直接SSE测试端点
@app.get("/a2a/test/direct-sse")
async def direct_sse_test(request: Request):
    """直接SSE测试端点"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到SSE测试请求: direct, 路径: {request.url.path}")
    logger.info(f"[{request_id}] 请求头: {dict(request.headers)}")
    logger.info(f"[{request_id}] Accept头: {request.headers.get('accept', 'None')}")

    # 创建SSE响应
    logger.info(f"[{request_id}] 开始创建SSE响应")
    response = create_test_sse_response("standard", 0.05)

    # 检查响应类型
    logger.info(f"[{request_id}] 创建SSE响应成功，类型: {type(response).__name__}")
    if hasattr(response, 'headers'):
        logger.info(f"[{request_id}] 创建后的响应头: {dict(response.headers)}")

        # 确保Content-Type正确
        if response.headers.get('content-type') != 'text/event-stream':
            logger.warning(f"[{request_id}] 响应Content-Type不正确: {response.headers.get('content-type')}")
            response.headers['content-type'] = 'text/event-stream'

        logger.info(f"[{request_id}] 响应头设置完成: {dict(response.headers)}")

    logger.info(f"[{request_id}] 测试SSE响应创建成功，类型: {type(response)}")
    return response
logger.debug("已注册路由: /a2a/test/direct-sse -> direct_sse_test")

# 简单SSE测试端点
@app.get("/a2a/test/simple-sse")
async def simple_sse_test(request: Request):
    """简单SSE测试端点"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到SSE测试请求: simple, 路径: {request.url.path}")
    logger.info(f"[{request_id}] 请求头: {dict(request.headers)}")
    logger.info(f"[{request_id}] Accept头: {request.headers.get('accept', 'None')}")

    # 创建SSE响应
    logger.info(f"[{request_id}] 开始创建SSE响应")
    response = create_test_sse_response("standard", 0.5)

    # 检查响应类型
    logger.info(f"[{request_id}] 创建SSE响应成功，类型: {type(response).__name__}")
    if hasattr(response, 'headers'):
        logger.info(f"[{request_id}] 创建后的响应头: {dict(response.headers)}")

        # 确保Content-Type正确
        if response.headers.get('content-type') != 'text/event-stream':
            logger.warning(f"[{request_id}] 响应Content-Type不正确: {response.headers.get('content-type')}")
            response.headers['content-type'] = 'text/event-stream'

        logger.info(f"[{request_id}] 响应头设置完成: {dict(response.headers)}")

    logger.info(f"[{request_id}] 测试SSE响应创建成功，类型: {type(response)}")
    return response
logger.debug("已注册路由: /a2a/test/simple-sse -> simple_sse_test")

# 通用SSE测试端点
@app.get("/a2a/test/sse")
async def sse_test(request: Request):
    """通用SSE测试端点"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到SSE测试请求: general, 路径: {request.url.path}")
    logger.info(f"[{request_id}] 请求头: {dict(request.headers)}")
    logger.info(f"[{request_id}] Accept头: {request.headers.get('accept', 'None')}")

    # 创建SSE响应
    logger.info(f"[{request_id}] 开始创建SSE响应")
    response = create_test_sse_response("standard", 0.5)

    # 检查响应类型
    logger.info(f"[{request_id}] 创建SSE响应成功，类型: {type(response).__name__}")
    if hasattr(response, 'headers'):
        logger.info(f"[{request_id}] 创建后的响应头: {dict(response.headers)}")

        # 确保Content-Type正确
        if response.headers.get('content-type') != 'text/event-stream':
            logger.warning(f"[{request_id}] 响应Content-Type不正确: {response.headers.get('content-type')}")
            response.headers['content-type'] = 'text/event-stream'

        logger.info(f"[{request_id}] 响应头设置完成: {dict(response.headers)}")

    logger.info(f"[{request_id}] 测试SSE响应创建成功，类型: {type(response)}")
    return response
logger.debug("已注册路由: /a2a/test/sse -> sse_test")

# 添加工具发现端点
@app.get("/a2a/discover")
async def discover_tools():
    """工具发现端点 - 返回所有可用工具"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到工具发现请求")

    # 创建测试工具列表
    tools = [
        {
            "name": "test_tool",
            "description": "测试工具 - 仅用于测试SSE功能"
        }
    ]

    # 查找并添加工具目录中的工具
    tools_dir = os.path.join(script_dir, 'a2a', 'tools')
    if os.path.exists(tools_dir):
        logger.info(f"[{request_id}] 检查工具目录: {tools_dir}")
        try:
            tool_files = [f for f in os.listdir(tools_dir) if f.endswith('.py') and not f.startswith('__')]
            for tool_file in tool_files:
                tool_name = tool_file.replace('_tool.py', '').replace('.py', '')
                logger.info(f"[{request_id}] 发现工具: {tool_name}")
                tools.append({
                    "name": tool_name,
                    "description": f"{tool_name} 工具"
                })
        except Exception as e:
            logger.error(f"[{request_id}] 读取工具目录失败: {str(e)}")

    logger.info(f"[{request_id}] 返回工具列表: {tools}")

    # 返回标准A2A工具发现响应
    return {
        "jsonrpc": "2.0",
        "result": {
            "tools": tools
        }
    }
logger.debug("已注册路由: /a2a/discover -> discover_tools")

# 添加Agent卡片端点
@app.get("/.well-known/agent.json")
async def get_agent_json():
    """获取agent.json"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到Agent卡片请求")

    # 创建Agent卡片
    agent_card = {
        "name": "Sisi A2A Server",
        "description": "基于A2A协议的Sisi服务",
        "version": "1.0.0",
        "contact": {
            "name": "Sisi团队",
            "url": "https://github.com/liusisi/SmartSisi"
        }
    }

    logger.info(f"[{request_id}] 返回Agent卡片")
    return agent_card
logger.debug("已注册路由: /.well-known/agent.json -> get_agent_json")

# 添加工具调用端点
@app.post("/a2a/invoke/{tool_name}")
async def invoke_tool(tool_name: str, request: Request):
    """工具调用端点 - 执行指定的工具"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到工具调用请求: {tool_name}")

    # 获取请求体
    try:
        body = await request.json()
        logger.info(f"[{request_id}] 工具调用参数: {body}")
    except Exception as e:
        logger.error(f"[{request_id}] 解析请求体失败: {str(e)}")
        body = {}

    # 检查工具是否存在
    tools_dir = os.path.join(script_dir, 'a2a', 'tools')
    tool_file = os.path.join(tools_dir, f"{tool_name}.py")
    tool_module_file = os.path.join(tools_dir, f"{tool_name}_tool.py")

    if not (os.path.exists(tool_file) or os.path.exists(tool_module_file)):
        # 尝试测试工具
        if tool_name == "test_tool":
            logger.info(f"[{request_id}] 执行测试工具")
            return {
                "jsonrpc": "2.0",
                "result": {
                    "status": "success",
                    "message": "这是测试工具的响应",
                    "data": body
                }
            }
        logger.error(f"[{request_id}] 工具不存在: {tool_name}")
        return JSONResponse(
            status_code=404,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"工具不存在: {tool_name}"
                }
            }
        )

    # 动态加载工具模块并执行
    try:
        logger.info(f"[{request_id}] 找到工具: {tool_name}，尝试动态加载并执行")

        # 确定模块路径
        module_path = None
        module_name = None

        if os.path.exists(tool_file):
            module_path = tool_file
            module_name = tool_name
        elif os.path.exists(tool_module_file):
            module_path = tool_module_file
            module_name = f"{tool_name}_tool"

        if not module_path:
            raise FileNotFoundError(f"找不到工具模块: {tool_name}")

        # 动态导入模块
        import importlib.util
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 检查模块是否有invoke函数
        if hasattr(module, 'invoke'):
            logger.info(f"[{request_id}] 找到工具的invoke函数，准备执行")

            # 准备参数
            # 检查是否是JSONRPC格式
            if isinstance(body, dict) and 'jsonrpc' in body and 'method' in body and 'params' in body:
                params = body.get('params', {})
                call_id = body.get('id', f'auto_{str(uuid.uuid4())[:8]}')
            else:
                params = body
                call_id = f'auto_{str(uuid.uuid4())[:8]}'

            # 执行工具
            try:
                result = module.invoke(params)
                logger.info(f"[{request_id}] 工具执行成功: {tool_name}")

                # 格式化响应
                return {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": call_id
                }
            except Exception as e:
                logger.error(f"[{request_id}] 工具执行失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())

                return JSONResponse(
                    status_code=500,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32000,
                            "message": f"工具执行错误: {str(e)}"
                        },
                        "id": call_id
                    }
                )
        else:
            logger.error(f"[{request_id}] 工具模块缺少invoke函数: {module_path}")
            return JSONResponse(
                status_code=500,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32000,
                        "message": f"工具模块缺少invoke函数"
                    }
                }
            )

    except Exception as e:
        logger.error(f"[{request_id}] 动态加载工具失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        # 由于真实工具加载失败，此处临时返回一个明确标记的错误响应
        # 不再返回模拟数据，避免误导用户
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": f"动态加载工具失败: {str(e)}"
                }
            }
        )
logger.debug("已注册路由: /a2a/invoke/{tool_name} -> invoke_tool")

# 添加工具元数据端点
@app.get("/a2a/tool/{tool_name}/metadata")
async def get_tool_metadata(tool_name: str):
    """获取工具元数据"""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 收到工具元数据请求: {tool_name}")

    # 检查工具是否存在
    tools_dir = os.path.join(script_dir, 'a2a', 'tools')
    tool_file = os.path.join(tools_dir, f"{tool_name}.py")
    tool_module_file = os.path.join(tools_dir, f"{tool_name}_tool.py")

    if not (os.path.exists(tool_file) or os.path.exists(tool_module_file)):
        # 特殊处理测试工具
        if tool_name == "test_tool":
            return {
                "name": "test_tool",
                "description": "测试工具 - 仅用于测试API功能",
                "schema": {
                    "input": {
                        "type": "object",
                        "properties": {
                            "test_param": {
                                "type": "string",
                                "description": "测试参数"
                            }
                        }
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "result": {
                                "type": "string",
                                "description": "测试结果"
                            }
                        }
                    }
                }
            }

        logger.error(f"[{request_id}] 工具不存在: {tool_name}")
        return JSONResponse(
            status_code=404,
            content={
                "detail": "Tool not found"
            }
        )

    # 根据不同工具返回不同元数据
    logger.info(f"[{request_id}] 找到工具: {tool_name}，返回工具元数据")

    if tool_name == "location_weather":
        return {
            "name": "location_weather",
            "description": "获取指定位置的天气信息",
            "schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "位置名称，如城市名"
                        }
                    }
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "weather": {
                            "type": "object",
                            "properties": {
                                "temperature": {"type": "string"},
                                "condition": {"type": "string"},
                                "humidity": {"type": "string"}
                            }
                        }
                    }
                }
            }
        }
    elif tool_name == "currency":
        return {
            "name": "currency",
            "description": "货币转换工具",
            "schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "from": {
                            "type": "string",
                            "description": "源货币代码，如USD"
                        },
                        "to": {
                            "type": "string",
                            "description": "目标货币代码，如CNY"
                        },
                        "amount": {
                            "type": "number",
                            "description": "转换金额"
                        }
                    }
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "conversion": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "rate": {"type": "number"},
                                "result": {"type": "number"}
                            }
                        }
                    }
                }
            }
        }
    else:
        # 动态加载工具并获取元数据
        try:
            # 尝试加载工具模块
            if os.path.exists(tool_module_file):
                tool_path = tool_module_file
            else:
                tool_path = tool_file
            
            # 动态导入工具
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"a2a_tool_{tool_name}", tool_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 查找工具类
            tool_instance = None
            for item_name in dir(module):
                item = getattr(module, item_name)
                if isinstance(item, type) and hasattr(item, 'get_metadata'):
                    try:
                        tool_instance = item()
                        break
                    except:
                        continue
            
            # 如果找到了工具实例且有get_metadata方法，调用它
            if tool_instance and hasattr(tool_instance, 'get_metadata'):
                metadata = tool_instance.get_metadata()
                logger.info(f"[{request_id}] 成功获取工具元数据: {tool_name}")
                return metadata
            else:
                # 回退到通用元数据
                logger.warning(f"[{request_id}] 工具没有get_metadata方法: {tool_name}")
                return {
                    "name": tool_name,
                    "description": f"{tool_name} 工具",
                    "schema": {
                        "input": {"type": "object", "properties": {}},
                        "output": {"type": "object", "properties": {}}
                    }
                }
        except Exception as e:
            logger.error(f"[{request_id}] 加载工具元数据失败: {str(e)}")
            # 返回通用元数据
            return {
                "name": tool_name,
                "description": f"{tool_name} 工具",
                "schema": {
                    "input": {"type": "object", "properties": {}},
                    "output": {"type": "object", "properties": {}}
                }
            }
logger.debug("已注册路由: /a2a/tool/{tool_name}/metadata -> get_tool_metadata")

# 获取当前已注册的路由信息
routes = []
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'name'):
        routes.append(f"{route.path} - {route.name}")

# 按字母顺序打印路由列表
logger.info(f"服务器启动前已注册的路由数量: {len(routes)}")
logger.info(f"路由列表: {routes}")

# 汇总路由优先级顺序信息
logger.debug("=== 路由注册优先级顺序汇总 ===")
for i, route in enumerate(app.routes):
    if hasattr(route, 'path'):
        logger.debug(f"[{i+1}] {route.path}")
logger.debug("=== 路由注册完成 ===")

# 启动服务器
if __name__ == "__main__":
    try:
        import uvicorn
        # 启动服务器
        logger.info("启动A2A服务器 http://0.0.0.0:8001")
        uvicorn.run(app, host="0.0.0.0", port=8001)
    except Exception as e:
        logger.error(f"启动服务器失败: {str(e)}")
        logger.error(traceback.format_exc())

