"""SSE工具模块 - 提供标准化的SSE响应处理"""
import json
import time
import asyncio
import logging
from typing import Dict, Any, AsyncGenerator, Optional, Union, AsyncIterable, Callable, Awaitable
from sse_starlette.sse import EventSourceResponse
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# 添加A2A错误码定义
class ErrorCode:
    """定义A2A标准错误码"""
    # 标准JSON-RPC错误码
    PARSE_ERROR = -32700       # 解析错误
    INVALID_REQUEST = -32600   # 无效请求
    METHOD_NOT_FOUND = -32601  # 方法未找到
    INVALID_PARAMS = -32602    # 无效参数
    INTERNAL_ERROR = -32603    # 内部错误
    
    # A2A特定错误码
    UNAUTHORIZED = -32000      # 未授权
    TASK_CREATION_FAILED = -32001 # 任务创建失败
    TASK_NOT_FOUND = -32001     # 任务未找到
    INVALID_TASK_STATE = -32002 # 无效任务状态 

# 为了向后兼容，保留原有类名
A2AErrorCodes = ErrorCode

def create_sse_response(
    generator, 
    status_code: int = 200,
    ping_interval: int = 15,
):
    """创建标准化的SSE响应"""
    return EventSourceResponse(
        content=generator,
        media_type="text/event-stream",
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # 添加Nginx兼容头，防止缓冲
        },
        status_code=status_code,
        ping=ping_interval
    )

async def standard_sse_generator(data_generator: AsyncIterable):
    """标准SSE事件流包装器
    
    Args:
        data_generator: 异步生成器，生成事件数据
            如果生成的数据包含"event"键，则使用其值作为事件类型
            否则使用"message"作为默认事件类型
    """
    # 发送连接事件
    connection_event = {"type": "connection_established", "timestamp": time.time()}
    logger.debug(f"SSE: 发送连接事件 {connection_event}")
    yield f"event: connected\ndata: {json.dumps(connection_event)}\n\n"
    
    # 处理实际数据
    async for event_data in data_generator:
        if isinstance(event_data, dict) and "event" in event_data:
            event_type = event_data.pop("event")
            logger.debug(f"SSE: 发送自定义事件 {event_type}: {event_data}")
            yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"
        else:
            logger.debug(f"SSE: 发送消息事件: {event_data}")
            yield f"event: message\ndata: {json.dumps(event_data)}\n\n"

async def error_event_generator(error_code: int, error_message: str):
    """生成标准格式的错误事件"""
    # 发送连接事件
    connection_event = {"type": "connection_established", "timestamp": time.time()}
    logger.debug(f"SSE错误: 发送连接事件 {connection_event}")
    yield f"event: connected\ndata: {json.dumps(connection_event)}\n\n"
    
    # 发送错误事件
    error_data = {
        "jsonrpc": "2.0",
        "error": {"code": error_code, "message": error_message}
    }
    logger.debug(f"SSE错误: 发送错误事件: {error_data}")
    yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
    
    # 发送结束事件
    logger.debug(f"SSE错误: 发送结束事件")
    yield f"event: final\ndata: {json.dumps({'final': True, 'timestamp': time.time()})}\n\n"

def create_error_response(error_code: int, error_message: str):
    """创建标准化的SSE错误响应"""
    logger.info(f"创建SSE错误响应: 代码={error_code}, 消息={error_message}")
    return create_sse_response(
        error_event_generator(error_code, error_message),
        status_code=200  # 使用200状态码，确保客户端接收SSE流
    )

def create_task_not_found_response(task_id: Union[str, Dict]):
    """创建任务未找到的标准错误响应"""
    # 处理task_id可能是字典的情况
    if isinstance(task_id, dict):
        task_id = task_id.get("id", "未知ID")
    logger.info(f"创建任务未找到的SSE响应: {task_id}")
    return create_error_response(
        ErrorCode.TASK_NOT_FOUND,
        f"任务未找到: {task_id}"
    )
    
def create_task_manager_not_initialized_response():
    """创建任务管理器未初始化的错误响应"""
    return create_error_response(
        ErrorCode.INTERNAL_ERROR,
        "任务管理器未初始化"
    )

async def generate_standard_sse_events(delay=0.5):
    """生成标准SSE事件流"""
    # 连接建立事件
    yield f"event: connected\ndata: {json.dumps({'type': 'connection_established', 'timestamp': time.time()})}\n\n"
    await asyncio.sleep(delay)
    
    # 更新事件（3个）
    for i in range(3):
        yield f"event: update\ndata: {json.dumps({'message': f'更新 {i+1}/3', 'timestamp': time.time()})}\n\n"
        await asyncio.sleep(delay)
    
    # 最终事件
    yield f"event: final\ndata: {json.dumps({'message': '测试完成', 'final': True, 'timestamp': time.time()})}\n\n"

async def generate_error_sse_events(delay=0.5):
    """生成错误SSE事件流"""
    # 连接建立事件
    yield f"event: connected\ndata: {json.dumps({'type': 'connection_established', 'timestamp': time.time()})}\n\n"
    await asyncio.sleep(delay)
    
    # 错误事件
    yield f"event: error\ndata: {json.dumps({'error': '测试错误', 'code': 500, 'timestamp': time.time()})}\n\n"
    await asyncio.sleep(delay)
    
    # 最终事件
    yield f"event: final\ndata: {json.dumps({'error': '测试错误', 'final': True, 'timestamp': time.time()})}\n\n"

async def generate_long_test_sse_events(delay=0.5):
    """生成长时间SSE事件流（10个更新）"""
    # 连接建立事件
    yield f"event: connected\ndata: {json.dumps({'type': 'connection_established', 'timestamp': time.time()})}\n\n"
    await asyncio.sleep(delay)
    
    # 更新事件（10个）
    for i in range(10):
        yield f"event: update\ndata: {json.dumps({'message': f'长测试更新 {i+1}/10', 'progress': (i+1)/10, 'timestamp': time.time()})}\n\n"
        await asyncio.sleep(delay)
    
    # 最终事件
    yield f"event: final\ndata: {json.dumps({'message': '长测试完成', 'final': True, 'timestamp': time.time()})}\n\n"

def create_test_sse_response(test_type="standard", delay=0.5):
    """
    创建测试SSE响应
    
    参数:
        test_type: 测试类型 (standard, error, long)
        delay: 事件间延迟(秒)
    
    返回:
        StreamingResponse: SSE流式响应
    """
    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    }
    
    # 根据测试类型选择不同的事件生成器
    if test_type == "error":
        generator = generate_error_sse_events(delay)
        logger.info(f"创建错误测试SSE响应，延迟={delay}秒")
    elif test_type == "long":
        generator = generate_long_test_sse_events(delay)
        logger.info(f"创建长测试SSE响应，延迟={delay}秒")
    else:  # standard
        generator = generate_standard_sse_events(delay)
        logger.info(f"创建标准测试SSE响应，延迟={delay}秒")
    
    # 创建StreamingResponse
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers=headers
    ) 