"""
LLM对话客户端，用于生成基于命理和场景数据的对话内容
"""

import json
import random
import logging
import requests
import time
from typing import Dict, Any, Optional, List, Union

# 设置日志
logger = logging.getLogger(__name__)

class LLMDialogueClient:
    """LLM对话客户端，调用大模型API生成对话内容"""
    
    def __init__(self, config=None):
        """
        初始化LLM对话客户端
        
        Args:
            config (dict, optional): LLM配置信息，包含API URL、密钥等
        """
        self.config = config or {}
        self.api_url = self.config.get('api_url', '')
        self.api_key = self.config.get('api_key', '')
        self.temperature = self.config.get('temperature', 0.7)
        
        # 命理流派列表
        self.divination_schools = [
            "奇门遁甲", "紫微斗数", "六爻", "太乙神数", 
            "紫薇易数", "八字", "风水", "面相学"
        ]
        
        # 对应流派的特有术语
        self.school_terms = {
            "奇门遁甲": ["九宫", "八门", "九星", "八神", "值符", "值使", "三奇", "六仪", "游三伏"],
            "紫微斗数": ["命宫", "财帛", "官禄", "迁移", "疾厄", "六亲", "天府", "武曲", "天相"],
            "六爻": ["卦象", "动爻", "静爻", "世爻", "应爻", "六亲", "卦变", "六神", "飞伏"],
            "太乙神数": ["太乙", "神将", "天目", "地盘", "四课", "三传", "归魂", "伏神", "游都"],
            "紫薇易数": ["星曜", "宫位", "四化", "三方", "命主", "身主", "大限", "流年", "星耀"],
            "八字": ["天干", "地支", "纳音", "十神", "神煞", "大运", "流年", "四柱", "五行"],
            "风水": ["山向", "水口", "明堂", "砂水", "龙脉", "气口", "穴位", "来龙", "去脉"],
            "面相学": ["三停", "五官", "骨相", "气色", "手相", "痣相", "耳相", "眉相", "额相"]
        }
    
    def generate_divination_dialogue(self, scene_data: Dict[str, Any], character_type: str = "铁观音") -> str:
        """
        生成基于命理和场景数据的对话内容
        
        Args:
            scene_data (dict): 场景分析数据
            character_type (str): 角色类型，默认为"铁观音"
            
        Returns:
            str: 生成的对话内容
        """
        try:
            # 随机选择一个命理流派
            selected_school = random.choice(self.divination_schools)
            
            # 构建提示词
            prompt = self._build_prompt(scene_data, selected_school, character_type)
            
            # 调用LLM API
            response = self._call_llm_api(prompt)
            
            # 如果调用失败，使用后备方案
            if not response:
                return self._generate_fallback_dialogue(scene_data, selected_school)
                
            return response
            
        except Exception as e:
            logger.error(f"生成命理对话出错: {e}")
            return "我似乎看到了一些迷雾，让我再仔细推演一下..."
    
    def _build_prompt(self, scene_data: Dict[str, Any], divination_school: str, character_type: str) -> str:
        """
        构建提示词
        
        Args:
            scene_data (dict): 场景分析数据
            divination_school (str): 选定的命理流派
            character_type (str): 角色类型
            
        Returns:
            str: 完整的提示词
        """
        # 获取该流派特有的术语
        terms = self.school_terms.get(divination_school, [])
        random.shuffle(terms)
        terms = terms[:3]  # 随机选择3个术语
        
        # 分析场景数据
        person_count = scene_data.get('person_count', 0)
        persons = scene_data.get('persons', [])
        
        # 构建关于人物的描述
        people_desc = self._build_people_description(persons, person_count)
        
        # 基础提示模板
        base_prompt = f"""
        你是一位精通{divination_school}的算命大师，名为{character_type}，性格神秘又温暖。
        你现在正在为客人解读天机，请基于以下信息，用{character_type}的口吻生成一段神秘而温暖的对话。
        
        场景信息：
        {json.dumps(scene_data, ensure_ascii=False, indent=2)}
        
        人物描述：
        {people_desc}
        
        要求：
        1. 对话要体现{divination_school}的特色，自然地融入以下术语：{', '.join(terms)}
        2. 语气要神秘但亲切，像是一位能洞察人心的长者
        3. 对话长度在100-200字之间
        4. 只输出对话内容，不要有额外的说明
        5. 使用第一人称，用"我"来指代自己
        6. 适当加入一些叹息、思考的语气词（如"唔..."，"嗯..."，"啊..."）
        7. 对话要符合现代赛博朋克风格，但保留传统命理的神秘感
        
        请生成对话：
        """
        
        return base_prompt
    
    def _build_people_description(self, persons: List[Dict[str, Any]], person_count: int) -> str:
        """构建人物描述"""
        if person_count == 0:
            return "场景中无人。"
            
        descriptions = []
        for i, person in enumerate(persons):
            gender = person.get('gender', '未知')
            age = person.get('age', '未知')
            gesture = person.get('gesture', '无特定姿势')
            
            desc = f"人物{i+1}：{gender}，{age}，姿势为{gesture}"
            descriptions.append(desc)
            
        return "\n".join(descriptions)
    
    def _call_llm_api(self, prompt: str) -> Optional[str]:
        """
        调用LLM API
        
        Args:
            prompt (str): 提示词
            
        Returns:
            str: 生成的对话内容，如果失败则返回None
        """
        try:
            # 只有在配置了API URL和密钥的情况下才调用API
            if not self.api_url or not self.api_key:
                logger.warning("LLM API未配置，将使用后备方案")
                return None
                
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "prompt": prompt,
                "temperature": self.temperature
            }
            
            # 添加重试逻辑
            max_retries = 3
            for i in range(max_retries):
                try:
                    response = requests.post(
                        self.api_url,
                        headers=headers,
                        json=data,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        # 根据API返回格式提取生成的文本
                        # 注意：这里的解析逻辑可能需要根据实际使用的API调整
                        generated_text = result.get('choices', [{}])[0].get('text', '')
                        return generated_text.strip()
                    else:
                        logger.warning(f"LLM API调用失败，状态码: {response.status_code}")
                        logger.warning(f"响应内容: {response.text}")
                        
                except requests.RequestException as e:
                    logger.warning(f"LLM API请求异常: {e}")
                    
                # 如果不是最后一次重试，则等待一下
                if i < max_retries - 1:
                    time.sleep(1)
            
            return None
                
        except Exception as e:
            logger.error(f"调用LLM API出错: {e}")
            return None
    
    def _generate_fallback_dialogue(self, scene_data: Dict[str, Any], divination_school: str) -> str:
        """
        生成后备对话内容，当LLM API调用失败时使用
        
        Args:
            scene_data (dict): 场景分析数据
            divination_school (str): 选定的命理流派
            
        Returns:
            str: 后备对话内容
        """
        terms = self.school_terms.get(divination_school, [])
        random.shuffle(terms)
        term1 = terms[0] if terms else "天机"
        term2 = terms[1] if len(terms) > 1 else "命理"
        
        person_count = scene_data.get('person_count', 0)
        
        if person_count == 0:
            return f"嗯...今日{term1}微妙，{term2}流转。虽无人在此，但我感知到一股特殊的能量。空间中留有痕迹，似是有人刚刚离去，又像是将有人到来。你可知道，无人之境往往藏着最深的天机？"
        
        elif person_count == 1:
            return f"啊...我看你{term1}隐隐有异，{term2}中显示近日将有变动。你的面相告诉我，你近期思虑过重，是否有什么心事？让我为你推演一番，或许能给你一些指引。"
        
        else:
            return f"哦！{person_count}人同至，甚是有缘。按{divination_school}的说法，{term1}相合，{term2}交融，必有奇事发生。我能感受到你们之间的能量流动，似有未解之谜，要不要让我详细解读？"
