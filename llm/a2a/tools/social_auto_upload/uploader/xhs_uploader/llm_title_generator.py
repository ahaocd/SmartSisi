"""
LLM标题生成器 - 使用DeepSeek-V3生成小红书封面标题
"""
import requests
import json
import random
import sys
from pathlib import Path

# 修复导入路径
current_dir = Path(__file__).parent.resolve()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from config_loader import load_xhs_cover_config


def _rewrite_title_from_seed(seed: str) -> str:
    """根据用户给的标题进行轻度改写/变体生成，不偏题。
    - 金额/天数模式：支持替换金额与天数的离散集合
    - 其余固定话题：用等价近义表述
    """
    s = (seed or "").strip()
    import re, random

    # 金额-天数模式，例如："5元花三天"、"8块我撑了5天"、"求5元花三天的办法"
    # 识别数字（中文数字也简单映射）
    cn_num = {"一":1,"两":2,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
    def to_int(t: str) -> int:
        t = t.strip()
        if t.isdigit():
            return int(t)
        return cn_num.get(t, 0)

    m = re.search(r"(?:(\d+)|([一二两二三四五六七八九十]))\s*(元|块).{0,6}?(?:(\d+)|([一二两二三四五六七八九十]))\s*天", s)
    if m:
        amt = to_int(m.group(1) or m.group(2) or "0")
        day = to_int(m.group(4) or m.group(5) or "0")
        # 允许的金额与天数集合
        amt_set = [3,5,8,9,10,12,15,20]
        day_set = [1,3,5,7]
        new_amt = random.choice(amt_set)
        new_day = random.choice(day_set)
        templates = [
            f"{new_amt}元花{new_day}天我怎么撑的",
            f"{new_amt}块我撑了{new_day}天",
            f"只用{new_amt}元扛过{new_day}天",
            f"{new_amt}元{new_day}天，能活下来吗？",
        ]
        return random.choice(templates)[:18]

    # 其它固定话题的轻度同义
    mapping = {
        "不想上班但是想挣钱的活": ["不想上班也想赚钱怎么办","不上班还能怎么赚","不打工的赚钱路子"],
        "年轻人能有什么赛道": ["年轻人到底走哪条赛道","20多岁该选哪条路","年轻人还有哪些赛道"],
        "员工一定要给工资吗？": ["不给工资算违法吗？","员工不发薪 合理吗？","工资必给吗？来杠"],
        "大学生生存指南": ["大学生真实生存手册","在校生怎么活下来","大学生怎么过得体面"],
        "马云给我的投资打水漂了怎么办": ["投资打水漂怎么补救","投失败了还怎么翻身","亏了还能不能补回来"],
        "这年头难道还能饿死人（这句话到底谁说的？）": ["这年头还会饿死人？","真有人会被饿到吗","别再拿这句话忽悠人"],
    }
    for k, vs in mapping.items():
        if k in s:
            return random.choice(vs)[:18]

    # 默认：截断做题眼
    return s[:18] if s else "说点实在的"


def generate_cover_titles(
    theme: str = "陪伴",
    income_min: int = 5000,
    income_max: int = 50000,
    seed: str | None = None,
    require_numbers: bool | None = None,
    source_title: str | None = None,
    strict_title: bool = True,
):
    """
    基于“讨论种子/给定标题”生成：标题（≤18字）、数字范围副标题（X-Y 可选）、短句标语（8-12字）、主体文案（2-3行）。
    - 招聘/陪伴 => 强约束数值梯度；
    - 非招聘：如果提供 source_title 且 strict_title=True，则固定用该标题（或其轻度变体），只用 LLM 生成 tagline/body；否则走 LLM 全生成。
    """
    try:
        config = load_xhs_cover_config()
        
        # 判断是否需要数字
        seed_topics = [
            "不想上班但是想挣钱的活",
            "主打的就是陪伴",
            "年轻人能有什么赛道",
            "员工一定要给工资吗？",
            "大学生生存指南",
            "求5元花三天的办法",
            "马云给我的投资打水漂了怎么办",
            "这年头难道还能饿死人（这句话到底谁说的？）",
            theme or "陪伴"
        ]
        chosen_seed = (seed or random.choice(seed_topics)).strip()
        auto_numbers = any(k in (chosen_seed + theme) for k in ["陪伴", "招聘", "陪聊", "情感"])
        need_numbers = require_numbers if require_numbers is not None else auto_numbers

        # 招聘/陪伴：固定规则
        if need_numbers:
            # 标题：随机前缀 + 陪伴
            title = f"{random.choice(['主打','就是','简单'])}陪伴"
            lowers = list(range(5000, 10001, 1000))
            uppers = list(range(20000, 50001, 5000))
            a = random.choice(lowers)
            b = random.choice([u for u in uppers if u > a])
            subtitle = f"{a}-{b}"
            tag_pool = ["就是这么简单","轻轻松松","快快乐乐","自在一点","别想太多","放轻松点","把复杂留给世界","喜欢就聊两句"]
            tagline = random.choice(tag_pool)
            body_pool = [
                "不讲大道理\n就聊聊天 走走心\n把陪伴变得不复杂",
                "你说 我听\n不催不问\n把心情放轻一点",
                "想说就说 想停就停\n像朋友那样自在\n把陪伴留给当下",
                "就是简单陪伴\n轻松一点 快乐一点\n别把生活过难",
            ]
            body = random.choice(body_pool)
            return {"main_title": title, "subtitle": subtitle, "tagline": tagline, "body": body}

        # 非招聘：若提供 source_title 且严格使用
        if source_title and strict_title:
            fixed_title = _rewrite_title_from_seed(source_title)
            # 只向 LLM 要 tagline + body
            prompt = (
                "你是年轻女性文案助手（18-25岁）。\n"
                f"标题已确定：{fixed_title}\n"
                "请仅生成：\n"
                '1) 标语：6-10字，轻松口语风格，像闺蜜聊天，禁止学术化/严肃化词汇。\n'
                '2) 主体文案：2-3行，30-60字，生活化、能引发讨论，用"姐妹"/"打工人"/"搞钱"/"yyds"等年轻化表达。\n\n'
                "只输出严格JSON（不要解释、不要代码块）：\n"
                '{\n  "tagline": "中文短句",\n  "body": "主体文案"\n}'
            )
            response = requests.post(
                f"{config['title_base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {config['title_api_key']}", "Content-Type": "application/json"},
                json={"model": config['title_model'], "messages": [{"role": "user", "content": prompt}], "temperature": max(0.7, float(config['title_temperature'])), "max_tokens": max(180, int(config['title_max_tokens']))},
                proxies={"http": None, "https": None}, timeout=30
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content'].strip()
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            data = json.loads(content)
            tagline = str(data.get('tagline', '')).strip() or "把小日子过得有点意思"
            body = str(data.get('body', '')).strip() or f"{fixed_title}｜说说你的看法。"
            return {"main_title": fixed_title, "subtitle": "", "tagline": tagline, "body": body}

        # 非招聘且不强制标题：走原 LLM 生成
        import random as _rnd
        seed_for_prompt = f'"{chosen_seed}"' if _rnd.random() < 0.5 else chosen_seed
        prompt = (
            "你是年轻女性文案生成器（18-25岁）。\n"
            f"基于这条讨论种子：{seed_for_prompt}\n"
            "生成：标题≤16字、标语6-10字、主体文案2-3行（30-60字）。不要生成数字范围。\n"
            '风格：轻松口语、像闺蜜聊天、禁止学术化/严肃化词汇（如"隐忧"/"背后"/"时代"/"深刻"等），多用"姐妹"/"打工人"/"搞钱"/"yyds"等年轻化表达。\n\n'
            "只输出严格JSON（不要解释、不要代码块）：\n"
            '{\n  "main_title": "中文标题",\n  "subtitle": "",\n  "tagline": "中文短句",\n  "body": "主体文案"\n}'
        )
        response = requests.post(
            f"{config['title_base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {config['title_api_key']}", "Content-Type": "application/json"},
            json={"model": config['title_model'], "messages": [{"role": "user", "content": prompt}], "temperature": max(0.7, float(config['title_temperature'])), "max_tokens": max(220, int(config['title_max_tokens']))},
            proxies={"http": None, "https": None}, timeout=30
        )
        response.raise_for_status()
        data = response.json()['choices'][0]['message']['content'].strip()
        if '```json' in data:
            data = data.split('```json')[1].split('```')[0].strip()
        elif '```' in data:
            data = data.split('```')[1].split('```')[0].strip()
        d = json.loads(data)
        title = str(d.get('main_title','')).strip()[:18] or _rewrite_title_from_seed(chosen_seed)
        tagline = str(d.get('tagline','')).strip() or "把小日子过得有点意思"
        body = str(d.get('body','')).strip() or f"{title}｜说说你的看法。"
        return {"main_title": title, "subtitle": "", "tagline": tagline, "body": body}
        
    except Exception as e:
        # 兜底
        title = _rewrite_title_from_seed(source_title or seed or theme)
        tagline = "把小日子过得有点意思"
        body = f"{title}｜你会怎么做？说说你的经历。"
        return {"main_title": title[:18], "subtitle": "", "tagline": tagline, "body": body}


if __name__ == "__main__":
    # 测试生成
    print("="*60)
    print("测试LLM标题生成器")
    print("="*60 + "\n")
    
    titles = generate_cover_titles(theme="陪伴", income_min=5000, income_max=50000)
    
    print(f"\n生成结果:")
    print(f"  主标题: {titles['main_title']}")
    print(f"  副标题: {titles['subtitle']}")
    print(f"  标语: {titles['tagline']}")

