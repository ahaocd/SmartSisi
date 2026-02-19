"""
小红书封面自动生成工作流接口（统一HTML实现）
用于集成到智能体自动化流程中
"""
import os
import sys
from pathlib import Path

# 修复导入路径
current_dir = Path(__file__).parent.resolve()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from cover_generator_html import XHSCoverGeneratorPro
from llm_title_generator import generate_cover_titles
from config_loader import load_xhs_cover_config


def generate_xhs_cover_for_workflow(
    content_theme: str = "陪伴",
    income_info: str = "5000-30000",
    main_title: str = None,
    subtitle: str = None,
    tagline: str = None,
    use_ai_background: bool = False,
    output_dir: str = None
) -> dict:
    """
    为工作流生成小红书封面
    
    Args:
        content_theme: 内容主题（用于LLM生成标题）
        income_info: 收入信息
        main_title: 主标题（如果提供则不使用LLM生成）
        subtitle: 副标题
        tagline: 标语/口号
        use_ai_background: 是否使用AI生成背景（False=快速渐变背景，True=AI生成约15秒）
        output_dir: 输出目录，默认为当前目录
        
    Returns:
        dict: {
            'success': bool,
            'cover_path': str,
            'message': str,
            'titles': dict
        }
    """
    try:
        # 设置输出目录
        if output_dir is None:
            output_dir = os.path.dirname(__file__)
        
        # 初始化统一的HTML生成器
        generator = XHSCoverGeneratorPro(output_dir=output_dir)
        
        # 准备标题
        # 标题准备（若未提供则用简单规则降级生成，避免额外依赖）
        titles = {
            'main_title': main_title or f"温暖{content_theme}",
            'subtitle': (subtitle or income_info),
            'tagline': (tagline or '遇见更好的自己')
        }

        # 生成PNG（自动截图）- 使用asyncio.run调用异步函数
        import asyncio
        cover_path = asyncio.run(generator.generate_cover_auto(
            main_title=titles['main_title'],
            subtitle=titles['subtitle'],
            tagline=titles['tagline'],
            use_ai_background=use_ai_background,
            emoji="💝"
        ))
        
        return {
            'success': True,
            'cover_path': cover_path,
            'message': '封面生成成功',
            'titles': titles
        }
        
    except Exception as e:
        return {
            'success': False,
            'cover_path': None,
            'message': f'封面生成失败: {str(e)}',
            'titles': None
        }


def quick_generate_cover(main_title: str, subtitle: str, tagline: str = "遇见更好的自己") -> str:
    """
    快速生成封面（使用渐变背景，约1秒）
    
    Args:
        main_title: 主标题
        subtitle: 副标题（通常是收入信息）
        tagline: 标语
        
    Returns:
        str: 封面路径
    """
    result = generate_xhs_cover_for_workflow(
        main_title=main_title,
        subtitle=subtitle,
        tagline=tagline,
        use_ai_background=False  # 快速模式
    )
    
    if result['success']:
        return result['cover_path']
    else:
        raise Exception(result['message'])


def ai_generate_cover(content_theme: str = "陪伴", income_info: str = "5000-30000") -> str:
    """
    使用AI生成完整封面（包含AI背景，约15秒）
    
    Args:
        content_theme: 内容主题
        income_info: 收入信息
        
    Returns:
        str: 封面路径
    """
    result = generate_xhs_cover_for_workflow(
        content_theme=content_theme,
        income_info=income_info,
        use_ai_background=True  # AI背景模式
    )
    
    if result['success']:
        return result['cover_path']
    else:
        raise Exception(result['message'])


# ============= 统一的便捷入口（替代 quick_cover 与 ai_cover_workflow、final_cover_generator） =============

