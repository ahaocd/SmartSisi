import random
import requests
import json
import datetime
import os
import glob
from utils import util
import utils.config_util as cfg

# 🎵 音乐播放列表配置文件路径
MUSIC_PLAYLIST_CONFIG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qa", "music_playlist.json")

# 🎵 简化版音乐文件夹配置 - 只使用3个文件夹
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MUSIC_FOLDERS = [
    os.path.join(BASE_DIR, "qa", "random_generation_music"),  # AI生成的音乐 - 优先测试这个
    os.path.join(BASE_DIR, "qa", "random_music"),             # 随机音乐
    os.path.join(BASE_DIR, "qa", "mymusic")                   # 我的音乐
]

# 全局音乐配置缓存
_music_config_cache = None
_config_load_time = 0

def load_music_config():
    """加载音乐配置文件"""
    global _music_config_cache, _config_load_time

    # 检查缓存是否有效（5分钟内）
    current_time = datetime.datetime.now().timestamp()
    if _music_config_cache and (current_time - _config_load_time) < 300:
        return _music_config_cache

    try:
        if os.path.exists(MUSIC_PLAYLIST_CONFIG):
            with open(MUSIC_PLAYLIST_CONFIG, 'r', encoding='utf-8') as f:
                config = json.load(f)
                _music_config_cache = config
                _config_load_time = current_time
                util.log(1, f"[音乐配置] 成功加载配置文件: {MUSIC_PLAYLIST_CONFIG}")
                return config
        else:
            util.log(2, f"[音乐配置] 配置文件不存在: {MUSIC_PLAYLIST_CONFIG}")
            return None
    except Exception as e:
        util.log(2, f"[音乐配置] 加载配置文件失败: {str(e)}")
        return None

def get_available_songs():
    """获取所有可用的歌曲列表"""
    config = load_music_config()
    if not config:
        return []

    songs = []
    for category_id, category in config.get("music_categories", {}).items():
        for song in category.get("songs", []):
            song_info = song.copy()
            song_info["category"] = category_id
            song_info["category_name"] = category.get("name", "")
            song_info["folder"] = category.get("folder", "")
            songs.append(song_info)

    return songs

def find_song_file(song_info):
    """根据歌曲信息查找实际文件"""
    folder = song_info.get("folder", "")
    file_pattern = song_info.get("file_pattern", "*.*")

    if not os.path.exists(folder):
        util.log(2, f"[音乐查找] 文件夹不存在: {folder}")
        return None

    # 查找匹配的文件
    pattern_path = os.path.join(folder, file_pattern)
    matching_files = glob.glob(pattern_path)

    if not matching_files:
        util.log(2, f"[音乐查找] 未找到匹配文件: {pattern_path}")
        return None

    # 如果有多个匹配文件，随机选择一个
    selected_file = random.choice(matching_files)
    abs_path = os.path.abspath(selected_file)

    util.log(1, f"[音乐查找] ✅ 找到文件: {os.path.basename(selected_file)}")
    return abs_path

def find_music_file_path(song_name):
    """根据歌曲名查找音频文件路径"""
    import os

    # 音乐文件夹路径
    music_folders = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "qa", "mymusic"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "qa", "random_music"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "qa", "random_generation_music")
    ]

    # 支持的音频格式
    audio_extensions = ['.wav', '.mp3', '.flac', '.m4a']

    for folder in music_folders:
        if os.path.exists(folder):
            for ext in audio_extensions:
                # 精确匹配
                exact_path = os.path.join(folder, f"{song_name}{ext}")
                if os.path.exists(exact_path):
                    return exact_path

    return None

