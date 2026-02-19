"""
特征触发式对话配置
"""

# 单一特征触发
SINGLE_TRIGGERS = {
    # 吸烟相关
    "smoking": {
        "responses": [
            "老人家，什么牌子的烟...欸，别说话！离我远点就行！",
            "年轻人少抽点，伤身的很...",
            "这烟味...咳咳，莫要污了这一方清气..."
        ],
        "emotions": ["disgusted", "concerned"],
        "cached_audio": ["smoking_audio_1.mp3", "smoking_audio_2.mp3"]  # 缓存的语音文件
    },
    
    # 使用手机
    "phone_use": {
        "responses": [
            "这方寸之间，竟藏乾坤...有趣",
            "莫要沉迷那虚幻世界，抬头看看这天地吧",
            "世人都在低头看手机，可曾抬头看过天空？",
            "这数字洪流中...倒也自在"
        ],
        "emotions": ["curious", "amused"]
    },
    
    # 祈祷/合十
    "praying": {
        "responses": [
            "这虔诚之心...倒是难得",
            "心诚则灵，不过...",
            "且看这祈愿之人..."
        ],
        "emotions": ["respectful", "thoughtful"]
    }
}

# 组合特征触发
COMBO_TRIGGERS = {
    # 多人互动
    "group_interaction": {
        "responses": [
            "这群人倒是其乐融融...",
            "看这热闹景象...",
            "众生百态，尽在眼前..."
        ],
        "emotions": ["amused", "interested"]
    }
}

# 场景特征触发
SCENE_TRIGGERS = {
    # 室内场景
    "indoor": {
        "responses": [
            "这室内景象...",
            "且看这一方天地...",
            "这一室之间..."
        ]
    },
    # 室外场景
    "outdoor": {
        "responses": [
            "这广阔天地...",
            "看这自然景象...",
            "且观这一方天地..."
        ]
    }
}

# 时间特征触发
TIME_TRIGGERS = {
    "morning": {
        "responses": [
            "晨光熹微...",
            "这清晨时分...",
            "朝阳初升..."
        ]
    },
    "noon": {
        "responses": [
            "正值午时...",
            "日正当空...",
            "这正午时分..."
        ]
    },
    "evening": {
        "responses": [
            "夕阳西下...",
            "这黄昏时分...",
            "暮色渐起..."
        ]
    },
    "night": {
        "responses": [
            "夜色已深...",
            "这夜晚时分...",
            "月上中天..."
        ]
    }
}

# 服装特征触发
CLOTHING_TRIGGERS = {
    "formal": {
        "openings": [
            "这一身正装...",
            "好一身华服..."
        ],
        "responses": [
            "想必是有要事在身...",
            "衣冠楚楚，气度不凡..."
        ]
    },
    "casual": {
        "openings": [
            "这一身便装...",
            "穿着随意..."
        ],
        "responses": [
            "倒是轻松自在...",
            "无拘无束，也好..."
        ]
    }
}

# 姿态特征触发
POSE_TRIGGERS = {
    "sitting": {
        "openings": [
            "这般安坐...",
            "静静而坐..."
        ],
        "responses": [
            "倒是悠然自得...",
            "一派闲适之态..."
        ]
    },
    "standing": {
        "openings": [
            "伫立于此...",
            "挺立而立..."
        ],
        "responses": [
            "倒是气度不凡...",
            "自有一番风骨..."
        ]
    }
}

# 情绪状态追踪
EMOTION_STATES = {
    "happy": {
        "intensity": 0.8,
        "duration": 300,  # 持续时间(秒)
        "decay_rate": 0.1,  # 衰减率
        "compatible": ["amused", "excited"],
        "incompatible": ["sad", "angry"]
    },
    "sad": {
        "intensity": 0.7,
        "duration": 600,
        "decay_rate": 0.05,
        "compatible": ["concerned", "sympathetic"],
        "incompatible": ["happy", "excited"]
    },
    "angry": {
        "intensity": 0.9,
        "duration": 180,
        "decay_rate": 0.15,
        "compatible": ["disgusted", "annoyed"],
        "incompatible": ["happy", "peaceful"]
    },
    "peaceful": {
        "intensity": 0.6,
        "duration": 450,
        "decay_rate": 0.08,
        "compatible": ["content", "serene"],
        "incompatible": ["angry", "anxious"]
    }
} 