def generate_html_cover(main_title: str, subtitle: str, tagline: str = "遇见更好的自己",
                        emoji: str = "💝", auto_open: bool = True) -> str:
    """生成HTML封面（手动保存）。"""
    generator = XHSCoverGeneratorPro()
    return generator.generate_cover(
        main_title=main_title,
        subtitle=subtitle,
        tagline=tagline,
        use_ai_background=False,
        emoji=emoji,
        auto_open=auto_open
    )


async def generate_png_cover(main_title: str, subtitle: str, tagline: str = "遇见更好的自己",
                       emoji: str = "💝", use_ai_bg: bool = False) -> str:
    """自动生成PNG封面（无需手动）- 异步版本。"""
    generator = XHSCoverGeneratorPro()
    return await generator.generate_cover_auto(
        main_title=main_title,
        subtitle=subtitle,
        tagline=tagline,
        use_ai_background=use_ai_bg,
        emoji=emoji
    )


def generate_xhs_cover(
    theme: str = "陪伴",
    income_min: int = 5000,
    income_max: int = 50000,
    use_ai_background: bool = False,
    bg_type: str = "luxury_products"
) -> dict:
    """完整流程：加载配置 + LLM标题 + 可选AI背景 + 输出PNG。"""
    try:
        print("\n" + "="*60)
        print("🎨 小红书封面生成器（统一入口）")
        print("="*60 + "\n")

        # 1. 加载配置
        print("[1/4] 加载system.conf配置...")
        config = load_xhs_cover_config()
        print(f"✓ 配置加载成功")
        print(f"  - 标题LLM: {config['title_model']}")
        print(f"  - 背景AI: {config['bg_model']}")

        # 2. LLM生成标题
        print(f"\n[2/4] LLM生成标题（主题：{theme}）...")
        titles = generate_cover_titles(
            theme=theme,
            income_min=income_min,
            income_max=income_max
        )

        # 3. 生成封面
        print(f"\n[3/4] 生成封面...")
        generator = XHSCoverGeneratorPro()

        bg_url = None
        if use_ai_background:
            print(f"  - 正在生成AI背景（{bg_type}）...")
            bg_url = generator.generate_background_image_url(bg_type=bg_type)

        # 注意：这个函数现在是同步的，如需异步请改造整个函数
        import asyncio
        img_path = asyncio.run(generator.generate_cover_auto(
            main_title=titles['main_title'],
            subtitle=titles['subtitle'],
            tagline=titles['tagline'],
            use_ai_background=(bg_url is not None),
            emoji=None
        ))

        print(f"\n[4/4] 完成！")
        print("\n" + "="*60)
        print("✓ 封面生成成功")
        print(f"  - 主标题: {titles['main_title']}")
        print(f"  - 副标题: {titles['subtitle']}")
        print(f"  - 标语: {titles['tagline']}")
        print(f"  - 背景: {'AI生成' if bg_url else '渐变'}")
        print(f"  - 保存路径: {img_path}")
        print("="*60 + "\n")

        return {
            'success': True,
            'image_path': img_path,
            'titles': titles,
            'config': config,
            'message': '封面生成成功'
        }
    except Exception as e:
        return {
            'success': False,
            'image_path': None,
            'titles': None,
            'config': None,
            'message': f'生成失败: {str(e)}'
        }


# ============= 示例用法 =============

if __name__ == "__main__":
    # 改为统一完整流程演示：LLM 生成标题 + 可选 AI 背景
    print("\n" + "="*60)
    print("示例：统一完整流程（LLM 标题 + 可选 AI 背景）")
    print("="*60)

    result = generate_xhs_cover(
        theme="陪伴",
        income_min=6000,
        income_max=24000,
        use_ai_background=True,   # 开启 AI 背景
        bg_type="luxury_products" # 可改：lifestyle / female_elegant
    )

    if result['success']:
        print(f"\n✓ 成功！")
        print(f"  图片: {result['image_path']}")
        print(f"  标题: {result['titles']}")
    else:
        print(f"\n✗ 失败: {result['message']}")