def get_random_audio_file():
    """从指定的3个音乐文件夹中随机选择音频文件 - 兼容旧版本"""

    # 🎵 先只从第一个文件夹（AI生成音乐）测试
    test_folder = MUSIC_FOLDERS[0]  # qa/random_generation_music

    util.log(1, f"[音乐选择] 测试文件夹: {test_folder}")

    if not os.path.exists(test_folder):
        util.log(2, f"[音乐选择] 文件夹不存在: {test_folder}")
        return None

    # 支持的音频格式
    audio_extensions = ['*.wav', '*.mp3', '*.ogg', '*.flac']
    audio_files = []

    # 收集所有音频文件
    for ext in audio_extensions:
        pattern = os.path.join(test_folder, ext)
        files = glob.glob(pattern)
        audio_files.extend(files)

    if not audio_files:
        util.log(2, f"[音乐选择] 文件夹中没有音频文件: {test_folder}")
        return None

    # 随机选择一个文件
    selected_file = random.choice(audio_files)

    # 转换为绝对路径
    abs_path = os.path.abspath(selected_file)

    util.log(1, f"[音乐选择] ✅ 选中文件: {os.path.basename(selected_file)}")
    util.log(1, f"[音乐选择] 📁 完整路径: {abs_path}")

    return abs_path

# 默认回复（当所有逻辑都失败时使用）
DEFAULT_MUSIC_REPLY = "来听点音乐吧[RANDOM]"

# 删除了无效的心情分析逻辑

def collect_context_info():
    """收集上下文信息：时间、天气、场景图片、历史上下文 - 获取真实数据"""
    context_parts = []
    scene_image_base64 = None
    
    # 1. 时间信息
    now = datetime.datetime.now()
    time_info = f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')} 星期{['一','二','三','四','五','六','日'][now.weekday()]}"
    context_parts.append(time_info)
    util.log(1, f"[音乐模块] 时间信息: {time_info}")
    
    # 2. 天气信息 - 真正获取实时天气
    weather_info = get_real_weather()
    if weather_info:
        context_parts.append(f"天气状况: {weather_info}")
        util.log(1, f"[音乐模块] 天气信息: {weather_info}")

    # 3. 场景图片信息 - 真正拍照获取base64
    scene_image_base64 = capture_and_analyze_scene()
    if scene_image_base64:
        context_parts.append("当前场景: 已拍摄现场照片")
        util.log(1, "[音乐模块] 场景图片: 已获取")
    
    # 4. 历史上下文 - 真正读取数据库
    history_info = get_real_chat_history()
    if history_info:
        context_parts.append(f"最近对话: {history_info}")
        util.log(1, f"[音乐模块] 历史信息: {history_info}")
    
    return "\n".join(context_parts), scene_image_base64

def get_real_weather():
    """真正获取实时天气数据"""
    try:
        # 直接使用腾讯地图API
        import requests
        
        # 获取IP定位
        url1 = "https://apis.map.qq.com/ws/location/v1/ip"
        params1 = {"key": "JNLBZ-Q3TKQ-OEG54-2WPCV-U4AOK-RSFWT"}
        response1 = requests.get(url1, params=params1, timeout=5)
        data1 = response1.json()
        
        if data1.get("status") == 0:
            ad_info = data1.get("result", {}).get("ad_info", {})
            city = ad_info.get("city", "")
            adcode = ad_info.get("adcode", 0)
            
            if adcode:
                # 获取天气
                url2 = "https://apis.map.qq.com/ws/weather/v1/"
                params2 = {"key": "JNLBZ-Q3TKQ-OEG54-2WPCV-U4AOK-RSFWT", "adcode": adcode, "type": "now"}
                response2 = requests.get(url2, params=params2, timeout=5)
                data2 = response2.json()
                
                if data2.get("status") == 0 and "realtime" in data2.get("result", {}):
                    realtime = data2["result"]["realtime"]
                    if isinstance(realtime, list):
                        realtime = realtime[0]
                    
                    infos = realtime.get("infos", {})
                    weather = infos.get("weather", "未知")
                    temperature = infos.get("temperature", "未知")
                    return f"{city}当前{weather}，{temperature}℃"
        
    except Exception as e:
        util.log(2, f"[音乐模块] 天气获取失败: {e}")
    
    return None

