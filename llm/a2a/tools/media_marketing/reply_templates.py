"""
回复模板库 - 预设短句系统

用于智能体在评论区回复时，优先使用预设的隐晦短句
AI会根据上下文（标题、评论内容、评论者）智能选择合适的模板
"""

# ============================================
# 预设回复短句库（可自定义）
# ============================================

# 类别1：人员招聘/推荐相关
REPLY_TEMPLATES_RECRUITMENT = [
    # 原始短句
    "商K 的妹子给安排一批不",
    "要上点质量不",
    "我这有些质量高的安排",
    "上点会玩的美女不",
    "店里还要点质量高的美女不",
    
    # 变体1：语气更随意
    "要不要安排点质量好的",
    "有批质量不错的，要不",
    "给你安排点会玩的？",
    "店里上点新面孔不",
    "这边有些高质量的资源",
    
    # 变体2：更隐晦
    "有好货，要不要",
    "给你介绍点靠谱的",
    "这边有些好的，聊聊？",
    "要不要看看我这边的",
    "有合适的资源，了解下不",
    
    # 变体3：询问需求
    "店里缺人不",
    "最近要不要补点新的",
    "需要的话我这边有",
    "要提升下质量不",
    "换批新的怎么样",
    
    # 变体4：强调质量
    "质量保证的有一批",
    "会玩的有几个，看不",
    "素质高的有，要不要",
    "形象好、素质高的有",
    "颜值在线的有几个",
    
    # 变体5：商务口吻
    "有好的资源可以对接",
    "可以安排对接下",
    "这边有渠道，聊聊？",
    "有合作的，质量不错",
    "可以介绍靠谱的",
]

# 类别2：资源分享/合作相关
REPLY_TEMPLATES_COOPERATION = [
    "可以互相介绍下资源",
    "咱们可以合作",
    "有需要可以互相推荐",
    "可以互通有无",
    "资源共享下？",
    "一起做大做强",
    "可以长期合作",
    "互相照应下",
]

# 类别3：认同+引导私聊
REPLY_TEMPLATES_LEAD_TO_DM = [
    "确实，我这边有办法，私聊",
    "理解，可以细聊",
    "懂的都懂，私下聊",
    "有方案，详细的私聊",
    "这个有门道，私信我",
    "可以帮忙，加个联系方式",
    "有路子，私下说",
]

# 类别4：试探性询问
REPLY_TEMPLATES_PROBE = [
    "老板是做这行的？",
    "也是开店的？",
    "也在做这个？",
    "同行？",
    "一起聊聊？",
    "方便加个联系方式不",
]

# 类别5：通用友好回复（保底）
REPLY_TEMPLATES_GENERAL = [
    "确实",
    "说得对",
    "有道理",
    "理解",
    "正常的",
    "可以的",
    "👍",
    "有办法",
    "可以聊聊",
]

# ============================================
# 回复模板配置（根据场景分类）
# ============================================

REPLY_TEMPLATE_CONFIG = {
    "招聘": {
        "keywords": ["招人", "缺人", "员工", "人手", "流失", "离职", "招聘"],
        "templates": REPLY_TEMPLATES_RECRUITMENT,
        "weight": 0.8  # 优先级权重
    },
    "人员质量": {
        "keywords": ["质量", "素质", "形象", "颜值", "会玩", "服务", "专业"],
        "templates": REPLY_TEMPLATES_RECRUITMENT,
        "weight": 0.9
    },
    "合作": {
        "keywords": ["合作", "资源", "介绍", "推荐", "渠道"],
        "templates": REPLY_TEMPLATES_COOPERATION,
        "weight": 0.7
    },
    "问题咨询": {
        "keywords": ["怎么", "如何", "有没有", "哪里", "求", "?", "？"],
        "templates": REPLY_TEMPLATES_LEAD_TO_DM,
        "weight": 0.6
    },
    "试探身份": {
        "keywords": ["老板", "店", "经营", "开", "做生意"],
        "templates": REPLY_TEMPLATES_PROBE,
        "weight": 0.5
    },
    "通用": {
        "keywords": [],  # 空表示任何情况都可以
        "templates": REPLY_TEMPLATES_GENERAL,
        "weight": 0.3
    }
}

# ============================================
# 智能匹配函数
# ============================================

def match_reply_template(comment_text: str, context: dict = None) -> list:
    """根据评论内容和上下文，匹配合适的回复模板
    
    Args:
        comment_text: 评论内容
        context: 上下文信息（视频标题、主播行业等）
    
    Returns:
        list: 匹配到的模板列表（按优先级排序）
    """
    matched_templates = []
    
    # 遍历所有配置
    for category, config in REPLY_TEMPLATE_CONFIG.items():
        keywords = config["keywords"]
        templates = config["templates"]
        weight = config["weight"]
        
        # 检查关键词是否匹配
        if not keywords:  # 通用类别
            matched_templates.append({
                "category": category,
                "templates": templates,
                "weight": weight,
                "match_score": 0.1
            })
        else:
            # 计算匹配度
            match_count = sum(1 for kw in keywords if kw in comment_text)
            if match_count > 0:
                match_score = (match_count / len(keywords)) * weight
                matched_templates.append({
                    "category": category,
                    "templates": templates,
                    "weight": weight,
                    "match_score": match_score
                })
    
    # 按匹配分数排序
    matched_templates.sort(key=lambda x: x["match_score"], reverse=True)
    
    # 返回top3类别的所有模板
    result = []
    for item in matched_templates[:3]:
        result.extend(item["templates"])
    
    # 去重
    return list(set(result))


def get_all_reply_templates() -> list:
    """获取所有回复模板（用于AI参考）"""
    all_templates = []
    all_templates.extend(REPLY_TEMPLATES_RECRUITMENT)
    all_templates.extend(REPLY_TEMPLATES_COOPERATION)
    all_templates.extend(REPLY_TEMPLATES_LEAD_TO_DM)
    all_templates.extend(REPLY_TEMPLATES_PROBE)
    all_templates.extend(REPLY_TEMPLATES_GENERAL)
    return list(set(all_templates))  # 去重


# ============================================
# 测试函数
# ============================================

if __name__ == "__main__":
    # 测试1：招聘相关评论
    test_comment_1 = "现在招人太难了，质量好的都找不到"
    templates_1 = match_reply_template(test_comment_1)
    print(f"评论：{test_comment_1}")
    print(f"匹配到 {len(templates_1)} 个模板:")
    for i, t in enumerate(templates_1[:5], 1):
        print(f"  {i}. {t}")
    
    print("\n" + "="*50 + "\n")
    
    # 测试2：咨询问题
    test_comment_2 = "有没有好的渠道推荐？"
    templates_2 = match_reply_template(test_comment_2)
    print(f"评论：{test_comment_2}")
    print(f"匹配到 {len(templates_2)} 个模板:")
    for i, t in enumerate(templates_2[:5], 1):
        print(f"  {i}. {t}")
    
    print("\n" + "="*50 + "\n")
    
    # 测试3：通用评论
    test_comment_3 = "确实是这样"
    templates_3 = match_reply_template(test_comment_3)
    print(f"评论：{test_comment_3}")
    print(f"匹配到 {len(templates_3)} 个模板:")
    for i, t in enumerate(templates_3[:5], 1):
        print(f"  {i}. {t}")

