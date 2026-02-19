"""
思思身体装备语义场景配置
基于语义理解的智能身体功能调用配置，而非硬编码关键词匹配

这个配置文件定义了思思的身体装备在不同语义场景下的使用策略：
- SISIeyes：思思的眼睛（摄像头）+ 表情屏（显示屏）+ 情绪灯（LED）
- sisidisk：思思的旋转底座，控制身体和音响转动
- 传感器：思思的触觉感知系统

让柳思思能够根据用户的真实意图智能使用自己的身体功能。
"""

# 语义场景权重配置
SEMANTIC_WEIGHTS = {
    "photography": 0.95,      # 摄影拍照场景 - 最高优先级
    "visualization": 0.90,    # 音频可视化场景
    "display": 0.85,          # 显示控制场景  
    "lighting": 0.80,         # 灯光控制场景
    "motor": 0.75,            # 电机控制场景
    "status": 0.70,           # 状态查询场景
    "system": 0.65,           # 系统控制场景
}

# 语义场景定义 - 基于意图而非关键词
SEMANTIC_SCENARIOS = {
    "photography": {
        "description": "用户想要拍照、记录、分享的场景",
        "intent_patterns": [
            "记录当前时刻",
            "保存这个画面", 
            "留个纪念",
            "发朋友圈需要照片",
            "自拍一张",
            "拍个照片看看效果",
            "记录一下现在的样子",
            "给这个时刻拍张照"
        ],
        "context_indicators": [
            "想要记录",
            "需要照片",
            "分享到社交媒体",
            "留作纪念",
            "查看效果",
            "保存画面"
        ],
        "emotional_triggers": [
            "开心想记录",
            "重要时刻",
            "美好瞬间",
            "值得纪念"
        ]
    },
    
    "visualization": {
        "description": "音频可视化和音乐增强体验场景",
        "intent_patterns": [
            "让音乐更有感觉",
            "增强音乐体验",
            "营造音乐氛围",
            "显示音乐节拍",
            "音乐跳动效果",
            "配合音乐的视觉效果",
            "让音乐更生动"
        ],
        "context_indicators": [
            "正在播放音乐",
            "音乐氛围",
            "视觉效果",
            "节拍感",
            "音乐体验"
        ],
        "emotional_triggers": [
            "想要更好的音乐体验",
            "营造浪漫氛围",
            "增加音乐感染力"
        ]
    },
    
    "display": {
        "description": "信息显示和文字展示场景",
        "intent_patterns": [
            "在屏幕上显示信息",
            "让我看到文字",
            "屏幕提示一下",
            "显示当前状态",
            "文字提醒",
            "屏幕显示时间",
            "显示重要信息"
        ],
        "context_indicators": [
            "需要看到信息",
            "屏幕显示",
            "文字提示",
            "信息展示",
            "状态显示"
        ],
        "emotional_triggers": [
            "需要确认信息",
            "重要提醒",
            "状态关注"
        ]
    },
    
    "lighting": {
        "description": "灯光控制和氛围营造场景",
        "intent_patterns": [
            "调节房间氛围",
            "营造灯光效果",
            "需要照明",
            "改变灯光颜色",
            "灯光提示",
            "营造浪漫氛围",
            "调节亮度"
        ],
        "context_indicators": [
            "房间太暗",
            "需要氛围",
            "灯光效果",
            "颜色变化",
            "亮度调节"
        ],
        "emotional_triggers": [
            "想要温馨氛围",
            "浪漫情调",
            "舒适环境"
        ]
    },
    
    "motor": {
        "description": "电机控制和角度调整场景",
        "intent_patterns": [
            "调整设备角度",
            "改变朝向",
            "转动设备",
            "调整位置",
            "换个角度",
            "转向另一边",
            "调整视角"
        ],
        "context_indicators": [
            "角度不对",
            "位置需要调整",
            "视角问题",
            "朝向改变"
        ],
        "emotional_triggers": [
            "当前角度不满意",
            "需要更好的视角",
            "位置不合适"
        ]
    },
    
    "status": {
        "description": "设备状态查询和健康检查场景",
        "intent_patterns": [
            "设备工作正常吗",
            "检查设备状态",
            "SISIeyes怎么样",
            "设备有问题吗",
            "查看设备信息",
            "设备连接正常吗",
            "硬件状态如何"
        ],
        "context_indicators": [
            "设备关注",
            "状态担心",
            "健康检查",
            "连接问题",
            "性能关注"
        ],
        "emotional_triggers": [
            "担心设备问题",
            "想了解设备状态",
            "确保正常工作"
        ]
    },
    
    "system": {
        "description": "系统控制和维护场景",
        "intent_patterns": [
            "设备需要重启",
            "恢复设备设置",
            "重新初始化",
            "设备出问题了",
            "需要复位设备",
            "重新启动系统",
            "恢复出厂设置"
        ],
        "context_indicators": [
            "设备异常",
            "需要维护",
            "系统问题",
            "重启需求",
            "复位需求"
        ],
        "emotional_triggers": [
            "设备出现问题",
            "需要解决故障",
            "系统维护需求"
        ]
    }
}