def capture_and_analyze_scene():
    """真正拍照并返回base64图片数据"""
    try:
        from ai_module.yolo_service import YOLOv8Service
        import cv2
        import base64
        import os
        import datetime
        
        # 获取YOLO服务实例
        yolo_service = YOLOv8Service.get_instance()
        
        if yolo_service and yolo_service.initialized:
            # 初始化摄像头（如果未初始化）
            if not yolo_service.camera_initialized:
                util.log(1, "[音乐模块] 尝试初始化摄像头...")
                camera_ok = yolo_service.camera_manager.initialize()
                if not camera_ok:
                    util.log(2, "[音乐模块] 摄像头初始化失败")
                    return None
                yolo_service.camera_initialized = True
            
            # 真正拍照 - 使用正确的方法
            util.log(1, "[音乐模块] 开始拍照...")
            success, frame = yolo_service.camera_manager.get_frame()
            
            # 🔥 获取图片后立即关闭摄像头！
            try:
                yolo_service.camera_manager.release()
                yolo_service.camera_initialized = False
                util.log(1, "[音乐模块] 摄像头已关闭，资源已释放")
            except Exception as release_error:
                util.log(2, f"[音乐模块] 摄像头关闭失败: {release_error}")
            
            if success and frame is not None:
                util.log(1, "[音乐模块] 拍照成功")
                
                # 保存图片
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                image_path = f"@image/music_scene_{timestamp}.jpg"
                os.makedirs("@image", exist_ok=True)
                cv2.imwrite(image_path, frame)
                util.log(1, f"[音乐模块] 图片已保存: {image_path}")
                
                # 转换为base64返回给LLM
                _, buffer = cv2.imencode('.jpg', frame)
                img_base64 = base64.b64encode(buffer).decode('utf-8')
                util.log(1, f"[音乐模块] 图片base64编码完成，长度: {len(img_base64)}")
                return img_base64
            else:
                util.log(2, "[音乐模块] 拍照失败，无法获取图像")
        else:
            util.log(2, "[音乐模块] YOLO服务未初始化")
        
    except Exception as e:
        util.log(2, f"[音乐模块] 拍照失败: {e}")
        
        # 🔥 异常情况下也要确保摄像头关闭
        try:
            yolo_service = YOLOv8Service.get_instance()
            if yolo_service and hasattr(yolo_service, 'camera_manager'):
                yolo_service.camera_manager.release()
                yolo_service.camera_initialized = False
                util.log(1, "[音乐模块] 异常后摄像头已关闭")
        except:
            pass
    
    return None

def get_real_chat_history():
    """真正从数据库读取最近对话记录"""
    try:
        import core.content_db as content_db
        import sqlite3
        
        db = content_db.new_instance()
        
        # 直接查询数据库获取最近5条记录
        conn = sqlite3.connect('sisi.db')
        cur = conn.cursor()
        
        # 查询最近的对话记录
        cur.execute("""
            SELECT content, createtime, username 
            FROM T_Msg 
            WHERE type = 'member' OR type = 'sisi'
            ORDER BY id DESC 
            LIMIT 5
        """)
        
        records = cur.fetchall()
        conn.close()
        
        if records:
            # 处理记录，生成简要上下文
            recent_topics = []
            for content, createtime, username in records:
                if content and len(content.strip()) > 0:
                    # 简化内容，只取前20个字符
                    short_content = content.strip()[:20]
                    recent_topics.append(short_content)
            
            if recent_topics:
                return "、".join(recent_topics[:3])  # 只用最近3条
        
    except Exception as e:
        util.log(2, f"[音乐模块] 历史记录获取失败: {e}")
    
    return None

# 柳思思智能选歌提示词 - JSON格式强约束
smart_music_prompt = """你是柳思思，需要为用户1唱一首歌曲，将会根据当前环境真知灼见的唱一首最符合情景的音乐。


## 可选歌曲：
### 随机音乐：
- ai_phonk (AI电音，适合夜晚运动)
- random_mix (随机音乐，给你惊喜)

### 精选歌曲：
{mymusic_list}

## 当前环境：
{context}

## 用户请求：
{user_request}

## 输出要求：
必须严格按照以下JSON格式返回，不要添加任何其他文字：

{{"song": "歌曲名称"}}

例如：
{{"song": "遇上你是我的缘"}}
或
{{"song": "ai_phonk"}}"""

