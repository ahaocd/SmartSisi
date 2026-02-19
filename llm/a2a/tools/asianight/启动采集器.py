"""
ASIANIGHT启动脚本
完整流程：Telegram采集 → 内容决策 → 整理分类 → AI洗稿
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from telegram_collector import TelegramCollector
from content_decision import ContentDecisionMaker, ContentOrganizer
from config_loader import get_config
from openai import AsyncOpenAI
import logging

logger = logging.getLogger("AsianightLauncher")


class AsianightLauncher:
    """ASIANIGHT完整启动器"""
    
    def __init__(self):
        self.config = get_config()
        self.collector = None
        self.decider = None
        self.organizer = None
        self.rewriter = None
    
    async def init_all(self):
        """初始化所有组件"""
        print("\n" + "🌙"*30)
        print("  ASIANIGHT内容自动化系统")
        print("🌙"*30 + "\n")
        
        # 1. 初始化Telegram采集器
        print("📱 初始化Telegram采集器...")
        self.collector = TelegramCollector()
        
        # 连接并登录
        if not await self.collector.connect_and_login():
            raise Exception("Telegram登录失败")
        
        # 2. 初始化内容决策器
        print("\n🎯 初始化内容决策器...")
        try:
            self.decider = ContentDecisionMaker()
        except Exception as e:
            print(f"⚠️  决策器初始化失败: {e}")
            self.decider = None
        
        # 3. 初始化内容整理器
        print("\n📊 初始化内容整理器...")
        try:
            self.organizer = ContentOrganizer()
        except Exception as e:
            print(f"⚠️  整理器初始化失败: {e}")
            self.organizer = None
        
        # 4. 初始化洗稿模型
        print("\n✍️  初始化洗稿模型...")
        try:
            rewrite_config = self.config.get_rewrite_model_config()
            self.rewriter = AsyncOpenAI(
                api_key=rewrite_config['api_key'],
                base_url=rewrite_config['base_url']
            )
            self.rewrite_model = rewrite_config['model']
            self.rewrite_temperature = rewrite_config['temperature']
            self.rewrite_max_tokens = rewrite_config['max_tokens']
        except Exception as e:
            print(f"⚠️  洗稿模型初始化失败: {e}")
            self.rewriter = None
        
        print("\n✅ 所有组件初始化完成\n")
    
    def load_groups_from_file(self, file_path: str = "groups.txt") -> list:
        """从文件加载群组列表"""
        groups_file = Path(file_path)
        
        if not groups_file.exists():
            logger.warning(f"群组配置文件不存在: {file_path}")
            return []
        
        groups = []
        with open(groups_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if line and not line.startswith('#'):
                    groups.append(line)
        
        return groups
    
    async def run_collect_only(self, groups: list, limit: int = 100):
        """仅采集模式"""
        print("\n" + "="*60)
        print("📥 模式：仅采集Telegram内容")
        print("="*60 + "\n")
        
        results = await self.collector.collect_multiple_groups(
            groups=groups,
            limit=limit,
            media_types=['photo', 'video', 'document']
        )
        
        return results
    
    async def run_full_workflow(self, groups: list, limit: int = 100):
        """完整工作流：采集 → 决策 → 整理 → 洗稿"""
        print("\n" + "="*60)
        print("🤖 模式：完整自动化工作流")
        print("="*60 + "\n")
        
        # 步骤1: 采集
        print("【步骤1/4】Telegram采集...")
        collect_results = await self.collector.collect_multiple_groups(
            groups=groups,
            limit=limit,
            media_types=['photo', 'video']
        )
        
        # 统计采集结果
        all_messages = []
        for result in collect_results:
            if result['success']:
                all_messages.extend(result.get('messages', []))
        
        if not all_messages:
            print("❌ 未采集到消息，工作流结束")
            return
        
        print(f"\n✅ 采集到 {len(all_messages)} 条消息\n")
        
        # 步骤2: 内容决策
        if self.decider:
            print("【步骤2/4】内容决策（AI判断）...")
            
            contents = [
                {'text': msg['text'], 'type': 'message'}
                for msg in all_messages[:50]  # 最多50条
            ]
            
            decisions = await self.decider.batch_decide(contents)
            
            # 筛选值得处理的内容
            valuable_contents = [
                msg for msg, dec in zip(all_messages[:50], decisions)
                if dec['should_collect'] and dec['score'] > 0.6
            ]
            
            print(f"✅ 筛选出 {len(valuable_contents)}/{len(contents)} 条有价值内容\n")
        else:
            valuable_contents = all_messages[:20]
            print("⚠️  跳过决策，使用前20条消息\n")
        
        # 步骤3: 内容整理
        if self.organizer and valuable_contents:
            print("【步骤3/4】内容整理（生成表格）...")
            
            media_list = [
                {
                    'message_id': msg['message_id'],
                    'caption': msg['text'],
                    'date': msg['date']
                }
                for msg in valuable_contents
            ]
            
            organized = await self.organizer.organize_media_info(media_list)
            
            print(f"\n总结: {organized['summary']}\n")
            print("数据表格:")
            self.organizer.print_table(organized['table'])
            
            print("洞察:")
            for insight in organized['insights']:
                print(f"  • {insight}")
            print()
        else:
            organized = None
            print("⚠️  跳过整理\n")
        
        # 步骤4: AI洗稿
        if self.rewriter and organized and organized['table']:
            print("【步骤4/4】AI洗稿（生成文章）...")
            
            # 选择高优先级内容
            high_priority = [
                row for row in organized['table']
                if row.get('优先级') == '高'
            ][:3]
            
            if high_priority:
                # 生成文章
                source_text = "\n".join([
                    f"• {row.get('主题', row.get('类型', ''))}"
                    for row in high_priority
                ])
                
                prompt = f"""基于以下信息创作一篇娱乐行业招聘文章：

