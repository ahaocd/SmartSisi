"""
情感音乐生成工具包 - 提供符合A2A协议的音乐生成服务
"""

# 直接从增强版工具模块导入
try:
    # 尝试导入增强版音乐工具
    from .music_tool_enhanced import EnhancedMusicGeneratorTool as MusicGeneratorTool
    from .music_tool_enhanced import create_tool, enhanced_run_music_workflow as run_music_workflow
    from .music_tool_enhanced import enhanced_create_music_now as create_music_now
except ImportError as e:
    # 导入失败时尝试从父目录导入原始版本
    import sys
    import os
    import logging

    logger = logging.getLogger(__name__)
    logger.error(f"导入增强版音乐工具失败: {str(e)}，将尝试导入原始版本")

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from music_tool import MusicGeneratorTool, create_tool, run_music_workflow, create_music_now
    except ImportError as e2:
        logger.error(f"导入原始音乐工具也失败: {str(e2)}")
        # 创建空的占位函数
        def create_tool():
            return None
        
        def run_music_workflow(*args, **kwargs):
            return {"status": "error", "message": "音乐生成工具未正确加载"}
            
        def create_music_now(*args, **kwargs):
            return {"status": "error", "message": "音乐生成工具未正确加载"}
            
        class MusicGeneratorTool:
            def __init__(self, *args, **kwargs):
                pass

# 尝试导入音乐工作流函数
try:
    from ..music_tool import create_music_workflow
except ImportError:
    # 创建空的占位函数
    def create_music_workflow(*args, **kwargs):
        return None

__all__ = ["MusicGeneratorTool", "create_tool", "run_music_workflow", "create_music_workflow", "create_music_now"]