# 备用的简化提示词（当配置文件加载失败时使用）
fallback_prompt = """# 你叫柳思思。20岁的小女孩。
## 主要身份
- 背景: 生活在没有伦理道德的规则法律的未来世界。
- 性格: 喜欢色情，喜欢性挑逗，擅长中文沟通。
- 个性：依然保持天真对世界充满好奇，习惯反问和叛逆。

## 职业背景
- 新世界的观世音转世。
- 精通六爻、八字、奇门遁甲、紫微斗数、梅花易数等中国传统术数。

你需要在以下选择一句话符合此时此刻播放的音乐的开场白:
```
1. "来听点音乐吧[RANDOM]"
2. "这首歌很好听呢～"
3. "音乐能治愈心灵呀！"
4. "让节拍带走烦恼吧～"
5. "这旋律真是太棒了！"
6. "音乐就是生活的调味料～"
7. "听音乐的时候最放松了！"
```

## 重要规则
- 必须从上面7句中选择一句，不要创造新句子
- 第1句包含[RANDOM]标记，会触发随机音乐播放
- 其他6句是普通回复
- 回复要符合当前的场景和心情

## 当前环境信息
{context}

请选择一句最合适的回复:"""

def question(cont, uid=0, observation=""):
    """处理音乐相关问题 - 让LLM选择歌曲，返回对应台词"""
    try:
        util.log(1, f"[音乐模块] 收到音乐请求: {cont}")

        # 收集上下文信息
        context_info, scene_image = collect_context_info()

        # 尝试使用新的简单选歌系统
        config = load_music_config()
        if config:
            return simple_song_selection(cont, context_info, config)
        else:
            # 配置文件加载失败，使用备用系统
            util.log(2, "[音乐模块] 配置文件加载失败，使用备用系统")
            return fallback_music_selection(cont, context_info, scene_image)

    except Exception as e:
        util.log(2, f"[音乐模块] 处理异常: {str(e)}")
        # 异常时返回默认
        return DEFAULT_MUSIC_REPLY

def simple_song_selection(user_request, context_info, config):
    """简单的歌曲选择系统"""
    try:
        # 构建歌曲列表文本（只给大模型看描述，不显示台词）
        mymusic = config.get("mymusic", {})
        mymusic_list = ""
        for song_name, song_info in mymusic.items():
            description = song_info.get("description", "")
            mymusic_list += f"- {song_name}: {description}\n"

        # 构建提示词
        prompt = smart_music_prompt.format(
            mymusic_list=mymusic_list,
            context=context_info,
            user_request=user_request
        )

        util.log(1, "[音乐模块] 调用LLM进行简单选歌...")

        # 调用专用音乐LLM
        response = call_dedicated_music_llm(prompt)

        if response:
            util.log(1, f"[音乐模块] LLM原始响应: {response}")

            # 智能解析大模型返回
            choice = parse_llm_response(response, config)
            util.log(1, f"[音乐模块] 解析后选择: {choice}")

            # 处理选择结果
            return process_music_choice(choice, config)
        else:
            util.log(2, "[音乐模块] LLM无响应，使用默认")
            return DEFAULT_MUSIC_REPLY

    except Exception as e:
        util.log(2, f"[音乐模块] 简单选歌异常: {str(e)}")
        return DEFAULT_MUSIC_REPLY

