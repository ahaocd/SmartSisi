"""
视频转文章工具 - FunASR版（使用你现有的本地ASR）

核心流程：
1. 提取视频音频 (moviepy)
2. FunASR 本地识别转文字（不需要下载3GB模型！）
3. 大模型洗稿生成文章

依赖：
    pip install moviepy openai funasr  (你已经装好了！)

使用：
    python video_to_article_funasr.py
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# 添加项目根目录
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

# 添加 ASR 路径
asr_path = project_root / "asr"
sys.path.insert(0, str(asr_path))

try:
    from moviepy.editor import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    print("❌ MoviePy未安装")

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("❌ OpenAI SDK未安装")

try:
    from funasr import AutoModel
    FUNASR_AVAILABLE = True
except ImportError:
    FUNASR_AVAILABLE = False
    print("❌ FunASR未安装")

from config_loader import get_config


class VideoToArticleFunASR:
    """使用FunASR的视频转文章工具"""
    
    def __init__(self):
        self.config = get_config()
        self.output_dir = Path("asianight_data/articles")
        self.temp_dir = Path("asianight_data/temp")
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # FunASR 模型（延迟加载）
        self.asr_model = None
        
        # AI 洗稿客户端
        self._init_ai_client()
        
        print("✅ FunASR视频转文章工具初始化完成")
    
    def _init_ai_client(self):
        """初始化AI客户端"""
        if not OPENAI_AVAILABLE:
            raise ImportError("请先安装: pip install openai")
        
        rewrite_config = self.config.get_rewrite_model_config()
        self.rewrite_client = AsyncOpenAI(
            api_key=rewrite_config['api_key'],
            base_url=rewrite_config['base_url']
        )
        self.rewrite_model = rewrite_config['model']
        self.rewrite_temperature = rewrite_config['temperature']
        self.rewrite_max_tokens = rewrite_config['max_tokens']
        
        print(f"✅ AI洗稿模型: {self.rewrite_model}")
    
    def _init_asr_model(self):
        """初始化FunASR模型（延迟加载）"""
        if self.asr_model is not None:
            return
        
        if not FUNASR_AVAILABLE:
            raise ImportError("FunASR未安装，请运行: pip install funasr")
        
        print("\n📥 加载 FunASR 模型...")
        print("   （首次运行会自动下载模型，约200MB，比Whisper小多了！）")
        
        try:
            # 使用 FunASR 的 Paraformer 模型
            # 这个模型比 Whisper 小得多，而且识别效果很好
            self.asr_model = AutoModel(
                model="paraformer-zh",  # 中文识别
                # model="paraformer",   # 多语言
                vad_model="fsmn-vad",   # 语音检测
                punc_model="ct-punc",   # 标点预测
                # 可选：指定模型路径，避免重复下载
                # model_dir="/path/to/models"
            )
            print("✅ FunASR 模型加载完成\n")
        
        except Exception as e:
            print(f"❌ FunASR 模型加载失败: {e}")
            print("\n💡 提示：首次使用会自动下载模型，请确保网络畅通")
            raise
    
    def extract_audio(self, video_path: str) -> str:
        """
        从视频提取音频
        
        Args:
            video_path: 视频文件路径
        
        Returns:
            音频文件路径
        """
        if not MOVIEPY_AVAILABLE:
            raise ImportError("MoviePy未安装")
        
        print(f"\n🎵 提取音频: {video_path}")
        
        video_path = Path(video_path)
        # FunASR 支持 wav, mp3, pcm 等格式
        audio_path = self.temp_dir / f"{video_path.stem}.wav"
        
        try:
            video = VideoFileClip(str(video_path))
            
            if video.audio is None:
                video.close()
                raise ValueError("视频没有音频轨道")
            
            # 导出为 WAV 格式（FunASR 推荐）
            video.audio.write_audiofile(
                str(audio_path),
                fps=16000,  # FunASR 推荐 16kHz
                nbytes=2,
                codec='pcm_s16le',
                logger=None
            )
            video.close()
            
            print(f"✅ 音频提取完成: {audio_path}")
            return str(audio_path)
        
        except Exception as e:
            print(f"❌ 音频提取失败: {e}")
            raise
    
    def transcribe_audio(self, audio_path: str) -> str:
        """
        使用FunASR转录音频
        
        Args:
            audio_path: 音频文件路径
        
        Returns:
            转录文本
        """
        # 初始化模型（延迟加载）
        self._init_asr_model()
        
        print(f"\n📝 FunASR 转录中...")
        
        try:
            # FunASR 转录
            result = self.asr_model.generate(
                input=audio_path,
                batch_size_s=300,  # 支持长音频（单位：秒）
                hotword='',  # 可以添加热词提高识别率
            )
            
            # 提取文本
            if isinstance(result, list) and len(result) > 0:
                # 方式1：如果返回的是列表
                texts = []
                for item in result:
                    if isinstance(item, dict):
                        text = item.get('text', '')
                    else:
                        text = str(item)
                    
                    if text:
                        texts.append(text)
                
                transcript = ' '.join(texts)
            
            elif isinstance(result, dict):
                # 方式2：如果返回的是字典
                transcript = result.get('text', '')
            
            else:
                # 方式3：直接转字符串
                transcript = str(result)
            
            print(f"✅ 转录完成，字数: {len(transcript)}")
            print(f"\n📄 转录预览（前200字）:")
            print(f"   {transcript[:200]}...")
            
            return transcript
        
        except Exception as e:
            print(f"❌ FunASR 转录失败: {e}")
            raise
    
    async def rewrite_to_article(
        self,
        transcript: str,
        title: str = "视频内容",
        style: str = "entertainment"
    ) -> str:
        """
        使用大模型洗稿
        
        Args:
            transcript: 转录文本
            title: 标题
            style: 风格
        
        Returns:
            Markdown文章
        """
        print(f"\n✍️  大模型洗稿中（风格: {style}）...")
        
        style_prompts = {
            "professional": "专业、深度、商业场景",
            "casual": "轻松口语、通俗易懂",
            "entertainment": "娱乐行业、生动有趣、夜场风格"
        }
        
        style_desc = style_prompts.get(style, style_prompts["entertainment"])
        
        prompt = f"""你是专业内容创作专家。请将以下视频转录改写成高质量原创文章。

