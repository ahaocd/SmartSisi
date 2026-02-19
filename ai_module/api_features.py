"""
百度API特征映射配置
"""

# 基础属性映射
BASIC_ATTRIBUTES = {
    "gender": {
        "name": "性别",
        "values": {
            "male": "男",
            "female": "女"
        }
    },
    "age": {
        "name": "年龄",
        "values": {
            "child": "幼儿",
            "teenager": "青少年",
            "youth": "青年",
            "middle_aged": "中年",
            "elderly": "老年"
        }
    },
    "upper_wear": {
        "name": "上装",
        "values": {
            "long_sleeve": "长袖",
            "short_sleeve": "短袖",
            "suit": "西装",
            "t_shirt": "T恤"
        }
    },
    "lower_wear": {
        "name": "下装",
        "values": {
            "long_pants": "长裤",
            "short_pants": "短裤",
            "skirt": "裙子"
        }
    }
}

# 行为属性映射
BEHAVIOR_ATTRIBUTES = {
    "smoke": {
        "name": "吸烟",
        "trigger": "smoking"
    },
    "cellphone": {
        "name": "使用手机",
        "trigger": "phone_use"
    },
    "carrying_item": {
        "name": "携带物品",
        "trigger": "carrying"
    },
    "umbrella": {
        "name": "打伞",
        "trigger": "umbrella"
    }
}

# 姿态属性映射
POSE_ATTRIBUTES = {
    "is_standing": {
        "name": "站立",
        "trigger": "standing"
    },
    "is_sitting": {
        "name": "坐姿",
        "trigger": "sitting"
    },
    "orientation": {
        "name": "朝向",
        "values": {
            "front": "正面",
            "back": "背面",
            "left": "左侧",
            "right": "右侧"
        }
    }
}

# 手势属性映射
GESTURE_ATTRIBUTES = {
    "point": {
        "name": "指点",
        "trigger": "pointing"
    },
    "wave": {
        "name": "挥手",
        "trigger": "waving"
    },
    "pray": {
        "name": "祈祷",
        "trigger": "praying"
    },
    "ok": {
        "name": "OK手势",
        "trigger": "ok_sign"
    },
    "thumbup": {
        "name": "点赞",
        "trigger": "thumbs_up"
    }
}

# 表情属性映射
EXPRESSION_ATTRIBUTES = {
    "smile": {
        "name": "微笑",
        "trigger": "smiling"
    },
    "laugh": {
        "name": "大笑",
        "trigger": "laughing"
    },
    "serious": {
        "name": "严肃",
        "trigger": "serious"
    },
    "sad": {
        "name": "悲伤",
        "trigger": "sad"
    },
    "surprised": {
        "name": "惊讶",
        "trigger": "surprised"
    },
    "confused": {
        "name": "困惑",
        "trigger": "confused"
    },
    "focused": {
        "name": "专注",
        "trigger": "focused"
    }
}

# 新增脸部动作属性映射
FACE_ACTION_ATTRIBUTES = {
    "head_pose": {
        "name": "头部姿态",
        "values": {
            "tilt": "歪头",
            "nod": "点头",
            "shake": "摇头",
            "up": "抬头",
            "down": "低头"
        }
    },
    "eye_state": {
        "name": "眼睛状态",
        "values": {
            "open": "睁眼",
            "closed": "闭眼",
            "blink": "眨眼"
        }
    },
    "mouth_state": {
        "name": "嘴部状态",
        "values": {
            "open": "张嘴",
            "closed": "闭嘴",
            "speaking": "说话"
        }
    },
    "face_direction": {
        "name": "面部朝向",
        "values": {
            "front": "正面",
            "left": "左侧",
            "right": "右侧",
            "up": "仰视",
            "down": "俯视"
        }
    }
}

# 场景属性映射
SCENE_ATTRIBUTES = {
    "crowd": {
        "thresholds": {
            "medium": 3,
            "many": 5
        },
        "triggers": {
            "medium": "medium_crowd",
            "many": "large_crowd"
        }
    },
    "interaction": {
        "types": {
            "conversation": "交谈",
            "gathering": "聚会",
            "queuing": "排队"
        }
    }
}

# 组合特征触发条件
COMBO_TRIGGERS = {
    "elderly_unstable": {
        "conditions": {
            "age": "elderly",
            "is_standing": False
        }
    },
    "youth_formal": {
        "conditions": {
            "age": ["youth", "teenager"],
            "upper_wear": "suit"
        }
    },
    "child_playing": {
        "conditions": {
            "age": "child",
            "action": "playing"
        }
    }
}

# 特征优先级配置
FEATURE_PRIORITIES = {
    "emergency": ["falling", "unstable", "distress"],
    "interaction": ["praying", "greeting", "conversation"],
    "appearance": ["clothing", "pose", "expression"],
    "scene": ["crowd", "atmosphere", "activity"]
} 