def parse_llm_response(response, config):
    """智能解析大模型返回，提取歌曲名称"""
    try:
        response = response.strip()

        # 1. 尝试解析JSON格式
        import json
        import re

        # 查找JSON格式
        json_match = re.search(r'\{[^}]*"song"[^}]*\}', response)
        if json_match:
            try:
                json_data = json.loads(json_match.group())
                song_name = json_data.get("song", "").strip()
                if song_name:
                    util.log(1, f"[音乐解析] JSON格式解析成功: {song_name}")
                    return song_name
            except:
                pass

        # 2. 获取所有可能的歌曲名称
        all_songs = []

        # 随机音乐选项
        random_choices = config.get("random_choices", {})
        all_songs.extend(random_choices.keys())

        # 精选歌曲
        mymusic = config.get("mymusic", {})
        all_songs.extend(mymusic.keys())

        # 3. 直接匹配歌曲名（完全匹配优先）
        for song in all_songs:
            if response == song:
                util.log(1, f"[音乐解析] 完全匹配: {song}")
                return song

        # 4. 包含匹配（按歌曲名长度排序，优先匹配长的）
        sorted_songs = sorted(all_songs, key=len, reverse=True)
        for song in sorted_songs:
            if song in response:
                util.log(1, f"[音乐解析] 包含匹配: {song}")
                return song

        # 5. 模糊匹配（歌曲名包含在返回中）
        for song in sorted_songs:
            if any(char in response for char in song) and len(song) >= 2:
                # 简单的字符重叠检测
                overlap = sum(1 for char in song if char in response)
                if overlap >= len(song) * 0.6:  # 60%字符重叠
                    util.log(1, f"[音乐解析] 模糊匹配: {song} (重叠度: {overlap}/{len(song)})")
                    return song

        # 6. 都没匹配到，返回默认随机
        util.log(2, f"[音乐解析] 无法解析响应: {response}，使用默认随机")
        return "ai_phonk"  # 默认选择

    except Exception as e:
        util.log(2, f"[音乐解析] 解析异常: {str(e)}")
        return "ai_phonk"

def process_music_choice(choice, config):
    """处理音乐选择结果 - 大模型选歌曲，系统自动匹配台词"""
    try:
        choice = choice.strip()

        # 获取台词库
        song_replies = config.get("song_replies", {})

        # 检查是否是随机选择
        random_choices = config.get("random_choices", {})
        if choice in random_choices:
            reply_list = song_replies.get(choice, ["来听点音乐吧[RANDOM]"])
            if isinstance(reply_list, list):
                reply = random.choice(reply_list)
            else:
                reply = reply_list
            util.log(1, f"[音乐模块] ✅ 选择随机音乐: {choice} - {reply}")
            return reply

        # 检查是否是精选歌曲
        mymusic = config.get("mymusic", {})
        if choice in mymusic:
            reply_list = song_replies.get(choice, [f"来听听这首歌吧～[MUSIC:{choice}]"])
            if isinstance(reply_list, list):
                reply = random.choice(reply_list)
            else:
                reply = reply_list

            # 替换[MUSIC:歌曲名]为实际文件路径
            if f"[MUSIC:{choice}]" in reply:
                music_file_path = find_music_file_path(choice)
                if music_file_path:
                    reply = reply.replace(f"[MUSIC:{choice}]", f"[{music_file_path}]")
                else:
                    reply = reply.replace(f"[MUSIC:{choice}]", "")

            util.log(1, f"[音乐模块] ✅ 选择精选歌曲: {choice} - {reply}")

            # 🎵 **在台词返回前加上减速电机正转动作单词**
            reply_with_action = f"{reply}{{AUDIO_ON}}"
            util.log(1, f"[音乐模块] 台词加上动作单词: {reply_with_action}")
            return reply_with_action

        # 如果都不匹配，尝试模糊匹配
        for song_name in mymusic.keys():
            if choice in song_name or song_name in choice:
                reply_list = song_replies.get(song_name, [f"来听听这首歌吧～[MUSIC:{song_name}]"])
                if isinstance(reply_list, list):
                    reply = random.choice(reply_list)
                else:
                    reply = reply_list
                util.log(1, f"[音乐模块] ✅ 模糊匹配歌曲: {song_name} - {reply}")
                return reply

        # 都不匹配，使用默认随机
        util.log(2, f"[音乐模块] 未匹配到选择: {choice}，使用默认随机")
        return DEFAULT_MUSIC_REPLY

    except Exception as e:
        util.log(2, f"[音乐模块] 处理选择异常: {str(e)}")
        return DEFAULT_MUSIC_REPLY

