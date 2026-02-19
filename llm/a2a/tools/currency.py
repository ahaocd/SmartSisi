"""
货币汇率转换工具 - 符合A2A规范
"""

import re
import requests
from typing import Optional, Dict, Any
import time

def get_currency_regex_result(query: str) -> Dict[str, Any]:
    """
    从查询文本中提取货币转换信息
    
    Args:
        query: 用户查询文本
        
    Returns:
        Dict: 包含提取的信息
    """
    # 匹配模式：
    # 1. 数字 + 货币单位1 + (转换/兑换/等于) + 货币单位2
    # 2. 货币单位1 + 和 + 货币单位2 + 汇率
    
    # 货币代码映射
    currency_map = {
        "人民币": "CNY", "元": "CNY", "rmb": "CNY", "cny": "CNY", "￥": "CNY",
        "美元": "USD", "美金": "USD", "刀": "USD", "usd": "USD", "$": "USD",
        "欧元": "EUR", "欧元": "EUR", "eur": "EUR", "€": "EUR",
        "日元": "JPY", "日币": "JPY", "jpy": "JPY", "¥": "JPY",
        "英镑": "GBP", "gbp": "GBP", "£": "GBP",
        "韩元": "KRW", "韩币": "KRW", "krw": "KRW",
        "港元": "HKD", "港币": "HKD", "hkd": "HKD",
        "澳元": "AUD", "澳币": "AUD", "aud": "AUD",
        "加元": "CAD", "加币": "CAD", "cad": "CAD",
    }
    
    # 模式1: 数值+货币单位+转换相关词+货币单位
    pattern1 = r'(\d+(?:\.\d+)?)\s*(美元|人民币|欧元|日元|英镑|韩元|港元|澳元|加元|美金|元|rmb|cny|usd|eur|jpy|gbp|krw|hkd|aud|cad|[\$\￥\€\£\¥])\s*(?:兑换|换|转换|等于|是|=|to|in|into)\s*(美元|人民币|欧元|日元|英镑|韩元|港元|澳元|加元|美金|元|rmb|cny|usd|eur|jpy|gbp|krw|hkd|aud|cad|[\$\￥\€\£\¥])'
    
    # 尝试匹配
    match = re.search(pattern1, query.lower())
    if match:
        amount_str, from_currency, to_currency = match.groups()
        
        # 转换货币单位为标准代码
        from_code = currency_map.get(from_currency.lower(), "CNY")
        to_code = currency_map.get(to_currency.lower(), "USD")
        
        # 确保数值正确
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 1.0
            
        return {
            "amount": amount,
            "from": from_code,
            "to": to_code
        }
    
    # 模式2: 简单的汇率查询
    pattern2 = r'(美元|人民币|欧元|日元|英镑|韩元|港元|澳元|加元|美金|元|rmb|cny|usd|eur|jpy|gbp|krw|hkd|aud|cad|[\$\￥\€\£\¥])\s*(?:和|兑|to|against)\s*(美元|人民币|欧元|日元|英镑|韩元|港元|澳元|加元|美金|元|rmb|cny|usd|eur|jpy|gbp|krw|hkd|aud|cad|[\$\￥\€\£\¥])(?:\s*的?汇率|exchange\s*rate)?'
    
    match = re.search(pattern2, query.lower())
    if match:
        from_currency, to_currency = match.groups()
        
        # 转换货币单位为标准代码
        from_code = currency_map.get(from_currency.lower(), "CNY")
        to_code = currency_map.get(to_currency.lower(), "USD")
            
        return {
            "amount": 1.0,
            "from": from_code,
            "to": to_code
        }
    
    # 无法匹配时返回默认值
    return {
        "amount": 1.0,
        "from": "CNY", 
        "to": "USD"
    }

def currency(query: str) -> str:
    """
    货币汇率转换工具 - 符合A2A规范
    
    Args:
        query: 用户查询内容
        
    Returns:
        str: 转换结果
    """
    try:
        # 解析查询文本
        currency_info = get_currency_regex_result(query)
        amount = currency_info["amount"]
        from_currency = currency_info["from"]
        to_currency = currency_info["to"]
        
        # 调用Frankfurt API获取汇率
        url = f"https://api.frankfurter.app/latest"
        params = {"amount": amount, "from": from_currency, "to": to_currency}
        
        response = requests.get(url, params=params)
        
        # 检查响应状态
        if response.status_code != 200:
            return f"汇率查询失败，错误码：{response.status_code}"
        
        # 解析响应
        data = response.json()
        
        if "rates" not in data:
            return f"无法获取{from_currency}和{to_currency}的汇率信息"
        
        # 获取转换结果
        converted_amount = data["rates"].get(to_currency)
        
        if converted_amount is None:
            return f"无法转换{from_currency}到{to_currency}的汇率"
        
        # 格式化结果
        base_date = data.get("date", "today")
        result = f"{amount} {from_currency} = {converted_amount} {to_currency} (日期: {base_date})"
        
        return result
        
    except Exception as e:
        return f"汇率转换出错: {str(e)}"

