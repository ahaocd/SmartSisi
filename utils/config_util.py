import json
import codecs
import os
from configparser import ConfigParser
import functools
from threading import Lock

# 添加自定义日志函数，避免循环导入
def log_message(level, message):
    """简单的日志函数，避免循环导入util模块"""
    print(message)

lock = Lock()
def synchronized(func):
  @functools.wraps(func)
  def wrapper(*args, **kwargs):
    with lock:
      return func(*args, **kwargs)
  return wrapper

config: json = None
system_config: ConfigParser = None
system_chrome_driver = None
key_ali_nls_key_id = None
key_ali_nls_key_secret = None
key_ali_nls_app_key = None
 
key_chat_module = None
sisi_llm_model = None
sisi_llm_api_key = None
sisi_llm_base_url = None
liuye_llm_model = None
liuye_llm_api_key = None
liuye_llm_base_url = None
liuye_llm_temperature = None
liuye_llm_max_tokens = None
key_xingchen_api_key = None
xingchen_characterid = None
xingchen_base_url = None
xingchen_model_engine = None
google_search_api_key = None  # Google搜索API密钥
google_search_api_base = None  # Google搜索API基础URL
proxy_config = None
ASR_mode = None
local_asr_ip = None
local_asr_port = None
ltp_mode = None
ollama_ip = None
ollama_model = None
tts_module = None
tts_type = None
coze_bot_id = None
coze_api_key = None
start_mode = None
sisi_voice_uri = None
cache_root = None
sisi_url = None
siliconflow_api_key = None
siliconflow_base_url = None
siliconflow_model = None
siliconflow_voice_type = None
# 柳叶TTS配置
liuye_tts_api_key = None
liuye_tts_base_url = None
liuye_tts_model = None
liuye_voice_uri = None
siliconflow_video_model = None
siliconflow_video_prompt_template = None
baidu_dialogue_emotion_app_id = None
baidu_dialogue_emotion_api_key = None
baidu_dialogue_emotion_secret_key = None

# 🧠 Sisi前脑系统模型配置
memory_llm_model = None
memory_embedding_model = None
rag_llm_model = None
rag_embedding_model = None
prompt_generator_model = None
audio_context_model = None
reasoning_model = None
quick_response_model = None
optimization_model = None
subscription_model = None

# 🎵 ACRCloud音乐识别配置
acrcloud_host = None
acrcloud_access_key = None
acrcloud_access_secret = None
acrcloud_timeout = None
acrcloud_enabled = None

# AEC / 半双工
aec_enabled = None
aec_backend = None
aec_dll_path = None
aec_required = None
aec_frame_ms = None
aec_filter_length_ms = None
half_duplex_enabled = None
half_duplex_hold_ms = None
half_duplex_tail_ms = None

# 🧠 Sisi前脑系统模型配置
memory_llm_model = None
memory_llm_api_key = None
memory_llm_base_url = None
memory_embedding_model = None
rag_llm_model = None
rag_llm_api_key = None
rag_llm_base_url = None
rag_embedding_model = None
prompt_generator_model = None
prompt_generator_api_key = None
prompt_generator_base_url = None
audio_context_model = None
audio_context_api_key = None
audio_context_base_url = None
audio_context_temperature = None
audio_context_max_tokens = None

# 🌐 网络代理配置
http_proxy = None
https_proxy = None
proxy_enabled = None

# 工具调用配置
agent_use_tools = True
agent_functions = None

# 添加百度人体分析配置项
baidu_body_app_id = None
baidu_body_api_key = None
baidu_body_secret_key = None
body_detection_interval = None
body_detection_enabled = None

# AGENTSS模型配置 - 改为小写以匹配配置文件
agentss_api_key = None
agentss_base_url = None
agentss_model_engine = None
agentss_max_tokens = None


# agent系统输出优化配置
llm_optimize_enabled = False
llm_optimize_url = None
llm_optimize_key = None
llm_optimize_model = None

# 图像处理模型配置
image_model_api_key = None
image_model_base_url = None
image_model_engine = None
image_model_path = None

# 音乐LLM配置
music_llm_api_key = None
music_llm_api_url = None
music_llm_model = None

# 🎯 抖音营销智能体配置（多模态分层分析）
douyin_marketing_text_model = None
douyin_marketing_text_api_key = None
douyin_marketing_text_base_url = None
douyin_marketing_text_temperature = None
douyin_marketing_text_max_tokens = None
douyin_marketing_vision_model = None
douyin_marketing_vision_api_key = None
douyin_marketing_vision_base_url = None
douyin_marketing_vision_temperature = None
douyin_marketing_vision_max_tokens = None
douyin_marketing_ocr_model = None
douyin_marketing_ocr_api_key = None
douyin_marketing_ocr_base_url = None
douyin_marketing_ocr_temperature = None
douyin_marketing_ocr_max_tokens = None
douyin_marketing_enabled = None
douyin_marketing_max_comments = None
douyin_marketing_analyze_count_high = None
douyin_marketing_analyze_count_medium = None
douyin_marketing_analyze_count_low = None
douyin_marketing_confidence_threshold_high = None
douyin_marketing_confidence_threshold_medium = None
douyin_marketing_min_comments_required = None
douyin_marketing_retry_on_failure = None
douyin_marketing_max_retries = None
douyin_marketing_fallback_to_strategy1 = None

__tts_config_logged = False
__config_loaded = False

