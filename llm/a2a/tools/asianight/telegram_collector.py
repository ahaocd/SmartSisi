"""
Telegram完整采集器
- Session管理（首次登录后保存）
- 数据库去重（不重复采集）
- 符合官方规则（速率限制）
- 自动重连
- 去水印
"""

import os
import sys
import asyncio
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

try:
    from telethon import TelegramClient, events
    from telethon.errors import (
        SessionPasswordNeededError,
        FloodWaitError,
        ChatAdminRequiredError,
        ChannelPrivateError
    )
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False

try:
    import cv2
    import numpy as np
    from PIL import Image
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from config_loader import get_config

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TelegramCollector")


class CollectorDatabase:
    """采集数据库 - 记录已采集消息，避免重复"""
    
    def __init__(self, db_path: str = "asianight_data/collector.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 已采集消息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collected_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                media_type TEXT,
                caption TEXT,
                file_path TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(group_name, message_id)
            )
        """)
        
        # 群组配置表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT UNIQUE NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_collect_time TIMESTAMP,
                last_message_id INTEGER DEFAULT 0,
                total_collected INTEGER DEFAULT 0
            )
        """)
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ 数据库初始化完成: {self.db_path}")
    
    def is_collected(self, group_name: str, message_id: int) -> bool:
        """检查消息是否已采集"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id FROM collected_messages WHERE group_name=? AND message_id=?",
            (group_name, message_id)
        )
        
        exists = cursor.fetchone() is not None
        conn.close()
        
        return exists
    
    def mark_collected(
        self,
        group_name: str,
        message_id: int,
        media_type: str = None,
        caption: str = None,
        file_path: str = None
    ):
        """标记消息已采集"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO collected_messages 
                (group_name, message_id, media_type, caption, file_path)
                VALUES (?, ?, ?, ?, ?)
            """, (group_name, message_id, media_type, caption, file_path))
            
            conn.commit()
        except Exception as e:
            logger.error(f"标记失败: {e}")
        finally:
            conn.close()
    
    def update_group_stats(self, group_name: str, last_message_id: int):
        """更新群组统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO group_config (group_name, last_collect_time, last_message_id, total_collected)
            VALUES (?, CURRENT_TIMESTAMP, ?, 1)
            ON CONFLICT(group_name) DO UPDATE SET
                last_collect_time=CURRENT_TIMESTAMP,
                last_message_id=?,
                total_collected=total_collected+1
        """, (group_name, last_message_id, last_message_id))
        
        conn.commit()
        conn.close()
    
    def get_group_stats(self, group_name: str) -> Dict[str, Any]:
        """获取群组统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT last_collect_time, last_message_id, total_collected
            FROM group_config WHERE group_name=?
        """, (group_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'last_collect_time': row[0],
                'last_message_id': row[1],
                'total_collected': row[2]
            }
        return {
            'last_collect_time': None,
            'last_message_id': 0,
            'total_collected': 0
        }


class WatermarkRemover:
    """去水印处理器"""
    
    def __init__(self):
        self.enabled = CV2_AVAILABLE
        if not self.enabled:
            logger.warning("OpenCV未安装，去水印功能禁用")
    
    def remove_watermark(self, image_path: str, output_path: str) -> bool:
        """去除图片水印"""
        if not self.enabled:
            return False
        
        try:
            img = cv2.imread(image_path)
            if img is None:
                return False
            
            h, w = img.shape[:2]
            
            # 常见水印位置
            watermark_regions = [
                (w-250, h-100, 250, 100),  # 右下角
                (w-250, 0, 250, 100),      # 右上角
                (0, h-100, 250, 100),      # 左下角
                (0, 0, 250, 100),          # 左上角
            ]
            
            for x, y, rw, rh in watermark_regions:
                # 创建mask
                mask = np.zeros(img.shape[:2], dtype=np.uint8)
                mask[y:y+rh, x:x+rw] = 255
                
                # Inpainting去水印
                img = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
            
            cv2.imwrite(output_path, img)
            logger.info(f"✅ 去水印完成: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 去水印失败: {e}")
            return False


class TelegramCollector:
    """Telegram完整采集器"""
    
    def __init__(self):
        if not TELETHON_AVAILABLE:
            raise ImportError("请安装 telethon: pip install telethon")
        
        # 加载配置
        self.config = get_config()
        telegram_config = self.config.get_telegram_config()
        
        self.api_id = telegram_config['api_id']
        self.api_hash = telegram_config['api_hash']
        self.phone = telegram_config['phone']
        
        if not self.api_id or not self.api_hash or not self.phone:
            raise ValueError("Telegram配置未完成，请在system.conf中填写asianight_telegram_*配置")
        
        # Session文件路径
        self.session_dir = Path("asianight_data/sessions")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / "telegram_session"
        
        # 初始化客户端
        self.client = TelegramClient(
            str(self.session_file),
            int(self.api_id),
            self.api_hash
        )
        
        # 数据库
        self.db = CollectorDatabase()
        
        # 去水印
        self.watermark_remover = WatermarkRemover()
        
        # 输出目录
        self.output_dir = Path("asianight_data/telegram_media")
        self.raw_dir = self.output_dir / "raw"
        self.clean_dir = self.output_dir / "cleaned"
        
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.clean_dir.mkdir(parents=True, exist_ok=True)
        
        # 速率控制
        self.request_count = 0
        self.last_request_time = time.time()
        
        logger.info("✅ Telegram采集器初始化完成")
    
    async def connect_and_login(self) -> bool:
        """
        连接并登录Telegram
        首次登录会引导输入验证码，之后使用保存的session
        """
        try:
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.info("\n" + "="*60)
                logger.info("🔐 首次登录Telegram")
                logger.info("="*60)
                
                # 发送验证码
                logger.info(f"📱 向 {self.phone} 发送验证码...")
                await self.client.send_code_request(self.phone)
                
                # 输入验证码
                code = input("\n请输入验证码: ").strip()
                
                try:
                    await self.client.sign_in(self.phone, code)
                except SessionPasswordNeededError:
                    # 需要两步验证密码
                    password = input("请输入两步验证密码: ").strip()
                    await self.client.sign_in(password=password)
                
                logger.info("✅ 登录成功！Session已保存")
                logger.info(f"   Session文件: {self.session_file}")
                logger.info("   下次启动将自动登录\n")
            else:
                logger.info(f"✅ 使用已保存的Session登录成功")
            
            # 获取用户信息
            me = await self.client.get_me()
            logger.info(f"👤 当前账号: {me.first_name} (@{me.username})")
            logger.info(f"📱 手机号: {me.phone}\n")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 登录失败: {e}")
            return False
    
    async def _rate_limit_check(self):
        """速率限制检查 - 符合Telegram官方规则"""
        self.request_count += 1
        current_time = time.time()
        
        # 每30个请求休息5秒
        if self.request_count % 30 == 0:
            logger.info("⏳ 速率控制：休息5秒...")
            await asyncio.sleep(5)
        
        # 每个请求至少间隔0.5秒
        time_since_last = current_time - self.last_request_time
        if time_since_last < 0.5:
            await asyncio.sleep(0.5 - time_since_last)
        
        self.last_request_time = time.time()
    
    async def collect_group(
        self,
        group_name: str,
        limit: int = 100,
        media_types: List[str] = ['photo', 'video']
    ) -> Dict[str, Any]:
        """
        采集群组内容
        
        Args:
            group_name: 群组名
            limit: 采集数量
            media_types: 媒体类型
        
        Returns:
            采集结果
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"📥 采集群组: {group_name}")
        logger.info(f"{'='*60}")
        
        result = {
            'success': False,
            'group': group_name,
            'photos': [],
            'videos': [],
            'documents': [],
            'messages': [],
            'skipped': 0,
            'new': 0
        }
        
        try:
            # 获取群组统计
            stats = self.db.get_group_stats(group_name)
            last_message_id = stats['last_message_id']
            
            logger.info(f"📊 群组统计:")
            logger.info(f"   上次采集: {stats['last_collect_time'] or '首次'}")
            logger.info(f"   已采集: {stats['total_collected']} 条")
            logger.info(f"   上次消息ID: {last_message_id}")
            
            # 获取消息
            logger.info(f"\n📥 开始获取消息（限制{limit}条）...")
            messages = await self.client.get_messages(group_name, limit=limit)
            logger.info(f"✅ 获取到 {len(messages)} 条消息\n")
            
            for i, msg in enumerate(messages):
                # 速率控制
                await self._rate_limit_check()
                
                # 检查是否已采集
                if self.db.is_collected(group_name, msg.id):
                    result['skipped'] += 1
                    continue
                
                # 采集图片
                if 'photo' in media_types and msg.photo:
                    logger.info(f"📷 [{i+1}/{len(messages)}] 处理图片: {msg.id}")
                    
                    # 下载原图
                    raw_filename = f"photo_{group_name}_{msg.id}.jpg"
                    raw_path = self.raw_dir / raw_filename
                    
                    downloaded = await self.client.download_media(
                        msg.photo,
                        file=str(raw_path)
                    )
                    
                    if downloaded:
                        # 去水印
                        clean_filename = f"photo_{group_name}_{msg.id}_clean.jpg"
                        clean_path = self.clean_dir / clean_filename
                        
                        self.watermark_remover.remove_watermark(
                            str(raw_path),
                            str(clean_path)
                        )
                        
                        result['photos'].append({
                            'message_id': msg.id,
                            'date': msg.date.isoformat(),
                            'raw_path': str(raw_path),
                            'clean_path': str(clean_path) if clean_path.exists() else None,
                            'caption': msg.text or ''
                        })
                        
                        # 标记已采集
                        self.db.mark_collected(
                            group_name,
                            msg.id,
                            'photo',
                            msg.text,
                            str(clean_path) if clean_path.exists() else str(raw_path)
                        )
                        
                        result['new'] += 1
                
                # 采集视频
                if 'video' in media_types and msg.video:
                    logger.info(f"🎬 [{i+1}/{len(messages)}] 处理视频: {msg.id}")
                    
                    video_filename = f"video_{group_name}_{msg.id}.mp4"
                    video_path = self.raw_dir / video_filename
                    
                    downloaded = await self.client.download_media(
                        msg.video,
                        file=str(video_path)
                    )
                    
                    if downloaded:
                        result['videos'].append({
                            'message_id': msg.id,
                            'date': msg.date.isoformat(),
                            'path': str(video_path),
                            'caption': msg.text or ''
                        })
                        
                        self.db.mark_collected(
                            group_name,
                            msg.id,
                            'video',
                            msg.text,
                            str(video_path)
                        )
                        
                        result['new'] += 1
                
                # 采集文档
                if 'document' in media_types and msg.document:
                    logger.info(f"📄 [{i+1}/{len(messages)}] 处理文档: {msg.file.name}")
                    
                    doc_filename = f"doc_{group_name}_{msg.id}_{msg.file.name}"
                    doc_path = self.raw_dir / doc_filename
                    
                    downloaded = await self.client.download_media(
                        msg.document,
                        file=str(doc_path)
                    )
                    
                    if downloaded:
                        result['documents'].append({
                            'message_id': msg.id,
                            'date': msg.date.isoformat(),
                            'path': str(doc_path),
                            'filename': msg.file.name
                        })
                        
                        self.db.mark_collected(
                            group_name,
                            msg.id,
                            'document',
                            msg.file.name,
                            str(doc_path)
                        )
                        
                        result['new'] += 1
                
                # 采集文字
                if msg.text:
                    result['messages'].append({
                        'message_id': msg.id,
                        'date': msg.date.isoformat(),
                        'text': msg.text
                    })
            
            # 更新群组统计
            if messages:
                latest_id = max(msg.id for msg in messages)
                self.db.update_group_stats(group_name, latest_id)
            
            result['success'] = True
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ 采集完成！")
            logger.info(f"{'='*60}")
            logger.info(f"   新采集: {result['new']} 条")
            logger.info(f"   跳过（已采集）: {result['skipped']} 条")
            logger.info(f"   图片: {len(result['photos'])} 张")
            logger.info(f"   视频: {len(result['videos'])} 个")
            logger.info(f"   文档: {len(result['documents'])} 个")
            logger.info(f"   消息: {len(result['messages'])} 条\n")
            
        except FloodWaitError as e:
            logger.error(f"❌ 被限速，需要等待 {e.seconds} 秒")
            result['error'] = f"FloodWait: {e.seconds}s"
            result['wait_seconds'] = e.seconds
            
        except ChannelPrivateError:
            logger.error(f"❌ 群组私有或未加入: {group_name}")
            result['error'] = "ChannelPrivate"
            
        except Exception as e:
            logger.error(f"❌ 采集失败: {e}")
            result['error'] = str(e)
        
        return result
    
    async def collect_multiple_groups(
        self,
        groups: List[str],
        limit: int = 100,
        media_types: List[str] = ['photo', 'video']
    ) -> List[Dict[str, Any]]:
        """批量采集多个群组"""
        logger.info(f"\n{'🌙'*30}")
        logger.info(f"  批量采集 {len(groups)} 个群组")
        logger.info(f"{'🌙'*30}\n")
        
        results = []
        
        for i, group in enumerate(groups):
            logger.info(f"\n进度: [{i+1}/{len(groups)}]")
            
            result = await self.collect_group(group, limit, media_types)
            results.append(result)
            
            # 群组间休息
            if i < len(groups) - 1:
                logger.info("⏳ 群组间休息10秒...\n")
                await asyncio.sleep(10)
        
        # 总结
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 批量采集总结")
        logger.info(f"{'='*60}")
        
        total_new = sum(r.get('new', 0) for r in results)
        total_skipped = sum(r.get('skipped', 0) for r in results)
        
        logger.info(f"   群组数: {len(groups)}")
        logger.info(f"   新采集: {total_new} 条")
        logger.info(f"   跳过: {total_skipped} 条")
        logger.info(f"   成功: {sum(1 for r in results if r['success'])}/{len(groups)}")
        logger.info("")
        
        return results
    
    async def close(self):
        """关闭连接"""
        if self.client.is_connected():
            await self.client.disconnect()
            logger.info("✅ 连接已关闭")


