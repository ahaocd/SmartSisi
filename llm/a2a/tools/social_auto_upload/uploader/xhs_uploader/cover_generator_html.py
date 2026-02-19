"""
小红书封面生成器 - 专业HTML/CSS版本
使用现代Web技术 + html2canvas实现高质量封面
"""
import os
import time
import json
import requests
import sys
from datetime import datetime
import re
import random
from pathlib import Path
from playwright.async_api import async_playwright

# 修复导入路径
current_dir = Path(__file__).parent.resolve()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from config_loader import load_xhs_cover_config


class XHSCoverGeneratorPro:
    """专业级小红书封面生成器（HTML/CSS）"""
    
    def __init__(self, output_dir=None):
        self.output_dir = output_dir or os.path.dirname(__file__)
        
        # 从system.conf加载配置
        try:
            config = load_xhs_cover_config()
            self.base_url = config['bg_base_url']
            self.api_key = config['bg_api_key']
        except Exception as e:
            print(f"! 配置加载失败，使用默认配置: {str(e)}")
            # 降级方案：使用硬编码配置
            self.base_url = 'https://api-inference.modelscope.cn/'
            self.api_key = "ms-a3f98b49-a8b5-456a-98a8-d1040f6412a3"
        
        self.session = requests.Session()
        self.session.trust_env = False
    
    def generate_background_image_url(self, bg_type="luxury_products"):
        """
        生成背景图并返回URL
        
        Args:
            bg_type: 背景类型
                - "luxury_products": 奢侈品产品细节
                - "lifestyle": 高品质生活场景
                - "female_elegant": 优雅女性主题
        """
        # 随机选择单一产品特写
        single_products = [
            # 手机/相机玻璃与金属
            "iPhone 16 Pro 钛金属边框与相机环玻璃，高光折射，4K",
            "iPhone 14 Pro 深紫色玻璃背板与金属边框，局部特写，4K",
            "华为Pura 70铂金版镜头环与陶瓷背板细节，品牌环形标识，写实，4K",
            "华为Mate 70 Pro机身边框与星闪徽标特写，质感光泽，4K",
            "小米15 Ultra陶瓷背板与徕卡相机环特写，红点标，4K",
            "索尼A1 II相机机顶拨轮与快门按钮特写，金属质感，4K",
            
            # 礼物/生活方式/旅行
            "精品法式草莓蛋糕切面特写，果胶光泽与金箔点缀，4K",
            "高端酒店套房室内细节，胡桃木墙板与亚麻床品，暖光，4K",
            "海景民宿无边泳池与玻璃栏杆细节，黄昏天光反射，4K",
            "米其林餐厅刀叉与白瓷盘边缘高光特写，桌面布纹，4K",
            "高级行李箱拉杆与金属角包边特写，复古棕色，4K",
            "头等舱靠枕与真皮缝线细节，机舱氛围灯，4K"
        ]
        selected_product = random.choice(single_products)
        
        prompts = {
            "pure_color_product_macro": f"""
                纯色女性色背景（不要渐变，不要纹理，plain background only）。
                颜色倾向：淡粉、天蓝、浅紫、奶杏（任取其一，纯色）。
                画面边缘放置 1~2 个“高清产品局部特写”（如皮革纹理、金属扣件、镜头玻璃等），写实风格，4K。
                大面积留白位于中部/上部用于文字，不出现完整产品、不堆满、不对称排布。
                光效：轻微柔焦与自然光影过渡（非渐变背景）。
                重要：不要包含任何文本、字母、LOGO 或中文字符（no text, no letters, no typography）。
                示例细节：{selected_product}
            """,
            "lifestyle": """
                精致女性生活场景，温馨浪漫氛围。
                画面：咖啡桌面，白色大理石材质，柔和自然光。
                桌上物品：拿铁咖啡、马卡龙甜点、鲜花、打开的笔记本、
                玫瑰金色iPhone、精致手表、珍珠耳环。
                背景虚化，粉色调，温馨舒适，生活美学摄影，4K画质。
            """,
            "female_elegant": """
                优雅女性主题摄影，唯美浪漫风格。
                柔和粉紫色背景，梦幻光斑效果。
                前景虚化的玫瑰花瓣、香水瓶、珍珠项链、丝巾等女性物品。
                中央大面积留白用于文字。
                柔光拍摄，浅景深，时尚杂志封面风格，超清画质。
            """
        }
        
        prompt = prompts.get(bg_type, prompts["pure_color_product_macro"])
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在生成AI背景图...")
        
        try:
            response = self.session.post(
                f"{self.base_url}v1/images/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-ModelScope-Async-Mode": "true"
                },
                data=json.dumps({
                    "model": "Qwen/Qwen-Image",
                    "prompt": prompt.strip()
                }, ensure_ascii=False).encode('utf-8'),
                proxies={"http": None, "https": None}
            )
            
            response.raise_for_status()
            task_id = response.json()["task_id"]
            
            # 轮询任务状态
            for i in range(30):
                time.sleep(5)
                result = self.session.get(
                    f"{self.base_url}v1/tasks/{task_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "X-ModelScope-Task-Type": "image_generation"
                    },
                    proxies={"http": None, "https": None}
                )
                
                data = result.json()
                
                if data["task_status"] == "SUCCEED":
                    image_url = data["output_images"][0]
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ AI背景生成成功")
                    return image_url
                elif data["task_status"] == "FAILED":
                    print(f"AI背景生成失败，使用默认渐变")
                    return None
            
            return None
        except Exception as e:
            print(f"AI背景生成异常: {str(e)}，使用默认渐变")
            return None
    
    def _normalize_income_text(self, text: str) -> str:
        """规范化收入副标题文本，避免出现尾随或前置短横等异常格式。
        规则：
        - 抽取所有连续数字块（允许千位分隔符被忽略）
        - 若得到2个及以上数字，取前两个，按从小到大用“-”连接
        - 若只有1个数字，直接返回该数字
        - 若没有数字或原文本为空，返回空串（不渲染）
        - 清除多余空格，并确保短横只出现在两个数字之间
        """
        if not isinstance(text, str):
            return ""
        raw = text.strip()
        if not raw:
            return ""
        # 提取数字序列
        nums = re.findall(r"\d+", raw)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            lo, hi = (a, b) if a <= b else (b, a)
            return f"{lo}-{hi}"
        if len(nums) == 1:
            return nums[0]
        return ""
    
    def create_html_template(self, main_title, subtitle, tagline, background_url=None, emoji=None):
        """
        创建HTML模板
        
        Args:
            main_title: 主标题（如"温暖陪伴"）
            subtitle: 副标题（如"5000-30000"）
            tagline: 标语（如"遇见更好的自己"）
            background_url: 背景图URL（可选）
            emoji: 装饰emoji（None则随机1-2个）
        """
        # --- 文案与排版的随机化参数 ---
        # 随机选择1-2个装饰性emoji（星星、行星等，不引导性别）
        if emoji is None:
            emoji_list = ['✨', '⭐', '🌟', '💫', '🌙', '☀️', '🌈', '🪐', '🌠', '🔮']
            num_emojis = random.choice([1, 2])  # 随机1或2个
            selected_emojis = random.sample(emoji_list, num_emojis)
            emoji = ' '.join(selected_emojis)
        
        # 提取关键词（主标题的后2个字作为高亮）
        if len(main_title) >= 2:
            keyword = main_title[-2:]  # 如"陪伴"
            title_before = main_title[:-2]  # 如"温暖"
        else:
            keyword = main_title
            title_before = ""
        
        # 规范化副标题中的数字区间，仅当传入不为空时
        subtitle = self._normalize_income_text(subtitle) if isinstance(subtitle, str) and subtitle.strip() else ""
        is_non_recruit = (subtitle == "")
        # 根据是否有副标题决定class（无内容则隐藏）
        subtitle_class = "subtitle" if subtitle else "subtitle hidden"
        main_title_class = "main-title" if not is_non_recruit else "hidden"
        tagline_class = "tagline" if not is_non_recruit else "hidden"
        center_card_class = "center-card" if is_non_recruit else "center-card hidden"

        # 非招聘：根据标点把标题拆成两行，并放大第二行
        card_title_line1 = main_title
        card_title_line2 = ""
        if is_non_recruit:
            m = re.split(r"[：:，,。！？!?]", main_title, maxsplit=1)
            if len(m) > 1 and m[1].strip():
                card_title_line1 = m[0].strip()
                card_title_line2 = m[1].strip()
        
        # 浅色纯色背景（不渐变），女性柔和风格
        bg_colors = [
            '#FFF0F5',  # 淡粉（薰衣草雾）
            '#FFE4E1',  # 淡玫瑰白
            '#FFF5EE',  # 海贝白
            '#F0F8FF',  # 爱丽丝蓝
            '#FAF0E6',  # 亚麻色
            '#FFFACD',  # 柠檬绸
            '#F5FFFA',  # 薄荷奶油
            '#FFF8DC',  # 玉米丝
        ]
        highlight_bg = random.choice(bg_colors)

        # 主标题"陪伴"样式：高对比的品牌色（天蓝/紫）或深色
        main_title_color = random.choice(['#2F80ED', '#7F56D9', '#111111'])
        main_stroke = 2  # 更细描边，避免笔划拼接感
        main_stroke_color = 'rgba(255,255,255,0.98)'
        main_shadow = True
        
        # 数字副标题样式：深灰+描边
        stroke_color = 'rgba(255,255,255,0.98)'  # 白色描边
        stroke_width = 8  # 固定8px描边
        shadow_y = 4  # 固定阴影偏移
        shadow_blur = 10  # 固定阴影模糊

        # 标语底部纯色气泡背景
        tagline_bg = random.choice(['#E6F0FF', '#FFE6F0', '#FFF3CD', '#E8FFF3'])
        frame_color = random.choice(['#9DBDFF', '#FFC1D9', '#FFDFA3', '#A8E6CF'])

        # 元素随机上下浮动与整体上下对齐方式
        vertical_position = 'center'  # 固定居中，避免上下随机
        main_float = random.randint(-12, 12)
        sub_float = random.randint(-8, 8)
        tag_float = random.randint(-6, 6)

        # 预留：字符柔和背景色能力（暂不启用，避免影响版式）

        # 高亮胶囊大小随机
        pad_v = random.randint(6, 12)
        pad_h = random.randint(22, 36)
        radius = random.randint(18, 28)
        
        # 生成散落emoji HTML
        scatter_count = random.randint(2, 5)
        scatter_candidates = ['✨', '⭐', '🌟', '💫', '🌙', '☀️', '🌈', '🪐', '🌠', '🔮', '💖', '💎', '🌸']
        scatter_html_parts = []
        for _ in range(scatter_count):
            e = random.choice(scatter_candidates)
            size = random.randint(48, 120)
            top = random.randint(5, 85)  # 百分比
            left = random.randint(5, 90)
            opacity = random.uniform(0.08, 0.22)
            rotate = random.randint(-25, 25)
            scatter_html_parts.append(
                f"<div class=\"scatter-emoji\" style=\"top:{top}%;left:{left}%;font-size:{size}px;opacity:{opacity:.2f};transform:rotate({rotate}deg);\">{e}</div>"
            )
        scatter_emojis_html = "\n".join(scatter_html_parts)

        # 背景样式
        if background_url:
            # 直接使用AI背景图，不加遮罩层
            background_style = f"""
                background-image: url('{background_url}');
                background-size: cover;
                background-position: center;
            """
        else:
            background_style = """
                background: linear-gradient(135deg, #FFD4E5 0%, #E8D4F5 50%, #D4E5FF 100%);
            """
        
        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>小红书封面</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;700;900&family=Poppins:wght@700;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        :root {{
            --primary-color: #FF69B4;
            --secondary-color: #FFD700;
            --text-dark: #2C2C2C;
            --text-light: #666;
            --shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
        }}
        
        body {{
            font-family: 'Noto Sans SC', sans-serif;
            overflow: hidden;
        }}
        
        #cover-container {{
            width: 1080px;
            height: 1440px;
            position: relative;
            {background_style}
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 80px 60px;
            overflow: hidden;
        }}
        
        /* 毛玻璃文字层容器 - 更通透显示AI背景 */
        #text-layer {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: {vertical_position};
            padding: 80px 60px;
        }}
        
        /* 散落的透明emoji（点缀） */
        .scatter-emoji {{
            position: absolute;
            z-index: 6; /* 在内容层之下、遮罩之上 */
            pointer-events: none;
            filter: drop-shadow(0 1px 2px rgba(0,0,0,0.12));
        }}
        
        /* 装饰性背景元素 - 移除 */
        .bg-decoration {{
            display: none;
        }}
        
        /* 主内容容器 */
        .content-wrapper {{
            position: static; /* 让绝对定位的标语相对#text-layer而非本容器 */
            z-index: 10;
            width: 100%;
            max-width: 900px;
            text-align: center;
            animation: fadeInUp 1s ease-out;
        }}
        .content-wrapper.left-mode {{
            text-align: left; /* 招聘版靠左排布 */
            margin: 0 auto;
        }}
        
        @keyframes fadeInUp {{
            from {{
                opacity: 0;
                transform: translateY(30px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        /* 顶部Emoji装饰 - 简洁版 */
        .top-emoji {{
            position: absolute;
            top: 40px;
            right: 50px;
            font-size: 70px;
            opacity: 0.7;
            filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
        }}
        
        /* 主标题区域（方正无衬线重体） */
        .main-title {{
            font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif; /* 只用已加载的字体 */
            font-size: 200px;
            font-weight: 500; /* 降到Medium避免偏旁粘连 */
            line-height: 1.0;
            margin-bottom: 60px;
            letter-spacing: 4px; /* 加大字距确保偏旁不重叠 */
            color: {main_title_color};
            /* 使用多层阴影模拟描边，避免描边造成的笔画裂缝 */
            text-shadow:
                0 0 2px rgba(255,255,255,0.95),
                0 0 6px rgba(255,255,255,0.9),
                0 2px 12px rgba(0,0,0,0.22);
            position: relative;
            display: inline-block;
            transform: translateY({main_float}px);
            -webkit-text-stroke: 0; /* 取消描边，避免笔画断裂 */
            filter: drop-shadow(0 8px 16px rgba(0,0,0,0.25));
            -webkit-font-smoothing: antialiased;
            text-rendering: optimizeLegibility;
        }}
        
        .title-normal {{
            display: inline-block;
            opacity: 0.85;
        }}
        
        .title-highlight {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: {main_title_color}; /* 与主标题一致的品牌色 */
            background: {highlight_bg};
            padding: {pad_v}px {pad_h}px;
            border-radius: {radius}px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
            position: relative;
            margin-left: 0; /* 取消偏移，整体更易居中 */
            letter-spacing: 2px; /* 适当增加字距避免偏旁重叠 */
            -webkit-text-stroke: 2px rgba(255,255,255,0.95); /* 细白描边增强层次 */
        }}
        
        
        /* 副标题（收入数字）- 深色渐变 + 强阴影（强制单行） */
        .subtitle {{
            font-family: 'Poppins', 'Noto Sans SC', sans-serif;
            font-size: 120px;
            font-weight: 900;
            margin-bottom: 40px;
            letter-spacing: 6px;
            position: relative;
            display: inline-block;
            color: #111; /* 基色深色，确保对比 */
            /* 取消描边，改用多层阴影形成外轮廓，避免笔画断裂 */
            -webkit-text-stroke: 0;
            text-shadow:
                0 0 2px rgba(255,255,255,0.95),
                0 0 6px rgba(255,255,255,0.9),
                0 4px 10px rgba(0,0,0,0.25);
            transform: translateY({sub_float}px);
            white-space: nowrap;
        }}
        .subtitle.hidden {{ display: none; }}
        
        /* 标语 */
        .tagline {{
            position: absolute;
            bottom: 110px; /* 固定到底部区域 */
            left: 50%;
            transform: translateX(-50%);
            font-family: 'Noto Sans SC', sans-serif;
            font-size: 48px;
            font-weight: 600;
            color: #333;
            letter-spacing: 2px;
            background: {tagline_bg};
            padding: 14px 26px;
            border-radius: 20px;
            box-shadow: 0 8px 22px rgba(0,0,0,0.18);
            -webkit-text-stroke: 1px rgba(255,255,255,0.6);
        }}
        
        /* 装饰性图标 - 移除 */
        .icon-decoration {{
            display: none;
        }}
        
        /* 底部装饰emoji - 移除 */
        .bottom-emoji {{
            display: none;
        }}
        
        /* 控制按钮 - 隐藏 */
        #save-button {{
            display: none;
        }}
        .char-pill {{
            background: {random.choice(['#FFE6F2','#E8F3FF','#EAFBF1','#FFF7E6','#F6EAFE','#E9F6FF'])};
            border-radius: 12px;
            padding: 0 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        }}
        .hidden {{ display: none; }}
        .center-card {{
            position: absolute;
            bottom: 110px; /* 固定到底部区域 */
            left: 50%;
            transform: translateX(-50%);
            font-family: 'Noto Sans SC', sans-serif;
            font-size: 48px;
            font-weight: 600;
            color: #333;
            letter-spacing: 2px;
            background: {tagline_bg};
            padding: 14px 26px;
            border-radius: 20px;
            box-shadow: 0 8px 22px rgba(0,0,0,0.18);
            -webkit-text-stroke: 1px rgba(255,255,255,0.6);
        }}

        /* 非招聘版：标题+副标题置于居中框体 */
        .center-card {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: min(90%, 900px);
            background: transparent; /* 仅边框，不要白底 */
            border: 6px solid {frame_color};
            border-radius: 28px;
            padding: 24px 28px;
            box-shadow: 0 18px 40px rgba(0,0,0,0.12);
            text-align: left; /* 框内文字靠左对齐 */
        }}
        .center-card .card-title {{
            font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
            font-weight: 400; /* 进一步降低字重：500 -> 400 */
            color: #FFFFFF; /* 白色字体 */
            font-size: clamp(62px, 8.2vw, 180px); /* 增大字号 */
            line-height: 1.2; /* 增加行高 */
            letter-spacing: 8px; /* 大幅增加字距：4px -> 8px */
            -webkit-text-stroke: 3px #000000; /* 黑色描边 */
            text-shadow: 
                0 4px 12px rgba(0,0,0,0.6),
                0 8px 24px rgba(0,0,0,0.4),
                0 12px 36px rgba(0,0,0,0.2); /* 强化多层阴影 */
            filter: drop-shadow(0 6px 18px rgba(0,0,0,0.5));
        }}
        .center-card .card-title-em {{
            font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
            font-weight: 400; /* 进一步降低字重：500 -> 400 */
            color: #FFFFFF; /* 白色字体 */
            font-size: clamp(72px, 9.2vw, 200px); /* 增大字号 */
            line-height: 1.2; /* 增加行高 */
            letter-spacing: 8px; /* 大幅增加字距：4px -> 8px */
            margin-top: 10px;
            -webkit-text-stroke: 3px #000000; /* 黑色描边 */
            text-shadow: 
                0 4px 12px rgba(0,0,0,0.6),
                0 8px 24px rgba(0,0,0,0.4),
                0 12px 36px rgba(0,0,0,0.2); /* 强化多层阴影 */
            filter: drop-shadow(0 6px 18px rgba(0,0,0,0.5));
        }}
        .center-card .card-subtitle {{
            margin-top: 18px;
            font-size: clamp(32px, 4.8vw, 72px); /* 增大字号 */
            font-weight: 400;
            color: #FFFFFF; /* 白色字体 */
            letter-spacing: 4px; /* 增加字距 */
            -webkit-text-stroke: 2px #000000; /* 黑色描边 */
            text-shadow: 
                0 3px 10px rgba(0,0,0,0.5),
                0 6px 20px rgba(0,0,0,0.3); /* 强化阴影 */
            filter: drop-shadow(0 4px 12px rgba(0,0,0,0.4));
        }}
    </style>
</head>
<body>
    <button id="save-button">
        <i class="fas fa-download"></i> 保存封面
    </button>
    
    <div id="cover-container">
        <!-- 毛玻璃文字层 -->
        <div id="text-layer">
            <!-- 透明散落emoji点缀 -->
            {scatter_emojis_html}
            <!-- 背景装饰文字 -->
            <div class="bg-decoration decoration-1">✨</div>
            <div class="bg-decoration decoration-2">💫</div>
            <div class="bg-decoration decoration-3">⭐</div>
            <div class="bg-decoration decoration-4">💖</div>
            
            <!-- 装饰性图标 -->
            <i class="fas fa-heart icon-decoration icon-1"></i>
            <i class="fas fa-gem icon-decoration icon-2"></i>
            <i class="fas fa-crown icon-decoration icon-3"></i>
            <i class="fas fa-star icon-decoration icon-4"></i>
            
            <!-- 主内容 -->
            <div class="content-wrapper">
                <div class="top-emoji">{emoji}</div>
                
                <h1 class="{main_title_class}">
                    <span class="title-normal">{title_before}</span><span class="title-highlight">{keyword}</span>
                </h1>
                
                <div class="{subtitle_class}">{subtitle}</div>
                
                <p class="{tagline_class}">{tagline}</p>

                <!-- 非招聘版 居中框体（将标语作为第二行） -->
                <div class="{center_card_class}">
                    <div class="card-title">{card_title_line1}</div>
                    {f'<div class="card-title-em">{card_title_line2}</div>' if card_title_line2 else ''}
                    <div class="card-subtitle">{tagline}</div>
                </div>
            </div>
            
            <!-- 底部装饰emoji -->
            <div class="bottom-emoji">🌸 ☕ 💄 👜 💍</div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script>
        document.getElementById('save-button').addEventListener('click', function() {{
            const button = this;
            button.textContent = '正在生成...';
            button.disabled = true;
            
            // 隐藏按钮
            button.style.display = 'none';
            
            setTimeout(() => {{
                html2canvas(document.getElementById('cover-container'), {{
                    width: 1080,
                    height: 1440,
                    scale: 2,
                    useCORS: true,
                    allowTaint: true,
                    backgroundColor: null
                }}).then(canvas => {{
                    // 转换为图片并下载
                    const link = document.createElement('a');
                    link.download = 'xhs_cover_' + new Date().getTime() + '.png';
                    link.href = canvas.toDataURL('image/png', 1.0);
                    link.click();
                    
                    // 恢复按钮
                    button.style.display = 'block';
                    button.textContent = '✓ 保存成功！';
                    button.disabled = false;
                    
                    setTimeout(() => {{
                        button.innerHTML = '<i class="fas fa-download"></i> 保存封面';
                    }}, 2000);
                }});
            }}, 100);
        }});
        
        // 给每个字符单独加白色背景
        function wrapCharsWithBackground(selector) {{
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => {{
                const text = el.textContent;
                el.innerHTML = '';
                for (let char of text) {{
                    if (char.trim()) {{ // 跳过空格
                        const span = document.createElement('span');
                        span.textContent = char;
                        span.style.background = 'rgba(255,255,255,0.85)';
                        span.style.padding = '4px 8px';
                        span.style.margin = '0 2px';
                        span.style.borderRadius = '6px';
                        span.style.display = 'inline-block';
                        span.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
                        el.appendChild(span);
                    }} else {{
                        el.appendChild(document.createTextNode(char));
                    }}
                }}
            }});
        }}
        
        // 只应用到card-title和card-title-em（主标题和副标题）
        wrapCharsWithBackground('.card-title');
        wrapCharsWithBackground('.card-title-em');
        
        // 自动保存（用于无头浏览器）
        if (window.autoSave) {{
            setTimeout(() => {{
                document.getElementById('save-button').click();
            }}, 1000);
        }}
    </script>