@synchronized
def load_config():
    global config
    global system_config
    global key_ali_nls_key_id
    global key_ali_nls_key_secret
    global key_ali_nls_app_key
    global key_ali_tss_key_id
    global key_ali_tss_key_secret
    global key_ali_tss_app_key
    global key_ms_tts_key
    global key_ms_tts_region
    global sisi_llm_model
    global sisi_llm_api_key
    global sisi_llm_base_url
    global liuye_llm_model
    global liuye_llm_api_key
    global liuye_llm_base_url
    global liuye_llm_temperature
    global liuye_llm_max_tokens
    global liuye_cmd_model
    global key_chat_module
    global key_xingchen_api_key
    global xingchen_characterid
    global xingchen_base_url
    global xingchen_model_engine
    global google_search_api_key
    global google_search_api_base
    global proxy_config
    global ASR_mode
    global local_asr_ip
    global local_asr_port
    global ltp_mode
    global ollama_ip
    global ollama_model
    global tts_module
    global tts_type
    global coze_bot_id
    global coze_api_key
    global start_mode
    global siliconflow_api_key
    global siliconflow_base_url
    global siliconflow_model
    global siliconflow_voice_type
    global sisi_voice_uri
    global cache_root
    global sisi_url
    global liuye_tts_api_key
    global liuye_tts_base_url
    global liuye_tts_model
    global liuye_voice_uri
    global siliconflow_video_model
    global siliconflow_video_prompt_template
    global baidu_dialogue_emotion_app_id
    global baidu_dialogue_emotion_api_key
    global baidu_dialogue_emotion_secret_key

    # 🧠 Sisi前脑系统模型配置全局变量
    global memory_llm_model, memory_llm_api_key, memory_llm_base_url, memory_embedding_model
    global rag_llm_model, rag_llm_api_key, rag_llm_base_url, rag_embedding_model
    global prompt_generator_model, prompt_generator_api_key, prompt_generator_base_url
    global audio_context_model, audio_context_api_key, audio_context_base_url
    global audio_context_temperature, audio_context_max_tokens
    global reasoning_model
    global quick_response_model
    global optimization_model
    global subscription_model

    # 🎵 ACRCloud音乐识别配置全局变量
    global acrcloud_host
    global acrcloud_access_key
    global acrcloud_access_secret
    global acrcloud_timeout
    global acrcloud_enabled

    # AEC / 半双工
    global aec_enabled
    global aec_backend
    global aec_dll_path
    global aec_required
    global aec_frame_ms
    global aec_filter_length_ms
    global half_duplex_enabled
    global half_duplex_hold_ms
    global half_duplex_tail_ms

    # 🌐 网络代理配置全局变量
    global http_proxy
    global https_proxy
    global proxy_enabled

    global agent_use_tools
    global agent_functions
    global baidu_body_app_id
    global baidu_body_api_key
    global baidu_body_secret_key
    global body_detection_interval
    global body_detection_enabled
    global __config_loaded
    global __tts_config_logged
    global os  # 添加全局声明，指定使用全局的os变量
    # AGENTSS相关变量 - 小写
    global agentss_api_key
    global agentss_base_url
    global agentss_model_engine
    global agentss_max_tokens
    # 图像处理模型配置
    global image_model_api_key
    global image_model_base_url
    global image_model_engine
    global image_model_path

    # 音乐LLM配置
    global music_llm_api_key
    global music_llm_api_url
    global music_llm_model

    # 打断模型配置
    global interrupt_model_api_key
    global interrupt_model_base_url
    global interrupt_model_engine
    global interrupt_model_max_tokens
    global interrupt_model_temperature
    global interrupt_model_enabled

    # 如果配置已加载且不是首次调用，返回配置字典
    if __config_loaded and os.path.exists('system.conf'):
        # 返回配置字典而不是None - 修复变量引用错误
        return {
            'memory_llm_api_key': memory_llm_api_key,
            'memory_llm_base_url': memory_llm_base_url,
            'memory_llm_model': memory_llm_model,
            'prompt_generator_model': prompt_generator_model,
            'prompt_generator_api_key': prompt_generator_api_key,
            'prompt_generator_base_url': prompt_generator_base_url
        }

    # 使用绝对路径加载config.json
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_json_path = os.path.join(base_dir, 'config', 'config.json')

    try:
        # 优先读取 config/config.json
        with codecs.open(config_json_path, encoding='utf-8') as f:
            config = json.load(f)
        print(f"成功加载config.json: {config_json_path}")
    except Exception as e:
        # 回退到根目录 config.json
        print(f"加载 config/config.json 失败: {str(e)}，尝试回退路径")
        try:
            with codecs.open(os.path.join(base_dir, 'config.json'), encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e2:
            print(f"读取回退 config.json 失败: {str(e2)}")
            config = {}  # 最终兜底为空配置

    system_config = ConfigParser()
    system_config_path = os.path.join(base_dir, 'system.conf')

    # 尝试使用绝对路径加载system.conf
    if os.path.exists(system_config_path):
        system_config.read(system_config_path, encoding='utf-8-sig')
        print(f"使用绝对路径加载system.conf: {system_config_path}")
    else:
        # 回退到相对路径
        system_config.read('system.conf', encoding='utf-8-sig')

    # 🔧 调试：检查system_config是否正确加载
    print(f"[调试] system_config类型: {type(system_config)}")
    if system_config and system_config.has_section('key'):
        acrcloud_key = system_config.get('key', 'acrcloud_access_key', fallback='')
        print(f"[调试] ACRCloud Key读取: {'成功' if acrcloud_key else '失败'} (长度: {len(acrcloud_key)})")
    else:
        print(f"[调试] system_config无效或缺少key section")

    # 加载其他配置项
    # 安全兜底：避免 system.conf 缺少某个 key 时直接抛 NoOptionError/NoSectionError 导致系统启动失败。
    # 说明：如果某个 key 是“必填项”，后续应在使用处做显式校验；这里仅保证读取阶段不崩溃。
    _orig_get = system_config.get

    def _safe_get(section, option, *, raw=False, vars=None, fallback=""):
        try:
            return _orig_get(section, option, raw=raw, vars=vars, fallback=fallback)
        except Exception:
            return fallback

    system_config.get = _safe_get

    def _normalize_url(val, default):
        if val is None:
            return default
        v = str(val).strip()
        if not v:
            return default
        if v.lower() in ("none", "null", "nil"):
            return default
        return v

    # 缓存根目录（统一缓存路径）
    _default_cache_root = os.path.join(base_dir, "cache_data")
    _cache_root = system_config.get('key', 'cache_root', fallback='').strip()
    if not _cache_root:
        cache_root = _default_cache_root
    else:
        cache_root = _cache_root if os.path.isabs(_cache_root) else os.path.join(base_dir, _cache_root)
    cache_root = os.path.normpath(cache_root)
    try:
        os.makedirs(cache_root, exist_ok=True)
    except Exception:
        pass

    key_ali_nls_key_id = system_config.get('key', 'ali_nls_key_id', fallback='')
    key_ali_nls_key_secret = system_config.get('key', 'ali_nls_key_secret', fallback='')
    key_ali_nls_app_key = system_config.get('key', 'ali_nls_app_key', fallback='')
    sisi_llm_model = system_config.get('key', 'sisi_llm_model', fallback='')
    sisi_llm_api_key = system_config.get('key', 'sisi_llm_api_key', fallback='')
    sisi_llm_base_url = system_config.get('key', 'sisi_llm_base_url', fallback='')
    liuye_llm_model = system_config.get('key', 'liuye_llm_model', fallback='')
    liuye_llm_api_key = system_config.get('key', 'liuye_llm_api_key', fallback='')
    liuye_llm_base_url = system_config.get('key', 'liuye_llm_base_url', fallback='')
    liuye_llm_temperature = system_config.get('key', 'liuye_llm_temperature', fallback='0.7')
    liuye_llm_max_tokens = system_config.get('key', 'liuye_llm_max_tokens', fallback='2000')
    key_chat_module = system_config.get('key', 'chat_module', fallback='')
    google_search_api_key = system_config.get('key', 'google_search_api_key', fallback='')
    google_search_api_base = system_config.get('key', 'google_search_api_base', fallback='')
    # system.conf 里是 asr_mode（小写）；兼容旧字段 ASR_mode（大写）
    ASR_mode = system_config.get('key', 'asr_mode', fallback=system_config.get('key', 'ASR_mode', fallback=''))
    local_asr_ip = system_config.get('key', 'local_asr_ip', fallback='')
    local_asr_port = system_config.get('key', 'local_asr_port', fallback='')
    proxy_config = system_config.get('key', 'proxy_config', fallback='')
    ltp_mode = system_config.get('key', 'ltp_mode', fallback='')
    ollama_ip = system_config.get('key', 'ollama_ip', fallback='')
    ollama_model = system_config.get('key', 'ollama_model', fallback='')
    tts_module = system_config.get('key', 'tts_module', fallback='')
    tts_type = tts_module or system_config.get('key', 'tts_type', fallback='')
    coze_bot_id = system_config.get('key', 'coze_bot_id', fallback='')
    coze_api_key = system_config.get('key', 'coze_api_key', fallback='')
    start_mode = system_config.get('key', 'start_mode', fallback='')
    sisi_url = system_config.get('key', 'sisi_url', fallback='127.0.0.1')
    siliconflow_api_key = system_config.get('key', 'siliconflow_api_key', fallback='')
    siliconflow_base_url = _normalize_url(
        system_config.get('key', 'siliconflow_base_url', fallback=''),
        'https://api.siliconflow.cn/v1'
    )
    siliconflow_model = system_config.get('key', 'siliconflow_model', fallback='')
    siliconflow_voice_type = system_config.get('key', 'siliconflow_voice_type', fallback='')
    sisi_voice_uri = system_config.get('key', 'sisi_voice_uri', fallback='')
    if sisi_voice_uri:
        siliconflow_voice_type = sisi_voice_uri
    elif siliconflow_voice_type:
        sisi_voice_uri = siliconflow_voice_type
    # 柳叶TTS配置
    liuye_tts_api_key = system_config.get('key', 'liuye_tts_api_key', fallback='')
    liuye_tts_base_url = _normalize_url(
        system_config.get('key', 'liuye_tts_base_url', fallback=''),
        siliconflow_base_url
    )
    liuye_tts_model = system_config.get('key', 'liuye_tts_model', fallback=siliconflow_model)
    liuye_voice_uri = system_config.get('key', 'liuye_voice_uri', fallback='')
    siliconflow_video_model = system_config.get('key', 'siliconflow_video_model', fallback='')
    siliconflow_video_prompt_template = system_config.get('key', 'siliconflow_video_prompt_template', fallback='')
    baidu_dialogue_emotion_app_id = system_config.get('key', 'baidu_dialogue_emotion_app_id', fallback='')
    baidu_dialogue_emotion_api_key = system_config.get('key', 'baidu_dialogue_emotion_api_key', fallback='')
    baidu_dialogue_emotion_secret_key = system_config.get('key', 'baidu_dialogue_emotion_secret_key', fallback='')

    # 🧠 加载Sisi前脑系统模型配置 (使用SiliconFlow最佳性价比模型)
    memory_llm_model = system_config.get('key', 'memory_llm_model', fallback='Qwen/Qwen3-8B')  # 免费，支持思考模式
    memory_llm_api_key = system_config.get('key', 'memory_llm_api_key', fallback='')
    memory_llm_base_url = system_config.get('key', 'memory_llm_base_url', fallback='https://api.siliconflow.cn/v1')
    memory_embedding_model = system_config.get('key', 'memory_embedding_model', fallback='BAAI/bge-large-zh-v1.5')  # 免费

    rag_llm_model = system_config.get('key', 'rag_llm_model', fallback='Qwen/Qwen3-14B')  # ￥2/M，性能更强
    rag_llm_api_key = system_config.get('key', 'rag_llm_api_key', fallback='')
    rag_llm_base_url = system_config.get('key', 'rag_llm_base_url', fallback='https://api.siliconflow.cn/v1')
    rag_embedding_model = system_config.get('key', 'rag_embedding_model', fallback='BAAI/bge-large-zh-v1.5')  # 免费

    prompt_generator_model = system_config.get('key', 'prompt_generator_model', fallback='GLM-4.5-X')  # 使用你配置的模型
    prompt_generator_api_key = system_config.get('key', 'prompt_generator_api_key', fallback='')
    prompt_generator_base_url = system_config.get('key', 'prompt_generator_base_url', fallback='https://api.siliconflow.cn/v1')

    audio_context_model = system_config.get('key', 'audio_context_model', fallback='Qwen/Qwen3-8B')  # 免费，支持思考模式
    audio_context_api_key = system_config.get('key', 'audio_context_api_key', fallback='')
    audio_context_base_url = system_config.get('key', 'audio_context_base_url', fallback='https://api.siliconflow.cn/v1')
    audio_context_temperature = system_config.get('key', 'audio_context_temperature', fallback='0.6')
    audio_context_max_tokens = system_config.get('key', 'audio_context_max_tokens', fallback='2000')

    # 🔧 修复：将前脑系统配置导出到全局命名空间
    globals()['memory_llm_model'] = memory_llm_model
    globals()['memory_llm_api_key'] = memory_llm_api_key
    globals()['memory_llm_base_url'] = memory_llm_base_url
    globals()['memory_embedding_model'] = memory_embedding_model

    globals()['rag_llm_model'] = rag_llm_model
    globals()['rag_llm_api_key'] = rag_llm_api_key
    globals()['rag_llm_base_url'] = rag_llm_base_url
    globals()['rag_embedding_model'] = rag_embedding_model

    globals()['prompt_generator_model'] = prompt_generator_model
    globals()['prompt_generator_api_key'] = prompt_generator_api_key
    globals()['prompt_generator_base_url'] = prompt_generator_base_url

    globals()['audio_context_model'] = audio_context_model
    globals()['audio_context_api_key'] = audio_context_api_key
    globals()['audio_context_base_url'] = audio_context_base_url
    globals()['audio_context_temperature'] = audio_context_temperature
    globals()['audio_context_max_tokens'] = audio_context_max_tokens

    minimax_api_key = system_config.get('key', 'minimax_api_key', fallback='')
    minimax_base_url = system_config.get('key', 'minimax_base_url', fallback='')
    minimax_model = system_config.get('key', 'minimax_model', fallback='')
    minimax_temperature = system_config.get('key', 'minimax_temperature', fallback='0.2')
    minimax_max_tokens = system_config.get('key', 'minimax_max_tokens', fallback='8000')


    # 🔥 修复：将医疗配置导出到全局命名空间
    globals()['minimax_api_key'] = minimax_api_key
    globals()['minimax_base_url'] = minimax_base_url
    globals()['minimax_model'] = minimax_model
    globals()['minimax_temperature'] = minimax_temperature
    globals()['minimax_max_tokens'] = minimax_max_tokens
    acrcloud_host = system_config.get('key', 'acrcloud_host', fallback='identify-cn-north-1.acrcloud.cn')
    acrcloud_access_key = system_config.get('key', 'acrcloud_access_key', fallback='')
    acrcloud_access_secret = system_config.get('key', 'acrcloud_access_secret', fallback='')
    acrcloud_timeout = system_config.get('key', 'acrcloud_timeout', fallback='10')
    acrcloud_enabled = system_config.get('key', 'acrcloud_enabled', fallback='true').lower() == 'true'

    # AEC / 半双工
    aec_enabled = system_config.get('key', 'aec_enabled', fallback='false').lower() == 'true'
    aec_backend = system_config.get('key', 'aec_backend', fallback='speexdsp')
    aec_dll_path = system_config.get('key', 'aec_dll_path', fallback='')
    aec_required = system_config.get('key', 'aec_required', fallback='false').lower() == 'true'
    aec_frame_ms = int(system_config.get('key', 'aec_frame_ms', fallback='16'))
    aec_filter_length_ms = int(system_config.get('key', 'aec_filter_length_ms', fallback='200'))
    half_duplex_enabled = system_config.get('key', 'half_duplex_enabled', fallback='true').lower() == 'true'
    half_duplex_hold_ms = int(system_config.get('key', 'half_duplex_hold_ms', fallback='120'))
    half_duplex_tail_ms = int(system_config.get('key', 'half_duplex_tail_ms', fallback='120'))

    # 🌐 加载网络代理配置
    http_proxy = system_config.get('key', 'http_proxy', fallback='')
    https_proxy = system_config.get('key', 'https_proxy', fallback='')
    proxy_enabled = system_config.get('key', 'proxy_enabled', fallback='false').lower() == 'true'

    # 这些是Agent系统的，不是前脑系统，使用fallback
    reasoning_model = system_config.get('key', 'reasoning_model', fallback='Qwen/QwQ-32B-Preview')
    quick_response_model = system_config.get('key', 'quick_response_model', fallback='Qwen/Qwen3-14B')
    optimization_model = system_config.get('key', 'optimization_model', fallback='Qwen/Qwen3-32B')
    subscription_model = system_config.get('key', 'subscription_model', fallback='Qwen/Qwen3-30B-A3B')

    # 加载图像处理模型配置
    try:
        image_model_api_key = system_config.get('key', 'image_model_api_key', fallback='')
        image_model_base_url = system_config.get('key', 'image_model_base_url', fallback='https://api.openai-proxy.org/v1')
        image_model_engine = system_config.get('key', 'image_model_engine', fallback='gpt-4o')
        # 使用fallback参数避免配置不存在时报错
        image_model_path = system_config.get('key', 'image_model_path', fallback='')

        # 验证配置有效性
        if not image_model_api_key:
            print("[警告] 图像处理模型API密钥未配置，图像分析功能将无法使用")

        if image_model_path and not os.path.exists(image_model_path):
            print(f"[警告] 图像处理模型测试图片路径不存在: {image_model_path}")

        # 输出日志确认配置（隐藏API密钥）
        masked_key = f"{image_model_api_key[:5]}...{image_model_api_key[-5:]}" if image_model_api_key and len(image_model_api_key) > 10 else "未设置"
        print(f"[系统] 图像处理模型配置已加载: engine={image_model_engine}, api_key={masked_key}")

        # 将这些变量设置到全局命名空间
        globals()['image_model_api_key'] = image_model_api_key
        globals()['image_model_base_url'] = image_model_base_url
        globals()['image_model_engine'] = image_model_engine
        globals()['image_model_path'] = image_model_path
    except Exception as e:
        # 过滤掉关于image_model_path的错误信息
        error_str = str(e)
        if "image_model_path" not in error_str:
            print(f"[系统] 加载图像处理模型配置失败: {error_str}")
        else:
            # 静默处理image_model_path相关错误
            print("[系统] 图像处理模型路径未配置，使用默认值")

        # 设置为空字符串而不是None，便于后续判断配置是否存在
        image_model_api_key = ""
        image_model_base_url = "https://api.openai-proxy.org/v1"
        image_model_engine = "gpt-4o"
        image_model_path = ""

        # 同样将默认值设置到全局命名空间
        globals()['image_model_api_key'] = image_model_api_key
        globals()['image_model_base_url'] = image_model_base_url
        globals()['image_model_engine'] = image_model_engine
        globals()['image_model_path'] = image_model_path

    # 加载音乐LLM配置
    try:
        music_llm_api_key = system_config.get('key', 'music_llm_api_key', fallback='')
        music_llm_api_url = system_config.get('key', 'music_llm_api_url', fallback='')
        music_llm_model = system_config.get('key', 'music_llm_model', fallback='')

        # 验证配置有效性
        if not music_llm_api_key:
            print("[警告] 音乐LLM API密钥未配置，音乐模块将使用备用回复")

        # 输出日志确认配置（隐藏API密钥）
        masked_key = f"{music_llm_api_key[:10]}...{music_llm_api_key[-10:]}" if music_llm_api_key and len(music_llm_api_key) > 20 else "未设置"
        print(f"[系统] 音乐LLM配置已加载: url={music_llm_api_url}, model={music_llm_model}, api_key={masked_key}")

        # 将这些变量设置到全局命名空间
        globals()['music_llm_api_key'] = music_llm_api_key
        globals()['music_llm_api_url'] = music_llm_api_url
        globals()['music_llm_model'] = music_llm_model
    except Exception as e:
        print(f"[系统] 加载音乐LLM配置失败: {str(e)}")
        # 设置为空字符串而不是None
        music_llm_api_key = ""
        music_llm_api_url = ""
        music_llm_model = ""

        # 同样将默认值设置到全局命名空间
        globals()['music_llm_api_key'] = music_llm_api_key
        globals()['music_llm_api_url'] = music_llm_api_url
        globals()['music_llm_model'] = music_llm_model

    # 加载打断模型配置
    try:
        interrupt_model_api_key = system_config.get('key', 'interrupt_model_api_key', fallback='')
        interrupt_model_base_url = system_config.get('key', 'interrupt_model_base_url', fallback='')
        interrupt_model_engine = system_config.get('key', 'interrupt_model_engine', fallback='')
        interrupt_model_max_tokens = system_config.get('key', 'interrupt_model_max_tokens', fallback='500')
        interrupt_model_temperature = system_config.get('key', 'interrupt_model_temperature', fallback='0.3')
        interrupt_model_enabled = system_config.get('key', 'interrupt_model_enabled', fallback='true')

        # 验证配置有效性
        if not interrupt_model_api_key:
            print("[警告] 打断模型API密钥未配置，智能打断功能将使用默认决策")

        # 输出日志确认配置（隐藏API密钥）
        masked_key = f"{interrupt_model_api_key[:10]}...{interrupt_model_api_key[-10:]}" if interrupt_model_api_key and len(interrupt_model_api_key) > 20 else "未设置"
        print(f"[系统] 打断模型配置已加载: url={interrupt_model_base_url}, engine={interrupt_model_engine}, enabled={interrupt_model_enabled}, api_key={masked_key}")

        # 将这些变量设置到全局命名空间
        globals()['interrupt_model_api_key'] = interrupt_model_api_key
        globals()['interrupt_model_base_url'] = interrupt_model_base_url
        globals()['interrupt_model_engine'] = interrupt_model_engine
        globals()['interrupt_model_max_tokens'] = interrupt_model_max_tokens
        globals()['interrupt_model_temperature'] = interrupt_model_temperature
        globals()['interrupt_model_enabled'] = interrupt_model_enabled
    except Exception as e:
        print(f"[系统] 加载打断模型配置失败: {str(e)}")
        # 设置为默认值
        interrupt_model_api_key = ""
        interrupt_model_base_url = ""
        interrupt_model_engine = ""
        interrupt_model_max_tokens = "500"
        interrupt_model_temperature = "0.3"
        interrupt_model_enabled = "true"

        # 同样将默认值设置到全局命名空间
        globals()['interrupt_model_api_key'] = interrupt_model_api_key
        globals()['interrupt_model_base_url'] = interrupt_model_base_url
        globals()['interrupt_model_engine'] = interrupt_model_engine
        globals()['interrupt_model_max_tokens'] = interrupt_model_max_tokens
        globals()['interrupt_model_temperature'] = interrupt_model_temperature
        globals()['interrupt_model_enabled'] = interrupt_model_enabled

    # 加载AGENTSS配置
    try:
        # 读取配置，使用一致的大写命名
        agentss_api_key = system_config.get('key', 'agentss_api_key')
        agentss_base_url = system_config.get('key', 'agentss_base_url')
        agentss_model_engine = system_config.get('key', 'agentss_model_engine')
        agentss_max_tokens = system_config.get('key', 'agentss_max_tokens')

        # 输出日志确认配置
        print(f"[系统] AGENTSS配置已加载: base_url={agentss_base_url}, model={agentss_model_engine}")
    except Exception as e:
        # 记录错误但不使用默认值
        print(f"[系统] 加载AGENTSS配置失败: {str(e)}")
        agentss_api_key = None
        agentss_base_url = None
        agentss_model_engine = None
        agentss_max_tokens = None

    # 加载工具调用配置
    agent_use_tools = system_config.get('key', 'agent_use_tools').lower() == 'true'

    # 尝试解析agent_functions为JSON格式
    try:
        agent_functions_str = system_config.get('key', 'agent_functions')
        if agent_functions_str and agent_functions_str.strip():
            agent_functions = json.loads(agent_functions_str)
        else:
            agent_functions = []
    except Exception as e:
        log_message(1, f"解析agent_functions异常: {str(e)}")
        agent_functions = []

    # 尝试加载xingchen配置，但若不存在则设置默认值
    try:
        key_xingchen_api_key = system_config.get('key', 'xingchen_api_key')
        xingchen_characterid = system_config.get('key', 'xingchen_characterid')
        xingchen_base_url = system_config.get('key', 'xingchen_base_url')
        xingchen_model_engine = system_config.get('key', 'xingchen_model_engine')
    except:
        key_xingchen_api_key = ""
        xingchen_characterid = ""
        xingchen_base_url = ""
        xingchen_model_engine = ""

    # 加载百度人体分析配置
    baidu_body_app_id = system_config.get('key', 'baidu_body_app_id')
    baidu_body_api_key = system_config.get('key', 'baidu_body_api_key')
    baidu_body_secret_key = system_config.get('key', 'baidu_body_secret_key')
    body_detection_interval = system_config.get('key', 'body_detection_interval')
    body_detection_enabled = system_config.get('key', 'body_detection_enabled').lower() == 'true'

    # 默认TTS引擎：不写回system.conf，避免污染配置文件
    if not tts_module:
        tts_module = "siliconflow"
    if not tts_type:
        tts_type = tts_module

    # 只在首次加载时输出配置信息用于调试，不重复打印
    global __tts_config_logged
    if not globals().get('__tts_config_logged', False):
        print(f"[系统] TTS配置: type={tts_type}, module={tts_module}")
        if siliconflow_api_key:
            masked_key = f"{siliconflow_api_key[:5]}...{siliconflow_api_key[-5:]}" if len(siliconflow_api_key) > 10 else "***"
            print(f"[系统] API Key已配置 (掩码: {masked_key})")
        print(f"[系统] 模型已加载: {os.path.basename(siliconflow_model)}")
        __tts_config_logged = True

    # 🔧 修复：确保system_config正确设置为全局变量
    globals()['system_config'] = system_config

    # 加载优化配置
    # 将这些配置作为全局变量导出
    global llm_optimize_enabled, llm_optimize_url, llm_optimize_key, llm_optimize_model
    try:
        llm_optimize_enabled = system_config.get('key', 'llm_optimize_enabled').lower() == 'true'
        llm_optimize_url = system_config.get('key', 'llm_optimize_url')
        llm_optimize_key = system_config.get('key', 'llm_optimize_key')
        llm_optimize_model = system_config.get('key', 'llm_optimize_model')

        key_preview = llm_optimize_key[:5] + "..." if llm_optimize_key and len(llm_optimize_key) > 5 else "未设置"
        print(f"[系统] 优化配置已加载: enabled={llm_optimize_enabled}, url={llm_optimize_url}, model={llm_optimize_model}, key={key_preview}")

        # 设置到全局命名空间
        globals()['llm_optimize_enabled'] = llm_optimize_enabled
        globals()['llm_optimize_url'] = llm_optimize_url
        globals()['llm_optimize_key'] = llm_optimize_key
        globals()['llm_optimize_model'] = llm_optimize_model
    except Exception as e:
        print(f"[系统] 加载优化配置出错: {str(e)}")
        # 清空配置
        llm_optimize_enabled = False
        llm_optimize_url = None
        llm_optimize_key = None
        llm_optimize_model = None

    # 标记配置已加载
    # 🎯 加载抖音营销智能体配置
    try:
        global douyin_marketing_text_model, douyin_marketing_text_api_key, douyin_marketing_text_base_url
        global douyin_marketing_text_temperature, douyin_marketing_text_max_tokens
        global douyin_marketing_vision_model, douyin_marketing_vision_api_key, douyin_marketing_vision_base_url
        global douyin_marketing_vision_temperature, douyin_marketing_vision_max_tokens
        global douyin_marketing_ocr_model, douyin_marketing_ocr_api_key, douyin_marketing_ocr_base_url
        global douyin_marketing_ocr_temperature, douyin_marketing_ocr_max_tokens
        global douyin_marketing_enabled, douyin_marketing_max_comments
        global douyin_marketing_analyze_count_high, douyin_marketing_analyze_count_medium, douyin_marketing_analyze_count_low
        global douyin_marketing_confidence_threshold_high, douyin_marketing_confidence_threshold_medium
        global douyin_marketing_min_comments_required, douyin_marketing_retry_on_failure
        global douyin_marketing_max_retries, douyin_marketing_fallback_to_strategy1
        
        # 文本模型配置
        douyin_marketing_text_model = system_config.get('key', 'douyin_marketing_text_model', fallback='moonshotai/Kimi-K2-Instruct-0905')
        douyin_marketing_text_api_key = system_config.get('key', 'douyin_marketing_text_api_key', fallback='')
        douyin_marketing_text_base_url = system_config.get('key', 'douyin_marketing_text_base_url', fallback='https://api.siliconflow.cn/v1')
        douyin_marketing_text_temperature = float(system_config.get('key', 'douyin_marketing_text_temperature', fallback='0.4'))
        douyin_marketing_text_max_tokens = int(system_config.get('key', 'douyin_marketing_text_max_tokens', fallback='1000'))
        
        # 视觉模型配置
        douyin_marketing_vision_model = system_config.get('key', 'douyin_marketing_vision_model', fallback='Pro/Qwen/Qwen2-VL-72B-Instruct')
        douyin_marketing_vision_api_key = system_config.get('key', 'douyin_marketing_vision_api_key', fallback='')
        douyin_marketing_vision_base_url = system_config.get('key', 'douyin_marketing_vision_base_url', fallback='https://api.siliconflow.cn/v1')
        douyin_marketing_vision_temperature = float(system_config.get('key', 'douyin_marketing_vision_temperature', fallback='0.3'))
        douyin_marketing_vision_max_tokens = int(system_config.get('key', 'douyin_marketing_vision_max_tokens', fallback='500'))
        
        # OCR模型配置
        douyin_marketing_ocr_model = system_config.get('key', 'douyin_marketing_ocr_model', fallback='deepseek-ai/deepseek-vl2')
        douyin_marketing_ocr_api_key = system_config.get('key', 'douyin_marketing_ocr_api_key', fallback='')
        douyin_marketing_ocr_base_url = system_config.get('key', 'douyin_marketing_ocr_base_url', fallback='https://api.siliconflow.cn/v1')
        douyin_marketing_ocr_temperature = float(system_config.get('key', 'douyin_marketing_ocr_temperature', fallback='0.1'))
        douyin_marketing_ocr_max_tokens = int(system_config.get('key', 'douyin_marketing_ocr_max_tokens', fallback='2000'))
        
        # 任务配置
        douyin_marketing_enabled = system_config.get('key', 'douyin_marketing_enabled', fallback='true').lower() == 'true'
        douyin_marketing_max_comments = int(system_config.get('key', 'douyin_marketing_max_comments', fallback='200'))
        douyin_marketing_analyze_count_high = int(system_config.get('key', 'douyin_marketing_analyze_count_high', fallback='30'))
        douyin_marketing_analyze_count_medium = int(system_config.get('key', 'douyin_marketing_analyze_count_medium', fallback='20'))
        douyin_marketing_analyze_count_low = int(system_config.get('key', 'douyin_marketing_analyze_count_low', fallback='10'))
        douyin_marketing_confidence_threshold_high = float(system_config.get('key', 'douyin_marketing_confidence_threshold_high', fallback='0.8'))
        douyin_marketing_confidence_threshold_medium = float(system_config.get('key', 'douyin_marketing_confidence_threshold_medium', fallback='0.5'))
        
        # 回退策略配置
        douyin_marketing_min_comments_required = int(system_config.get('key', 'douyin_marketing_min_comments_required', fallback='10'))
        douyin_marketing_retry_on_failure = system_config.get('key', 'douyin_marketing_retry_on_failure', fallback='true').lower() == 'true'
        douyin_marketing_max_retries = int(system_config.get('key', 'douyin_marketing_max_retries', fallback='3'))
        douyin_marketing_fallback_to_strategy1 = system_config.get('key', 'douyin_marketing_fallback_to_strategy1', fallback='true').lower() == 'true'
        
        # 导出到全局命名空间
        globals()['douyin_marketing_text_model'] = douyin_marketing_text_model
        globals()['douyin_marketing_text_api_key'] = douyin_marketing_text_api_key
        globals()['douyin_marketing_text_base_url'] = douyin_marketing_text_base_url
        globals()['douyin_marketing_vision_model'] = douyin_marketing_vision_model
        globals()['douyin_marketing_vision_api_key'] = douyin_marketing_vision_api_key
        globals()['douyin_marketing_vision_base_url'] = douyin_marketing_vision_base_url
        globals()['douyin_marketing_ocr_model'] = douyin_marketing_ocr_model
        globals()['douyin_marketing_ocr_api_key'] = douyin_marketing_ocr_api_key
        globals()['douyin_marketing_ocr_base_url'] = douyin_marketing_ocr_base_url
        globals()['douyin_marketing_enabled'] = douyin_marketing_enabled
        globals()['douyin_marketing_max_comments'] = douyin_marketing_max_comments
        
        print(f"[系统] 抖音营销智能体配置已加载:")
        print(f"  - 文本模型: {douyin_marketing_text_model}")
        print(f"  - 视觉模型: {douyin_marketing_vision_model}")
        print(f"  - OCR模型: {douyin_marketing_ocr_model}")
        print(f"  - 最大评论数: {douyin_marketing_max_comments}")
        print(f"  - 分析数量: 高={douyin_marketing_analyze_count_high}, 中={douyin_marketing_analyze_count_medium}, 低={douyin_marketing_analyze_count_low}")
        
    except Exception as e:
        print(f"[系统] 加载抖音营销配置失败: {str(e)}")
        # 使用默认值
        douyin_marketing_text_model = 'moonshotai/Kimi-K2-Instruct-0905'
        douyin_marketing_vision_model = 'Pro/Qwen/Qwen2-VL-72B-Instruct'
        douyin_marketing_enabled = True

    __config_loaded = True

    # 🔧 修复：返回配置字典供其他模块使用
    return {
        'memory_llm_api_key': memory_llm_api_key,
        'memory_llm_base_url': memory_llm_base_url,
        'memory_llm_model': memory_llm_model,
        'prompt_generator_model': prompt_generator_model,
        'prompt_generator_api_key': prompt_generator_api_key,
        'prompt_generator_base_url': prompt_generator_base_url,
        'audio_context_model': audio_context_model,
        'audio_context_api_key': audio_context_api_key,
        'audio_context_base_url': audio_context_base_url,
        'audio_context_temperature': audio_context_temperature,
        'audio_context_max_tokens': audio_context_max_tokens,
        'douyin_marketing_text_model': douyin_marketing_text_model,
        'douyin_marketing_text_api_key': douyin_marketing_text_api_key,
        'douyin_marketing_text_base_url': douyin_marketing_text_base_url,
        'douyin_marketing_vision_model': douyin_marketing_vision_model,
        'douyin_marketing_vision_api_key': douyin_marketing_vision_api_key,
        'douyin_marketing_vision_base_url': douyin_marketing_vision_base_url,
        'system_config': system_config
    }

@synchronized
def save_config(config_data):
    global config
    config = config_data
    _write_config_json_nolock(config_data)

def get_persona_llm_config(persona="sisi"):
    """Return persona-specific LLM config (api_key, base_url, model)."""
    if not config:
        load_config()
    p = (persona or "sisi").strip().lower()
    if p == "liuye":
        api_key = liuye_llm_api_key
        base_url = liuye_llm_base_url
        model = liuye_llm_model
    else:
        api_key = sisi_llm_api_key
        base_url = sisi_llm_base_url
        model = sisi_llm_model
    if not base_url or not model:
        raise RuntimeError(f"Missing LLM config for persona={p}: base_url/model required")
    if not api_key:
        raise RuntimeError(f"Missing LLM api_key for persona={p}")
    return {"api_key": api_key, "base_url": base_url, "model": model}


def get_multimodal_config():
    """
    Return multimodal feature config with safe defaults.
    Keys are read from [key] section in system.conf:
    - multimodal_max_image_mb
    - multimodal_max_video_mb
    - multimodal_max_audio_mb
    - multimodal_strategy
    - multimodal_allowed_sources
    - multimodal_retention
    """
    parser = system_config
    if parser is None:
        parser = read_system_conf()

    def _get(name, fallback):
        try:
            return parser.get("key", name, fallback=fallback)
        except Exception:
            return fallback

    def _to_int(value, fallback):
        try:
            return int(str(value).strip())
        except Exception:
            return fallback

    max_image_mb = _to_int(_get("multimodal_max_image_mb", "20"), 20)
    max_video_mb = _to_int(_get("multimodal_max_video_mb", "500"), 500)
    max_audio_mb = _to_int(_get("multimodal_max_audio_mb", "80"), 80)
    strategy = str(_get("multimodal_strategy", "direct_first") or "direct_first").strip().lower()
    allowed_sources_raw = str(_get("multimodal_allowed_sources", "local,url") or "local,url").strip()
    allowed_sources = [s.strip().lower() for s in allowed_sources_raw.split(",") if s.strip()]
    retention = str(_get("multimodal_retention", "manual_only") or "manual_only").strip().lower()

    if "local" not in allowed_sources and "url" not in allowed_sources:
        allowed_sources = ["local", "url"]

    return {
        "max_image_mb": max(1, max_image_mb),
        "max_video_mb": max(1, max_video_mb),
        "max_audio_mb": max(1, max_audio_mb),
        "strategy": strategy or "direct_first",
        "allowed_sources": allowed_sources,
        "retention": retention or "manual_only",
    }


def get_multimodal_llm_override(persona="sisi"):
    """
    Return LLM override config for multimodal requests.

    Strict mode:
    - only explicit multimodal_llm_* keys are accepted
    - no implicit fallback to other providers
    """
    parser = system_config
    if parser is None:
        parser = read_system_conf()

    def _get(name, fallback=""):
        try:
            return str(parser.get("key", name, fallback=fallback) or "").strip()
        except Exception:
            return str(fallback or "").strip()

    def _normalize_api_style(raw_style, model_name):
        style = str(raw_style or "").strip().lower()
        if style in ("openai", "anthropic"):
            return style
        model_lower = str(model_name or "").strip().lower()
        if model_lower.startswith("claude-"):
            return "anthropic"
        return "openai"

    def _sanitize(base_url, api_key, model, provider_id, api_style=""):
        b = str(base_url or "").strip().rstrip("/")
        k = str(api_key or "").strip()
        m = str(model or "").strip()
        if not b or not k or not m:
            return None
        return {
            "provider_id": str(provider_id or "multimodal_llm").strip() or "multimodal_llm",
            "base_url": b,
            "api_key": k,
            "model": m,
            "api_style": _normalize_api_style(api_style, m),
            "persona": str(persona or "sisi").strip().lower() or "sisi",
        }

    return _sanitize(
        _get("multimodal_llm_base_url", ""),
        _get("multimodal_llm_api_key", ""),
        _get("multimodal_llm_model", "") or _get("multimodal_llm_model_engine", ""),
        "multimodal_llm",
        _get("multimodal_llm_api_style", ""),
    )


# config-all helpers
def _get_base_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@synchronized
def read_config_json(base_dir=None):
    base = base_dir or _get_base_dir()
    path = os.path.join(base, "config", "config.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with codecs.open(path, encoding="utf-8") as f:
        return json.load(f)

def _write_config_json_nolock(config_data, base_dir=None):
    base = base_dir or _get_base_dir()
    path = os.path.join(base, "config", "config.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with codecs.open(path, mode="w", encoding="utf-8") as f:
        f.write(json.dumps(config_data, sort_keys=True, indent=4, separators=(",", ": ")))
    return path


@synchronized
def write_config_json(config_data, base_dir=None):
    return _write_config_json_nolock(config_data, base_dir=base_dir)


@synchronized
def read_system_conf(base_dir=None):
    base = base_dir or _get_base_dir()
    path = os.path.join(base, "system.conf")
    parser = ConfigParser()
    parser.read(path, encoding="utf-8-sig")
    return parser


def system_conf_to_dict(parser):
    out = {}
    if not parser:
        return out
    for section in parser.sections():
        out[section] = {}
        for option in parser.options(section):
            out[section][option] = parser.get(section, option, fallback="")
    return out


def dict_to_system_conf(data):
    parser = ConfigParser()
    if not isinstance(data, dict):
        return parser
    for section, kv in data.items():
        if section is None:
            continue
        parser.add_section(str(section))
        if isinstance(kv, dict):
            for k, v in kv.items():
                parser.set(str(section), str(k), "" if v is None else str(v))
    return parser


@synchronized
def write_system_conf(conf_dict, base_dir=None):
    base = base_dir or _get_base_dir()
    path = os.path.join(base, "system.conf")
    parser = dict_to_system_conf(conf_dict)
    with codecs.open(path, mode="w", encoding="utf-8") as f:
        parser.write(f)
    return path


@synchronized
def update_system_conf_keys(updates, section="key", base_dir=None):
    """
    仅更新 system.conf 指定 section 中的若干键，尽量保留原有注释与顺序。
    """
    if not isinstance(updates, dict) or not updates:
        return None
    base = base_dir or _get_base_dir()
    path = os.path.join(base, "system.conf")

    if os.path.exists(path):
        with codecs.open(path, mode="r", encoding="utf-8-sig") as f:
            text = f.read()
    else:
        text = ""

    lines = text.splitlines()
    if not lines:
        lines = [f"[{section}]", ""]

    section_lower = str(section).strip().lower()
    in_section = False
    section_start = None
    section_end = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            name = stripped[1:-1].strip().lower()
            if name == section_lower:
                in_section = True
                section_start = i
                continue
            if in_section:
                section_end = i
                in_section = False
                break

    if section_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        section_start = len(lines)
        lines.append(f"[{section}]")
        lines.append("")
        section_end = len(lines)

    found = set()
    for i in range(section_start + 1, section_end):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        for key, value in updates.items():
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} "):
                lines[i] = f"{key} = {value}"
                found.add(key)

    insert_at = section_end
    for key, value in updates.items():
        if key not in found:
            lines.insert(insert_at, f"{key} = {value}")
            insert_at += 1

    with codecs.open(path, mode="w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path

@synchronized
def get_value(key, default=None):
    """获取system.conf中的配置值"""
    if system_config and system_config.has_option('key', key):
        return system_config.get('key', key)
    return default

@synchronized
def get_yaml_value(key, default_value=None):
    """获取配置中的YAML格式值，若不存在则返回默认值"""
    if key in config:
        return config[key]
    return default_value