async def main():
    """主函数"""
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║        📱 Telegram完整采集器 📱                             ║
║                                                            ║
║  功能：                                                     ║
║    ✅ Session管理（首次登录后保存）                         ║
║    ✅ 数据库去重（不重复采集）                              ║
║    ✅ 符合官方规则（速率限制）                              ║
║    ✅ 自动去水印                                            ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
""")
    
    collector = TelegramCollector()
    
    try:
        # 连接并登录
        if not await collector.connect_and_login():
            print("❌ 登录失败，退出")
            return
        
        # 示例：采集单个群组
        print("\n" + "="*60)
        print("请输入要采集的群组名称（用逗号分隔多个）:")
        print("例如：python,javascript,数字游民Newbe")
        print("="*60)
        
        groups_input = input("\n群组名称: ").strip()
        
        if not groups_input:
            print("❌ 未输入群组名称")
            return
        
        groups = [g.strip() for g in groups_input.split(',')]
        
        # 开始采集
        results = await collector.collect_multiple_groups(
            groups=groups,
            limit=100,
            media_types=['photo', 'video', 'document']
        )
        
        # 显示结果
        print(f"\n✅ 采集完成！数据保存在: asianight_data/telegram_media/")
        
    except KeyboardInterrupt:
        print("\n\n👋 用户取消")
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await collector.close()


if __name__ == '__main__':
    asyncio.run(main())