# 上下文关联规则
CONTEXT_RULES = {
    "music_playing": {
        "description": "当前正在播放音乐时的上下文",
        "boost_scenarios": ["visualization"],
        "boost_weight": 0.3
    },
    "photo_sharing": {
        "description": "用户提到分享、朋友圈等社交场景",
        "boost_scenarios": ["photography"],
        "boost_weight": 0.4
    },
    "atmosphere_creation": {
        "description": "用户想要营造氛围的场景",
        "boost_scenarios": ["lighting", "visualization"],
        "boost_weight": 0.3
    },
    "device_concern": {
        "description": "用户对设备状态表示关注",
        "boost_scenarios": ["status", "system"],
        "boost_weight": 0.4
    }
}

# 语义分析函数
def analyze_semantic_intent(user_input: str, context: dict = None) -> dict:
    """
    分析用户输入的语义意图，判断是否需要调用SISIeyes工具
    
    Args:
        user_input: 用户输入文本
        context: 上下文信息（对话历史、当前状态等）
        
    Returns:
        dict: 包含语义分析结果的字典
    """
    result = {
        "should_call_sisieyes": False,
        "confidence": 0.0,
        "primary_scenario": None,
        "scenarios": {},
        "reasoning": ""
    }
    
    user_input_lower = user_input.lower()
    context = context or {}
    
    # 计算每个场景的匹配度
    for scenario_name, scenario_config in SEMANTIC_SCENARIOS.items():
        score = 0.0
        matched_patterns = []
        
        # 检查意图模式匹配
        for pattern in scenario_config["intent_patterns"]:
            if any(word in user_input_lower for word in pattern.lower().split()):
                score += 0.3
                matched_patterns.append(pattern)
        
        # 检查上下文指示器
        for indicator in scenario_config["context_indicators"]:
            if indicator.lower() in user_input_lower:
                score += 0.2
        
        # 检查情感触发器
        for trigger in scenario_config["emotional_triggers"]:
            if any(word in user_input_lower for word in trigger.lower().split()):
                score += 0.1
        
        # 应用上下文规则加权
        for rule_name, rule_config in CONTEXT_RULES.items():
            if scenario_name in rule_config["boost_scenarios"]:
                # 这里可以根据实际上下文信息进行加权
                # 简化实现，可以根据需要扩展
                if rule_name in str(context):
                    score += rule_config["boost_weight"]
        
        # 应用场景权重
        final_score = score * SEMANTIC_WEIGHTS.get(scenario_name, 0.5)
        
        result["scenarios"][scenario_name] = {
            "score": final_score,
            "matched_patterns": matched_patterns
        }
    
    # 确定主要场景和是否调用工具
    if result["scenarios"]:
        primary_scenario = max(result["scenarios"].items(), key=lambda x: x[1]["score"])
        result["primary_scenario"] = primary_scenario[0]
        result["confidence"] = primary_scenario[1]["score"]
        
        # 设置调用阈值
        CALL_THRESHOLD = 0.4
        if result["confidence"] >= CALL_THRESHOLD:
            result["should_call_sisieyes"] = True
            result["reasoning"] = f"检测到{primary_scenario[0]}场景，置信度{result['confidence']:.2f}，超过阈值{CALL_THRESHOLD}"
        else:
            result["reasoning"] = f"最高匹配场景{primary_scenario[0]}，置信度{result['confidence']:.2f}，未达到调用阈值{CALL_THRESHOLD}"
    else:
        result["reasoning"] = "未检测到明确的SISIeyes使用场景"
    
    return result

# 快速判断函数（供Agent使用）
def should_call_sisieyes(user_input: str, context: dict = None) -> bool:
    """
    快速判断是否应该调用SISIeyes工具
    
    Args:
        user_input: 用户输入
        context: 上下文信息
        
    Returns:
        bool: 是否应该调用SISIeyes工具
    """
    analysis = analyze_semantic_intent(user_input, context)
    return analysis["should_call_sisieyes"]

# 获取调用参数建议
def get_sisieyes_params(user_input: str, primary_scenario: str) -> dict:
    """
    根据语义场景生成SISIeyes工具调用参数
    
    Args:
        user_input: 用户输入
        primary_scenario: 主要场景类型
        
    Returns:
        dict: 工具调用参数
    """
    return {
        "query": user_input,
        "scenario": primary_scenario,
        "semantic_analysis": True
    }
