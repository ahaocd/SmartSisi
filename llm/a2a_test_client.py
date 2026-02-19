"""
A2A客户端测试脚本
测试A2A服务器是否正常工作
"""

import os
import sys
import json
import time
import asyncio
import requests
import argparse
import logging
from typing import Dict, Any, List

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class A2AClient:
    """A2A客户端"""
    
    def __init__(self, server_url: str = "http://localhost:8001"):
        """
        初始化A2A客户端
        
        Args:
            server_url: A2A服务器URL
        """
        self.server_url = server_url
    
    def get_agent_card(self) -> Dict[str, Any]:
        """获取代理卡片信息"""
        try:
            response = requests.get(f"{self.server_url}/.well-known/agent.json", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取代理卡片失败: {str(e)}")
            return {"error": str(e)}
    
    def send_task(self, query: str) -> Dict[str, Any]:
        """
        发送任务请求
        
        Args:
            query: 查询文本
            
        Returns:
            任务响应
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "invoke",
            "params": {
                "query": query,
                "id": f"task_{int(time.time())}",
                "sessionId": f"session_{int(time.time())}",
                "acceptedOutputModes": ["text"],
                "inputMode": "text"
            },
            "id": f"call_{int(time.time())}"
        }
        
        try:
            response = requests.post(
                f"{self.server_url}/a2a/jsonrpc",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"发送任务失败: {str(e)}")
            return {"error": str(e)}
    
    def invoke_tool(self, tool_name: str, query: str) -> Dict[str, Any]:
        """
        直接调用工具
        
        Args:
            tool_name: 工具名称
            query: 查询文本
            
        Returns:
            工具响应
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "invoke",
            "params": {
                "query": query,
                "sync": True
            },
            "id": f"call_{int(time.time())}"
        }
        
        try:
            response = requests.post(
                f"{self.server_url}/a2a/invoke/{tool_name}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"调用工具失败: {str(e)}")
            return {"error": str(e)}
    
    def get_task_status(self, task_id: str, tool_name: str = "langgraph") -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            tool_name: 工具名称
            
        Returns:
            任务状态
        """
        try:
            response = requests.get(
                f"{self.server_url}/a2a/task/{tool_name}/{task_id}",
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取任务状态失败: {str(e)}")
            return {"error": str(e)}
    
    def route_query(self, query: str) -> Dict[str, Any]:
        """
        路由查询到合适的工具
        
        Args:
            query: 查询文本
            
        Returns:
            路由结果
        """
        try:
            response = requests.post(
                f"{self.server_url}/a2a/route/query",
                json={"query": query},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"路由查询失败: {str(e)}")
            return {"error": str(e)}
            
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            response = requests.get(f"{self.server_url}/a2a/health", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"健康检查失败: {str(e)}")
            return {"error": str(e)}

def print_json(data: Dict[str, Any]):
    """美化打印JSON"""
    print(json.dumps(data, indent=2, ensure_ascii=False))

async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="A2A客户端测试工具")
    parser.add_argument("--url", default="http://localhost:8001", help="A2A服务器URL")
    parser.add_argument("--action", default="info", choices=["info", "query", "tool", "status", "route", "health"], 
                        help="执行的操作")
    parser.add_argument("--query", default="今天天气怎么样？", help="查询文本")
    parser.add_argument("--tool", default="langgraph", help="工具名称")
    parser.add_argument("--task", default="", help="任务ID")
    args = parser.parse_args()
    
    # 创建客户端
    client = A2AClient(server_url=args.url)
    
    # 执行操作
    if args.action == "info":
        logger.info("获取代理卡片信息...")
        result = client.get_agent_card()
        print_json(result)
        
    elif args.action == "query":
        logger.info(f"发送查询: {args.query}")
        result = client.send_task(args.query)
        print_json(result)
        
        # 如果成功获取任务ID，等待并获取状态
        if "result" in result and "task_id" in result["result"]:
            task_id = result["result"]["task_id"]
            logger.info(f"任务ID: {task_id}, 等待任务完成...")
            
            # 轮询任务状态
            for _ in range(10):
                time.sleep(2)
                status = client.get_task_status(task_id)
                
                if "result" in status:
                    task_status = status["result"]["status"]["state"]
                    logger.info(f"任务状态: {task_status}")
                    
                    if task_status in ["completed", "failed", "canceled"]:
                        print_json(status)
                        break
                else:
                    logger.error("获取任务状态失败")
                    break
            
    elif args.action == "tool":
        logger.info(f"直接调用工具 {args.tool}, 查询: {args.query}")
        result = client.invoke_tool(args.tool, args.query)
        print_json(result)
        
    elif args.action == "status":
        if not args.task:
            logger.error("缺少任务ID参数 --task")
            return
            
        logger.info(f"获取任务状态: {args.task}")
        result = client.get_task_status(args.task, args.tool)
        print_json(result)
        
    elif args.action == "route":
        logger.info(f"路由查询: {args.query}")
        result = client.route_query(args.query)
        print_json(result)
        
    elif args.action == "health":
        logger.info("执行健康检查...")
        result = client.health_check()
        print_json(result)

if __name__ == "__main__":
    asyncio.run(main()) 