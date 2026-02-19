"""
观察配置和属性映射
"""

# 观察触发词配置
OBSERVATION_TRIGGERS = {
    "priority_order": ["scene_specific", "long_term", "short_term", "stop"],
    
    "scene_specific": {
        "priority": 3,  # 最高优先级
        "人物": {
            "patterns": [
                "看看是谁",
                "看看何人在此",
                "且看何人",
                "观察一下人物"
            ],
            "weight": 1.0
        },
        "动作": {
            "patterns": [
                "看看在做什么",
                "观察一下动作",
                "且看其动作",
                "看看他在干什么"
            ],
            "weight": 0.9
        },
        "表情": {
            "patterns": [
                "看看什么表情",
                "观察表情",
                "且看其神态",
                "看看脸色"
            ],
            "weight": 0.8
        },
        "服装": {
            "patterns": [
                "看看穿着",
                "观察装束",
                "且看其衣着",
                "看看打扮"
            ],
            "weight": 0.7
        }
    },
    
    "long_term": {
        "priority": 2,
        "patterns": [
            "仔细观察",
            "细看",
            "好好看看",
            "仔细看看",
            "且让本座看个仔细"
        ],
        "weight": 0.8
    },
    
    "short_term": {
        "priority": 1,
        "patterns": [
            "看一下",
            "瞧瞧",
            "看看",
            "让本座看看",
            "我看一下"  
        ],
        "weight": 0.6
    },
    
    "stop": {
        "priority": 4,  # 停止命令优先级最高
        "patterns": [
            "别看了",
            "停止观察",
            "收回天眼",
            "不看了"
        ],
        "weight": 1.0
    }
}

# 语言组织配置
LANGUAGE_STRUCTURE = {
    "transitions": {
        "time_to_count": [
            "只见",
            "但见",
            "忽见",
            "此时"
        ],
        "count_to_person": [
            "其中",
            "当中",
            "之中"
        ],
        "person_to_action": [
            "正在",
            "此刻",
            "眼下"
        ],
        "action_to_mood": [
            "使得",
            "令得",
            "让这里"
        ]
    },
    
    "particles": {
        "emphasis": [
            "却是",
            "倒是",
            "着实",
            "当真"
        ],
        "connection": [
            "而",
            "且",
            "又",
            "亦"
        ],
        "conclusion": [
            "这般",
            "如此",
            "这样",
            "这般模样"
        ]
    }
}

# 属性映射配置
ATTRIBUTE_MAPPINGS = {
    "gender": {
        "male": ["男子", "公子", "男儿"],
        "female": ["女子", "姑娘", "女儿"],
        "unknown": ["此人", "那人", "一人"]
    },
    "age": {
        "child": ["稚童", "小童", "童子"],
        "teenager": ["少年", "青年", "年轻人"],
        "youth": ["青年", "年轻人", "后生"],
        "middle_aged": ["中年", "壮年", "成年"],
        "elderly": ["长者", "老者", "老人"],
        "unknown": ["此人", "那人"]
    },
    "upper_wear": {
        "long_sleeve": ["长衫", "长袍", "长衣"],
        "short_sleeve": ["短衫", "短衣", "短袖"],
        "coat": ["外衣", "大衣", "罩衣"],
        "jacket": ["夹衣", "短装", "外套"],
        "unknown": ["衣衫", "衣裳", "衣物"]
    },
    "upper_color": {
        "red": ["红", "朱", "赤"],
        "green": ["绿", "碧", "青"],
        "blue": ["蓝", "靛", "湛"],
        "black": ["墨", "玄", "黑"],
        "white": ["素", "白", "雪"],
        "yellow": ["黄", "金", "橙"],
        "purple": ["紫", "青", "蓝"],
        "unknown": ["素", "淡", "雅"]
    },
    "lower_wear": {
        "pants": "长裤",
        "shorts": "短裤",
        "skirt": "裙装",
        "unknown": "下装"
    },
    "lower_color": {
        "red": "红",
        "green": "绿",
        "blue": "蓝",
        "black": "墨",
        "white": "素",
        "yellow": "黄",
        "purple": "紫",
        "unknown": "素"
    }
}