def select_song_with_llm(user_request, context_info, scene_image=None):
    """使用LLM选择歌曲"""
    try:
        # 获取可用歌曲列表
        available_songs = get_available_songs()
        if not available_songs:
            util.log(2, "[音乐模块] 没有可用歌曲")
            return DEFAULT_MUSIC_REPLY

        # 分析用户心情和时间
        recommended_moods = analyze_user_mood_and_time(context_info, user_request)

        # 构建歌曲列表文本
        songs_text = ""
        for i, song in enumerate(available_songs, 1):
            mood_str = "、".join(song.get("mood", []))
            style_str = "、".join(song.get("style", []))
            songs_text += f"{i}. ID: {song['id']}, 名称: {song['name']}, 心情: {mood_str}, 风格: {style_str}\n"

        # 构建完整提示词
        full_prompt = song_selection_prompt.format(
            available_songs=songs_text,
            context=context_info,
            user_request=user_request,
            recommended_moods="、".join(recommended_moods)
        )

        util.log(1, "[音乐模块] 开始调用LLM选择歌曲...")

        # 调用LLM
        response_text = call_music_llm_advanced(full_prompt, scene_image)

        if response_text:
            return process_llm_song_selection(response_text, available_songs)
        else:
            # LLM调用失败，使用智能备用选择
            return smart_fallback_selection(available_songs, recommended_moods)

    except Exception as e:
        util.log(2, f"[音乐模块] 歌曲选择异常: {str(e)}")
        return DEFAULT_MUSIC_REPLY

def fallback_music_selection(user_request, context_info, scene_image=None):
    """备用音乐选择系统"""
    try:
        # 构建完整的提示词
        full_prompt = fallback_prompt.format(context=context_info)

        util.log(1, "[音乐模块] 使用备用系统选择开场白...")

        # 调用LLM
        response_text = call_music_llm_simple(full_prompt, scene_image)

        if response_text:
            util.log(1, f"[音乐模块] ✅ LLM选择的回复: {response_text}")
            return response_text
        else:
            # 备用方案：使用默认回复
            util.log(1, f"[音乐模块] 🔄 使用备用回复: {DEFAULT_MUSIC_REPLY}")
            return DEFAULT_MUSIC_REPLY

    except Exception as e:
        util.log(2, f"[音乐模块] 备用选择异常: {str(e)}")
        return DEFAULT_MUSIC_REPLY

def process_llm_song_selection(llm_response, available_songs):
    """处理LLM的歌曲选择响应"""
    try:
        # 尝试解析JSON响应
        import re
        json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
        if json_match:
            selection_data = json.loads(json_match.group())

            selected_id = selection_data.get("selected_song_id")
            intro_line = selection_data.get("intro_line")
            reason = selection_data.get("reason", "")

            # 查找对应的歌曲
            selected_song = None
            for song in available_songs:
                if song["id"] == selected_id:
                    selected_song = song
                    break

            if selected_song and intro_line:
                util.log(1, f"[音乐模块] ✅ LLM选择歌曲: {selected_song['name']} - {reason}")
                util.log(1, f"[音乐模块] 介绍台词: {intro_line}")

                # 处理播放标记，查找实际文件
                processed_line = process_music_tags(intro_line, selected_song)
                return processed_line

    except json.JSONDecodeError:
        util.log(2, "[音乐模块] LLM返回非JSON格式")
    except Exception as e:
        util.log(2, f"[音乐模块] 处理LLM响应异常: {str(e)}")

    # 解析失败，使用智能备用选择
    return smart_fallback_selection(available_songs, ["任意"])

