"""
内容采集决策器
使用AI判断哪些内容值得采集
"""

import asyncio
from typing import List, Dict, Any
from openai import AsyncOpenAI
from config_loader import get_config

class ContentDecisionMaker:
    """内容采集决策器"""
    
    def __init__(self):
        config = get_config()
        model_config = config.get_decision_model_config()
        
        if not model_config['enabled']:
            raise ValueError("采集决策模型未启用")
        
        self.client = AsyncOpenAI(
            api_key=model_config['api_key'],
            base_url=model_config['base_url']
        )
        self.model = model_config['model']
        self.temperature = model_config['temperature']
        self.max_tokens = model_config['max_tokens']
        
        print(f"✅ 采集决策器初始化 - 模型: {self.model}")
    
    async def should_collect(
        self,
        content_text: str,
        content_type: str = 'message',
        keywords: List[str] = None
    ) -> Dict[str, Any]:
        """
        判断内容是否值得采集
        
        Args:
            content_text: 内容文本
            content_type: 内容类型 (message/photo/video)
            keywords: 关键词列表
        
        Returns:
            {
                'should_collect': bool,
                'reason': str,
                'score': float,  # 0-1
                'tags': List[str]
            }
        """
        # 构建提示词
        keywords_str = '、'.join(keywords) if keywords else '娱乐行业、夜场、KTV、招聘、女性服务人员'
        
        prompt = f"""你是ASIANIGHT内容采集决策专家。

任务：判断以下{content_type}内容是否值得采集到数据库。

关键词：{keywords_str}

内容：
{content_text[:500]}

评估标准：
1. 是否与娱乐行业（KTV、夜场、商务会所、足浴等）相关？
2. 是否涉及招聘、服务人员、行业信息？
3. 内容质量如何（原创度、信息量、实用性）？
4. 是否包含广告、垃圾信息？

请以JSON格式回复：
{{
    "should_collect": true/false,
    "reason": "判断原因",
    "score": 0.85,
    "tags": ["标签1", "标签2"]
}}"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是专业的内容筛选专家，擅长判断内容价值。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            return {
                'should_collect': result.get('should_collect', False),
                'reason': result.get('reason', ''),
                'score': result.get('score', 0.0),
                'tags': result.get('tags', [])
            }
            
        except Exception as e:
            print(f"❌ 决策失败: {e}")
            # 默认保守策略：采集
            return {
                'should_collect': True,
                'reason': f'决策失败，默认采集: {str(e)}',
                'score': 0.5,
                'tags': []
            }
    
    async def batch_decide(
        self,
        contents: List[Dict[str, str]],
        keywords: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        批量判断内容
        
        Args:
            contents: [{'text': '...', 'type': 'message'}, ...]
            keywords: 关键词列表
        
        Returns:
            决策结果列表
        """
        tasks = []
        for content in contents:
            task = self.should_collect(
                content_text=content.get('text', ''),
                content_type=content.get('type', 'message'),
                keywords=keywords
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        return results


class ContentOrganizer:
    """内容整理器 - 提取结构化信息"""
    
    def __init__(self):
        config = get_config()
        model_config = config.get_organize_model_config()
        
        if not model_config['enabled']:
            raise ValueError("内容整理模型未启用")
        
        self.client = AsyncOpenAI(
            api_key=model_config['api_key'],
            base_url=model_config['base_url']
        )
        self.model = model_config['model']
        self.temperature = model_config['temperature']
        self.max_tokens = model_config['max_tokens']
        
        print(f"✅ 内容整理器初始化 - 模型: {self.model}")
    
    async def organize_media_info(
        self,
        media_list: List[Dict[str, Any]],
        media_type: str = 'mixed'
    ) -> Dict[str, Any]:
        """
        整理媒体信息，输出结构化表格
        
        Args:
            media_list: 媒体列表 [{
                'message_id': 123,
                'caption': '...',
                'path': '...',
                'date': '...'
            }, ...]
            media_type: 媒体类型 (photo/video/mixed)
        
        Returns:
            {
                'summary': str,  # 总结
                'table': List[Dict],  # 表格数据
                'insights': List[str]  # 洞察
            }
        """
        # 构建提示词
        media_info_text = "\n".join([
            f"ID: {m.get('message_id')}, 说明: {m.get('caption', '无')[:100]}, 时间: {m.get('date', '未知')}"
            for m in media_list[:50]  # 最多50条
        ])
        
        prompt = f"""你是ASIANIGHT内容整理专家。

任务：整理以下{len(media_list)}个{media_type}媒体文件的信息，输出结构化表格。

媒体信息：
{media_info_text}

请分析并输出JSON格式：
{{
    "summary": "简要总结（100字内）",
    "table": [
        {{
            "序号": 1,
            "ID": 12345,
            "类型": "招聘信息",
            "主题": "KTV服务员招聘",
            "关键词": ["KTV", "包吃住", "日结"],
            "优先级": "高",
            "建议标签": ["招聘", "夜场"]
        }}
    ],
    "insights": [
        "大部分内容集中在KTV和商务会所招聘",
        "薪资范围主要在5000-15000元",
        "包吃住是常见福利"
    ]
}}

注意：
1. 表格包含所有重要信息
2. 提取核心关键词
3. 按优先级排序
4. 给出可操作的洞察"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是专业的数据分析师，擅长整理和分析媒体内容。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            return {
                'summary': result.get('summary', ''),
                'table': result.get('table', []),
                'insights': result.get('insights', [])
            }
            
        except Exception as e:
            print(f"❌ 整理失败: {e}")
            return {
                'summary': f'整理失败: {str(e)}',
                'table': [],
                'insights': []
            }
    
    def print_table(self, table_data: List[Dict[str, Any]]):
        """打印表格"""
        if not table_data:
            print("❌ 无数据")
            return
        
        # 表头
        headers = list(table_data[0].keys())
        
        # 计算列宽
        col_widths = {}
        for header in headers:
            col_widths[header] = max(
                len(str(header)),
                max(len(str(row.get(header, ''))) for row in table_data)
            ) + 2
        
        # 打印表头
        header_line = "| " + " | ".join(
            str(h).ljust(col_widths[h]) for h in headers
        ) + " |"
        
        separator = "|-" + "-|-".join(
            "-" * col_widths[h] for h in headers
        ) + "-|"
        
        print("\n" + separator)
        print(header_line)
        print(separator)
        
        # 打印数据行
        for row in table_data:
            row_line = "| " + " | ".join(
                str(row.get(h, '')).ljust(col_widths[h]) for h in headers
            ) + " |"
            print(row_line)
        
        print(separator + "\n")


if __name__ == '__main__':
    # 测试
    async def test_decision():
        """测试采集决策"""
        decider = ContentDecisionMaker()
        
        # 测试内容
        test_contents = [
            {
                'text': 'KTV招聘服务员，包吃住，月薪8000-15000，日结可选',
                'type': 'message'
            },
            {
                'text': '今天天气真好',
                'type': 'message'
            },
            {
                'text': '商务会所招聘，形象好气质佳，薪资面议',
                'type': 'message'
            }
        ]
        
        print("\n🎯 测试采集决策：\n")
        results = await decider.batch_decide(test_contents)
        
        for i, (content, result) in enumerate(zip(test_contents, results)):
            print(f"内容 {i+1}: {content['text'][:50]}")
            print(f"  是否采集: {'✅ 是' if result['should_collect'] else '❌ 否'}")
            print(f"  评分: {result['score']:.2f}")
            print(f"  原因: {result['reason']}")
            print(f"  标签: {', '.join(result['tags'])}\n")
    
    async def test_organize():
        """测试内容整理"""
        organizer = ContentOrganizer()
        
        # 测试数据
        test_media = [
            {
                'message_id': 12345,
                'caption': 'KTV招聘服务员，包吃住，月薪8000',
                'date': '2024-10-30'
            },
            {
                'message_id': 12346,
                'caption': '商务会所招聘，形象好',
                'date': '2024-10-30'
            },
            {
                'message_id': 12347,
                'caption': '足浴店招技师，日结300',
                'date': '2024-10-30'
            }
        ]
        
        print("\n📊 测试内容整理：\n")
        result = await organizer.organize_media_info(test_media, 'message')
        
        print(f"总结: {result['summary']}\n")
        
        print("📋 数据表格:")
        organizer.print_table(result['table'])
        
        print("💡 洞察:")
        for insight in result['insights']:
            print(f"  • {insight}")
    
    async def main():
        await test_decision()
        await test_organize()
    
    asyncio.run(main())