</body>
</html>
        """
        
        return html
    
    def generate_cover(self, main_title, subtitle, tagline="遇见更好的自己", 
                       use_ai_background=False, emoji="💝", auto_open=False):
        """
        生成封面
        
        Args:
            main_title: 主标题
            subtitle: 副标题（收入信息）
            tagline: 标语
            use_ai_background: 是否使用AI背景
            emoji: 顶部装饰emoji
            auto_open: 是否自动打开浏览器查看
            
        Returns:
            str: HTML文件路径
        """
        print(f"\n{'='*60}")
        print(f"开始生成专业级小红书封面...")
        print(f"{'='*60}\n")
        
        # 1. 生成背景图（可选）
        background_url = None
        if use_ai_background:
            background_url = self.generate_background_image_url()
        
        # 2. 创建HTML
        html_content = self.create_html_template(
            main_title=main_title,
            subtitle=subtitle,
            tagline=tagline,
            background_url=background_url,
            emoji=emoji
        )
        
        # 3. 保存HTML文件
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_filename = f"xhs_cover_{timestamp}.html"
        html_filepath = os.path.join(self.output_dir, html_filename)
        
        with open(html_filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✓ HTML模板已生成: {html_filepath}")
        
        # 4. 如果需要，自动打开浏览器
        if auto_open:
            import webbrowser
            webbrowser.open(f'file:///{os.path.abspath(html_filepath)}')
            print(f"✓ 已在浏览器中打开，点击\"保存封面\"按钮即可下载图片")
        
        print(f"\n{'='*60}")
        print(f"✓ 封面生成完成！")
        print(f"  HTML路径: {html_filepath}")
        print(f"  ")
        print(f"  使用方式：")
        print(f"  1. 在浏览器中打开HTML文件")
        print(f"  2. 点击右上角\"保存封面\"按钮")
        print(f"  3. 图片将自动下载到浏览器下载目录")
        print(f"{'='*60}\n")
        
        return html_filepath
    
    async def generate_cover_auto(self, main_title, subtitle, tagline="遇见更好的自己",
                            use_ai_background=False, emoji="💝"):
        """
        使用Playwright自动生成并保存图片（异步版本）
        
        Args:
            main_title: 主标题
            subtitle: 副标题
            tagline: 标语
            use_ai_background: 是否使用AI背景
            emoji: 装饰emoji
            
        Returns:
            str: 图片文件路径
        """
        print(f"\n{'='*60}")
        print(f"开始自动生成封面图片（无头浏览器模式）...")
        print(f"{'='*60}\n")
        
        # 1. 生成HTML
        html_filepath = self.generate_cover(
            main_title=main_title,
            subtitle=subtitle,
            tagline=tagline,
            use_ai_background=use_ai_background,
            emoji=emoji,
            auto_open=False
        )
        
        # 2. 使用Playwright截图
        print("正在使用无头浏览器截图...")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        img_filename = f"xhs_cover_{timestamp}.png"
        img_filepath = os.path.join(self.output_dir, img_filename)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1080, 'height': 1440})
            await page.goto(f'file:///{os.path.abspath(html_filepath)}')
            await page.wait_for_timeout(2000)  # 等待渲染完成
            
            # 截图
            await page.locator('#cover-container').screenshot(path=img_filepath)
            await browser.close()
        
        print(f"\n{'='*60}")
        print(f"✓ 封面图片生成完成！")
        print(f"  图片路径: {img_filepath}")
        print(f"  图片尺寸: 1080x1440")
        print(f"{'='*60}\n")
        
        return img_filepath


def main():
    """示例用法"""
    generator = XHSCoverGeneratorPro()
    
    # 方式1：生成HTML（手动保存）
    html_path = generator.generate_cover(
        main_title="温暖陪伴",
        subtitle="5000-30000",
        tagline="开启品质生活",
        use_ai_background=False,
        emoji="💝",
        auto_open=True  # 自动打开浏览器
    )
    
    # 方式2：自动生成PNG（推荐用于工作流）
    # img_path = generator.generate_cover_auto(
    #     main_title="温暖陪伴",
    #     subtitle="5000-30000",
    #     tagline="开启品质生活",
    #     use_ai_background=False,
    #     emoji="💝"
    # )


if __name__ == "__main__":
    main()