{source_text}

要求：
1. 800-1000字
2. 原创改写
3. 突出行业特点和招聘优势
4. 包含标题、正文、总结"""
                
                response = await self.rewriter.chat.completions.create(
                    model=self.rewrite_model,
                    messages=[
                        {"role": "system", "content": "你是专业的内容创作者。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.rewrite_temperature,
                    max_tokens=self.rewrite_max_tokens
                )
                
                article = response.choices[0].message.content
                
                # 保存文章
                from datetime import datetime
                article_file = Path(f"asianight_data/articles/article_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
                article_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(article_file, 'w', encoding='utf-8') as f:
                    f.write(article)
                
                print(f"✅ 文章已生成: {article_file}\n")
                print("="*60)
                print(article[:500] + "...")
                print("="*60 + "\n")
            else:
                print("⚠️  无高优先级内容，跳过洗稿\n")
        else:
            print("⚠️  跳过洗稿\n")
        
        print("\n" + "="*60)
        print("✅ 完整工作流执行完成")
        print("="*60 + "\n")
    
    async def interactive_menu(self):
        """交互式菜单"""
        while True:
            print("\n" + "="*60)
            print("请选择操作模式：")
            print("="*60)
            print("  1. 仅采集Telegram内容")
            print("  2. 完整工作流（采集+决策+整理+洗稿）")
            print("  3. 从文件加载群组列表 (groups.txt)")
            print("  4. 手动输入群组")
            print("  0. 退出")
            print("="*60)
            
            choice = input("\n请选择 [0-4]: ").strip()
            
            if choice == '0':
                print("\n👋 再见！")
                break
            
            # 获取群组列表
            if choice == '3':
                groups = self.load_groups_from_file()
                if not groups:
                    print("❌ groups.txt为空或不存在")
                    continue
                print(f"\n✅ 加载了 {len(groups)} 个群组:")
                for g in groups:
                    print(f"  • {g}")
            elif choice in ['1', '2', '4']:
                groups_input = input("\n请输入群组名称（逗号分隔）: ").strip()
                if not groups_input:
                    print("❌ 未输入群组")
                    continue
                groups = [g.strip() for g in groups_input.split(',')]
            else:
                print("❌ 无效选项")
                continue
            
            # 获取采集数量
            limit_input = input(f"每个群组采集数量 [默认100]: ").strip()
            limit = int(limit_input) if limit_input.isdigit() else 100
            
            # 执行
            try:
                if choice in ['1', '3', '4']:
                    await self.run_collect_only(groups, limit)
                elif choice == '2':
                    await self.run_full_workflow(groups, limit)
            except Exception as e:
                print(f"❌ 执行失败: {e}")
                import traceback
                traceback.print_exc()
    
    async def close(self):
        """关闭所有连接"""
        if self.collector:
            await self.collector.close()


async def main():
    """主函数"""
    launcher = AsianightLauncher()
    
    try:
        # 初始化
        await launcher.init_all()
        
        # 显示配置
        launcher.config.print_config_summary()
        
        # 进入交互菜单
        await launcher.interactive_menu()
        
    except KeyboardInterrupt:
        print("\n\n👋 用户取消")
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await launcher.close()


if __name__ == '__main__':
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║        🌙 ASIANIGHT 内容自动化系统 🌙                      ║
║                                                            ║
║  SmartSisi子系统 - 娱乐行业内容采集与处理                  ║
║                                                            ║
║  配置位置：E:\\liusisi\\SmartSisi\\system.conf              ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
""")
    
    input("\n按回车键开始...\n")
    
    asyncio.run(main())



