"""
AI 分析引擎

包含所有AI相关的分析功能
- 生成评论
- 初步筛选用户
- 深度多模态分析（头像+封面+文本）
"""

import json
import asyncio
import random
from typing import Dict, List

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except:
    OPENAI_AVAILABLE = False

# Logger
import logging
logger = logging.getLogger(__name__)

# 导入提示词（稍后会用）
# from .prompts import FALLBACK_COMMENTS


# ==================== AI分析引擎 ====================
class AIAnalysisEngine:
    """AI分析引擎 - 多模态分层分析"""
    
    def __init__(self, config: Dict = None):
        if not OPENAI_AVAILABLE:
            raise Exception("需要安装openai: pip install openai")
        
        # 初始化变量
        text_api_key = None
        text_base_url = None
        vision_api_key = None
        vision_base_url = None
        
        # 从配置文件读取（如果config为None，使用system.conf）
        if config is None:
            # 导入配置工具
            import sys
            from pathlib import Path
            
            # 方法1：尝试相对导入（如果是包内调用）
            try:
                from SmartSisi.utils import config_util as cfg
                cfg.load_config()
                logger.info(f"✅ 使用包导入加载system.conf")
            except ImportError:
                # 方法2：添加项目根路径到sys.path（直接运行脚本）
                # 路径: ai_engine.py -> media_marketing -> tools -> a2a -> llm -> SmartSisi -> liusisi
                try:
                    project_root = Path(__file__).parent.parent.parent.parent.parent.parent
                    if str(project_root) not in sys.path:
                        sys.path.insert(0, str(project_root))
                    from SmartSisi.utils import config_util as cfg
                    cfg.load_config()
                    logger.info(f"✅ 使用绝对路径导入加载system.conf (项目根路径: {project_root})")
                except ImportError as e:
                    raise Exception(f"❌ 无法加载config_util，请检查路径！错误: {e}")
            
            # 从system.conf读取配置
            text_api_key = cfg.douyin_marketing_text_api_key
            text_base_url = cfg.douyin_marketing_text_base_url
            self.text_model = cfg.douyin_marketing_text_model
            vision_api_key = cfg.douyin_marketing_vision_api_key
            vision_base_url = cfg.douyin_marketing_vision_base_url
            self.vision_model = cfg.douyin_marketing_vision_model
            
            logger.info(f"✅ 配置加载成功")
            logger.info(f"   文本模型: {self.text_model}")
            logger.info(f"   视觉模型: {self.vision_model}")
        else:
            # 使用传入的config
            text_api_key = config.get('api_key', '')
            text_base_url = config.get('base_url', 'https://api.siliconflow.cn/v1')
            self.text_model = config.get('text_model', 'moonshotai/Kimi-K2-Instruct-0905')
            vision_api_key = config.get('vision_api_key', text_api_key)
            vision_base_url = config.get('vision_base_url', text_base_url)
            self.vision_model = config.get('vision_model', 'Pro/Qwen/Qwen2-VL-72B-Instruct')
        
        # 创建OpenAI客户端（文本和视觉使用相同的客户端）
        # 🔥 禁用代理，避免proxy配置错误导致连接失败
        import httpx
        http_client = httpx.AsyncClient(proxies=None)
        self.client = AsyncOpenAI(api_key=text_api_key, base_url=text_base_url, http_client=http_client)
        
        logger.info(f"AI引擎初始化完成:")
        logger.info(f"  - 文本模型: {self.text_model}")
        logger.info(f"  - 视觉模型: {self.vision_model}")
        logger.info(f"  - API Base: {text_base_url}")
    
    async def generate_comment(self, video_info: Dict, my_name: str = "亚洲之夜", video_comments: List[Dict] = None, broadcaster_info: Dict = None, is_reply: bool = False, target_comment: Dict = None) -> str:
        """生成软引流评论 - 传递完整上下文
        
        Args:
            video_info: 视频信息
            my_name: 我的昵称
            video_comments: 评论区评论列表（用于参考语境）
            broadcaster_info: 主播信息
            is_reply: 是否是回复别人的评论（新增参数）
            target_comment: 要回复的目标评论（新增参数）
        """
        
        # ========== 场景1：回复别人的评论 ==========
        if is_reply and target_comment:
            comment_text = target_comment.get('comment_text', target_comment.get('comment', target_comment.get('text', '')))
            
            context = f"""视频标题：{video_info.get('title', '未知标题')}

要回复的评论：
- 评论者昵称：{target_comment.get('nickname', '未知')}
- 评论内容：{comment_text}
- 评论者签名：{target_comment.get('signature', '无')}"""
            
            # ========== 智能匹配预设模板 ==========
            preset_templates = []
            try:
                from .reply_templates import match_reply_template
                preset_templates = match_reply_template(comment_text, context={
                    'video_title': video_info.get('title', ''),
                    'broadcaster_info': broadcaster_info
                })
                logger.info(f"   📋 匹配到 {len(preset_templates)} 个预设回复模板")
            except Exception as e:
                logger.warning(f"   ⚠️  模板匹配失败: {e}，使用默认模式")
            
            # 从prompts导入回复提示词
            try:
                from .prompts import get_reply_generation_prompt
                prompt = get_reply_generation_prompt(context, preset_templates=preset_templates)
            except:
                # 如果导入失败，使用内联提示词（简化版）
                prompt = f"""你要回复一条抖音评论：

{context}

我的身份：
- 行业：娱乐场所人力资源服务商（足浴/KTV/按摩等）
- 回复口吻：行业老手、管理者、从业人员

回复风格要求：
1. **针对性强** - 直接针对对方说的内容回复，不要答非所问
2. **简短精悍** - 8-20字最佳（不要太长！）
3. **自然隐晦** - 行业内部话术
4. **表达角度**：
   - 资源对接："可以安排" / "有渠道"
   - 试探需求："要不要xxx" / "店里需要不"
   - 强调质量："质量保证" / "素质高的"
5. **表情**：偶尔用一个（👍💪🤝😄等），不用也行

生成一条回复（只输出回复文本，不要带@昵称）："""
        
        # ========== 场景2：发表对视频的评论 ==========
        else:
            # 构建丰富的上下文信息
            context = f"""视频标题：{video_info.get('title', '未知标题')}
视频描述：{video_info.get('description', '无描述')}"""
            
            # 添加主播信息
            if broadcaster_info:
                context += f"\n主播昵称：{broadcaster_info.get('nickname', '未知')}"
                context += f"\n主播行业：{broadcaster_info.get('industry', '足浴/按摩/健康行业')}"
            
            # 添加评论区上下文（前5条）
            if video_comments and len(video_comments) > 0:
                context += "\n\n评论区热评（参考语境）："
                for i, comment in enumerate(video_comments[:5], 1):
                    comment_text = comment.get('comment', comment.get('text', ''))
                    if comment_text:
                        context += f"\n{i}. {comment_text}"
            
            # 从prompts导入
            try:
                from .prompts import get_comment_generation_prompt
                prompt = get_comment_generation_prompt(context)
            except:
                # 如果导入失败，使用内联提示词
                prompt = f"""根据视频内容生成一条抖音评论：

{context}

我的身份：
- 行业：娱乐场所人力资源服务商（足浴/KTV/按摩等）
- 评论口吻：行业老手、管理者、从业人员

评论风格要求：
1. **口语化、随意** - 像日常聊天，不要模板化
2. **短小精悍** - 8-18字最佳
3. **表达角度**：
   - 轻描淡写：问题不大、差不多、还好、正常
   - 过来人语气：有办法、可以解决、不麻烦
   - 主动分享：可以分享下思路、有方案、我这边可以调人
   - 管理视角：费劲、不容易、看情况、要看怎么做
4. **表情**：偶尔用一个（👍💪🤝😄等），不用也行
5. **不要用**："我们之前也"、"后来解决了"（太假）

示例评论（根据场景选一个思路）：
- 招聘话题 → "问题不大"、"可以调人"、"有渠道"、"差不多吧"
- 员工管理 → "看怎么管"、"有办法"、"不麻烦"、"费点劲"
- 培训话题 → "培训就好了"、"不难"、"有方案"
- 流失问题 → "正常的"、"可以控制"、"还好"
- 其他话题 → "有思路"、"分享下经验"、"我这边也做这个"

生成一条评论（只输出评论文本）："""
        
        # 重试机制：最多3次
        for attempt in range(3):
            try:
                resp = await self.client.chat.completions.create(
                    model=self.text_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=100
                )
                
                comment = resp.choices[0].message.content.strip()
                
                # 移除可能的引号
                comment = comment.strip('"\'""''')
                
                # 验证长度
                if 10 <= len(comment) <= 50:
                    return comment
                else:
                    logger.warning(f"生成的评论长度不合适: {len(comment)}字，重试...")
                    continue
                    
            except Exception as e:
                logger.error(f"生成评论失败 (尝试{attempt+1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue
        
        # 所有重试都失败后，返回智能回退（更随意、更像行业人士）
        logger.warning("AI生成失败，使用备选评论库")
        fallback_comments = [
            "问题不大",
            "差不多吧",
            "还好",
            "有办法",
            "可以调人",
            "有方案👍",
            "费点劲",
            "看情况",
            "正常的",
            "不麻烦",
            "有思路",
            "可以分享下经验",
        ]
        return random.choice(fallback_comments)
    
    async def should_visit_profile(self, user: Dict, context: Dict = None) -> Dict:
        """AI判断：是否需要打开这个用户的主页进行深度分析（宽松筛选+上下文语义分析）"""
        try:
            # 提取上下文信息
            account_name = ""
            account_industry = ""
            video_title = ""
            
            if context:
                account = context.get('account', {})
                video = context.get('video', {})
                account_name = account.get('nickname', '')
                account_industry = account.get('industry', '')
                video_title = video.get('title', '')
            
            prompt = f"""你是初步筛选助手，判断评论者是否是潜在目标客户（老板/管理层/供应商/从业者）。

【核心方法】结合评论上下文，倒推评论者的身份！

## 评论上下文（重要！）

### 主播信息
- 主播昵称：{account_name}
- 行业标签：{account_industry}
- 视频标题：{video_title}

### 评论者信息
- 昵称：{user.get('nickname', '未知')}
- 签名：{user.get('signature', '无')}
- 评论内容：{user.get('comment_text', '无')}

---

## 【关键】倒推分析法（重点！）

### 1️⃣ 语气/口吻分析
根据评论内容，判断Ta的身份视角：

**从业者/管理者语气**（建议打开）：
- "这个我们也在用"、"我们店里也是这样"
- "确实是这样，经营不易"、"现在客源不好做"
- "招人太难了"、"员工流动性大"
- 提到成本、营收、管理、运营等
- 使用"我们"（暗示有团队）、"店里"（有场所）

**顾客/爱好者语气**（可跳过）：
- "来玩过几次"、"经常来"、"感觉不错"
- 纯粹的娱乐体验描述

**员工语气**（可跳过）：
- "我在这上班"、"我是这里的服务员"
- 抱怨工作、吐槽老板

### 2️⃣ 专业度分析

**行业内部人视角**（建议打开）：
- 评论显示专业知识（设备、管理、运营）
- 对行业痛点有共鸣（"确实是这样"）
- 谈论供应链、合作、同行

**外行视角**（可跳过）：
- 纯好奇、问基础问题
- 只关注娱乐体验

### 3️⃣ 需求倒推

根据评论，推测Ta可能有什么需求：
- 寻找解决方案？→ 可能是管理者
- 寻求合作/供应？→ 可能是从业者
- 交流经验？→ 可能是同行老板
- 纯娱乐评论？→ 可能是顾客

### 4️⃣ 身份线索（辅助）

**强线索**：
- 昵称/签名含：老板、店长、经理、创始人、合伙人
- 昵称/签名含场所：XX球馆、XX会所、XX娱乐

**中等线索**：
- 昵称含地域+行业（"深圳台球"）
- 签名体现商务/创业身份

**弱线索**：
- 昵称正常，但评论语气像从业者

---

## 判断逻辑（宽松策略）

### ✅ 建议打开（满足任一即可）

1. **评论语气是管理者/从业者视角**
   - 用"我们"、"店里"等
   - 谈论经营、管理、成本
   
2. **评论显示行业内部人思维**
   - 对痛点有共鸣
   - 专业知识/经验分享
   
3. **昵称/签名有明显职位/场所标识**
   - 老板、店长、XX馆
   
4. **评论体现寻找解决方案/合作需求**

5. **不是明显的学生/打工人/纯粉丝**

### ❌ 明确跳过

- 昵称含"学生""00后""备考"
- 昵称含"打工人""社畜""搬砖"
- 评论纯娱乐（"哈哈哈""爱了"）
- 评论是员工吐槽

---

## 返回JSON

{{
    "should_visit": true/false,
    "reason": "简短理由（20字内，说明关键判断点）",
    "identity_hint": "推测身份（老板/管理/从业者/顾客/未知）"
}}

【策略】宁可多看几个（后续多模态会严格筛选），不要漏掉潜在老板！"""
            
            resp = await self.client.chat.completions.create(
                model=self.text_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100
            )
            
            result_text = resp.choices[0].message.content.strip()
            
            # 提取JSON
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
            
            result = json.loads(result_text)
            return result
            
        except Exception as e:
            logger.error(f"AI判断失败: {e}")
            # 默认不打开（保守策略）
            return {"should_visit": False, "reason": "判断失败"}
    
    # 以下是视觉分析和综合分析的方法（simplified version）
    # 完整版太长，暂时简化
    
    async def analyze_avatar(self, avatar_url: str, target_category: str = "球房运营") -> Dict:
        """【第3.1层】单独分析头像 - 使用视觉模型"""
        logger.info(f"   🖼️  分析头像（简化版）...")
        return {"职业特征": "需要完整实现", "置信度": 0.5}
    
    async def analyze_video_covers(self, cover_urls: List[str], target_category: str = "球房运营") -> List[Dict]:
        """【第3.2层】单独分析视频封面（批量）- 使用视觉模型"""
        logger.info(f"   🎬 分析视频封面（简化版）...")
        return []
    
    async def analyze_text_semantics(self, video_titles: List[str], profile_comments: List[str], target_category: str = "球房运营") -> Dict:
        """【第4层】文本语义分析 - 分析视频标题和评论区别人的称呼"""
        logger.info(f"   📝 文本语义分析（简化版）...")
        return {"语气特征": "未知", "置信度": 0.5}
    
    async def analyze_user_profile(self, user_comment_data: Dict, profile_data: Dict, target_category: str = "球房运营") -> Dict:
        """【第5层】综合汇总分析 - 基于文本的简化版（暂不使用视觉模型）"""
        try:
            nickname = user_comment_data.get('nickname', '未知')
            logger.info(f"      🔮 AI大模型分析中...")
            logger.info(f"         用户: {nickname[:20]}")
            logger.info(f"         签名: {user_comment_data.get('signature', '无')[:30]}")
            logger.info(f"         视频数: {len(profile_data.get('video_titles', []))}")
            
            # 构建分析上下文
            prompt = f"""你是资深的B2B销售，判断这个抖音用户是否是娱乐场所的老板/管理者。

## 用户评论信息
- 昵称：{user_comment_data.get('nickname', '未知')}
- 签名：{user_comment_data.get('signature', '无')}
- 评论内容：{user_comment_data.get('comment_text', '无')}

## 用户主页信息
- 主页昵称：{profile_data.get('nickname', '未知')}
- 主页签名：{profile_data.get('signature', '无')}
- 视频标题（最近5个）：{', '.join(profile_data.get('video_titles', [])[:5])}
- 地区：{profile_data.get('location', '未知')}
- 评论区别人对TA的称呼：{', '.join(profile_data.get('comments_about_user', [])[:3])}

## 判断标准（{target_category}）

### ✅ 强目标信号（满足1个即可）
1. **职位标识**：昵称/签名含"老板、店长、经理、创始人、合伙人、负责人"
2. **场所标识**：昵称/签名含"XX足浴、XX会所、XX台球、XX娱乐"
3. **称呼验证**：别人叫TA"老板、X总、店长"
4. **内容特征**：视频标题全是店铺运营/管理相关内容

### ⚠️ 中等信号（满足2个以上）
1. 视频标题有2个以上关于经营/管理/员工的
2. 签名体现创业/商务身份
3. 评论语气是从业者视角（"我们店"、"经营不易"）
4. 地区+行业明确（"深圳足浴"）

### ❌ 排除信号
- 昵称/签名含"学生、打工人、社畜、宝妈"
- 视频标题全是个人生活/娱乐
- 评论是员工吐槽老板
- 明显是顾客视角

## 输出JSON

{{
    "is_target": true/false,
    "confidence": 0.0-1.0,  // 置信度：0.7以上才私信
    "reason": "简短判断理由（30字内）",
    "key_signals": ["信号1", "信号2"]  // 关键证据
}}

【要求】必须有明确证据，不确定宁可返回false！"""
            
            resp = await self.client.chat.completions.create(
                model=self.text_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200
            )
            
            result_text = resp.choices[0].message.content.strip()
            
            # 提取JSON
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
            
            result = json.loads(result_text)
            
            # 详细输出分析结果
            is_target = result.get('is_target', False)
            confidence = result.get('confidence', 0.0)
            reason = result.get('reason', '无')
            signals = result.get('key_signals', [])
            
            logger.info(f"      ✅ 分析完成:")
            logger.info(f"         目标客户: {'是' if is_target else '否'}")
            logger.info(f"         意向度: {confidence:.2f}")
            logger.info(f"         判断依据: {reason}")
            if signals:
                logger.info(f"         关键证据: {', '.join(signals[:3])}")
            
            return result
            
        except Exception as e:
            logger.error(f"综合分析失败: {e}")
            return {
                "is_target": False,
                "confidence": 0.0,
                "reason": f"分析失败: {e}"
            }

