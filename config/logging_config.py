"""
日志配置管理
用于统一管理系统中各种库的日志级别，避免调试信息泄露到用户界面
"""

import logging
import os
import warnings

def configure_system_logging():
    """配置系统日志级别，禁用不必要的调试信息"""

    # 0. 前置修复：兼容 SciPy 1.14+ 移除 signal.hann
    # 必须尽早执行，在任何可能导入 librosa/scipy 的位置之前
    try:
        import scipy.signal as _sig  # noqa: F401
        try:
            from scipy.signal import windows as _win  # noqa: F401
            if not hasattr(_sig, 'hann'):
                _sig.hann = _win.hann  # 提供兼容别名，避免下游依赖调用失败
                print(" scipy.signal.hann 兼容补丁已前置")
        except Exception:
            # 旧版 SciPy 无 windows 子模块时无需处理
            pass
    except Exception:
        # 未安装 SciPy 时跳过
        pass

    # 1. 禁用numba的调试日志
    try:
        # 在导入numba之前设置环境变量
        os.environ['NUMBA_DISABLE_JIT'] = '0'  # 保持JIT启用
        os.environ['NUMBA_DEBUG'] = '0'        # 禁用调试模式
        os.environ['NUMBA_VERBOSE'] = '0'      # 禁用详细输出
        os.environ['NUMBA_DEBUG_CACHE'] = '0'  # 禁用缓存调试
        os.environ['NUMBA_DEBUGINFO'] = '0'    # 禁用调试信息

        import numba
        # 设置numba相关的所有日志级别
        for logger_name in ['numba', 'numba.core', 'numba.core.ssa', 'numba.core.types',
                           'numba.core.compiler', 'numba.core.lowering']:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.ERROR)  # 只显示错误信息
            logger.propagate = False  # 阻止向上传播

        print(" Numba日志级别已设置为ERROR")
    except ImportError:
        pass
    
    # 2. 禁用numpy的警告信息
    try:
        import numpy as np
        # 禁用numpy的运行时警告
        np.seterr(all='ignore')
        # numpy 2.0+ 移除了 VisibleDeprecationWarning，使用标准库的
        if hasattr(np, 'VisibleDeprecationWarning'):
            warnings.filterwarnings('ignore', category=np.VisibleDeprecationWarning)
        else:
            warnings.filterwarnings('ignore', category=DeprecationWarning)
        print(" Numpy警告已禁用")
    except ImportError:
        pass
    
    # 3. 禁用librosa的调试信息
    try:
        librosa_logger = logging.getLogger('librosa')
        librosa_logger.setLevel(logging.WARNING)
        print(" Librosa日志级别已设置为WARNING")
    except:
        pass
    
    # 4. 配置SmartSisi系统中所有库的日志级别
    library_loggers = {
        # 基础库
        'requests': logging.WARNING,
        'urllib3': logging.WARNING,
        'httpx': logging.WARNING,
        'websockets': logging.WARNING,
        'websocket': logging.WARNING,
        'ws4py': logging.WARNING,

        # 音频处理库
        'pyaudio': logging.WARNING,
        'pydub': logging.WARNING,
        'pygame': logging.WARNING,
        'scipy': logging.WARNING,
        'opencv': logging.WARNING,
        'cv2': logging.WARNING,
        
        # SmartSisi内部模块 - 减少调试日志
        'smart_audio_collector': logging.WARNING,  # 只显示警告和错误
        'sisi_brain': logging.WARNING,  # 前脑系统只显示警告和错误
        'sisi_brain.audio_accumulation_manager': logging.WARNING,
        'sisi_brain.audio_humanized_analyzer': logging.WARNING,
        'sisi_brain.music_humanized_processor': logging.WARNING,
        'sisi_brain.dynamic_context_hub': logging.WARNING,
        'sisi_brain.sisi_info_pipeline': logging.WARNING,
        'sisi_brain.acrcloud_music_analyzer': logging.WARNING,

        # Web框架
        'flask': logging.WARNING,
        'werkzeug': logging.WARNING,
        'gevent': logging.WARNING,

        # AI/ML库
        'langchain': logging.WARNING,
        'langgraph': logging.WARNING,
        'chromadb': logging.WARNING,
        'chroma': logging.WARNING,
        'tenacity': logging.WARNING,
        'openai': logging.WARNING,
        'azure': logging.WARNING,
        'aliyun': logging.WARNING,

        # 深度学习库
        'tensorflow': logging.ERROR,
        'torch': logging.WARNING,
        'transformers': logging.WARNING,

        # 其他工具库
        'psutil': logging.WARNING,
        'openpyxl': logging.WARNING,
        'bs4': logging.WARNING,
        'beautifulsoup4': logging.WARNING,
        'edge_tts': logging.WARNING,
        'simhash': logging.WARNING,
        'pytz': logging.WARNING
    }

    configured_count = 0
    for lib_name, level in library_loggers.items():
        try:
            logger = logging.getLogger(lib_name)
            logger.setLevel(level)
            logger.propagate = False  # 阻止向上传播
            configured_count += 1
        except:
            pass

    print(f" 已配置 {configured_count} 个库的日志级别")
    
    # 6. 设置根日志级别
    root_logger = logging.getLogger()
    if root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.INFO)
    
    print(" 系统日志配置完成")

def setup_sisi_logging():
    """设置SmartSisi专用的日志配置"""
    
    # 创建SmartSisi专用的日志格式
    sisi_formatter = logging.Formatter(
        '[%(asctime)s][系统] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S.%f'
    )
    
    # 配置SmartSisi核心日志
    sisi_logger = logging.getLogger('SmartSisi')
    sisi_logger.setLevel(logging.INFO)
    
    # 如果没有处理器，添加控制台处理器
    if not sisi_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(sisi_formatter)
        sisi_logger.addHandler(console_handler)
    
    print(" SmartSisi日志配置完成")

# 自动配置
if __name__ == "__main__":
    configure_system_logging()
    setup_sisi_logging()

# 在模块导入时自动配置
configure_system_logging()