**原始视频**: {title}

**转录内容**:
{transcript[:4000]}

**改写要求**:
1. 风格: {style_desc}
2. 原创度: 95%+，完全重写表达方式
3. 格式: Markdown
4. 结构:
   - # 吸引人的标题
   - ## 引言（200字）
   - ## 核心内容1（400字）
   - ## 核心内容2（400字）
   - ## 总结（200字）
5. 字数: 1200-1500字
6. 语言: 简体中文，流畅自然
7. 保留核心观点，用全新表达

**输出**: 完整Markdown文章

开始创作："""
        
        try:
            response = await self.rewrite_client.chat.completions.create(
                model=self.rewrite_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是顶级内容创作专家。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=self.rewrite_temperature,
                max_tokens=self.rewrite_max_tokens
            )
            
            article = response.choices[0].message.content
            
            # 清理格式
            if article.startswith("```markdown"):
                article = article.replace("```markdown", "").replace("```", "").strip()
            elif article.startswith("```"):
                article = article.replace("```", "").strip()
            
            print(f"✅ 洗稿完成，字数: {len(article)}")
            return article
        
        except Exception as e:
            print(f"❌ 洗稿失败: {e}")
            return f"# {title}\n\n{transcript}"
    
    async def convert(
        self,
        video_path: str,
        title: str = None,
        style: str = "entertainment"
    ) -> Dict[str, Any]:
        """
        完整转换流程
        
        Args:
            video_path: 视频路径
            title: 标题
            style: 风格
        
        Returns:
            转换结果
        """
        print("\n" + "="*70)
        print("🎬 视频转文章 - FunASR版（本地识别，模型小）")
        print("="*70)
        
        video_path = Path(video_path)
        if not video_path.exists():
            return {"success": False, "error": "视频文件不存在"}
        
        if title is None:
            title = video_path.stem.replace("_", " ").replace("-", " ")
        
        result = {
            "success": False,
            "video_path": str(video_path),
            "title": title,
            "transcript": "",
            "article": "",
            "article_file": ""
        }
        
        try:
            # 步骤1: 提取音频
            print("\n【步骤1/3】提取音频...")
            audio_path = self.extract_audio(str(video_path))
            
            # 步骤2: FunASR 转录
            print("\n【步骤2/3】FunASR 本地转录...")
            transcript = self.transcribe_audio(audio_path)
            result["transcript"] = transcript
            
            # 保存转录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            transcript_file = self.output_dir / f"transcript_{timestamp}.txt"
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(f"视频: {video_path.name}\n")
                f.write(f"转录时间: {datetime.now()}\n\n")
                f.write(transcript)
            
            print(f"✅ 转录已保存: {transcript_file}")
            
            # 步骤3: 大模型洗稿
            print("\n【步骤3/3】大模型洗稿...")
            article = await self.rewrite_to_article(transcript, title, style)
            result["article"] = article
            
            # 保存文章
            article_file = self.output_dir / f"article_{timestamp}.md"
            with open(article_file, "w", encoding="utf-8") as f:
                f.write(f"<!-- 原始视频: {video_path.name} -->\n")
                f.write(f"<!-- 生成时间: {datetime.now()} -->\n\n")
                f.write(article)
            
            result["article_file"] = str(article_file)
            result["success"] = True
            
            print("\n" + "="*70)
            print("✅ 转换完成！")
            print("="*70)
            print(f"📄 转录: {transcript_file}")
            print(f"📝 文章: {article_file}")
            print(f"📊 转录字数: {len(transcript)}")
            print(f"📊 文章字数: {len(article)}")
            
            # 预览
            print("\n📖 文章预览：")
            print("-"*70)
            lines = article.split('\n')[:15]
            print('\n'.join(lines))
            if len(article.split('\n')) > 15:
                print("...")
            print("-"*70)
            
            # 清理临时文件
            if os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"\n🗑️  临时音频已删除")
        
        except Exception as e:
            result["error"] = str(e)
            print(f"\n❌ 转换失败: {e}")
            import traceback
            traceback.print_exc()
        
        return result


async def main():
    """主函数"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║        🎬 视频转文章 - FunASR 本地版 🎬                         ║
