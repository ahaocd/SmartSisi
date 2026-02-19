"""
清理工具 - 自动清理media_marketing文件夹的临时文件

功能：
1. 清理Chrome缓存（chrome_data/）
2. 清理旧日志文件（超过30天）
3. 清理Python缓存
4. 保留关键数据（数据库、Cookie）
"""

import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging
from utils import util

logger = logging.getLogger("CleanupUtils")


class MediaMarketingCleaner:
    """媒体营销文件夹清理器"""
    
    def __init__(self, base_dir: Path = None):
        """初始化清理器
        
        Args:
            base_dir: media_marketing文件夹路径
        """
        if base_dir is None:
            base_dir = Path(__file__).parent
        
        self.base_dir = base_dir
        self.chrome_data_dir = base_dir / "chrome_data"
        self.logs_dir = Path(util.ensure_log_dir("tools", "media_marketing"))
        self.pycache_dir = base_dir / "__pycache__"
        
        # 不能删除的关键文件/文件夹
        self.protected_items = [
            "douyin_marketing.db",
            "cookies",
            "ai_engine.py",
            "prompts.py",
            "test_ai_prompts.py",
            "目标主播配置.json",
            "足浴运营主播.txt",
            "球房运营主播.txt",
            "技术实现说明.md",
            "cleanup_utils.py"
        ]
    
    def clean_chrome_data(self, keep_days: int = 0):
        """清理Chrome缓存数据
        
        Args:
            keep_days: 保留最近N天的数据，0表示全部删除
        """
        if not self.chrome_data_dir.exists():
            logger.info("   ✅ chrome_data不存在，跳过")
            return
        
        try:
            # 计算清理前大小
            before_size = sum(f.stat().st_size for f in self.chrome_data_dir.rglob('*') if f.is_file())
            before_mb = before_size / (1024 * 1024)
            
            if keep_days == 0:
                # 全部删除
                shutil.rmtree(self.chrome_data_dir)
                self.chrome_data_dir.mkdir(exist_ok=True)
                logger.info(f"   ✅ 清理chrome_data: {before_mb:.2f}MB → 0MB")
            else:
                # 只删除旧文件
                cutoff_time = datetime.now() - timedelta(days=keep_days)
                deleted_count = 0
                
                for item in self.chrome_data_dir.rglob('*'):
                    if item.is_file():
                        mtime = datetime.fromtimestamp(item.stat().st_mtime)
                        if mtime < cutoff_time:
                            item.unlink()
                            deleted_count += 1
                
                after_size = sum(f.stat().st_size for f in self.chrome_data_dir.rglob('*') if f.is_file())
                after_mb = after_size / (1024 * 1024)
                logger.info(f"   ✅ 清理chrome_data旧文件: {before_mb:.2f}MB → {after_mb:.2f}MB (删除{deleted_count}个)")
        
        except Exception as e:
            logger.error(f"   ❌ 清理chrome_data失败: {e}")
    
    def clean_old_logs(self, keep_days: int = 30):
        """清理旧日志文件
        
        Args:
            keep_days: 保留最近N天的日志
        """
        if not self.logs_dir.exists():
            logger.info("   ✅ logs目录不存在，跳过")
            return
        
        try:
            cutoff_time = datetime.now() - timedelta(days=keep_days)
            deleted_count = 0
            deleted_size = 0
            
            for log_file in self.logs_dir.glob('*.log'):
                # 跳过README
                if log_file.name.lower() == 'readme.txt':
                    continue
                
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff_time:
                    file_size = log_file.stat().st_size
                    log_file.unlink()
                    deleted_count += 1
                    deleted_size += file_size
            
            if deleted_count > 0:
                logger.info(f"   ✅ 清理旧日志: 删除{deleted_count}个文件，释放{deleted_size/(1024*1024):.2f}MB")
            else:
                logger.info(f"   ✅ 无需清理日志（最近{keep_days}天内）")
        
        except Exception as e:
            logger.error(f"   ❌ 清理日志失败: {e}")
    
    def clean_pycache(self):
        """清理Python缓存"""
        if not self.pycache_dir.exists():
            logger.info("   ✅ __pycache__不存在，跳过")
            return
        
        try:
            shutil.rmtree(self.pycache_dir)
            logger.info("   ✅ 清理__pycache__完成")
        except Exception as e:
            logger.error(f"   ❌ 清理__pycache__失败: {e}")
    
    def clean_temp_screenshots(self):
        """清理临时截图文件"""
        try:
            deleted_count = 0
            deleted_size = 0
            
            # 在base_dir和上级目录查找临时截图
            for pattern in ['*screenshot*.png', '*ocr*.png', '*temp*.png']:
                for img_file in self.base_dir.glob(pattern):
                    file_size = img_file.stat().st_size
                    img_file.unlink()
                    deleted_count += 1
                    deleted_size += file_size
                
                # 也检查上级目录（根目录）
                parent_dir = self.base_dir.parent.parent.parent.parent
                for img_file in parent_dir.glob(pattern):
                    if 'SmartSisi' not in str(img_file):
                        file_size = img_file.stat().st_size
                        img_file.unlink()
                        deleted_count += 1
                        deleted_size += file_size
            
            if deleted_count > 0:
                logger.info(f"   ✅ 清理临时截图: 删除{deleted_count}个，释放{deleted_size/(1024*1024):.2f}MB")
            else:
                logger.info("   ✅ 无临时截图需要清理")
        
        except Exception as e:
            logger.error(f"   ❌ 清理临时截图失败: {e}")
    
    def run_full_cleanup(self, chrome_keep_days: int = 0, log_keep_days: int = 30):
        """执行完整清理
        
        Args:
            chrome_keep_days: Chrome缓存保留天数（0=全删）
            log_keep_days: 日志保留天数
        """
        logger.info("🧹 开始清理media_marketing文件夹...")
        
        # 1. 清理Chrome缓存
        self.clean_chrome_data(keep_days=chrome_keep_days)
        
        # 2. 清理旧日志
        self.clean_old_logs(keep_days=log_keep_days)
        
        # 3. 清理Python缓存
        self.clean_pycache()
        
        # 4. 清理临时截图
        self.clean_temp_screenshots()
        
        logger.info("✅ 清理完成！")
    
    def get_folder_sizes(self) -> dict:
        """获取各文件夹大小（MB）"""
        sizes = {}
        
        for item in self.base_dir.iterdir():
            if item.is_dir():
                total_size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                sizes[item.name] = round(total_size / (1024 * 1024), 2)
        
        return sizes


# ==================== 命令行工具 ====================
if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    
    parser = argparse.ArgumentParser(description="清理media_marketing文件夹")
    parser.add_argument("--chrome-days", type=int, default=0, help="Chrome缓存保留天数（0=全删）")
    parser.add_argument("--log-days", type=int, default=30, help="日志保留天数")
    parser.add_argument("--check-only", action="store_true", help="仅检查大小，不清理")
    
    args = parser.parse_args()
    
    cleaner = MediaMarketingCleaner()
    
    if args.check_only:
        print("\n📊 当前文件夹大小：")
        sizes = cleaner.get_folder_sizes()
        for folder, size_mb in sorted(sizes.items(), key=lambda x: x[1], reverse=True):
            print(f"   {folder:20s} {size_mb:8.2f} MB")
    else:
        cleaner.run_full_cleanup(
            chrome_keep_days=args.chrome_days,
            log_keep_days=args.log_days
        )









