import os
import time
import requests
import cv2
import numpy as np
import base64
import threading
import json
from utils import util, config_util as cfg
import random
from core.interact import Interact
from .baidu_api_manager import BaiduAPIManager
from .observation_config import (
    OBSERVATION_TRIGGERS, 
    ATTRIBUTE_MAPPINGS, 
    ATMOSPHERE_CONFIG, 
    PERSON_FEATURES,
    LANGUAGE_STRUCTURE
)
from .templates import DIALOGUE_TEMPLATES, TIME_PERIOD_TEMPLATES, COMMAND_TEMPLATES
from .opening_config import OpeningManager
from core import wsa_server
import math

class YOLOv8:
    """
    人体分析模块 - 使用百度人体分析API
    """
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super(YOLOv8, cls).__new__(cls)
                # 初始化实例属性
                cls._instance.camera_lock = threading.Lock()
                cls._instance.cache_lock = threading.Lock()
                cls._instance.status = False
                cls._instance.last_img = None
                cls._instance.last_detection_time = 0
                cls._instance.cap = None
                cls._instance.api_manager = None
                cls._instance.opening_manager = OpeningManager()
            return cls._instance

    def __init__(self):
        """初始化"""
        from core import wsa_server
        try:
            util.log(1, "[初始化] 👁️ 开始初始化LIUSISI的EYES... 👁️")
            
            # 导入配置(确保在使用前导入)
            from ai_module.observation_config import ATTRIBUTE_MAPPINGS
            from ai_module.templates import DIALOGUE_TEMPLATES
            
            # 设置类属性
            self.ATTRIBUTE_MAPPINGS = ATTRIBUTE_MAPPINGS
            self.DIALOGUE_TEMPLATES = DIALOGUE_TEMPLATES
            
            # 添加手势映射
            self.ATTRIBUTE_MAPPINGS["gesture"] = {
                "wave": "挥手",
                "point": "指点",
                "pray": "祈祷",
                "hold": "持物",
                "clap": "鼓掌",
                "unknown": "未知手势"
            }
            
            # 初始化锁和状态
            self.camera_lock = threading.Lock()
            self.cache_lock = threading.Lock()
            self.status = False
            self.last_img = None
            self.last_detection_time = 0
            self.cap = None
            
            # 初始化API管理器和开场白管理器
            self.api_manager = BaiduAPIManager.get_instance()
            self.opening_manager = OpeningManager()
            
            # 添加API锁
            self.api_lock = threading.Lock()
            self.access_token = None
            self.last_token_time = 0
            self.context_memory = {}
            self.last_observation = None
            self.last_features = None
            self.cache = {}
            self._last_camera_time = 0
            
            # 添加命令处理锁和命令历史记录
            self.command_lock = threading.Lock()
            self.last_command_type = None
            self.last_command_time = 0
            self.command_cooldown = 5.0  # 命令冷却时间，5秒内不重复处理相同命令
            
            util.log(1, "[初始化] ✨ LIUSISI的EYES初始化成功 ✨")
            
        except Exception as e:
            util.log(1, f"[错误] YOLOv8初始化失败: {str(e)}")
            raise

    @classmethod
    def new_instance(cls):
        """获取YOLOv8单例"""
        instance = cls()
        instance.status = True  # 设置初始状态为启用
        return instance

    def get_status(self):
        """获取状态"""
        with self.camera_lock:
            return self.status and self.cap is not None and self.cap.isOpened()

    def initialize(self):
        """初始化摄像头和API服务"""
        with self.camera_lock:
            try:
                # 如果状态被禁用，直接返回 False
                if not self.status:
                    return False
                    
                util.log(1, "👁️ 开始初始化LIUSISI的EYES... 👁️")
                
                # 检查API配置
                cfg.load_config()
                if not cfg.baidu_body_app_id or not cfg.baidu_body_api_key or not cfg.baidu_body_secret_key:
                    util.log(1, "[x] 百度人体分析API配置缺失，请检查system.conf")
                    return False
                util.log(1, "API配置验证通过")
                    
                # 初始化摄像头
                util.log(1, "正在初始化摄像头...")
                if self.cap is not None and self.cap.isOpened():
                    util.log(1, "关闭已存在的摄像头连接")
                    self.cap.release()
                    self.cap = None
                
                # 尝试不同的摄像头初始化方式
                backends = [
                    (cv2.CAP_DSHOW, "DirectShow"),
                    (0, "默认"),
                    (cv2.CAP_MSMF, "Media Foundation"),
                    (cv2.CAP_ANY, "自动选择")
                ]
                
                success = False
                for backend, backend_name in backends:
                    util.log(1, f"尝试使用 {backend_name} 后端打开摄像头...")
                    if self._try_camera_backend(backend, backend_name):
                        success = True
                        break
                
                if not success or not self.cap or not self.cap.isOpened():
                    util.log(1, "[x] 所有后端都无法打开摄像头，请检查:")
                    util.log(1, "1. 摄像头是否正确连接")
                    util.log(1, "2. 摄像头ID是否正确")
                    util.log(1, "3. 其他程序是否占用摄像头")
                    return False
                
                # 验证API access token
                util.log(1, "正在验证百度API access token...")
                if not self.api_manager.get_access_token():
                    util.log(1, "[x] 验证百度API失败，请检查API密钥配置")
                    self.close()
                    return False
                
                util.log(1, "百度API验证成功")
                self.status = True
                util.log(1, "✨ LIUSISI的EYES初始化完成 ✨")
                return True
                
            except Exception as e:
                util.log(1, f"[x] 初始化过程发生异常: {str(e)}")
                import traceback
                util.log(1, traceback.format_exc())
                self.close()
                self.status = False
                return False

    def close(self):
        """关闭摄像头和清理资源"""
        with self.camera_lock:
            try:
                if hasattr(self, 'cap') and self.cap is not None:
                    self.cap.release()
                    self.cap = None
                    self.status = False  # 更新状态
                    util.log(1, "摄像头已关闭")
            except Exception as e:
                util.log(1, f"关闭摄像头时出错: {str(e)}")
            finally:
                self.status = False  # 确保状态被更新

    def _map_attribute(self, category, value):
        """映射属性值到中文描述"""
        if not value:
            return self.ATTRIBUTE_MAPPINGS[category].get("unknown")
        return self.ATTRIBUTE_MAPPINGS[category].get(value.lower(), value)

    def _extract_attributes(self, person):
        """提取人物属性"""
        if not person:
            return None
        
        try:
            attrs = person.get("attributes", {})
            if not attrs:
                return None
            
            # 基本属性
            basic_attrs = {
                "gender": attrs.get("gender", {}).get("name", "未知"),
                "age": attrs.get("age", {}).get("name", "未知"),
                "face_mask": attrs.get("face_mask", {}).get("name", "no") == "yes",
                "glasses": attrs.get("glasses", {}).get("name", "no") == "yes",
                "hat": attrs.get("headwear", {}).get("name", "no") == "yes",
                "bag": attrs.get("bag", {}).get("name", "no") == "yes",
                "smoking": attrs.get("smoke", {}).get("name", "no") == "yes",  # 抽烟
                "calling": attrs.get("cellphone", {}).get("name", "no") == "yes"  # 手机使用
            }
            
            # 上衣属性
            upper_wear = {
                "type": attrs.get("upper_wear", {}).get("name", "未知"),
                "color": attrs.get("upper_color", {}).get("name", "未知"),
                "texture": attrs.get("upper_wear_texture", {}).get("name", "未知"),
                "sleeve_length": attrs.get("upper_wear_sleeve_length", {}).get("name", "未知")
            }
            
            # 下装属性
            lower_wear = {
                "type": attrs.get("lower_wear", {}).get("name", "未知"),
                "color": attrs.get("lower_color", {}).get("name", "未知"),
                "length": attrs.get("lower_wear_length", {}).get("name", "未知")
            }
            
            # 鞋子属性
            shoes = {
                "type": attrs.get("shoes", {}).get("name", "未知"),
                "color": attrs.get("shoes_color", {}).get("name", "未知")
            }
            
            # 行为属性
            behaviors = {
                "smoking": attrs.get("smoke", {}).get("name", "no") == "yes",
                "calling": attrs.get("cellphone", {}).get("name", "no") == "yes",
                "carrying": attrs.get("carrying_item", {}).get("name", "no") == "yes",
                "umbrella": attrs.get("umbrella", {}).get("name", "no") == "yes"
            }
            
            # 姿态属性
            pose = {
                "orientation": attrs.get("orientation", {}).get("name", "未知"),
                "standing": attrs.get("is_standing", {}).get("name", "no") == "yes",
                "sitting": attrs.get("is_sitting", {}).get("name", "no") == "yes",
                "lying": attrs.get("is_lying", {}).get("name", "no") == "yes"
            }
            
            # 头发属性
            hair = {
                "length": attrs.get("hair_length", {}).get("name", "未知"),
                "style": attrs.get("hair_style", {}).get("name", "未知"),
                "color": attrs.get("hair_color", {}).get("name", "未知")
            }
            
            # 组合所有属性
            return {
                "basic": basic_attrs,
                "upper_wear": upper_wear,
                "lower_wear": lower_wear,
                "shoes": shoes,
                "behaviors": behaviors,
                "pose": pose,
                "hair": hair,
                "distance": "unknown"
            }
            
        except Exception as e:
            util.log(1, f"属性提取失败: {str(e)}")
            return None

    def _extract_gestures(self, gesture_result):
        """提取手势信息"""
        gestures = []
        if "result" in gesture_result:
            for gesture in gesture_result["result"]:
                if isinstance(gesture, dict):
                    gesture_type = gesture.get("classname", "unknown")
                    gestures.append({
                        "type": self._map_attribute("gesture", gesture_type),
                        "probability": gesture.get("probability", 0)
                    })
        return gestures

    def _extract_keypoints(self, keypoint_result):
        """提取关键点信息"""
        keypoints = {}
        if "body_parts" in keypoint_result:
            for part_name, part_info in keypoint_result["body_parts"].items():
                if isinstance(part_info, dict):
                    keypoints[part_name] = {
                        "x": float(part_info.get("x", 0)),
                        "y": float(part_info.get("y", 0)),
                        "score": float(part_info.get("score", 0))
                    }
        return keypoints

    def _analyze_actions(self, body_parts):
        """分析人物动作"""
        try:
            actions = []
            
            if not body_parts:
                return actions
            
            # 分析站/坐姿态
            hip = body_parts.get("hip", {})
            knee = body_parts.get("right_knee", {}) or body_parts.get("left_knee", {})
            if hip and knee:
                hip_y = float(hip.get("y", 0))
                knee_y = float(knee.get("y", 0))
                if abs(hip_y - knee_y) < 50:
                    actions.append("sitting")
                else:
                    actions.append("standing")
            
            # 分析手部动作
            if self._is_using_phone(body_parts):
                actions.append("using_phone")
            if self._is_waving(body_parts):
                actions.append("waving")
            if self._is_pointing(body_parts):
                actions.append("pointing")
            if self._is_praying(body_parts):
                actions.append("praying")
            
            # 增加新的动作分析逻辑
            if self._is_dancing(body_parts):
                actions.append("dancing")
            if self._is_clapping(body_parts):
                actions.append("clapping")
            if self._is_sitting_crosslegged(body_parts):
                actions.append("sitting_crosslegged")
                
            # 分析脸部动作
            face_actions = self._analyze_face_actions(body_parts)
            if face_actions:
                actions.extend(face_actions)
            
            return actions
            
        except Exception as e:
            util.log(1, f"分析动作时出错: {str(e)}")
            return []

    def _analyze_face_actions(self, body_parts):
        """分析脸部动作"""
        try:
            face_actions = []
            
            if not body_parts:
                return face_actions
                
            # 获取关键点
            nose = body_parts.get("nose", {})
            left_eye = body_parts.get("left_eye", {})
            right_eye = body_parts.get("right_eye", {})
            mouth = body_parts.get("mouth", {})
            neck = body_parts.get("neck", {})
            
            # 检测头部姿态
            if nose and neck:
                nose_x = float(nose.get("x", 0))
                nose_y = float(nose.get("y", 0))
                neck_x = float(neck.get("x", 0))
                neck_y = float(neck.get("y", 0))
                
                # 头部倾斜
                if abs(nose_x - neck_x) > 30:
                    face_actions.append("head_tilt")
                
                # 点头/抬头
                angle = math.degrees(math.atan2(nose_y - neck_y, nose_x - neck_x))
                if angle > 20:
                    face_actions.append("head_down")
                elif angle < -20:
                    face_actions.append("head_up")
            
            # 检测眼睛状态
            if left_eye and right_eye:
                left_score = float(left_eye.get("score", 0))
                right_score = float(right_eye.get("score", 0))
                
                if left_score < 0.3 and right_score < 0.3:
                    face_actions.append("eyes_closed")
                elif left_score > 0.7 and right_score > 0.7:
                    face_actions.append("eyes_open")
            
            # 检测嘴部动作
            if mouth:
                mouth_height = float(mouth.get("height", 0))
                mouth_score = float(mouth.get("score", 0))
                
                if mouth_height > 20 and mouth_score > 0.5:
                    face_actions.append("mouth_open")
                elif mouth_height < 10 and mouth_score > 0.5:
                    face_actions.append("mouth_closed")
            
            return face_actions
            
        except Exception as e:
            util.log(1, f"分析脸部动作时出错: {str(e)}")
            return []

    def _is_using_phone(self, body_parts):
        """检测是否在使用手机"""
        try:
            head = body_parts.get("head", {})
            left_hand = body_parts.get("left_hand", {})
            right_hand = body_parts.get("right_hand", {})
            
            if head and (left_hand or right_hand):
                head_y = float(head.get("y", 0))
                left_hand_y = float(left_hand.get("y", 0)) if left_hand else 0
                right_hand_y = float(right_hand.get("y", 0)) if right_hand else 0
                
                return (abs(left_hand_y - head_y) < 100) or (abs(right_hand_y - head_y) < 100)
        except:
            pass
        return False

    def _is_praying(self, body_parts):
        """检测是否在祈祷/作揖"""
        try:
            left_hand = body_parts.get("left_hand", {})
            right_hand = body_parts.get("right_hand", {})
            
            if left_hand and right_hand:
                left_x = float(left_hand.get("x", 0))
                right_x = float(right_hand.get("x", 0))
                left_y = float(left_hand.get("y", 0))
                right_y = float(right_hand.get("y", 0))
                return abs(left_x - right_x) < 50 and abs(left_y - right_y) < 50
        except:
            pass
        return False

    def _is_waving(self, body_parts):
        """检测是否在挥手"""
        try:
            left_hand = body_parts.get("left_hand", {})
            right_hand = body_parts.get("right_hand", {})
            left_elbow = body_parts.get("left_elbow", {})
            right_elbow = body_parts.get("right_elbow", {})
            
            def is_hand_above_elbow(hand, elbow):
                if hand and elbow:
                    return float(hand.get("y", 0)) < float(elbow.get("y", 0))
                return False
            
            return is_hand_above_elbow(left_hand, left_elbow) or is_hand_above_elbow(right_hand, right_elbow)
        except:
            pass
        return False

    def _is_pointing(self, body_parts):
        """检测是否在指点"""
        try:
            left_hand = body_parts.get("left_hand", {})
            right_hand = body_parts.get("right_hand", {})
            left_elbow = body_parts.get("left_elbow", {})
            right_elbow = body_parts.get("right_elbow", {})
            
            def is_hand_extended(hand, elbow):
                if hand and elbow:
                    dx = float(hand.get("x", 0)) - float(elbow.get("x", 0))
                    dy = float(hand.get("y", 0)) - float(elbow.get("y", 0))
                    distance = (dx * dx + dy * dy) ** 0.5
                    return distance > 100
                return False
            
            return is_hand_extended(left_hand, left_elbow) or is_hand_extended(right_hand, right_elbow)
        except:
            pass
        return False

    def _is_clapping(self, body_parts):
        """检测是否在鼓掌"""
        try:
            left_hand = body_parts.get("left_hand", {})
            right_hand = body_parts.get("right_hand", {})
            
            if left_hand and right_hand:
                left_x = float(left_hand.get("x", 0))
                right_x = float(right_hand.get("x", 0))
                left_y = float(left_hand.get("y", 0))
                right_y = float(right_hand.get("y", 0))
                
                # 检查双手是否在相近的高度且距离适中
                height_diff = abs(left_y - right_y)
                width_diff = abs(left_x - right_x)
                
                return height_diff < 50 and width_diff < 100
        except:
            pass
        return False

    def _is_sitting_crosslegged(self, body_parts):
        """检测是否盘腿而坐"""
        try:
            left_knee = body_parts.get("left_knee", {})
            right_knee = body_parts.get("right_knee", {})
            left_ankle = body_parts.get("left_ankle", {})
            right_ankle = body_parts.get("right_ankle", {})
            
            if all([left_knee, right_knee, left_ankle, right_ankle]):
                # 检查膝盖是否在同一高度
                knee_height_diff = abs(float(left_knee.get("y", 0)) - float(right_knee.get("y", 0)))
                
                # 检查脚踝是否交叉
                ankle_x_diff = abs(float(left_ankle.get("x", 0)) - float(right_ankle.get("x", 0)))
                ankle_y_diff = abs(float(left_ankle.get("y", 0)) - float(right_ankle.get("y", 0)))
                
                return knee_height_diff < 30 and ankle_x_diff < 50 and ankle_y_diff < 30
        except:
            pass
        return False

    def _calculate_distance(self, person):
        """计算人物距离"""
        try:
            location = person.get("location", {})
            if location:
                frame_height = 1080  # 假设标准高度
                relative_position = (location.get("top", 0) + location.get("height", 0)) / frame_height
                if relative_position > 0.7:
                    return "near"
                elif relative_position > 0.4:
                    return "medium"
                else:
                    return "far"
        except:
            pass
        return "unknown"

    def _analyze_group_relationships(self, persons):
        """分析群体关系"""
        if len(persons) <= 1:
            return
            
        try:
            # 更新群体信息
            for i, person in enumerate(persons):
                person["attributes"]["group_info"] = f"group_member_{i+1}_of_{len(persons)}"
                
            # 分析人物之间的距离
            for i in range(len(persons)):
                for j in range(i + 1, len(persons)):
                    distance = self._calculate_person_distance(persons[i], persons[j])
                    if distance < 200:  # 假设阈值
                        persons[i]["attributes"]["group_info"] += "_close"
                        persons[j]["attributes"]["group_info"] += "_close"
        except Exception as e:
            util.log(1, f"群体关系分析异常: {str(e)}")

    def _calculate_person_distance(self, person1, person2):
        """计算两个人之间的距离"""
        try:
            loc1 = person1.get("location", {})
            loc2 = person2.get("location", {})
            
            x1 = loc1.get("left", 0) + loc1.get("width", 0) / 2
            y1 = loc1.get("top", 0) + loc1.get("height", 0) / 2
            x2 = loc2.get("left", 0) + loc2.get("width", 0) / 2
            y2 = loc2.get("top", 0) + loc2.get("height", 0) / 2
            
            return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
        except:
            return float('inf')

    def _is_same_person(self, location1, location2, threshold=50):
        """判断两个位置信息是否属于同一个人"""
        try:
            x1, y1 = location1.get("left", 0) + location1.get("width", 0)/2, location1.get("top", 0) + location1.get("height", 0)/2
            x2, y2 = location2.get("left", 0) + location2.get("width", 0)/2, location2.get("top", 0) + location2.get("height", 0)/2
            distance = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
            return distance < threshold
        except:
            return False

    def _generate_observation_summary(self, detection_result):
        """生成观察总结"""
        try:
            if not detection_result or not isinstance(detection_result, dict):
                return random.choice(DIALOGUE_TEMPLATES["empty_scene"])
            
            persons = detection_result.get("persons", [])
            person_count = len(persons)
            
            # 1. 时间氛围
            time_period = detection_result.get("time_period", self._get_time_period())
            description_parts = [random.choice(ATMOSPHERE_CONFIG["time_mood"][time_period])]
            
            # 2. 人数描述
            if person_count == 0:
                return random.choice(ATMOSPHERE_CONFIG["person_count"][0])
            
            count_desc = ATMOSPHERE_CONFIG["person_count"].get(
                person_count if person_count <= 2 else "many"
            )[0]
            description_parts.append(count_desc)
            
            # 3. 人物描述
            for person in persons:
                description_parts.append(self._generate_single_person_description(person))
            
            # 4. 场景氛围
            mood = detection_result.get("atmosphere", "peaceful")
            description_parts.append(random.choice(ATMOSPHERE_CONFIG["scene_mood"][mood]))
            
            return "，".join(description_parts) + "。"
            
        except Exception as e:
            util.log(1, f"[x] 生成观察总结失败: {str(e)}")
            return "本座看到了一些人影，但具体情况不太清楚..."

    def _update_context_memory(self, time_period, mood, descriptions):
        """更新上下文记忆"""
        self._context_memory["last_time"] = time_period
        self._context_memory["last_mood"] = mood
        self._context_memory["last_descriptions"] = descriptions
        
        # 限制历史记录长度
        self._emotion_memory.append(mood)
        if len(self._emotion_memory) > self._max_emotion_history:
            self._emotion_memory.pop(0)

    def _analyze_group_dynamics(self, persons):
        """分析群体动态关系"""
        relationships = []
        
        if len(persons) > 1:
            for i, person1 in enumerate(persons):
                for j, person2 in enumerate(persons[i+1:], i+1):
                    relation = self._infer_relationship(person1, person2)
                    if relation:
                        relationships.append(relation)
        
        return relationships

    def _infer_relationship(self, person1, person2):
        """推测两人关系"""
        try:
            distance = self._calculate_distance_between_persons(person1, person2)
            interaction = self._detect_interaction(person1, person2)
            
            # 根据距离和互动推测关系
            if distance < 0.5 and interaction.get("type") == "conversation":
                return {
                    "type": "亲密",
                    "description": random.choice([
                        "看这亲密无间的模样，想必关系匪浅",
                        "两人举止亲密，似是挚友或亲眷",
                        "这般默契，定是常年相识"
                    ])
                }
            elif distance < 1.0 and interaction.get("type") == "cooperation":
                return {
                    "type": "同伴",
                    "description": random.choice([
                        "看这默契配合，应是同事或伙伴",
                        "两人举止投契，想必是共事之人",
                        "这般协作，定是老搭档了"
                    ])
                }
            
            return None
        except Exception as e:
            util.log(1, f"推测关系时出错: {str(e)}")
            return None

    def _generate_mood_transition(self, current_mood, previous_mood):
        """生成情感过渡描述"""
        if not previous_mood or current_mood == previous_mood:
            return ""
        
        transitions = {
            ("平静", "热闹"): [
                "原本平静的气氛渐渐热络起来",
                "寂静被打破，热闹的气息涌动而来",
                "静谧的空间开始热闹起来"
            ],
            ("热闹", "平静"): [
                "喧嚣渐渐平息，恢复了宁静",
                "热闹的氛围慢慢沉淀下来",
                "繁华散去，留下一片静谧"
            ],
            ("专注", "放松"): [
                "紧绷的气氛渐渐舒缓",
                "凝重的神色开始舒展",
                "专注的神情逐渐轻松"
            ]
        }
        
        key = (previous_mood, current_mood)
        return random.choice(transitions.get(key, ["气氛渐渐转变"]))

    def _generate_description(self, attrs):
        """根据属性生成描述"""
        try:
            desc_elements = []
            
            # 1. 基础身份描述
            gender = attrs.get("gender", "unknown")
            age = attrs.get("age", "unknown")
            if gender != "unknown" and gender in DIALOGUE_TEMPLATES["api_feature_mapping"]["gender"]:
                desc_elements.append(random.choice(DIALOGUE_TEMPLATES["api_feature_mapping"]["gender"][gender]))
            if age != "unknown" and age in DIALOGUE_TEMPLATES["api_feature_mapping"]["age"]:
                desc_elements.append(random.choice(DIALOGUE_TEMPLATES["api_feature_mapping"]["age"][age]))
            
            # 2. 服饰描述
            upper_wear = attrs.get("upper_wear", "unknown")
            upper_color = attrs.get("upper_color", "unknown")
            lower_wear = attrs.get("lower_wear", "unknown")
            lower_color = attrs.get("lower_color", "unknown")
            
            if upper_wear != "unknown" and upper_wear in ATTRIBUTE_MAPPINGS["upper_wear"]:
                wear_desc = random.choice(ATTRIBUTE_MAPPINGS["upper_wear"][upper_wear])
                if upper_color != "unknown" and upper_color in ATTRIBUTE_MAPPINGS["upper_color"]:
                    color_desc = random.choice(ATTRIBUTE_MAPPINGS["upper_color"][upper_color])
                    desc_elements.append(f"{color_desc}色{wear_desc}")
                else:
                    desc_elements.append(wear_desc)
                
            if lower_wear != "unknown" and lower_wear in ATTRIBUTE_MAPPINGS["lower_wear"]:
                wear_desc = ATTRIBUTE_MAPPINGS["lower_wear"][lower_wear]
                if lower_color != "unknown" and lower_color in ATTRIBUTE_MAPPINGS["lower_color"]:
                    color_desc = ATTRIBUTE_MAPPINGS["lower_color"][lower_color]
                    desc_elements.append(f"{color_desc}色{wear_desc}")
                else:
                    desc_elements.append(wear_desc)
            
            # 使用连接词组合描述
            if len(desc_elements) > 1:
                connection = random.choice(LANGUAGE_STRUCTURE["particles"]["connection"])
                return f"{desc_elements[0]}，{connection}{desc_elements[1]}"
            elif desc_elements:
                return desc_elements[0]
            else:
                return None
            
        except Exception as e:
            util.log(1, f"[错误] 生成人物描述失败: {str(e)}")
            return None

    def generate_observation_json(self, processed_data):
        """生成结构化的观察数据供LLM使用"""
        try:
            util.log(1, f"[观察] 开始生成JSON数据, 原始数据: {json.dumps(processed_data, ensure_ascii=False)[:200]}...")
            
            # 确保processed_data是字典类型
            if not isinstance(processed_data, dict):
                util.log(1, f"[观察] 无效的数据类型: {type(processed_data)}")
                return None
            
            # 获取人数
            persons = processed_data.get("persons", [])
            person_count = len(persons)
            util.log(1, f"[观察] 检测到 {person_count} 个人")
            
            observation = {
                "scene": {
                    "timestamp": time.strftime("%H:%M:%S"),
                    "person_count": person_count,
                    "crowd_density": "高" if person_count > 5 else "中" if person_count > 2 else "低",
                    "time_period": self._get_time_period(),
                    "is_camera_closing": time.time() - self.last_detection_time >= float(cfg.body_detection_interval) * 0.8
                },
                "persons": [],
                "atmosphere": {
                    "time": self._get_time_period(),
                    "crowd": "热闹" if person_count > 3 else "安静",
                    "mood": "活跃" if person_count > 2 else "平静"
                }
            }
            
            # 处理每个人的数据
            for person in persons:
                try:
                    attrs = person.get("attributes", {})
                    person_data = {
                        "identity": {
                            "gender": attrs.get("gender", "unknown"),
                            "age": attrs.get("age", "unknown"),
                            "description": self._generate_description(attrs)
                        },
                        "appearance": {
                            "upper_wear": {
                                "type": attrs.get("upper_wear", {}).get("type", "unknown"),
                                "color": attrs.get("upper_wear", {}).get("color", "unknown")
                            },
                            "lower_wear": {
                                "type": attrs.get("lower_wear", {}).get("type", "unknown"),
                                "color": attrs.get("lower_wear", {}).get("color", "unknown")
                            },
                            "face_mask": attrs.get("face_mask", False)
                        },
                        "behavior": {
                            "orientation": attrs.get("orientation", "unknown"),
                            "actions": person.get("actions", []),
                            "gestures": person.get("gestures", []),
                            "is_using_phone": any(action == "using_phone" for action in person.get("actions", [])),
                            "is_praying": any(action == "praying" for action in person.get("actions", []))
                        },
                        "position": {
                            "distance": self._calculate_distance(person),
                            "location": person.get("location", {})
                        }
                    }
                    observation["persons"].append(person_data)
                    util.log(1, f"[观察] 成功处理第 {len(observation['persons'])} 个人的数据")
                    
                except Exception as e:
                    util.log(1, f"[观察] 处理单个人物数据时出错: {str(e)}")
                    continue
            
            # 添加群体动态分析
            if person_count > 1:
                observation["group_dynamics"] = self._analyze_group_dynamics(persons)
                util.log(1, f"[观察] 已添加群体动态分析")
            
            # 添加情感建议
            observation["suggested_emotions"] = self._suggest_emotions(observation)
            util.log(1, f"[观察] 已添加情感建议")
            
            # 验证生成的JSON数据
            try:
                json_str = json.dumps(observation, ensure_ascii=False)
                util.log(1, f"[观察] 成功生成JSON数据: {json_str[:200]}...")
                return observation
            except Exception as e:
                util.log(1, f"[观察] JSON序列化失败: {str(e)}")
                return None
            
        except Exception as e:
            util.log(1, f"[观察] 生成JSON数据时出错: {str(e)}")
            import traceback
            util.log(1, traceback.format_exc())
            return None

    def _get_time_period(self):
        """获取当前时间段"""
        hour = int(time.strftime("%H"))
        if 5 <= hour < 8:
            return "黎明"
        elif 8 <= hour < 12:
            return "午时"
        elif 12 <= hour < 18:
            return "黄昏"
        else:
            return "子夜"

    def _suggest_emotions(self, observation):
        """基于场景建议情感状态"""
        emotions = []
        
        # 基于人数和氛围
        if observation["scene"]["person_count"] == 0:
            emotions.extend(["平静", "思考"])
        elif observation["scene"]["person_count"] > 3:
            emotions.extend(["热闹", "欢快"])
        
        # 基于时间
        time_emotions = {
            "黎明": ["希望", "期待"],
            "午时": ["活力", "忙碌"],
            "黄昏": ["感慨", "怀旧"],
            "子夜": ["深沉", "思考"]
        }
        emotions.extend(time_emotions.get(observation["scene"]["time_period"], []))
        
        # 基于人物行为
        for person in observation["persons"]:
            if person["behavior"]["is_using_phone"]:
                emotions.append("专注")
            if person["behavior"]["is_praying"]:
                emotions.append("虔诚")
        
        # 如果摄像头即将关闭
        if observation["scene"]["is_camera_closing"]:
            emotions.append("告别")
        
        return list(set(emotions))  # 去重

    def check_observation_trigger(self, text):
        """检查观察触发词"""
        try:
            text = text.strip().lower()
            best_match = None
            max_weight = -1
            
            # 按优先级顺序检查触发词
            for trigger_type in OBSERVATION_TRIGGERS["priority_order"]:
                config = OBSERVATION_TRIGGERS[trigger_type]
                
                if trigger_type == "scene_specific":
                    # 检查场景特定触发词
                    for scene_type, scene_config in config.items():
                        if scene_type != "priority":  # 跳过优先级配置
                            for pattern in scene_config["patterns"]:
                                if pattern in text:
                                    weight = scene_config["weight"] * len(pattern)
                                    if weight > max_weight:
                                        max_weight = weight
                                        best_match = f"scene_{scene_type}"
                else:
                    # 检查其他类型触发词
                    for pattern in config["patterns"]:
                        if pattern in text:
                            weight = config["weight"] * len(pattern)
                            if weight > max_weight:
                                max_weight = weight
                                best_match = trigger_type
            
            if best_match:
                # 检查命令冷却时间，防止重复触发
                with self.command_lock:
                    current_time = time.time()
                    if (self.last_command_type == best_match and 
                        current_time - self.last_command_time < self.command_cooldown):
                        util.log(1, f"[系统] 命令 {best_match} 处于冷却中，忽略该触发")
                        return None
                        
                util.log(1, f"[Debug] 匹配到触发词类型: {best_match}")
                return best_match
            
            return None
            
        except Exception as e:
            util.log(1, f"[Debug] 触发词检查失败: {str(e)}")
            return None

    def process_command(self, command_type):
        """处理观察命令"""
        try:
            # 防止短时间内重复触发相同命令
            with self.command_lock:
                current_time = time.time()
                if (self.last_command_type == command_type and 
                    current_time - self.last_command_time < self.command_cooldown):
                    util.log(1, f"[系统] 命令冷却中，忽略重复的 {command_type} 命令")
                    return None
                
                # 记录当前命令和时间
                self.last_command_type = command_type
                self.last_command_time = current_time
            
            # 1. 立即准备开场白
            opening_line = random.choice(COMMAND_TEMPLATES.get(command_type, COMMAND_TEMPLATES['short_term']))
            opening_interact = Interact("opening", 2, {
                "user": "User",
                "text": opening_line,
                "tone": "lyrical"  # 开场白使用抒情语气
            })

            # 2. 立即开始TTS合成并播放开场白
            self.say(opening_interact, opening_line)

            # 3. 启动并行初始化线程
            init_success = False
            def async_initialize():
                nonlocal init_success
                try:
                    init_success = self.initialize()
                except Exception as e:
                    util.log(1, f"[错误] 初始化失败: {str(e)}")
                    init_success = False

            init_thread = threading.Thread(target=async_initialize)
            init_thread.start()

            # 4. 等待开场白播放完成 - 使用事件而不是标志位
            if hasattr(self, 'play_complete_event'):
                # 使用更可靠的事件等待机制
                wait_timeout = 10.0  # 最长等待10秒
                self.play_complete_event.wait(timeout=wait_timeout)
            else:
                # 兼容旧的等待机制
                timeout = 0
                max_timeout = 10.0  # 秒
                while self.speaking and timeout < max_timeout:
                    time.sleep(0.1)
                    timeout += 0.1

            # 5. 如果是停止命令，直接返回
            if command_type == "stop":
                with self.camera_lock:
                    if self.cap:
                        self.cap.release()
                        self.cap = None
                    self.status = False
                    util.log(1, "[系统] 摄像头已关闭")
                    return {
                        "opening": opening_line,
                        "scene": None,
                        "ending": None,
                        "features": None,
                        "is_stop": True
                    }

            # 6. 等待初始化完成
            init_thread.join()
            if not init_success:
                error_scene = "本座天眼受阻，暂时看不真切..."
                error_interact = Interact("error", 2, {
                    "user": "User",
                    "text": error_scene,
                    "tone": "gentle"
                })
                self.say(error_interact, error_scene)
                return {
                    "opening": opening_line,
                    "scene": error_scene,
                    "ending": None,
                    "features": None,
                    "is_stop": False
                }

            # 7. 获取图像和分析结果
            with self.api_lock:
                frame = self.get_img()
                if frame is None:
                    self.close()
                    error_scene = "本座天眼受阻，暂时看不真切..."
                    error_interact = Interact("error", 2, {
                        "user": "User",
                        "text": error_scene,
                        "tone": "gentle"
                    })
                    self.say(error_interact, error_scene)
                    return {
                        "opening": opening_line,
                        "scene": error_scene,
                        "ending": None,
                        "features": None,
                        "is_stop": False
                    }

                # 8. 获取API分析结果并播放场景描述
                try:
                    # 发送API请求
                    api_response = self._extract_features(frame)
                    if not api_response:
                        raise Exception("API分析失败")

                    # 生成场景描述并播放
                    scene_description = self._generate_scene_description(api_response)
                    scene_interact = Interact("scene", 2, {
                        "user": "User",
                        "text": scene_description,
                        "tone": "gentle"
                    })
                    self.say(scene_interact, scene_description)

                    # 等待场景描述播放完成
                    while self.speaking:
                        time.sleep(0.1)

                    # 根据人数选择结束语并播放
                    person_count = len(api_response.get("persons", []))
                    ending_type = "热闹" if person_count > 2 else "空旷" if person_count == 0 else "普通"
                    ending = random.choice(DIALOGUE_TEMPLATES['scene_endings'][ending_type])
                    ending_interact = Interact("ending", 2, {
                        "user": "User",
                        "text": ending,
                        "tone": "gentle"
                    })
                    self.say(ending_interact, ending)

                    # 设置自动关闭
                    def auto_close():
                        try:
                            time.sleep(20)
                            if self.status:
                                util.log(1, "[系统] 观察超时，自动关闭摄像头")
                                self.close()
                        except Exception as e:
                            util.log(1, f"[错误] 自动关闭异常: {str(e)}")

                    close_thread = threading.Thread(target=auto_close, daemon=True)
                    close_thread.start()

                    return {
                        "opening": opening_line,
                        "scene": scene_description,
                        "ending": ending,
                        "features": api_response,
                        "is_stop": False
                    }

                except Exception as e:
                    util.log(1, f"[错误] 处理观察命令失败: {str(e)}")
                    error_scene = "本座天眼受阻，暂时看不真切..."
                    error_ending = random.choice(DIALOGUE_TEMPLATES['scene_endings']['特殊'])
                    error_interact = Interact("error", 2, {
                        "user": "User",
                        "text": error_scene,
                        "tone": "gentle"
                    })
                    self.say(error_interact, error_scene)
                    return {
                        "opening": opening_line,
                        "scene": error_scene,
                        "ending": error_ending,
                        "features": None,
                        "is_stop": False
                    }

        except Exception as e:
            util.log(1, f"[错误] 处理观察命令失败: {str(e)}")
            error_scene = "本座天眼受阻，暂时看不真切..."
            error_ending = random.choice(DIALOGUE_TEMPLATES['scene_endings']['特殊'])
            error_interact = Interact("error", 2, {
                "user": "User",
                "text": error_scene,
                "tone": "gentle"
            })
            self.say(error_interact, error_scene)
            return {
                "opening": opening_line,
                "scene": error_scene,
                "ending": error_ending,
                "features": None,
                "is_stop": False
            }

    def say(self, interact, text):
        """播放文本并管理状态"""
        try:
            # 1. 状态检查和锁定
            with threading.Lock():
                self.speaking = True
                # 创建播放完成事件
                if not hasattr(self, 'play_complete_event'):
                    self.play_complete_event = threading.Event()
                self.play_complete_event.clear()
            
            # 2. 根据交互类型设置优先级
            is_opening = isinstance(interact, Interact) and interact.interact_type == "opening"
            is_scene = isinstance(interact, Interact) and interact.interact_type == "scene"
            
            # 3. 发送到WebSocket（确保线程安全）
            try:
                web_instance = wsa_server.get_web_instance()
                if web_instance and hasattr(web_instance, 'is_connected') and web_instance.is_connected("User"):
                    web_instance.add_cmd({
                        "panelMsg": text,
                        "Username": "User"
                    })
            except Exception as e:
                util.log(1, f"[警告] WebSocket消息发送失败: {str(e)}")
            
            # 4. 记录到日志
            util.log(1, f"[播放] {text}")

            # 5. 使用火山引擎TTS合成
            from tts import get_engine
            sp = get_engine()
            sp.connect()
            
            # 设置语气
            style = "lyrical" if is_opening else "gentle"
            
            # 合成音频
            try:
                result = sp.to_sample(text, style)
                if result:
                    # 播放音频
                    import wave
                    import sounddevice as sd
                    import numpy as np
                    
                    with wave.open(result, 'rb') as wf:
                        frames = wf.readframes(wf.getnframes())
                        audio_data = np.frombuffer(frames, dtype=np.int16)
                        # 使用回调函数标记播放结束
                        def callback(outdata, frames, time, status):
                            if status:
                                util.log(1, f"[警告] 播放回调状态: {status}")
                            return None
                        
                        # 非阻塞播放，但使用事件等待完成
                        stream = sd.OutputStream(
                            samplerate=wf.getframerate(),
                            channels=wf.getnchannels(),
                            callback=callback,
                            finished_callback=lambda: self.play_complete_event.set()
                        )
                        
                        with stream:
                            sd.play(audio_data, wf.getframerate())
                            # 使用事件等待播放完成
                            self.play_complete_event.wait(timeout=len(audio_data)/wf.getframerate() + 2.0)  # 添加2秒安全间隔
                            sd.wait()  # 确保播放完成
            except Exception as e:
                util.log(1, f"[错误] TTS合成或播放失败: {str(e)}")
                with threading.Lock():
                    self.speaking = False
                    self.play_complete_event.set()  # 设置事件避免死锁
            
            return text
            
        except Exception as e:
            util.log(1, f"[错误] 播放失败: {str(e)}")
            with threading.Lock():
                self.speaking = False
                if hasattr(self, 'play_complete_event'):
                    self.play_complete_event.set()  # 设置事件避免死锁
            return text
        
        finally:
            # 确保状态正确重置
            if not is_opening and not is_scene:  # 开场白和场景描述需要保持speaking状态
                with threading.Lock():
                    self.speaking = False
                    if hasattr(self, 'play_complete_event'):
                        self.play_complete_event.set()  # 确保事件被设置

    def _save_to_cache(self, cache_type, key, value):
        pass

    def _get_from_cache(self, cache_type, key):
        pass

    def _extract_features(self, frame):
        """从图像中提取特征"""
        try:
            # 1. 图像编码和预处理
            _, img_encoded = cv2.imencode('.jpg', frame)
            if img_encoded is None:
                util.log(1, "[错误] 图像编码失败")
                return None
            
            image_base64 = base64.b64encode(img_encoded).decode('utf-8')
            
            # 2. 获取access token
            if not self.access_token or time.time() - self.last_token_time > 3600:
                self.access_token = self.api_manager.get_access_token()
                if not self.access_token:
                    util.log(1, "[错误] 无法获取API access token")
                    return None
                self.last_token_time = time.time()
            
            # 3. 准备API调用
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            data = {'image': image_base64}
            max_retries = 3
            retry_delay = 1
            
            # 4. 调用多个API并合并结果
            api_results = {}
            
            # 4.1 人体检测和属性识别
            util.log(1, "[API] 发送人体检测和属性识别请求...")
            url = f"https://aip.baidubce.com/rest/2.0/image-classify/v1/body_attr?access_token={self.access_token}"
            response = self._make_api_call(url, headers, data, max_retries, retry_delay)
            if response:
                api_results["body_attr"] = response
            
            # 4.2 人体关键点识别
            util.log(1, "[API] 发送人体关键点识别请求...")
            url = f"https://aip.baidubce.com/rest/2.0/image-classify/v1/body_analysis?access_token={self.access_token}"
            response = self._make_api_call(url, headers, data, max_retries, retry_delay)
            if response:
                api_results["body_analysis"] = response
            
            # 4.3 手势识别
            util.log(1, "[API] 发送手势识别请求...")
            url = f"https://aip.baidubce.com/rest/2.0/image-classify/v1/gesture?access_token={self.access_token}"
            response = self._make_api_call(url, headers, data, max_retries, retry_delay)
            if response:
                api_results["gesture"] = response
            
            # 4.4 人流量统计
            util.log(1, "[API] 发送人流量统计请求...")
            url = f"https://aip.baidubce.com/rest/2.0/image-classify/v1/body_num?access_token={self.access_token}"
            response = self._make_api_call(url, headers, data, max_retries, retry_delay)
            if response:
                api_results["crowd_count"] = response
            
            # 4.5 手部关键点识别
            util.log(1, "[API] 发送手部关键点识别请求...")
            url = f"https://aip.baidubce.com/rest/2.0/image-classify/v1/hand_analysis?access_token={self.access_token}"
            response = self._make_api_call(url, headers, data, max_retries, retry_delay)
            if response:
                api_results["hand_analysis"] = response

            # 5. 处理API结果
            if not api_results:
                util.log(1, "[错误] 所有API调用均失败")
                return None
            
            # 6. 合并处理结果
            persons = []
            
            # 6.1 处理人体属性结果
            if "body_attr" in api_results:
                body_attr = api_results["body_attr"]
                for person in body_attr.get("person_info", []):
                    person_data = {
                        "attributes": self._extract_attributes(person),
                        "location": person.get("location", {}),
                        "body_parts": {},
                        "actions": [],
                        "gestures": []
                    }
                    persons.append(person_data)
            
            # 6.2 处理人体关键点结果
            if "body_analysis" in api_results:
                body_analysis = api_results["body_analysis"]
                for i, person in enumerate(body_analysis.get("person_info", [])):
                    if i < len(persons):
                        persons[i]["body_parts"] = person.get("body_parts", {})
                        persons[i]["actions"].extend(self._analyze_actions(person.get("body_parts", {})))
            
            # 6.3 处理手势识别结果
            if "gesture" in api_results:
                gesture_result = api_results["gesture"]
                for i, person in enumerate(persons):
                    person["gestures"] = self._extract_gestures(gesture_result)
            
            # 6.4 处理手部关键点结果
            if "hand_analysis" in api_results:
                hand_result = api_results["hand_analysis"]
                for i, person in enumerate(persons):
                    if i < len(persons):
                        persons[i]["hand_keypoints"] = hand_result.get("hand_info", [])
            
            # 6.5 添加人流量信息
            crowd_info = {
                "total_count": len(persons),
                "density": "高" if len(persons) > 10 else "中" if len(persons) > 5 else "低"
            }
            if "crowd_count" in api_results:
                crowd_result = api_results["crowd_count"]
                crowd_info["detected_count"] = crowd_result.get("person_num", len(persons))
            
            return {
                "persons": persons,
                "crowd_info": crowd_info,
                "timestamp": time.time()
            }
            
        except Exception as e:
            util.log(1, f"[错误] 特征提取失败: {str(e)}")
            import traceback
            util.log(1, traceback.format_exc())
            return None

    def _make_api_call(self, url, headers, data, max_retries, retry_delay):
        """统一的API调用方法"""
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, data=data)
                if response.status_code == 200:
                    result = response.json()
                    if "error_code" not in result:
                        return result
                    else:
                        util.log(1, f"[错误] API返回错误: {result.get('error_msg', '')}")
            
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                
            except Exception as e:
                util.log(1, f"[错误] API调用异常: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        
        return None

    def _generate_scene_description(self, features):
        """生成场景描述"""
        try:
            if not features or not features.get("persons"):
                return random.choice(DIALOGUE_TEMPLATES["empty_scene"])
            
            desc_parts = []
            current_tone = "gentle"  # 默认语气
            
            # 1. 时间氛围
            time_period = self._get_time_period()
            time_config = ATMOSPHERE_CONFIG["time_mood"][time_period]
            time_desc = random.choice(time_config["patterns"])
            current_tone = time_config["tone"]
            desc_parts.append(time_desc)
            
            # 2. 人数描述
            person_count = len(features["persons"])
            count_key = person_count if person_count <= 2 else "many"
            count_config = ATMOSPHERE_CONFIG["person_count"][count_key]
            transition = random.choice(LANGUAGE_STRUCTURE["transitions"]["time_to_count"])
            count_desc = f"{transition}{random.choice(count_config['patterns'])}"
            current_tone = count_config["tone"]
            desc_parts.append(count_desc)
            
            # 3. 人物描述
            for i, person in enumerate(features["persons"]):
                if i > 0:
                    desc_parts.append(random.choice(LANGUAGE_STRUCTURE["transitions"]["count_to_person"]))
                
                person_desc = self._generate_single_person_description(person)
                if person_desc:
                    desc_parts.append(person_desc)
                    
                # 添加动作描述
                action_desc = self._generate_action_description(person.get("actions", []))
                if action_desc:
                    transition = random.choice(LANGUAGE_STRUCTURE["transitions"]["person_to_action"])
                    desc_parts.append(f"{transition}{action_desc}")
            
            # 4. 场景氛围
            mood = self._analyze_scene_mood(features)
            mood_config = ATMOSPHERE_CONFIG["scene_mood"][mood]
            transition = random.choice(LANGUAGE_STRUCTURE["transitions"]["action_to_mood"])
            mood_desc = f"{transition}{random.choice(mood_config)}"
            desc_parts.append(mood_desc)
            
            # 5. 添加结语
            conclusion = random.choice(LANGUAGE_STRUCTURE["particles"]["conclusion"])
            desc_parts.append(conclusion)
            
            # 组合描述
            description = "，".join(desc_parts) + "。"
            
            # 记录使用的语气
            if hasattr(self, '_last_tone'):
                self._last_tone = current_tone
            
            return description
            
        except Exception as e:
            util.log(1, f"[错误] 生成场景描述失败: {str(e)}")
            return "本座天眼受阻，暂时看不真切..."

    def _generate_single_person_description(self, person):
        """生成单人描述"""
        try:
            desc_parts = []
            
            # 1. 获取基础属性
            attrs = person.get("attributes", {})
            gender = attrs.get("gender", "unknown")
            age = attrs.get("age", "unknown")
            
            # 2. 生成身份描述
            if gender != "unknown" and age != "unknown":
                gender_key = "男" if "男" in gender else "女"
                age_key = age.replace("_", "")
                if gender_key in PERSON_FEATURES["identity"] and age_key in PERSON_FEATURES["identity"][gender_key]:
                    identity_config = PERSON_FEATURES["identity"][gender_key][age_key]
                    desc_parts.append(random.choice(identity_config["patterns"]))
            
            # 3. 生成服饰描述
            upper_wear = attrs.get("upper_wear", "unknown")
            upper_color = attrs.get("upper_color", "unknown")
            
            if upper_wear != "unknown" and upper_color != "unknown":
                if upper_wear in ATTRIBUTE_MAPPINGS["upper_wear"] and upper_color in ATTRIBUTE_MAPPINGS["upper_color"]:
                    wear_desc = random.choice(ATTRIBUTE_MAPPINGS["upper_wear"][upper_wear])
                    color_desc = random.choice(ATTRIBUTE_MAPPINGS["upper_color"][upper_color])
                    desc_parts.append(f"身着{color_desc}色{wear_desc}")
            
            # 4. 生成姿态描述
            actions = person.get("actions", [])
            if "站立" in actions:
                desc_parts.append("挺立而立")
            elif "坐着" in actions:
                desc_parts.append("静坐一旁")
            
            # 使用连接词组合描述
            if len(desc_parts) > 1:
                connection = random.choice(LANGUAGE_STRUCTURE["particles"]["connection"])
                return f"{desc_parts[0]}，{connection}{desc_parts[1]}"
            elif desc_parts:
                return desc_parts[0]
            else:
                return None
            
        except Exception as e:
            util.log(1, f"[错误] 生成人物描述失败: {str(e)}")
            return None

    def _analyze_scene_mood(self, features):
        """分析场景氛围"""
        try:
            # 基于人数判断
            person_count = len(features.get("persons", []))
            if person_count == 0:
                return "peaceful"
            elif person_count > 3:
                return "lively"
                
            # 基于动作判断
            solemn_actions = ["pray", "meditation", "ceremony"]
            lively_actions = ["talk", "laugh", "play"]
            
            action_count = {"solemn": 0, "lively": 0, "peaceful": 0}
            
            for person in features.get("persons", []):
                for action in person.get("actions", []):
                    if action in solemn_actions:
                        action_count["solemn"] += 1
                    elif action in lively_actions:
                        action_count["lively"] += 1
                    else:
                        action_count["peaceful"] += 1
                        
            # 根据动作统计判断氛围
            max_action = max(action_count.items(), key=lambda x: x[1])[0]
            return max_action
            
        except Exception as e:
            util.log(1, f"[x] 场景氛围分析失败: {str(e)}")
            return "peaceful"

    def _check_standing_pose(self, body_parts):
        """检查是否站立"""
        try:
            if not body_parts:
                return False
            
            # 检查关键点得分
            key_points = ["nose", "neck", "right_knee", "left_knee"]
            scores = [body_parts.get(point, {}).get("score", 0) for point in key_points]
            
            # 如果关键点得分都较高，说明可能是站立姿势
            return all(score > 0.5 for score in scores)
            
        except Exception as e:
            util.log(1, f"[x] 姿态检查失败: {str(e)}")
            return False
    
    def _check_sitting_pose(self, body_parts):
        """检查是否坐着"""
        try:
            if not body_parts:
                return False
                
            # 检查膝盖和臀部的位置关系
            hip_y = body_parts.get("hip", {}).get("y", 0)
            knee_y = body_parts.get("knee", {}).get("y", 0)
            
            # 如果膝盖高于臀部，可能是坐姿
            return hip_y > 0 and knee_y > 0 and knee_y < hip_y
            
        except Exception as e:
            util.log(1, f"[x] 姿态检查失败: {str(e)}")
            return False

    def _try_camera_backend(self, backend, backend_name):
        """尝试使用特定后端打开摄像头"""
        try:
            if backend == 0:
                self.cap = cv2.VideoCapture(0)
            else:
                self.cap = cv2.VideoCapture(0 + backend)
            
            if self.cap is None or not self.cap.isOpened():
                util.log(1, f"[x] {backend_name} 后端无法打开摄像头")
                return False
            
            # 测试是否能读取帧
            ret, frame = self.cap.read()
            if not ret or frame is None:
                util.log(1, f"[x] {backend_name} 后端无法读取画面")
                if self.cap:
                    self.cap.release()
                    self.cap = None
                return False
            
            # 设置摄像头参数
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            util.log(1, f"使用 {backend_name} 后端成功打开摄像头")
            return True
            
        except Exception as e:
            util.log(1, f"使用 {backend_name} 后端失败: {str(e)}")
            if self.cap:
                self.cap.release()
                self.cap = None
            return False

    def get_img(self):
        """获取摄像头图像"""
        try:
            with self.camera_lock:
                if not self.cap or not self.cap.isOpened():
                    if not self.initialize():
                        return None
                        
                # 检查时间间隔
                current_time = time.time()
                if current_time - self.last_detection_time < float(cfg.body_detection_interval):
                    return None
                    
                # 读取图像
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    util.log(1, "[!] 无法读取摄像头画面")
                    return None
                    
                self.last_detection_time = current_time
                return frame
                
        except Exception as e:
            util.log(1, f"[x] 获取图像失败: {str(e)}")
            return None

    def _generate_action_description(self, actions):
        """生成动作描述"""
        if not actions:
            return None
        
        action_templates = {
            "using_phone": ["正在看手机", "低头玩手机", "专注于手机"],
            "waving": ["在挥手", "挥舞着手臂", "正在打招呼"],
            "pointing": ["指着远方", "做出指点的姿势", "手指向前方"],
            "praying": ["双手合十", "做出祈祷姿势", "虔诚地祷告"],
            # 新增脸部动作描述
            "head_tilt": ["歪着头", "头微微倾斜", "侧着头"],
            "head_down": ["低着头", "垂首而立", "头微微低垂"],
            "head_up": ["抬着头", "仰望远方", "昂首而立"],
            "eyes_closed": ["闭着眼睛", "双目微闭", "合眼沉思"],
            "eyes_open": ["睁大眼睛", "目光炯炯", "眼神专注"],
            "mouth_open": ["张着嘴", "正在说话", "口若悬河"],
            "mouth_closed": ["抿着嘴", "默默无言", "沉默不语"]
        }
        
        descriptions = []
        for action in actions:
            if action in action_templates:
                descriptions.append(random.choice(action_templates[action]))
            
        if descriptions:
            return "，".join(descriptions)
        return None

    def _generate_gesture_description(self, gestures):
        """生成手势描述"""
        if not gestures:
            return None
        
        gesture_templates = {
            "wave": ["挥手示意", "友好地挥手", "打着招呼"],
            "point": ["指向前方", "做出指引姿势", "手指某处"],
            "pray": ["双手合十", "作揖行礼", "恭敬地行礼"],
            "hold": ["手持物品", "拿着什么", "掌中有物"]
        }
        
        descriptions = []
        for gesture in gestures:
            gesture_type = gesture.get("type")
            if gesture_type in gesture_templates:
                descriptions.append(random.choice(gesture_templates[gesture_type]))
            
        if descriptions:
            return "，".join(descriptions)
        return None

    def _check_api_limits(self):
        """检查API调用限制"""
        with self.api_lock:
            current_time = time.time()
            
            # 检查调用间隔
            if current_time - self._api_limits['last_call_time'] < self._api_limits['min_interval']:
                time.sleep(self._api_limits['min_interval'])
            
            # 检查每日限制
            today = time.strftime("%Y-%m-%d")
            if today != getattr(self, '_last_check_date', None):
                self._api_limits['calls_today'] = 0
                self._last_check_date = today
                
            if self._api_limits['calls_today'] >= self._api_limits['daily_limit']:
                raise Exception("已达到每日API调用限制")
            
            # 更新计数器
            self._api_limits['last_call_time'] = current_time
            self._api_limits['calls_today'] += 1
            
            return True

    def _save_opening_line(self, command_type, opening_line):
        """保存开场白到缓存"""
        with self.cache_lock:
            self._opening_lines_cache[command_type] = opening_line

    def _get_opening_line(self, command_type):
        """从缓存获取开场白"""
        with self.cache_lock:
            return self._opening_lines_cache.get(command_type)

    def _is_dancing(self, body_parts):
        """检测是否在跳舞"""
        try:
            left_leg = body_parts.get("left_leg", {})
            right_leg = body_parts.get("right_leg", {})
            left_hand = body_parts.get("left_hand", {})
            right_hand = body_parts.get("right_hand", {})
            
            if left_leg and right_leg and (left_hand or right_hand):
                left_leg_y = float(left_leg.get("y", 0))
                right_leg_y = float(right_leg.get("y", 0))
                left_hand_y = float(left_hand.get("y", 0)) if left_hand else 0
                right_hand_y = float(right_hand.get("y", 0)) if right_hand else 0
                
                # 判断腿部和手部的相对位置
                if abs(left_leg_y - right_leg_y) < 50 and abs(left_hand_y - left_leg_y) < 100:
                    return True
        except:
            pass
        return False