def create_tool():
    """创建工具实例"""
    class CurrencyTool:
        """货币汇率转换工具"""
        
        def __init__(self):
            """初始化工具"""
            self.name = "currency"
            self.description = "货币汇率转换查询工具"
            self.version = "1.0.0"
            self.task_states = {}  # 存储任务状态
        
        def run(self, query: str, task_id: str = None):
            """异步执行查询"""
            result = currency(query)
            return {"status": "completed", "result": result}
        
        def invoke(self, query):
            return currency(query)
            
        async def ainvoke(self, query):
            return currency(query)
        
        def create_task(self, query: str):
            """创建新任务"""
            import uuid
            task_id = str(uuid.uuid4())
            self.task_states[task_id] = {"status": "submitted", "query": query}
            return {"task_id": task_id}
        
        def update_task_state(self, task_id: str, status: str, result=None):
            """更新任务状态"""
            if task_id in self.task_states:
                self.task_states[task_id]["status"] = status
                if result is not None:
                    self.task_states[task_id]["result"] = result
        
        def get_task_state(self, task_id: str):
            """获取任务状态"""
            return self.task_states.get(task_id, {"status": "unknown"})
        
        def health_check(self):
            """健康状态检查"""
            return {"status": "healthy"}
        
        def get_capabilities(self):
            """获取工具能力列表"""
            return [
                "货币汇率转换",
                "支持多种常见货币",
                "使用实时汇率数据"
            ]
        
        def get_examples(self):
            """获取工具示例列表"""
            return [
                "1美元等于多少人民币",
                "100元人民币可以换多少日元",
                "50欧元兑换美金"
            ]
        
        def get_metadata(self):
            """获取工具元数据 - A2A标准卡片格式"""
            return {
                "name": self.name,
                "version": self.version,
                "description": self.description,
                "capabilities": self.get_capabilities(),
                "examples": self.get_examples()
            }
        
        def handle_a2a_request(self, request):
            """处理A2A标准请求"""
            method = request.get("method", "")
            params = request.get("params", {})
            
            if method == "invoke":
                query = params.get("query", "")
                result = currency(query)
                return {"success": True, "result": {"message": result}}
            
            return {"success": False, "error": "不支持的方法"}
    
    # 返回工具实例，不要返回类定义！
    return CurrencyTool()

# 用于测试
if __name__ == "__main__":
    test_queries = [
        "1美元等于多少人民币",
        "100元人民币兑换美元",
        "10欧元转换成日元",
        "美元和人民币的汇率",
        "500港币换成人民币"
    ]
    
    for query in test_queries:
        print(f"查询: {query}")
        result = currency(query)
        print(f"结果: {result}\n") 

# 添加模块级的invoke函数，作为A2A服务器调用的入口点
def invoke(params):
    """
    模块级invoke函数，供A2A服务器直接调用
    
    Args:
        params: 调用参数，可以是字符串或字典
        
    Returns:
        Dict: 工具执行结果
    """
    print(f"[currency] 模块级invoke调用，参数: {params}")
    
    # 提取查询文本
    query = None
    if isinstance(params, dict):
        # 如果是JSON-RPC格式
        if "jsonrpc" in params and "method" in params and "params" in params:
            inner_params = params.get("params", {})
            query = inner_params.get("query", "")
        else:
            # 尝试各种可能的参数名
            for key in ["query", "text", "amount", "from", "to"]:
                if key in params:
                    query = params
                    break
            if query is None:
                query = str(params)
    else:
        # 如果是字符串或其他类型
        query = str(params)
    
    if isinstance(query, str):
        # 直接调用currency函数
        result = currency(query)
    else:
        # 针对字典类型参数的处理
        amount = query.get("amount", 1.0)
        from_currency = query.get("from", "CNY")
        to_currency = query.get("to", "USD")
        
        try:
            # 调用Frankfurt API获取汇率
            url = f"https://api.frankfurter.app/latest"
            params = {"amount": amount, "from": from_currency, "to": to_currency}
            
            response = requests.get(url, params=params)
            
            # 检查响应状态
            if response.status_code != 200:
                result = f"汇率查询失败，错误码：{response.status_code}"
            else:
                # 解析响应
                data = response.json()
                
                if "rates" not in data:
                    result = f"无法获取{from_currency}和{to_currency}的汇率信息"
                else:
                    # 获取转换结果
                    converted_amount = data["rates"].get(to_currency)
                    
                    if converted_amount is None:
                        result = f"无法转换{from_currency}到{to_currency}的汇率"
                    else:
                        # 格式化结果
                        base_date = data.get("date", "today")
                        result = f"{amount} {from_currency} = {converted_amount} {to_currency} (日期: {base_date})"
        except Exception as e:
            result = f"汇率转换出错: {str(e)}"
    
    # 构建标准响应格式
    return {
        "conversion": {
            "query": str(query),
            "result": result,
            "timestamp": time.time()
        }
    } 