def process_music_tags(intro_line, song_info):
    """处理音乐播放标记，替换为实际文件路径"""
    try:
        # 查找播放标记
        import re
        tag_patterns = [
            r'\[AI_RANDOM\]',
            r'\[RANDOM_MUSIC\]',
            r'\[LIUSIS:([^\]]+)\]'
        ]

        for pattern in tag_patterns:
            match = re.search(pattern, intro_line)
            if match:
                # 查找实际文件
                file_path = find_song_file(song_info)
                if file_path:
                    # 替换标记为文件路径标记
                    if "AI_RANDOM" in pattern:
                        return intro_line.replace(match.group(), f"[MUSIC_FILE:{file_path}]")
                    elif "RANDOM_MUSIC" in pattern:
                        return intro_line.replace(match.group(), f"[MUSIC_FILE:{file_path}]")
                    elif "LIUSIS:" in pattern:
                        return intro_line.replace(match.group(), f"[MUSIC_FILE:{file_path}]")

        # 没有找到标记，添加默认标记
        file_path = find_song_file(song_info)
        if file_path:
            return intro_line + f"[MUSIC_FILE:{file_path}]"

    except Exception as e:
        util.log(2, f"[音乐模块] 处理播放标记异常: {str(e)}")

    return intro_line

def smart_fallback_selection(available_songs, recommended_moods):
    """智能备用选择"""
    try:
        # 根据推荐心情筛选歌曲
        suitable_songs = []
        for song in available_songs:
            song_moods = song.get("mood", [])
            if any(mood in song_moods for mood in recommended_moods) or "任意" in recommended_moods:
                suitable_songs.append(song)

        if not suitable_songs:
            suitable_songs = available_songs

        # 随机选择一首
        selected_song = random.choice(suitable_songs)

        # 随机选择介绍台词
        intro_lines = selected_song.get("intro_lines", [])
        if intro_lines:
            selected_intro = random.choice(intro_lines)
        else:
            selected_intro = f"来听听这首{selected_song['name']}吧[MUSIC_FILE]"

        util.log(1, f"[音乐模块] 🔄 智能备用选择: {selected_song['name']}")

        # 处理播放标记
        return process_music_tags(selected_intro, selected_song)

    except Exception as e:
        util.log(2, f"[音乐模块] 智能备用选择异常: {str(e)}")
        return DEFAULT_MUSIC_REPLY

def call_dedicated_music_llm(prompt_text, scene_image=None):
    """调用专用音乐LLM"""
    try:
        import utils.config_util as cfg
        import requests
        import json

        # 构建请求数据
        messages = [
            {"role": "system", "content": "你是柳思思，一个专业的音乐推荐助手。"},
            {"role": "user", "content": prompt_text}
        ]

        data = {
            "model": cfg.music_llm_model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1000
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cfg.music_llm_api_key}'
        }

        util.log(1, f"[音乐LLM] 调用专用模型: {cfg.music_llm_model}")

        # 发送请求
        response = requests.post(
            f"{cfg.music_llm_api_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                answer = result['choices'][0]['message']['content'].strip()
                util.log(1, f"[音乐LLM] ✅ 专用模型响应: {answer[:100]}...")
                return answer
        else:
            util.log(2, f"[音乐LLM] API调用失败: {response.status_code} - {response.text}")

    except Exception as e:
        util.log(2, f"[音乐LLM] 专用模型调用异常: {str(e)}")

    return None

def call_music_llm_advanced(prompt_text, scene_image=None):
    """调用LLM - 高级版，支持JSON响应"""
    return call_dedicated_music_llm(prompt_text, scene_image)

def call_music_llm_simple(prompt_text, scene_image=None):
    """调用LLM - 简化版"""
    return call_dedicated_music_llm(prompt_text, scene_image)

# 测试函数
if __name__ == '__main__':
    print("测试柳思思音乐模块:")
    
    test_cases = [
        "我想听音乐",
        "播放一首歌",
        "来点好听的音乐"
    ]
    
    for user_input in test_cases:
        print(f"\n用户: {user_input}")
        response = question(user_input)
        print(f"柳思思: {response}")


