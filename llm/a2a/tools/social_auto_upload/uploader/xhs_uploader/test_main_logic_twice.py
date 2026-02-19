import sys
import asyncio
import random
from pathlib import Path

# ensure imports work when running directly
CURRENT_DIR = Path(__file__).parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from llm_title_generator import generate_cover_titles
from auto_cover_workflow import generate_png_cover

MODE = (sys.argv[1] if len(sys.argv) > 1 else "auto").lower()  # recruit | non | both | auto

async def run_once(iter_idx: int, require_numbers: bool, theme: str = "情感陪伴类") -> None:
    kind = "招聘陪伴（带数字）" if require_numbers else "非招聘（无数字）"
    print("\n" + "="*60)
    print(f"第 {iter_idx} 次 - {kind}")
    print("="*60)

    titles = generate_cover_titles(theme=theme, require_numbers=require_numbers)

    # tag pools (sync with xiaohongshu_auto_upload_tool.py)
    if require_numbers:
        tag_pool = [
            '陪伴', '倾听', '情感支持', '温暖', '治愈', '贴心',
            '理解', '共情', '时间自由', '灵活工作', '副业',
            '在家工作', '兼职', '轻松赚钱', '暖心', '真诚',
            '成长', '美好生活', '陪伴经济', '情感陪护'
        ]
    else:
        tag_pool = [
            '生活分享', '日常', '真实', '省钱攻略', '穷鬼快乐',
            '大学生', '打工人', '搞笑', '沙雕', '整活',
            '生活记录', 'vlog', '美食', '探店', '好物分享',
            '生活方式', '自我成长', '精致穷', '小确幸'
        ]
    tags = random.sample(tag_pool, min(6, len(tag_pool)))

    print(f"主标题: {titles['main_title']}")
    print(f"副标题: {titles['subtitle']}")
    print(f"标语: {titles.get('tagline','')}")
    print(f"正文: {titles.get('body','')[:60]}...")
    print(f"标签: {', '.join(tags)}")

    img_path = await generate_png_cover(
        main_title=titles['main_title'],
        subtitle=titles['subtitle'],
        tagline=titles.get('tagline', '遇见更好的自己'),
        emoji=random.choice(["💖", "💝", "✨", "🌸", "💫"]),
        use_ai_bg=True
    )
    print(f"封面图片: {img_path}")

async def main():
    print("\n主程序同链路 - 生成两次（只生成不发布） mode=", MODE)
    if MODE == "recruit":
        await run_once(1, True)
        await run_once(2, True)
    elif MODE == "non":
        await run_once(1, False)
        await run_once(2, False)
    elif MODE == "both":
        await run_once(1, True)
        await run_once(2, False)
    else:  # auto
        await run_once(1, random.random() < 0.5)
        await run_once(2, random.random() < 0.5)
    print("\n完成。\n")

if __name__ == "__main__":
    asyncio.run(main())
