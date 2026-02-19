#浣滅敤鏄煶棰戝綍鍒讹紝瀵逛簬aliyun asr鏉ヨ锛岃竟褰曞埗杈箂tt锛屼絾瀵逛簬鍏朵粬鏉ヨ锛屾槸鍏堜繚瀛樻垚鏂囦欢鍐嶆帹閫佺粰asr妯″瀷锛岄€氳繃瀹炵幇瀛愮被鐨勬柟寮忥紙sisi_booter.py 涓婃湁瀹炵幇锛夋潵绠＄悊闊抽娴佺殑鏉ユ簮
import audioop
import math
import time
import threading
import os
from abc import abstractmethod
from collections import deque
from queue import Queue

from asr.ali_nls import ALiNls
from asr.funasr import FunASR
from core import wsa_server
from scheduler.thread_manager import MyThread
from utils import util
from utils import config_util as cfg
import numpy as np
import wave
from core import sisi_core
from core import shared_state
from core import interact

# 楹﹀厠椋庡惎鍔ㄦ椂闂?(绉?
_ATTACK = 0.1

# 楹﹀厠椋庨噴鏀炬椂闂?(绉?
_RELEASE = 1.0

def _is_enabled_flag(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class Recorder:

    def __init__(self, sisi):
        self.__sisi = sisi
        self.__running = True
        self.__processing = False
        self.__history_level = []
        self.__history_data = []
        self.__dynamic_threshold = 0.5 # 澹伴煶璇嗗埆鐨勯煶閲忛槇鍊?
        # 闃叉姈涓庣ǔ瀹氭€у寮?
        self.__voiced_run = 0  # 杩炵画鏈夊０甯ц鏁?
        self.__silent_run = 0  # 杩炵画闈欓煶甯ц鏁?
        self.__threshold_min = 0.15  # 鍔ㄦ€侀槇鍊间笅鐣?
        self.__threshold_max = 0.75  # 鍔ㄦ€侀槇鍊间笂鐣?

        self.__MAX_LEVEL = 25000
        self.__MAX_BLOCK = 100
        
        # 鏈湴 ASR 妯″紡閰嶇疆
        self.ASRMode = cfg.ASR_mode
        self.__aLiNls = None
        self.is_awake = False
        self.wakeup_matched = False
        # 鍞ら啋绐楀彛鎺у埗锛堟椂闂翠笌杞锛?
        self.wake_window_seconds = int(cfg.config['source'].get('wake_window_seconds', 60))
        self.wake_window_turns = int(cfg.config['source'].get('wake_window_turns', 3))
        self.wake_remaining_turns = 0
        self.sleep_phrases = set(cfg.config['source'].get('sleep_phrases', []))
        self.wake_front_window_chars = int(cfg.config['source'].get('wake_front_window_chars', 6))
        if cfg.config['source']['wake_word_enabled']:
            self.timer = threading.Timer(self.wake_window_seconds, self._on_wake_timer_timeout)  # 鎸夐厤缃鏃?
        self.username = 'User' #榛樿鐢ㄦ埛锛屽瓙绫诲疄鐜版椂浼氶噸鍐?
        self.channels = 1
        self.sample_rate = 16000
        self.is_reading = False
        self.stream = None

        self.__last_ws_notify_time = 0
        self.__ws_notify_interval = 0.5  # 鏈€灏忛€氱煡闂撮殧锛堢锛?
        self.__ws_notify_thread = None
        # 棰勫敜閱掔紦鍐诧細鏈€澶氳浣?鍙?
        self._prewake_buffer = deque(maxlen=2)

        # AEC / ?????
        self._aec = None
        self._aec_enabled = False
        self._aec_required = False
        self._aec_frame_ms = 16
        self._aec_filter_length_ms = 200
        self._half_duplex_enabled = False
        self._half_duplex_hold_ms = 120
        self._half_duplex_tail_ms = 120
        # AEC diagnostics (throttled) for remote capture troubleshooting
        self._aec_diag_last_ts = 0.0
        self._aec_diag_interval_s = 2.0
        self._aec_diag_frames = 0
        self._aec_diag_ref_silent_frames = 0
        self._aec_diag_half_duplex_drops = 0
        # Server-side wake session authority.
        self._wake_session_epoch = 0
        self._wake_session_id = ""
        self._wake_session_open_ts = 0.0
        self._wake_session_last_ts = 0.0
        self._wake_stale_asr_drops = 0
        self._asr_result_seq = 0

    def asrclient(self):
        if self.ASRMode == "ali":
            asrcli = ALiNls(self.username)
        elif self.ASRMode == "funasr" or self.ASRMode == "sensevoice":
            asrcli = FunASR(self.username)
        return asrcli
    def _make_timestamped_input_path(self, cache_root: str) -> str:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return os.path.join(cache_root, f"input_{ts}.wav")

    def save_buffer_to_file(self, buffer):
        cache_root = cfg.cache_root or "cache_data"
        os.makedirs(cache_root, exist_ok=True)
        file_path = self._make_timestamped_input_path(cache_root)
        with wave.open(file_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(buffer)

        # 记录最近一次保存的音频文件，供后续流程复用
        self.latest_audio_file = file_path

        return file_path

    def __get_history_average(self, number):
        total = 0
        num = 0
        for i in range(len(self.__history_level) - 1, -1, -1):
            level = self.__history_level[i]
            total += level
            num += 1
            if num >= number:
                break
        return total / num

    def __get_history_percentage(self, number):
        return (self.__get_history_average(number) / self.__MAX_LEVEL) * 1.05 + 0.02

    def _build_wake_session_id(self):
        return f"{self.username}-{self._wake_session_epoch}-{int(time.time() * 1000)}"

    def _restart_wake_timer(self):
        if not cfg.config['source']['wake_word_enabled']:
            return
        try:
            self.timer.cancel()
        except Exception:
            pass
        self.timer = threading.Timer(self.wake_window_seconds, self._on_wake_timer_timeout)
        self.timer.start()

    def _open_wake_session(self, reason):
        now_ts = time.time()
        self._wake_session_epoch += 1
        self._wake_session_id = self._build_wake_session_id()
        self._wake_session_open_ts = now_ts
        self._wake_session_last_ts = now_ts
        self.wakeup_matched = True
        self.wake_remaining_turns = self.wake_window_turns
        with shared_state.auto_play_lock:
            shared_state.can_auto_play = False
        self._restart_wake_timer()
        util.log(
            1,
            "[wake_session] action=open id={} epoch={} reason={} turns={}".format(
                self._wake_session_id,
                int(self._wake_session_epoch),
                reason,
                int(self.wake_remaining_turns),
            ),
        )

    def _touch_wake_session(self):
        if not self.wakeup_matched:
            return
        self._wake_session_last_ts = time.time()

    def _close_wake_session(self, reason, clear_prewake=False):
        had_session = bool(self.wakeup_matched or self._wake_session_id)
        session_id = self._wake_session_id or "none"
        session_epoch = int(self._wake_session_epoch)
        self.wakeup_matched = False
        self.wake_remaining_turns = 0
        if clear_prewake and hasattr(self, "_prewake_buffer"):
            self._prewake_buffer.clear()
        with shared_state.auto_play_lock:
            shared_state.can_auto_play = True
        try:
            self.timer.cancel()
        except Exception:
            pass
        if had_session:
            util.log(
                1,
                "[wake_session] action=close id={} epoch={} reason={}".format(
                    session_id,
                    session_epoch,
                    reason,
                ),
            )

    def _on_wake_timer_timeout(self):
        self._close_wake_session("timer_expired")

    def reset_wakeup_status(self):
        self._close_wake_session("manual_reset")

    def apply_external_wake_hit(self, source="device_kws", keyword="", confidence=""):
        if not cfg.config['source']['wake_word_enabled']:
            util.log(
                1,
                "[wake_session] action=ignore_external_wake reason=wake_disabled source={}".format(
                    source or "unknown",
                ),
            )
            return False
        reason = "external:{}:{}".format(source or "unknown", keyword or "none")
        if self.wakeup_matched:
            self._touch_wake_session()
            self._restart_wake_timer()
            util.log(
                1,
                "[wake_session] action=touch_external_wake id={} epoch={} source={} keyword={} confidence={}".format(
                    self._wake_session_id or "none",
                    int(self._wake_session_epoch),
                    source or "unknown",
                    keyword or "",
                    confidence or "",
                ),
            )
            return True
        self._open_wake_session(reason)
        util.log(
            1,
            "[wake_session] action=apply_external_wake id={} epoch={} source={} keyword={} confidence={}".format(
                self._wake_session_id or "none",
                int(self._wake_session_epoch),
                source or "unknown",
                keyword or "",
                confidence or "",
            ),
        )
        return True

    def _normalize_text(self, text):
        """Normalize recognized text for wake matching."""
        if not text:
            return ""
        t = str(text).strip()
        # 鍘婚櫎绌虹櫧銆佸叏瑙掔┖鏍?
        t = t.replace('\u3000', ' ')
        t = ' '.join(t.split())
        # Replace common punctuation with spaces for stable wake-word matching.
        for ch in ['，', '。', '！', '？', ',', '.', '!', '?', '：', ':', '；', ';', '、', '（', '）', '(', ')']:
            t = t.replace(ch, ' ')
        return t

    def _contains_sleep_phrase(self, text):
        if not text or not self.sleep_phrases:
            return False
        t = self._normalize_text(text)
        return any(p in t for p in self.sleep_phrases)


    def _load_audio_controls(self):
        try:
            cfg.load_config()
            self._aec_enabled = str(getattr(cfg, 'aec_enabled', False)).lower() == 'true'
            self._aec_required = str(getattr(cfg, 'aec_required', False)).lower() == 'true'
            self._aec_frame_ms = int(getattr(cfg, 'aec_frame_ms', 16))
            self._aec_filter_length_ms = int(getattr(cfg, 'aec_filter_length_ms', 200))
            self._half_duplex_enabled = str(getattr(cfg, 'half_duplex_enabled', False)).lower() == 'true'
            self._half_duplex_hold_ms = int(getattr(cfg, 'half_duplex_hold_ms', 120))
            self._half_duplex_tail_ms = int(getattr(cfg, 'half_duplex_tail_ms', 120))
        except Exception:
            pass

    def _ensure_aec(self):
        if not self._aec_enabled:
            return
        if self._aec is not None:
            return
        from utils.aec import get_aec_processor
        self._aec = get_aec_processor(sample_rate=self.sample_rate)

    def _should_bypass_server_aec(self):
        """Remote device capture always uses Android-side AEC as the single owner."""
        return bool(self.is_remote())

    def _mix_to_mono(self, data):
        if self.channels == 1:
            return data
        try:
            return audioop.tomono(data, 2, 0.5, 0.5)
        except Exception:
            return data

    def _bytes_to_int16(self, data):
        return np.frombuffer(data, dtype=np.int16)
    def _should_process_input(self, text):
        """Filter trivial/noise inputs before processing."""
        try:
            if not text or len(text.strip()) == 0:
                util.log(1, "[interrupt] empty input, ignore")
                return False

            noise_patterns = ["?", "?", "?", "?", "?", "?", "?", "?", "?"]
            if text.strip() in noise_patterns:
                util.log(1, f"[interrupt] noise input ignored: {text}")
                return False

            if len(text.strip()) <= 2 and not any(keyword in text for keyword in ["?", "?", "?", "?", "?"]):
                util.log(1, f"[interrupt] too short, ignored: {text}")
                return False

            util.log(1, f"[interrupt] accept input: {text}")
            return True

        except Exception as e:
            util.log(2, f"[interrupt] check failed: {str(e)}")
            return True

    def _immediate_response(self, response_text):
        """绔嬪嵆鍥炲棰勮鐭"""
        try:
            util.log(1, f"[鏅鸿兘鎵撴柇] 绔嬪嵆鍥炲: {response_text}")
            # 楂樹紭鍏堢骇TTS杈撳嚭
            self.__sisi.say(response_text, 7)  # 鏈€楂樹紭鍏堢骇
        except Exception as e:
            util.log(2, f"[鏅鸿兘鎵撴柇] 绔嬪嵆鍥炲寮傚父: {str(e)}")

    def _stop_current_tasks(self):
        """鍋滄褰撳墠浠诲姟"""
        try:
            util.log(1, f"[鏅鸿兘鎵撴柇] 鍋滄褰撳墠浠诲姟")

            # 鍋滄褰撳墠璇磋瘽
            if hasattr(self.__sisi, 'speaking'):
                self.__sisi.speaking = False

            # 鍋滄褰撳墠澶勭悊
            if hasattr(self.__sisi, 'chatting'):
                self.__sisi.chatting = False

            # 閫夋嫨鎬ф竻绌洪煶棰戦槦鍒楋紝淇濇姢闊充箰鏂囦欢
            if hasattr(self.__sisi, 'sound_query'):
                # 淇濆瓨闊充箰鏂囦欢锛屽彧娓呯┖TTS闊抽
                music_items = []
                while not self.__sisi.sound_query.empty():
                    try:
                        item = self.__sisi.sound_query.get_nowait()
                        # 妫€鏌ユ槸鍚︿负闊充箰鏂囦欢锛堟牴鎹柊鐨勯槦鍒楁牸寮忥級
                        if len(item) >= 2 and ('music_' in str(item[1]) or 'random_generation_music' in str(item[1])):
                            music_items.append(item)  # 淇濈暀闊充箰鏂囦欢
                            util.log(1, f"[鏅鸿兘鎵撴柇] 淇濇姢闊充箰鏂囦欢: {item[1]}")
                    except:
                        break

                # 灏嗛煶涔愭枃浠堕噸鏂版斁鍥為槦鍒?
                for item in music_items:
                    self.__sisi.sound_query.put(item)

                if music_items:
                    util.log(1, f"[interrupt] preserved_music_items={len(music_items)}")

        except Exception as e:
            util.log(2, f"[鏅鸿兘鎵撴柇] 鍋滄浠诲姟寮傚父: {str(e)}")

    def _pause_current_tasks(self):
        """Pause current tasks while keeping backend tasks alive."""
        try:
            util.log(1, f"[鏅鸿兘鎵撴柇] 鏆傚仠褰撳墠浠诲姟")

            # 馃敟 浣跨敤缁熶竴鎺у埗鍣ㄧ殑鏆傚仠鍔熻兘
            from core.unified_system_controller import get_unified_controller
            unified_controller = get_unified_controller()

            # 鏆傚仠鎵€鏈夋椿鍔ㄤ絾淇濇寔API璋冪敤缁х画
            unified_controller.pause_all_activities()

            util.log(1, f"[鏅鸿兘鎵撴柇] 浠诲姟宸叉殏鍋滐紝鍚庡彴缁х画杩愯")

        except Exception as e:
            util.log(2, f"[鏅鸿兘鎵撴柇] 鏆傚仠浠诲姟寮傚父: {str(e)}")

    def __waitingResult(self, iat: asrclient, audio_data, capture_epoch=None, asr_seq=0):
        self.processing = True
        t = time.time()
        tm = time.time()
        if self.ASRMode == "funasr"  or self.ASRMode == "sensevoice":
            file_url = self.save_buffer_to_file(audio_data)
            self.__aLiNls.send_url(file_url)

        # 馃敟 闊抽鍒嗗弶锛氬壇娴佺▼鍙戦€佸埌鍓嶈剳绯荤粺锛堝悗鍙板紓姝ワ紝涓嶉樆濉炰富娴佺▼锛?
        # 馃幆 浼犻€掑凡淇濆瓨鐨勬枃浠惰矾寰勶紝閬垮厤閲嶅淇濆瓨
        audio_file_path = getattr(self, 'latest_audio_file', None)
        self._send_to_background_brain(audio_data, audio_file_path)

        # return
        # 绛夊緟缁撴灉杩斿洖锛堟寜闊抽鏃堕暱鍔ㄦ€佽缃秴鏃讹紝鍑忓皯闀垮彞琚垽绌猴級
        try:
            sr = 16000
            dur_s = len(audio_data) / sr if hasattr(audio_data, '__len__') else 0
        except Exception:
            dur_s = 0
        # 鏈€鐭?s锛屾渶闀?0s锛岄€氬父涓衡€滈煶棰戞椂闀?1.5s鈥?
        timeout_sec = max(3.0, min(10.0, (dur_s or 0) + 1.5))
        while not iat.done and (time.time() - t) < timeout_sec:
            time.sleep(0.02)
        # 鍐嶇粰缃戠粶/鍥炶皟涓€鐐圭紦鍐?
        if not iat.done and not getattr(iat, 'finalResults', ''):
            time.sleep(0.2)
        text = iat.finalResults
        util.printInfo(1, self.username, "语音处理完成！耗时: {} ms".format(math.floor((time.time() - tm) * 1000)))
        current_epoch = int(self._wake_session_epoch)
        if (
            capture_epoch is not None
            and int(capture_epoch) != current_epoch
            and self.wakeup_matched
        ):
            self._wake_stale_asr_drops += 1
            util.log(
                1,
                "[wake_session] action=drop_stale_asr seq={} capture_epoch={} current_epoch={} drops={}".format(
                    int(asr_seq),
                    int(capture_epoch),
                    int(current_epoch),
                    int(self._wake_stale_asr_drops),
                ),
            )
            self.processing = False
            return
        if len(text) > 0:
            if cfg.config['source']['wake_word_enabled']:
                #鏅€氬敜閱掓ā寮?
                if cfg.config['source']['wake_word_type'] == 'common':

                    if not self.wakeup_matched:
                        #鍞ら啋璇嶅垽鏂?
                        wake_word =  cfg.config['source']['wake_word']
                        wake_word_list = [w.strip() for w in wake_word.split(',') if w.strip()]
                        wake_up = False
                        norm_text = self._normalize_text(text)
                        for word in wake_word_list:
                            if word and (word in norm_text):
                                    wake_up = True
                        if wake_up:
                            util.printInfo(1, self.username, "唤醒成功！")
                            if wsa_server.get_web_instance() and wsa_server.get_web_instance().is_connected(self.username):
                                wsa_server.get_web_instance().add_cmd({"panelMsg": "唤醒成功！", "agent_status": "listening", "Username" : self.username , 'robot': f'http://{cfg.sisi_url}:5000/robot/Listening.jpg'})
                            if wsa_server.get_instance() and wsa_server.get_instance().is_connected(self.username):
                                content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': "唤醒成功！"}, 'Username' : self.username, 'robot': f'http://{cfg.sisi_url}:5000/robot/Listening.jpg'}
                                wsa_server.get_instance().add_cmd(content)
                            self._open_wake_session("common_wake_word")
                            #self.on_speaking(text)
                            intt = interact.Interact("auto_play", 2, {'user': self.username, 'text': "在呢，你说吧？"})
                            self.__sisi.on_interact(intt)
                            self.processing = False
                            
                        else:
                            util.printInfo(1, self.username, "[!] 等待唤醒！")
                            # 缂撳瓨鏈敜閱掕鍙ワ紝渚涗笅娆″敜閱掗杞嫾鎺?
                            try:
                                if text and len(text.strip()) > 0:
                                    self._prewake_buffer.append(text.strip())
                                    util.log(1, f"[预唤醒缓存] 已缓存: {text.strip()}")
                            except Exception:
                                pass
                            if wsa_server.get_web_instance() and wsa_server.get_web_instance().is_connected(self.username):
                                wsa_server.get_web_instance().add_cmd({"panelMsg": "[!] 等待唤醒！", "agent_status": "wake_pending", "Username" : self.username , 'robot': f'http://{cfg.sisi_url}:5000/robot/Normal.jpg'})
                            if wsa_server.get_instance() and wsa_server.get_instance().is_connected(self.username):
                                content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': "[!] 等待唤醒！"}, 'Username' : self.username, 'robot': f'http://{cfg.sisi_url}:5000/robot/Normal.jpg'}
                                wsa_server.get_instance().add_cmd(content)
                    else:
                        # 鍞ら啋绐楀彛鍐呯殑瀵硅瘽杞鎺у埗
                        if self._contains_sleep_phrase(text):
                            util.printInfo(1, self.username, "检测到休眠指令，结束唤醒窗口")
                            self._close_wake_session("sleep_phrase", clear_prewake=True)
                            self.processing = False
                        else:
                            # 棣栨杞锛氳嫢鍓嶉潰缂撳瓨浜嗘湭鍞ら啋璇彞锛屾嫾鎺ュ悗鍙戦€?
                            if self.wake_remaining_turns == self.wake_window_turns and hasattr(self, '_prewake_buffer') and self._prewake_buffer:
                                prev = " ".join(list(self._prewake_buffer))
                                merged = f"{text} {prev}".strip()
                                self._prewake_buffer.clear()
                                self.on_speaking(merged)
                                self._touch_wake_session()
                            else:
                                self.on_speaking(text)
                                self._touch_wake_session()
                            if self.wake_remaining_turns > 0:
                                self.wake_remaining_turns -= 1
                            if self.wake_remaining_turns == 0:
                                self._close_wake_session("turns_exhausted")
                            else:
                                self._restart_wake_timer()
                        self.processing = False
                
                #鍓嶇疆鍞ら啋璇嶆ā寮?
                elif  cfg.config['source']['wake_word_type'] == 'front':
                    wake_word =  cfg.config['source']['wake_word']
                    wake_word_list = [w.strip() for w in wake_word.split(',') if w.strip()]
                    norm_text = self._normalize_text(text)

                    # 宸插敜閱掔獥鍙ｏ細鏃犻渶鍐嶆鍒ゅ敜閱掕瘝
                    if self.wakeup_matched:
                        # 浼戠湢鐭
                        if self._contains_sleep_phrase(text):
                            util.printInfo(1, self.username, "[front] 检测到休眠指令，结束唤醒窗口")
                            self._close_wake_session("sleep_phrase", clear_prewake=True)
                            self.processing = False
                        else:
                            # 棣栬疆鍏滃簳鍚堝苟
                            if self.wake_remaining_turns == self.wake_window_turns and hasattr(self, '_prewake_buffer') and self._prewake_buffer:
                                prev = " ".join(list(self._prewake_buffer))
                                merged = f"{text} {prev}".strip()
                                util.log(1, f"[预唤醒拼接] front窗口已唤醒，首轮合并: {merged}")
                                self._prewake_buffer.clear()
                                self.on_speaking(merged)
                                self._touch_wake_session()
                            else:
                                self.on_speaking(text)
                                self._touch_wake_session()

                            # 杞-1 涓庤鏃跺櫒缁湡
                            if self.wake_remaining_turns > 0:
                                self.wake_remaining_turns -= 1
                            if self.wake_remaining_turns == 0:
                                self._close_wake_session("turns_exhausted")
                            else:
                                self._restart_wake_timer()
                        self.processing = False
                    else:
                        # 鏈敜閱掞細鍓嶇獥鍙ｅ尮閰嶈Е鍙?
                        wake_up = False
                        for word in wake_word_list:
                            if not word:
                                continue
                            pos = norm_text.find(word)
                            if pos == 0 or (0 <= pos < self.wake_front_window_chars):
                                util.log(1, f"[唤醒判定] front窗口触发: 词='{word}', 位置={pos}, 窗口={self.wake_front_window_chars}")
                                wake_up = True
                                break
                        if wake_up:
                            util.printInfo(1, self.username, "唤醒成功！")
                            if wsa_server.get_web_instance() and wsa_server.get_web_instance().is_connected(self.username):
                                wsa_server.get_web_instance().add_cmd({"panelMsg": "唤醒成功！", "agent_status": "listening", "Username" : self.username , 'robot': f'http://{cfg.sisi_url}:5000/robot/Listening.jpg'})
                            if wsa_server.get_instance() and wsa_server.get_instance().is_connected(self.username):
                                content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': "唤醒成功！"}, 'Username' : self.username, 'robot': f'http://{cfg.sisi_url}:5000/robot/Listening.jpg'}
                                wsa_server.get_instance().add_cmd(content)

                            # 涓嶆埅鏂敜閱掕瘝锛屾暣鍙ヨ繘鍏?
                            question = text
                            self._open_wake_session("front_wake_word")
                            from utils.stream_sentence import AudioPriorityQueue
                            self.__sisi.sound_query = AudioPriorityQueue()
                            time.sleep(0.3)
                            if hasattr(self, '_prewake_buffer') and self._prewake_buffer:
                                prev = " ".join(list(self._prewake_buffer))
                                question = f"{question} {prev}".strip()
                                util.log(1, f"[预唤醒拼接] front模式合并: {question}")
                                self._prewake_buffer.clear()
                            self.on_speaking(question)
                            self._touch_wake_session()
                            self.processing = False
                        else:
                            util.printInfo(1, self.username, "[!] 等待唤醒！")
                            # 缂撳瓨鏈敜閱掕鍙?
                            try:
                                if text and len(text.strip()) > 0:
                                    self._prewake_buffer.append(text.strip())
                                    util.log(1, f"[预唤醒缓存] 已缓存: {text.strip()}")
                            except Exception:
                                pass
                            if wsa_server.get_web_instance() and wsa_server.get_web_instance().is_connected(self.username):
                                wsa_server.get_web_instance().add_cmd({"panelMsg": "[!] 等待唤醒！", "agent_status": "wake_pending", "Username" : self.username , 'robot': f'http://{cfg.sisi_url}:5000/robot/Normal.jpg'})
                            if wsa_server.get_instance() and wsa_server.get_instance().is_connected(self.username):
                                content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': "[!] 等待唤醒！"}, 'Username' : self.username, 'robot': f'http://{cfg.sisi_url}:5000/robot/Normal.jpg'}
                                wsa_server.get_instance().add_cmd(content)

            #闈炲敜閱掓ā寮?
            else:
                 # 鍦ㄦ湭鍞ら啋鐘舵€佷笅锛屼繚瀛樻渶杩戠殑1-2鍙ョ敤鎴疯瘽鏈埌棰勫敜閱掔紦鍐?
                 try:
                     if text and len(text.strip()) > 0:
                         self._prewake_buffer.append(text.strip())
                 except Exception:
                     pass
                 self.on_speaking(text)
                 self.processing = False
        else:
            #TODO 涓轰粈涔堣繖涓涓篎alse
            # if self.wakeup_matched:
            #     self.wakeup_matched = False
            self.processing = False
            util.printInfo(1, self.username, "[!] 语音未检测到内容！")
            self.dynamic_threshold = self.__get_history_percentage(30)
            if wsa_server.get_web_instance() and wsa_server.get_web_instance().is_connected(self.username):
                wsa_server.get_web_instance().add_cmd({"panelMsg": "", "agent_status": "idle", 'Username' : self.username, 'robot': f'http://{cfg.sisi_url}:5000/robot/Normal.jpg'})
            if wsa_server.get_instance() and wsa_server.get_instance().is_connected(self.username):
                content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': ""}, 'Username' : self.username, 'robot': f'http://{cfg.sisi_url}:5000/robot/Normal.jpg'}
                wsa_server.get_instance().add_cmd(content)

    def __record(self):   
        try:
            stream = self.get_stream() #閫氳繃姝ゆ柟娉曠殑闃诲鏉ヨ绋嬪簭寰€涓嬫墽琛?
            self._load_audio_controls()
            
            # 娣诲姞瀵硅繙绋嬭澶囩殑鏀寔 - 鍏佽stream涓篘one
            if stream is None and hasattr(self, 'is_remote') and self.is_remote():
                print(f"[杩滅▼褰曢煶] {self.username} 浣跨敤杩滅▼闊抽婧愶紝璺宠繃鏈湴楹﹀厠椋庡垵濮嬪寲")
                # 浣跨敤绠€鍖栫殑褰曢煶寰幆
                while self.__running:
                    time.sleep(0.1)  # 闄嶄綆CPU浣跨敤鐜?                    # 澶勭悊杩滅▼璁惧鐨勭壒娈婇€昏緫
                    continue
                return
            if stream is None:
                util.printInfo(1, self.username, "请检查录音设备是否有误，再重新启动")
                return
            
        except Exception as e:
                print(e)
                util.printInfo(1, self.username, "请检查录音设备是否有误，再重新启动")
                return
        
        isSpeaking = False
        last_mute_time = time.time() #鐢ㄦ埛涓婃璇磋瘽瀹岃瘽鐨勬椂鍒伙紝鐢ㄤ簬VAD鐨勫紑濮嬪垽鏂紙涔熶細褰卞搷sisi璇村畬璇濆埌鏀跺惉鐢ㄦ埛璇磋瘽鐨勬椂闂撮棿闅旓級 
        last_speaking_time = time.time()#鐢ㄦ埛涓婃璇磋瘽鐨勬椂鍒伙紝鐢ㄤ簬VAD鐨勭粨鏉熷垽鏂?
        data = None
        concatenated_audio = bytearray()
        audio_data_list = []
        active_capture_epoch = int(self._wake_session_epoch)
        ref_key = "broadcast" if self.is_remote() else None
        while self.__running:
            try:
                cfg.load_config()
                source_cfg = cfg.config.get('source', {}) if isinstance(cfg.config, dict) else {}
                record_cfg = source_cfg.get('record', {}) if isinstance(source_cfg.get('record', {}), dict) else {}
                input_mode = str(source_cfg.get('input_mode', 'device_only') or 'device_only').strip().lower()
                local_capture_enabled = _is_enabled_flag(record_cfg.get('enabled', False)) and input_mode != 'device_only'

                if not local_capture_enabled and not self.is_remote():
                    time.sleep(0.2)
                    continue
                self.is_reading = True
                data = stream.read(1024, exception_on_overflow=False)
                self.is_reading = False
            except Exception as e:
                data = None
                print(e)
                util.log(1, "请检查录音设备是否有误，再重新启动")
                self.__running = False
            if not data:
                continue 
            #鏄惁鍙互鎷鹃煶,涓嶅彲浠ュ氨鎺夊純褰曢煶
            # AEC / ???
            mono_data = self._mix_to_mono(data)
            mic_rms_pre = audioop.rms(mono_data, 2) if mono_data else 0
            ref_rms = 0
            aec_ready = False
            server_aec_applied = False
            bypass_server_aec = self._should_bypass_server_aec()
            if self._half_duplex_enabled:
                try:
                    from utils import audio_ref
                    if audio_ref.should_suppress_input(time.time(), self._half_duplex_hold_ms, self._half_duplex_tail_ms, key=ref_key):
                        self._aec_diag_half_duplex_drops += 1
                        continue
                except Exception:
                    pass
            if self._aec_enabled and not bypass_server_aec:
                try:
                    self._ensure_aec()
                    from utils import audio_ref
                    ref_data = audio_ref.pop_reference_pcm(len(mono_data), key=ref_key)
                    ref_rms = audioop.rms(ref_data, 2) if ref_data else 0
                    if self._aec:
                        try:
                            aec_ready = bool(self._aec.is_ready())
                        except Exception:
                            aec_ready = True
                        mono_data = self._aec.process(mono_data, ref_data)
                        server_aec_applied = True
                except Exception:
                    if self._aec_required:
                        util.log(3, '[閿欒][AEC] required backend not available')
                        self.__running = False
                        return
                    pass
            elif bypass_server_aec:
                aec_ready = True
            mic_rms_post = audioop.rms(mono_data, 2) if mono_data else 0
            self._aec_diag_frames += 1
            if ref_rms <= 0:
                self._aec_diag_ref_silent_frames += 1
            now_diag = time.time()
            if now_diag - self._aec_diag_last_ts >= self._aec_diag_interval_s:
                util.log(
                    1,
                    "[AEC_DIAG] remote={} key={} aec_enabled={} aec_ready={} server_aec_applied={} server_aec_bypassed={} frames={} ref_silent={} half_duplex_drops={} mic_rms_pre={} mic_rms_post={} ref_rms={}".format(
                        bool(self.is_remote()),
                        ref_key or "default",
                        bool(self._aec_enabled),
                        bool(aec_ready),
                        int(bool(server_aec_applied)),
                        int(bool(bypass_server_aec)),
                        int(self._aec_diag_frames),
                        int(self._aec_diag_ref_silent_frames),
                        int(self._aec_diag_half_duplex_drops),
                        int(mic_rms_pre),
                        int(mic_rms_post),
                        int(ref_rms),
                    ),
                )
                self._aec_diag_last_ts = now_diag
                self._aec_diag_frames = 0
                self._aec_diag_ref_silent_frames = 0
                self._aec_diag_half_duplex_drops = 0
            level = audioop.rms(mono_data, 2)
            if len(self.__history_data) >= 10:#淇濆瓨婵€娲诲墠鐨勯煶棰戯紝浠ュ厤淇℃伅鎺夊け
                self.__history_data.pop(0)
            if len(self.__history_level) >= 500:
                self.__history_level.pop(0)
            self.__history_data.append(mono_data)
            self.__history_level.append(level)
            percentage = level / self.__MAX_LEVEL
            history_percentage = self.__get_history_percentage(30)
            if history_percentage > self.__dynamic_threshold:
                self.__dynamic_threshold += (history_percentage - self.__dynamic_threshold) * 0.0025
            elif history_percentage < self.__dynamic_threshold:
                self.__dynamic_threshold += (history_percentage - self.__dynamic_threshold) * 1
            
           
            #鐢ㄦ埛姝ｅ湪璇磋瘽锛屾縺娲绘嬀闊?
            try:
                if percentage > self.__dynamic_threshold:
                    last_speaking_time = time.time() 

                    if not self.__processing and not isSpeaking and time.time() - last_mute_time > _ATTACK:
                        isSpeaking = True  #鐢ㄦ埛姝ｅ湪璇磋瘽
                        active_capture_epoch = int(self._wake_session_epoch)
                        util.printInfo(1, self.username, "聆听中...")
                        if wsa_server.get_web_instance() and wsa_server.get_web_instance().is_connected(self.username):
                            wsa_server.get_web_instance().add_cmd({"panelMsg": "聆听中...", "agent_status": "listening", 'Username' : self.username, 'robot': f'http://{cfg.sisi_url}:5000/robot/Listening.jpg'})
                        if wsa_server.get_instance() and wsa_server.get_instance().is_connected(self.username):
                            content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': "聆听中..."}, 'Username' : self.username, 'robot': f'http://{cfg.sisi_url}:5000/robot/Listening.jpg'}
                            wsa_server.get_instance().add_cmd(content)
                        concatenated_audio.clear()
                        self.__aLiNls = self.asrclient()
                        task_id = self.__aLiNls.start()
                        while not self.__aLiNls.started:
                            time.sleep(0.01)
                        for i in range(len(self.__history_data) - 1): #褰撳墠data鍦ㄤ笅闈細鍋氬彂閫侊紝杩欓噷鏄彂閫佹縺娲诲墠鐨勯煶棰戞暟鎹紝浠ュ厤婕忔帀淇℃伅
                            buf = self.__history_data[i]
                            audio_data_list.append(self._bytes_to_int16(buf))
                            if self.ASRMode == "ali":
                                self.__aLiNls.send(buf)
                            else:
                                concatenated_audio.extend(buf)
                        self.__history_data.clear()
                else:#缁撴潫鎷鹃煶
                    last_mute_time = time.time()
                    if isSpeaking:
                        if time.time() - last_speaking_time > _RELEASE:
                            isSpeaking = False
                            self.__aLiNls.end()
                            util.printInfo(1, self.username, "语音处理中...")
                            
                            mono_data = self.__concatenate_audio_data(audio_data_list)
                            self._asr_result_seq += 1
                            self.__waitingResult(
                                self.__aLiNls,
                                mono_data,
                                capture_epoch=active_capture_epoch,
                                asr_seq=self._asr_result_seq,
                            )
                            cache_root = cfg.cache_root or "cache_data"
                            os.makedirs(cache_root, exist_ok=True)
                            also_timestamp = not (self.ASRMode == "funasr" or self.ASRMode == "sensevoice")
                            self.__save_audio_to_wav(
                                mono_data,
                                self.sample_rate,
                                os.path.join(cache_root, "input.wav"),
                                also_save_timestamp=also_timestamp
                            )
                            audio_data_list = []
                            active_capture_epoch = int(self._wake_session_epoch)
                
                #鎷鹃煶涓?
                if isSpeaking:
                    audio_data_list.append(self._bytes_to_int16(mono_data))
                    if self.ASRMode == "ali":
                        self.__aLiNls.send(mono_data)
                    else:
                        concatenated_audio.extend(mono_data)
            except Exception as e:
                util.printInfo(1, self.username, "褰曢煶澶辫触: " + str(e))

    def __save_audio_to_wav(self, data, sample_rate, filename, also_save_timestamp=True):
        # ensure int16
        if data.dtype != np.int16:
            data = data.astype(np.int16)

        with wave.open(filename, 'wb') as wf:
            n_channels = 1
            sampwidth = 2
            wf.setnchannels(n_channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(sample_rate)
            wf.writeframes(data.tobytes())

        if also_save_timestamp:
            cache_root = cfg.cache_root or "cache_data"
            os.makedirs(cache_root, exist_ok=True)
            ts_path = self._make_timestamped_input_path(cache_root)
            with wave.open(ts_path, 'wb') as wf:
                wf.setnchannels(n_channels)
                wf.setsampwidth(sampwidth)
                wf.setframerate(sample_rate)
                wf.writeframes(data.tobytes())
            self.latest_audio_file = ts_path


    def __concatenate_audio_data(self, audio_data_list):
        # 灏嗙疮绉殑闊抽鏁版嵁鍧楄繛鎺ヨ捣鏉?
        data = np.concatenate(audio_data_list)
        return data
    
    #杞彉涓哄崟澹伴亾np.int16
    def __process_audio_data(self, data, channels):
        data = bytearray(data)
        # 灏嗗瓧鑺傛暟鎹浆鎹负 numpy 鏁扮粍
        data = np.frombuffer(data, dtype=np.int16)
        # 閲嶅鏁扮粍锛屽皢鏁版嵁鍒嗙鎴愬涓０閬?
        data = np.reshape(data, (-1, channels))
        # 瀵规墍鏈夊０閬撶殑鏁版嵁杩涜骞冲潎锛岀敓鎴愬崟澹伴亾
        mono_data = np.mean(data, axis=1).astype(np.int16)
        return mono_data
     
    def _send_to_background_brain(self, audio_data, audio_file_path=None):
        """Send audio to background brain processing asynchronously."""
        try:
            # 妫€鏌ュ墠鑴戠郴缁熸槸鍚﹀惎鐢?
            if not hasattr(self, '_brain_enabled') or not self._brain_enabled:
                return

            # 寮傛鍙戦€佸埌鍓嶈剳绯荤粺
            import threading
            threading.Thread(
                target=self._background_brain_process,
                args=(audio_data, audio_file_path),
                daemon=True
            ).start()

        except Exception as e:
            # 后台前脑处理失败不影响主流程
            util.log(2, f"[音频分叉] 后台前脑处理失败: {e}")

    def _background_brain_process(self, audio_data, audio_file_path=None):
        """Background brain processing that reuses main-pipeline audio files."""
        try:
            # 馃敟 鑾峰彇褰撳墠杞锛屼笉閲嶅閫掑锛堜富娴佺▼宸茬粡閫掑杩囦簡锛?
            from sisi_brain.real_brain_system import get_real_brain_system
            brain_system = get_real_brain_system()

            # 鑾峰彇褰撳墠杞锛堜笉閫掑锛岄伩鍏嶉噸澶嶈鏁帮級
            current_round = brain_system.current_round

            if current_round < 3:
                util.log(1, f"[audio_split] warmup_round={current_round}, skip background analysis")
                return

            util.log(1, f"[audio_split] enabled_round={current_round}, start background analysis")
            util.log(1, "[audio_split] backend analysis only, no duplicated full brain pipeline")

            # 馃敟 浼樺厛浣跨敤涓绘祦绋嬪凡淇濆瓨鐨勬枃浠讹紝閬垮厤閲嶅淇濆瓨
            if audio_file_path and os.path.exists(audio_file_path):
                brain_audio_file = audio_file_path
                util.log(1, f"[音频分叉] ✅ 复用主流程音频文件: {brain_audio_file}")
            else:
                # 澶囩敤锛氬鏋滄病鏈変紶鍏ユ枃浠惰矾寰勶紝鎵嶄繚瀛樻柊鏂囦欢锛堥€氬父涓嶅簲璇ヨ蛋鍒拌繖閲岋級
                brain_audio_file = self.save_buffer_to_file(audio_data)
                util.log(1, f"[音频分叉] ℹ️ 主流程无文件，新建音频文件: {brain_audio_file}")

            # 闊抽鍒嗗弶涓嶈皟鐢ㄤ俊鎭閬擄紝閬垮厤閲嶅璋冪敤
            # 闊抽鍒嗗弶鐨勪綔鐢ㄦ槸鍚庡彴闊抽鍒嗘瀽锛屼笉鏄畬鏁寸殑鍓嶈剳澶勭悊
            # 淇℃伅绠￠亾搴旇鍙敱涓诲墠鑴戠郴缁熻皟鐢?

            util.log(1, "[音频分叉] 🚀 开始后台音频分析（不调用信号通道）")

            # 馃幆 鎭㈠闊抽鍒嗗弶鐨凷martAudioCollector璋冪敤
            try:
                # 馃敟 璋冪敤SmartAudioCollector杩涜鍚庡彴闊抽鍒嗘瀽
                from core.smart_audio_collector import get_smart_audio_collector

                collector = get_smart_audio_collector()
                util.log(1, "[音频分叉] 📊 开始SmartAudioCollector后台分析")

                # 鍒嗘瀽闊抽鏂囦欢
                audio_type, confidence = collector._classify_audio_type(brain_audio_file)
                util.log(1, f"[音频分叉] 🎯 音频分类结果: {audio_type}, 置信度: {confidence:.3f}")

                # 濡傛灉鏄煶涔愶紝瑙﹀彂闊充箰璇嗗埆
                if audio_type == "music" and confidence > 0.6:
                    util.log(1, "[audio_split] music detected, trigger backend music recognition")
                    # 鍒涘缓闊抽鐗囨瀵硅薄
                    from core.smart_audio_collector import AudioSegment
                    from datetime import datetime

                    segment = AudioSegment(
                        file_path=brain_audio_file,
                        timestamp=datetime.now(),
                        duration=10.0,
                        audio_type=audio_type,
                        confidence=confidence,
                        features={}
                    )

                    # 鍙戦€佺粰闊充箰璇嗗埆
                    collector._send_to_music_recognition(segment)

                util.log(1, "[音频分叉] ✅ SmartAudioCollector后台分析完成")

            except Exception as e:
                util.log(2, f"[音频分叉] SmartAudioCollector分析异常: {e}")
                # 馃敟 鍒嗗弶澶辫触涓嶅奖鍝嶄富娴佺▼锛岀户缁繍琛?

        except Exception as e:
            util.log(2, f"[音频分叉] 前脑系统后台处理异常: {e}")

    def enable_brain_background(self, enabled=True):
        """启用或禁用后台前脑系统。"""
        self._brain_enabled = enabled
        util.log(1, f"[音频分叉] 后台前脑系统: {'启用' if enabled else '禁用'}")

    def set_processing(self, processing):
        self.__processing = processing

    def start(self):
        MyThread(target=self.__record).start()

    def stop(self):
        self.__running = False

    @abstractmethod
    def on_speaking(self, text):
        pass

    # TODO: 瀛愮被瀹炵幇鍏蜂綋娴佹潵婧愶紙楹﹀厠椋庛€佹湰鍦版枃浠舵垨缃戠粶娴侊級
    @abstractmethod
    def get_stream(self):
        pass

    @abstractmethod
    def is_remote(self):
        pass

    def is_active(self):
        """
        妫€鏌ュ綍闊冲櫒鏄惁澶勪簬娲诲姩鐘舵€?
        """
        return self.__running

# 淇敼涓哄欢杩熷鍏ュ嚱鏁?
def get_wsa_server():
    from core import wsa_server
    return wsa_server