# 场景氛围配置
ATMOSPHERE_CONFIG = {
    "time_mood": {
        "黎明": {
            "patterns": [
                "晨光熹微",
                "旭日初升",
                "晨曦微露"
            ],
            "tone": "gentle"
        },
        "午时": {
            "patterns": [
                "日正当空",
                "阳光正好",
                "天朗气清"
            ],
            "tone": "cheerful"
        },
        "黄昏": {
            "patterns": [
                "夕阳西下",
                "暮色渐浓",
                "落日余晖"
            ],
            "tone": "lyrical"
        },
        "子夜": {
            "patterns": [
                "月上中天",
                "夜色深沉",
                "星河璀璨"
            ],
            "tone": "calm"
        }
    },
    
    "person_count": {
        0: {
            "patterns": [
                "空无一人",
                "无人在此",
                "一片寂静"
            ],
            "tone": "calm"
        },
        1: {
            "patterns": [
                "只见一人",
                "有一人在此",
                "独见一人"
            ],
            "tone": "gentle"
        },
        2: {
            "patterns": [
                "二人在此",
                "见两个人影",
                "两人相对"
            ],
            "tone": "gentle"
        },
        "many": {
            "patterns": [
                "人影绰绰",
                "几人在此",
                "不少人在场"
            ],
            "tone": "lively"
        }
    },
    "scene_mood": {
        "peaceful": [
            "一片祥和",
            "静谧安详",
            "平静安宁"
        ],
        "lively": [
            "热闹非凡",
            "人声鼎沸",
            "好不热闹"
        ],
        "solemn": [
            "庄严肃穆",
            "气氛凝重",
            "肃穆庄严"
        ]
    }
}

# 人物特征配置
PERSON_FEATURES = {
    "identity": {
        "男": {
            "青年": {
                "patterns": ["俊朗青年", "年轻男子", "清秀公子"],
                "tone": "gentle"
            },
            "中年": {
                "patterns": ["中年男子", "壮年男子", "成年男子"],
                "tone": "respectful"
            },
            "长者": {
                "patterns": ["老者", "长者", "老先生"],
                "tone": "respectful"
            }
        },
        "女": {
            "青年": {
                "patterns": ["俊俏女子", "年轻女子", "秀丽女子"],
                "tone": "gentle"
            },
            "中年": {
                "patterns": ["中年女子", "成年女子", "端庄女子"],
                "tone": "respectful"
            },
            "长者": {
                "patterns": ["老妪", "老婆婆", "老太太"],
                "tone": "respectful"
            }
        }
    },
    "clothing": {
        "upper_wear": {
            "长衫": {
                "红": {
                    "patterns": ["一袭红衫", "红色长衫", "朱红衣衫"],
                    "tone": "cheerful"
                },
                "绿": {
                    "patterns": ["碧绿长衫", "绿色衣衫", "青绿衣裳"],
                    "tone": "gentle"
                },
                "蓝": {
                    "patterns": ["蓝色长衫", "靛青衣衫", "湛蓝衣裳"],
                    "tone": "calm"
                },
                "墨": {
                    "patterns": ["墨色长衫", "黑色衣衫", "玄色衣裳"],
                    "tone": "solemn"
                },
                "素": {
                    "patterns": ["素色长衫", "白色衣衫", "素雅衣裳"],
                    "tone": "gentle"
                }
            }
        },
        "pose": {
            "standing": {
                "elegant": ["伫立于此", "挺立而立", "静立于前"],
                "casual": ["随意而立", "闲立于此", "站在一旁"]
            },
            "sitting": {
                "formal": ["正襟危坐", "端坐于此", "安坐一旁"],
                "casual": ["随意而坐", "闲坐一隅", "坐在一旁"]
            }
        },
        "gesture": {
            "wave": ["挥手示意", "轻摆手臂", "挥手而立"],
            "point": ["指点远方", "手指前方", "遥指远处"],
            "pray": ["双手合十", "作揖行礼", "拱手而立"],
            "hold": ["手持物件", "掌中有物", "手执一物"]
        },
        "expression": {
            "smile": ["面带笑意", "嘴角含笑", "笑意盈盈"],
            "serious": ["神色严肃", "面容肃穆", "神情凝重"],
            "calm": ["神色平静", "面容安详", "神情淡然"]
        }
    }
} 