║                                                                ║
║  特点: 使用 FunASR 本地识别（模型小，速度快）                  ║
║  依赖: moviepy, openai, funasr (你已经装好了！)               ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
""")
    
    converter = VideoToArticleFunASR()
    
    while True:
        print("\n" + "="*70)
        print("请输入视频文件路径（或输入 q 退出）：")
        print("="*70)
        
        video_path = input("\n视频路径: ").strip().strip('"')
        
        if video_path.lower() == 'q':
            print("👋 退出")
            break
        
        if not video_path:
            print("❌ 未输入路径")
            continue
        
        # 标题
        title = input("标题（回车=自动）: ").strip()
        
        # 风格
        print("\n风格:")
        print("  1. entertainment - 娱乐行业（默认）")
        print("  2. professional - 专业正式")
        print("  3. casual - 轻松口语")
        style_choice = input("选择 [1-3]: ").strip()
        
        styles = {"1": "entertainment", "2": "professional", "3": "casual"}
        style = styles.get(style_choice, "entertainment")
        
        # 转换
        result = await converter.convert(video_path, title, style)
        
        if result["success"]:
            print(f"\n🎉 成功！文章: {result['article_file']}")
        else:
            print(f"\n❌ 失败: {result.get('error')}")
        
        # 继续？
        cont = input("\n继续处理其他视频？(y/n): ").strip().lower()
        if cont != 'y':
            break


if __name__ == "__main__":
    # 检查依赖
    missing = []
    if not MOVIEPY_AVAILABLE:
        missing.append("moviepy")
    if not OPENAI_AVAILABLE:
        missing.append("openai")
    if not FUNASR_AVAILABLE:
        missing.append("funasr")
    
    if missing:
        print(f"\n❌ 缺少依赖: {', '.join(missing)}")
        print(f"请运行: pip install {' '.join(missing)}")
        sys.exit(1)
    
    print("✅ 依赖检查通过（你都装好了！）\n")
    asyncio.run(main())

