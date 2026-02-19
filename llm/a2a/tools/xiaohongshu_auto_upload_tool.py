"""
🤖 小红书自动发布智能体 - XiaoHongShu Auto Upload Agent
功能：比特浏览器多账号轮流自动发布图文内容

核心功能：
1. 自动生成招聘引流封面
2. AI智能生成标题和标签
3. 比特浏览器多环境轮流发布
4. 失败直接停止（不重试）
5. 完善的错误处理和日志

作者：SiSi AI Team
版本：1.0 - 比特浏览器版
"""

import json
import logging
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 添加项目路径
TOOL_DIR = Path(__file__).parent
social_auto_upload_dir = TOOL_DIR / "social_auto_upload"
if str(social_auto_upload_dir) not in sys.path:
    sys.path.insert(0, str(social_auto_upload_dir))

logger = logging.getLogger(__name__)

# ==================== 配置管理 ====================

class XHSConfig:
    """小红书发布配置"""
    
    def __init__(self):
        self.base_dir = TOOL_DIR / "social_auto_upload"
        self.uploader_dir = self.base_dir / "uploader" / "xhs_uploader"
        
        # 比特浏览器默认配置（官方API端口）
        self.bitbrowser_api_url = "http://127.0.0.1:54345"
        
        # 发布配置
        self.default_theme = "情感陪伴类"
        # 改为分钟区间 + 每日上限6
        self.default_interval_minutes = (30, 50)
        self.default_posts_per_day = 6
        
        # 三个环境ID（从比特浏览器获取）
        self.profile_ids = self._load_profile_ids()
    
    def _load_profile_ids(self) -> List[str]:
        """从比特浏览器API获取环境ID（已配置3个小红书环境）"""
        # 固定配置：3个小红书专用环境（从比特浏览器获取）
        profile_ids = [
            "6f60ef87c8744b9caf8c6d9a12f50732",  # XIAOHONGSHU3
            "ab3974b9e3094d7fa3db31afab24b40a",  # XIAOHONGSHU2
            "9d8cb03a23144c0c82b4ce82d9fa398f"   # xiaohongshu1
        ]
        logger.info(f"[配置] 已加载 {len(profile_ids)} 个比特浏览器环境")
        return profile_ids

config = XHSConfig()

# ==================== 发布管理器 ====================

class XHSPublishManager:
    """小红书发布管理器"""
    
    def __init__(self):
        self.config = config
        self.db_file = self.config.base_dir / "db" / "xhs_schedule.json"
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
    
    async def publish_single(
        self,
        profile_id: str,
        theme: str = "情感陪伴类",
        title: str = None,
        tags: List[str] = None,
        content: str = None,
        image_path: str = None
    ) -> Dict[str, Any]:
        """发布单个帖子
        
        Args:
            profile_id: 比特浏览器环境ID
            theme: 主题类型
            title: 标题（可选，自动生成）
            tags: 标签（可选，自动生成）
            content: 正文（可选，自动生成）
            image_path: 封面图片（可选，自动生成）
        
        Returns:
            {"success": bool, "message": str, "error": str}
        """
        try:
            from uploader.xhs_uploader.main import (
                XHSImageUploader,
                FingerprintBrowserAPI
            )
            from uploader.xhs_uploader.auto_cover_workflow import generate_png_cover
            from uploader.xhs_uploader.llm_title_generator import generate_cover_titles
            import random
            import os
            
            logger.info(f"[发布] 开始发布到环境: {profile_id}")
            
            # 判断是否招聘主题（带数字）
            is_recruitment = theme in ["情感陪伴类", "陪伴类", "招聘陪伴"]
            
            # 生成内容（使用新版LLM）
            if not title or not tags or not content:
                # 环境变量可强制指定：1=招聘(带数字), 0=非招聘
                env_force = os.getenv('XHS_REQUIRE_NUMBERS')
                if env_force is not None:
                    require_numbers = env_force.strip() in ('1','true','True')
                else:
                    # 默认50%概率招聘（带数字），50%非招聘（无数字）
                    require_numbers = random.random() < 0.5
                
                logger.info(f"[发布] 生成类型: {'招聘陪伴（带数字）' if require_numbers else '非招聘（无数字）'}")
                
                titles_dict = generate_cover_titles(
                    theme=theme,
                    require_numbers=require_numbers
                )
                
                if not title:
                    title = titles_dict['main_title']
                if not tags:
                    # 根据类型动态生成标签
                    if require_numbers:
                        # 招聘类标签池（多样化）
                        tag_pool = [
                            '陪伴', '倾听', '情感支持', '温暖', '治愈', '贴心',
                            '理解', '共情', '时间自由', '灵活工作', '副业',
                            '在家工作', '兼职', '轻松赚钱', '暖心', '真诚',
                            '成长', '美好生活', '陪伴经济', '情感陪护'
                        ]
                    else:
                        # 非招聘类标签池（生活类）
                        tag_pool = [
                            '生活分享', '日常', '真实', '省钱攻略', '穷鬼快乐',
                            '大学生', '打工人', '搞笑', '沙雕', '整活',
                            '生活记录', 'vlog', '美食', '探店', '好物分享',
                            '生活方式', '自我成长', '精致穷', '小确幸'
                        ]
                    tags = random.sample(tag_pool, min(2, len(tag_pool)))  # 最多2个标签
                if not content:
                    content = titles_dict.get('body', '用心陪伴，温暖相伴')
            
            if not image_path:
                logger.info("[发布] 生成AI封面图片（约需15-20秒）...")
                # 使用LLM生成的标题和副标题
                image_path = await generate_png_cover(
                    main_title=titles_dict['main_title'],
                    subtitle=titles_dict['subtitle'],  # 招聘有数字，非招聘为空
                    tagline=titles_dict.get('tagline', '遇见更好的自己'),
                    emoji=random.choice(["💖", "💝", "✨", "🌸", "💫"]),
                    use_ai_bg=True  # 启用AI背景图生成
                )
            
            logger.info(f"[发布] 标题: {title}")
            logger.info(f"[发布] 标签: {', '.join(tags)}")
            
            # 创建浏览器API
            browser_api = FingerprintBrowserAPI(
                browser_type="bitbrowser",
                api_url=self.config.bitbrowser_api_url
            )
            
            # 创建上传器
            uploader = XHSImageUploader(
                title=title,
                image_path=image_path,
                tags=tags,
                content=content,
                publish_date=0,  # 立即发布
                profile_id=profile_id,
                browser_api=browser_api,
                theme=theme,
                max_retries=1  # 失败不重试
            )
            
            # 执行上传
            logger.info(f"[发布] 正在上传...")
            success = await uploader.main()
            
            if success:
                logger.info(f"[发布] ✅ 发布成功！")
                return {
                    "success": True,
                    "profile_id": profile_id,
                    "title": title,
                    "tags": tags,
                    "message": "发布成功"
                }
            else:
                logger.error(f"[发布] ❌ 发布失败")
                return {
                    "success": False,
                    "profile_id": profile_id,
                    "error": "发布失败"
                }
        
        except Exception as e:
            logger.error(f"[发布] 异常: {e}", exc_info=True)
            return {
                "success": False,
                "profile_id": profile_id,
                "error": str(e)
            }
    
    async def batch_publish(
        self,
        profile_ids: List[str] = None,
        theme: str = "情感陪伴类",
        count: int = 6,
        interval_minutes: tuple = (30, 50),
        auto_loop: bool = False
    ) -> Dict[str, Any]:
        """批量发布（多环境轮流）
        
        Args:
            profile_ids: 环境ID列表（默认使用配置的3个环境）
            theme: 主题类型
            count: 每日发布数量（默认6）
            interval_minutes: 间隔分钟范围（默认30-50）
            auto_loop: 是否自动循环（False=完成停止）
        
        Returns:
            {"success": bool, "published": int, "failed": int, "results": []}
        """
        try:
            from uploader.xhs_uploader.main import (
                XHSMultiAccountScheduler,
                FingerprintBrowserAPI
            )
            
            if not profile_ids:
                profile_ids = self.config.profile_ids
            
            if not profile_ids:
                return {
                    "success": False,
                    "error": "未配置比特浏览器环境，请先在比特浏览器中创建环境"
                }
            
            logger.info("=" * 60)
            logger.info("🚀 小红书批量发布任务启动")
            logger.info("=" * 60)
            logger.info(f"环境数量: {len(profile_ids)}")
            logger.info(f"主题: {theme}")
            logger.info(f"每日目标: {count} 个")
            logger.info(f"间隔: {interval_minutes[0]}-{interval_minutes[1]} 分钟（随机）")
            logger.info(f"自动循环: {'是' if auto_loop else '否'}")
            logger.info("=" * 60)
            
            # 创建调度器
            scheduler = XHSMultiAccountScheduler(
                profile_ids=profile_ids,
                browser_type="bitbrowser",
                api_url=self.config.bitbrowser_api_url,
                posts_per_day=count,
                interval_minutes=interval_minutes,
                random_delay_range=(0.1, 0.5)  # 测试模式：6-30秒随机延迟
            )
            
            # 创建发布队列
            post_queue = [{'theme': theme} for _ in range(count)]
            
            # 执行发布
            await scheduler.schedule_publish(post_queue, auto_loop=auto_loop)
            
            # 统计结果
            stats = scheduler.schedule_state
            published = stats.get('total_success', 0)
            failed = stats.get('total_fail', 0)
            
            logger.info("=" * 60)
            logger.info(f"✅ 批量发布完成！")
            logger.info(f"成功: {published}, 失败: {failed}")
            logger.info("=" * 60)
            
            return {
                "success": True,
                "published": published,
                "failed": failed,
                "profile_count": len(profile_ids),
                "stats": stats
            }
        
        except Exception as e:
            logger.error(f"[批量发布] 失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def stop_scheduler(self) -> Dict[str, Any]:
        """停止调度器"""
        try:
            from uploader.xhs_uploader.main import stop_xhs_scheduler
            result = stop_xhs_scheduler()
            logger.info("[控制] 已发送停止信号")
            return result
        except Exception as e:
            logger.error(f"[控制] 停止失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """获取发布状态"""
        try:
            from uploader.xhs_uploader.main import get_xhs_status
            status = get_xhs_status()
            return status
        except Exception as e:
            logger.error(f"[状态] 获取失败: {e}")
            return {"success": False, "error": str(e)}

# ==================== A2A入口函数 ====================

async def a2a_tool_xiaohongshu_auto_upload(query: str, **kwargs) -> str:
    """
    小红书自动发布智能体 A2A入口
    
    支持操作：
    1. publish_single: 发布单个帖子
       {"action":"publish_single","profile_id":"环境ID","theme":"情感陪伴类","title":"标题","tags":["标签"]}
    
    2. batch_publish: 批量发布（多环境轮流）
       {"action":"batch_publish","theme":"情感陪伴类","count":6,"interval_minutes":[30,50],"auto_loop":false}
    
    3. stop: 停止调度器
       {"action":"stop"}
    
    4. status: 查询状态
       {"action":"status"}
    
    5. list_environments: 列出比特浏览器环境
       {"action":"list_environments"}
    """
    try:
        # 解析参数
        if isinstance(query, str):
            try:
                params = json.loads(query)
            except:
                return json.dumps({"success": False, "error": "参数格式错误，需要JSON"}, ensure_ascii=False)
        else:
            params = query
        
        action = params.get("action", "batch_publish")
        manager = XHSPublishManager()
        
        # 执行操作
        if action == "publish_single":
            # 发布单个帖子
            result = await manager.publish_single(
                profile_id=params.get("profile_id"),
                theme=params.get("theme", "情感陪伴类"),
                title=params.get("title"),
                tags=params.get("tags"),
                content=params.get("content"),
                image_path=params.get("image_path")
            )
        
        elif action == "batch_publish":
            # 批量发布
            result = await manager.batch_publish(
                profile_ids=params.get("profile_ids"),
                theme=params.get("theme", "情感陪伴类"),
                count=params.get("count", 6),
                interval_minutes=tuple(params.get("interval_minutes", [30, 50])),
                auto_loop=params.get("auto_loop", False)
            )
        
        elif action == "stop":
            # 停止调度器
            result = manager.stop_scheduler()
        
        elif action == "status":
            # 查询状态
            result = manager.get_status()
        
        elif action == "list_environments":
            # 列出环境
            result = {
                "success": True,
                "environments": config.profile_ids,
                "count": len(config.profile_ids)
            }
        
        else:
            result = {"success": False, "error": f"未知操作: {action}"}
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        logger.error(f"智能体执行失败: {e}", exc_info=True)
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

# ==================== 工具元数据 ====================

TOOL_METADATA = {
    "name": "xiaohongshu_auto_upload",
    "description": "小红书自动发布智能体 - 比特浏览器多账号轮流发布",
    "version": "1.0",
    "features": [
        "自动生成招聘引流封面",
        "AI智能生成标题和标签",
        "比特浏览器多环境管理",
        "失败直接停止（不重试）",
        "完善的错误处理和日志"
    ],
    "parameters": {
        "query": {
            "type": "string",
            "description": "JSON格式的操作请求"
        }
    },
    "examples": [
        {
            "name": "批量发布（默认）",
            "query": {
                "action": "batch_publish",
                "theme": "情感陪伴类",
                "count": 6,
                "interval_minutes": [30, 50],
                "auto_loop": False
            }
        },
        {
            "name": "发布单个帖子",
            "query": {
                "action": "publish_single",
                "profile_id": "环境ID",
                "theme": "情感陪伴类"
            }
        },
        {
            "name": "停止调度器",
            "query": {"action": "stop"}
        },
        {
            "name": "查询状态",
            "query": {"action": "status"}
        },
        {
            "name": "列出环境",
            "query": {"action": "list_environments"}
        }
    ]
}

# ==================== 直接运行入口 ====================

if __name__ == "__main__":
    """直接运行 - 批量发布模式"""
    import os
    
    # Windows控制台UTF-8编码
    if os.name == 'nt':
        os.system('chcp 65001 >nul 2>&1')
    
    print("""
╔════════════════════════════════════════════════════════════════╗
║  小红书自动发布智能体 v1.0                                    ║
║  功能: 比特浏览器多账号轮流自动发布                          ║
║  特点: 失败直接停止 + 元素定位 + 完善日志                    ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    print("=" * 70)
    print("⚠️  运行前请确保：")
    print("=" * 70)
    print("1. ✅ 比特浏览器已启动")
    print("2. ✅ 已创建3个环境（名称包含xiaohongshu或xhs）")
    print("3. ✅ 每个环境已手动登录小红书一次")
    print("=" * 70 + "\n")
    
    # 默认批量发布
    async def main():
        manager = XHSPublishManager()
        
        # 检查环境
        if not config.profile_ids:
            print("❌ 错误: 未找到比特浏览器环境")
            print("💡 请在比特浏览器中创建环境，名称包含 'xiaohongshu' 或 'xhs'")
            return
        
        print(f"📋 找到 {len(config.profile_ids)} 个环境\n")
        
        # 开始批量发布
        result = await manager.batch_publish(
            theme="情感陪伴类",
            count=6,
            interval_minutes=(30, 50),
            auto_loop=False  # 完成后停止
        )
        
        if result.get("success"):
            print("\n✅ 批量发布完成！")
            print(f"   成功: {result.get('published', 0)}")
            print(f"   失败: {result.get('failed', 0)}")
        else:
            print(f"\n❌ 批量发布失败: {result.get('error')}")
    
    asyncio.run(main())

