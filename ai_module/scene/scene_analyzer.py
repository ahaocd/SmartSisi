# 场景分析器模块
"""
场景分析器模块，负责对摄像头捕获的图像进行分析和解释。
"""

import time
import random
import threading
import logging
import cv2
import numpy as np
from utils import util
from ai_module.api.baidu_api_client import BaiduAPIClient

class SceneAnalyzer:
    """场景分析器，分析摄像头捕获的图像内容"""
    
    # 单例实例
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """
        获取SceneAnalyzer的单例实例
        
        Returns:
            SceneAnalyzer: 场景分析器实例
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = SceneAnalyzer()
            return cls._instance
    
    def __init__(self):
        """初始化场景分析器"""
        self.logger = logging.getLogger(__name__)
        self.api_client = BaiduAPIClient.get_instance()
        
        # 分析缓存
        self.analysis_cache = {}
        self.cache_lock = threading.Lock()
        
        # 分析线程
        self.analyzing = False
        self.analysis_thread = None
        
        # 最近分析结果
        self.last_results = {}
        
        # 场景描述模板
        self.scene_templates = {
            "empty": [
                "我的目光所至之处空无一物，似乎大家都避开了我的天眼之力...",
                "灵气稀薄，此处无人可见，是否有什么隐匿了形迹？",
                "奇怪，我的神识未能捕捉到任何人影，真是清净...",
                "视野中一片空旷，莫非世人都已睡去了？"
            ],
            "single_person": [
                "我看到了一位{gender}在我面前，{posture}，{dress}，似乎{action}...",
                "只有一个{gender}映入我眼帘，{posture}，正在{action}...",
                "我的天眼只捕捉到一位{gender}的身影，{dress}，{posture}...",
                "孤单的{gender}在我眼前{posture}，{dress}，似乎在{action}..."
            ],
            "multiple_people": [
                "我看到了{count}个人，有{gender_summary}，大多数人都在{action}...",
                "神识所见，此处有{count}人聚集，{gender_summary}，似乎在{action}...",
                "天眼之下，{count}个凡人现形，{gender_summary}，他们正在{action}...",
                "我一眼望去，有{count}个人在我面前，{gender_summary}，{action}..."
            ],
            "gesture": [
                "我看到你在比划{gesture}的手势，有何玄机？",
                "你的手势我已洞悉，这是{gesture}之形，有何用意？",
                "凡人的手势虽简单，但我能看出你在做{gesture}...",
                "有趣，你的手在做{gesture}的动作，想传达什么信息吗？"
            ]
        }
        
        # 姿态描述
        self.posture_descriptions = [
            "站立得笔直",
            "略微前倾",
            "悠闲地站着",
            "微微侧身",
            "挺拔如松",
            "似乎有些疲惫",
            "精神焕发",
            "神态自若"
        ]
        
        # 服装描述
        self.dress_descriptions = [
            "衣着整洁",
            "穿着随意",
            "装扮简朴",
            "衣着考究",
            "打扮时尚",
            "衣衫素雅",
            "装束独特",
            "衣着朴素"
        ]
        
        # 动作描述
        self.action_descriptions = [
            "在沉思",
            "观察着周围",
            "似乎在等待什么",
            "正在专注地思考",
            "静静地凝视前方",
            "在做些细微的动作",
            "打量着四周",
            "对周围环境很感兴趣"
        ]
        
        # 手势映射表
        self.gesture_mapping = {
            "One": "数字1",
            "Five": "数字5/伸掌",
            "Fist": "握拳",
            "Ok": "OK",
            "Prayer": "祈祷",
            "Congratulation": "作揖/祝贺",
            "Heart_single": "单手比心",
            "Thumb_up": "点赞",
            "Thumb_down": "差评",
            "ILY": "我爱你",
            "Palm_up": "手掌向上",
            "Heart_3": "双手比心",
            "Two": "数字2/胜利",
            "Three": "数字3",
            "Four": "数字4",
            "Six": "数字6",
            "Seven": "数字7",
            "Eight": "数字8",
            "Nine": "数字9",
            "Rock": "摇滚手势",
            "Palm_down": "手掌向下",
            "Camera": "相机手势"
        }
    
    def analyze_frame(self, frame):
        """
        分析视频帧
        
        Args:
            frame (numpy.ndarray): 视频帧数据
            
        Returns:
            dict: 分析结果
        """
        if frame is None or frame.size == 0:
            util.log(1, "无效的视频帧")
            return {"error": "无效的视频帧"}
        
        # 创建分析结果字典
        result = {
            "timestamp": time.time(),
            "has_content": False
        }
        
        try:
            # 人体检测
            body_result = self.api_client.detect_body(frame)
            
            # 检查是否有有效结果
            if 'error_code' not in body_result or body_result['error_code'] == 0:
                result['body'] = body_result
                
                # 记录人数
                person_count = len(body_result.get('person_info', []))
                result['person_count'] = person_count
                
                if person_count > 0:
                    result['has_content'] = True
            
            # 手势识别
            gesture_result = self.api_client.detect_gesture(frame)
            
            # 检查是否有有效结果
            if 'error_code' not in gesture_result or gesture_result['error_code'] == 0:
                result['gesture'] = gesture_result
                
                # 记录手势
                gestures = []
                for res in gesture_result.get('result', []):
                    if 'classname' in res:
                        gestures.append(res['classname'])
                
                if gestures:
                    result['gestures'] = gestures
                    result['has_content'] = True
            
            # 更新最近分析结果
            self.last_results = result
            
            return result
        except Exception as e:
            util.log(1, f"场景分析出错: {str(e)}")
            return {"error": str(e)}
    
    def analyze(self, api_result):
        """
        分析API结果，提取关键信息用于对话生成
        
        Args:
            api_result (dict): API返回的分析结果
            
        Returns:
            dict: 统一格式的场景分析结果
        """
        try:
            # 检查API结果是否有效
            if not api_result or not api_result.get("success", False):
                util.log(1, "[场景] API结果无效或分析失败")
                return {
                    "has_content": False,
                    "scene_description": "我尝试观察周围，但似乎出了些问题，我的天眼暂时失灵了...",
                    "person_count": 0,
                    "persons": [],
                    "gestures": []
                }
            
            # 初始化场景数据
            scene_data = {
                "has_content": True,
                "timestamp": api_result.get("timestamp", time.time()),
                "person_count": 0,
                "persons": [],
                "gestures": []
            }
            
            # 处理人体检测结果
            if "body" in api_result:
                body_result = api_result["body"]
                
                # 提取人数
                scene_data["person_count"] = body_result.get("person_count", body_result.get("person_num", 0))
                
                # 提取人体信息
                persons_info = []
                if "persons" in body_result and body_result["persons"]:
                    util.log(1, f"[API] 分析完成，检测到 {scene_data['person_count']} 人")
                    for person in body_result["persons"]:
                        person_data = {
                            "gender": person.get("basic", {}).get("gender", "unknown"),
                            "age": person.get("basic", {}).get("age", "unknown"),
                            "upper_color": person.get("basic", {}).get("upper_color", "unknown"),
                            "lower_color": person.get("basic", {}).get("lower_color", "unknown"),
                            "location": person.get("location", {})
                        }
                        persons_info.append(person_data)
                elif "person_info" in body_result:
                    util.log(1, f"[API] 分析完成，检测到 {scene_data['person_count']} 人 (旧格式)")
                    for person in body_result["person_info"]:
                        person_data = {
                            "gender": person.get("attributes", {}).get("gender", {}).get("name", "unknown"),
                            "age": person.get("attributes", {}).get("age", {}).get("name", "unknown"),
                            "upper_color": person.get("attributes", {}).get("upper_color", {}).get("name", "unknown"),
                            "lower_color": person.get("attributes", {}).get("lower_color", {}).get("name", "unknown"),
                            "location": person.get("location", {})
                        }
                        persons_info.append(person_data)
                else:
                    util.log(1, f"[警告] 检测到人数({scene_data['person_count']})>0，但没有人体详细信息")
                    # 如果检测到人但没有详细信息，添加默认人物数据
                    for i in range(scene_data["person_count"]):
                        persons_info.append({
                            "gender": "unknown",
                            "age": "unknown",
                            "upper_color": "unknown",
                            "lower_color": "unknown",
                            "location": {}
                        })
                
                # 更新场景数据中的人物信息
                scene_data["persons"] = persons_info
            
            # 处理手势识别结果
            if "gesture" in api_result:
                gesture_result = api_result["gesture"]
                
                # 提取手势列表
                gesture_list = []
                if "result" in gesture_result:
                    for gesture in gesture_result["result"]:
                        classname = gesture.get("classname", "unknown")
                        if classname != "unknown":
                            gesture_list.append(classname)
                
                scene_data["gestures"] = gesture_list
                scene_data["has_gesture"] = len(gesture_list) > 0
            
            # 生成场景描述（已由dialogue_generator接管，这里只提供数据）
            util.log(1, f"[场景] 分析完成: 检测到 {scene_data['person_count']} 人, {len(scene_data['gestures'])} 个手势")
            
            return scene_data
        
        except Exception as e:
            util.log(1, f"[场景] 分析异常: {str(e)}")
            import traceback
            util.log(1, traceback.format_exc())
            
            # 返回默认场景数据
            return {
                "has_content": False,
                "scene_description": "我尝试观察周围，但似乎出了些问题，我的天眼暂时失灵了...",
                "person_count": 0,
                "persons": [],
                "gestures": []
            }
    
    def _generate_people_description(self, person_num, persons):
        if person_num == 1:
            person = persons[0]
            template = random.choice(self.scene_templates['single_person'])
            return template.format(
                gender=person['gender'],
                posture=random.choice(self.posture_descriptions),
                dress=random.choice(self.dress_descriptions),
                action=random.choice(self.action_descriptions)
            )
        elif person_num > 1:
            gender_summary = ""
            male_count = sum(1 for person in persons if person['gender'] == "男性")
            female_count = person_num - male_count
            
            if male_count > 0 and female_count > 0:
                gender_summary = f"其中有{male_count}位男性和{female_count}位女性"
            elif male_count > 0:
                gender_summary = f"全是{male_count}位男性"
            else:
                gender_summary = f"全是{female_count}位女性"
            
            template = random.choice(self.scene_templates['multiple_people'])
            return template.format(
                count=person_num,
                gender_summary=gender_summary,
                action=random.choice(self.action_descriptions)
            )
    
    def _generate_gesture_description(self, gestures):
        gesture_desc = "、".join([self.gesture_mapping.get(g, g) for g in gestures if g in self.gesture_mapping])
        if not gesture_desc:
            gesture_desc = "、".join(gestures)
        
        templates = [
            f"我看到你做了{gesture_desc}的手势，是在对我表达什么吗？",
            f"你的{gesture_desc}手势我已看到，这是何意？",
            f"你手上的{gesture_desc}动作非常清晰，想要传达什么讯息？",
            f"我注意到你的{gesture_desc}手势了，是否有何指示？"
        ]
        return random.choice(templates)
    
    def analyze_scene(self, frame):
        """
        分析场景，识别图像中的人体、手势等元素
        
        Args:
            frame: 摄像头采集的图像帧
            
        Returns:
            dict: 场景分析结果
        """
        if frame is None:
            return {
                "success": False,
                "error": "无效的图像帧",
                "people_count": 0,
                "gestures": [],
                "timestamp": time.time()
            }
            
        try:
            # 转换图像格式用于API调用
            success, image_data = cv2.imencode('.jpg', frame)
            if not success:
                return {
                    "success": False,
                    "error": "图像编码失败",
                    "people_count": 0,
                    "gestures": [],
                    "timestamp": time.time()
                }
                
            # 检测人体
            body_result = self.api_client.detect_body(image_data.tobytes())
            
            # 初始化结果
            people_count = 0
            gestures = []
            
            # 处理人体检测结果
            if body_result and body_result.get("success"):
                people_count = len(body_result.get("person_info", []))
                
                # 如果检测到人，尝试识别手势
                if people_count > 0:
                    gesture_result = self.api_client.detect_gesture(image_data.tobytes())
                    
                    # 处理手势识别结果
                    if gesture_result and gesture_result.get("success"):
                        for hand_info in gesture_result.get("result", []):
                            gesture_type = hand_info.get("gesture", -1)
                            if gesture_type >= 0:
                                # 将手势代码转换为描述性文本
                                gesture_text = self._get_gesture_text(gesture_type)
                                if gesture_text:
                                    gestures.append(gesture_text)
            
            # 返回分析结果
            return {
                "success": True,
                "error": None,
                "people_count": people_count,
                "gestures": gestures,
                "timestamp": time.time()
            }
            
        except Exception as e:
            util.log(1, f"场景分析错误: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "people_count": 0,
                "gestures": [],
                "timestamp": time.time()
            }
    
    def _get_gesture_text(self, gesture_code):
        """
        将手势代码转换为描述性文本
        
        Args:
            gesture_code: 百度API返回的手势代码
            
        Returns:
            str: 手势描述文本
        """
        # 手势代码映射到文本描述
        gesture_map = {
            0: "拳头",
            1: "OK",
            2: "比心",
            3: "祈祷",
            4: "鄙视",
            5: "点赞",
            6: "比六",
            7: "作揖",
            8: "我爱你",
            9: "武术",
            10: "双手比心",
            11: "数字1",
            12: "数字2",
            13: "数字3",
            14: "摇滚",
            15: "托举"
        }
        
        return gesture_map.get(gesture_code)

    def generate_dialogue_from_analysis(self, analysis_result, command_type=None):
        """
        根据分析结果生成对话内容
        
        Args:
            analysis_result (dict): 分析结果
            command_type (str, optional): 命令类型
            
        Returns:
            str: 生成的对话内容
        """
        # 如果分析失败或无内容，返回默认文本
        if not analysis_result or not analysis_result.get('success', False):
            return "我尝试观察周围，但似乎出了些问题，无法看清..."
            
        # 获取人数和手势信息
        people_count = analysis_result.get('person_count', 0)
        gestures = analysis_result.get('gestures', [])
        
        # 根据分析结果生成文本
        if gestures:
            # 有手势时优先描述手势
            gesture_desc = "、".join([self.gesture_mapping.get(g, g) for g in gestures if g in self.gesture_mapping])
            if not gesture_desc:
                gesture_desc = "、".join(gestures)
                
            templates = [
                f"我看到你做了{gesture_desc}的手势，是在对我表达什么吗？",
                f"你的{gesture_desc}手势我已看到，这是何意？",
                f"你手上的{gesture_desc}动作非常清晰，想要传达什么讯息？",
                f"我注意到你的{gesture_desc}手势了，是否有何指示？"
            ]
            return random.choice(templates)
            
        elif people_count > 0:
            # 描述人物情况
            if people_count == 1:
                templates = [
                    "我看到了一个人在眼前，似乎正在观察我...",
                    "我的神识捕捉到一个人影，正在我的感知范围内活动...",
                    "有一个人在我面前，我已经察觉到了...",
                    "我看到你了，就在我眼前..."
                ]
                return random.choice(templates)
            else:
                templates = [
                    f"我看到了{people_count}个人在我的视野中，他们似乎在观察着什么...",
                    f"我的天眼捕捉到{people_count}个人影，在此地聚集...",
                    f"场中有{people_count}人现身，我已尽收眼底...",
                    f"我看到了{people_count}个人，各有各的姿态神情..."
                ]
                return random.choice(templates)
        else:
            # 没有人时的描述
            templates = [
                "我的目光所及之处空无一人，四下静悄悄的...",
                "此地无人，只有虚空与我对视...",
                "奇怪，我没看到任何人，你在哪里呢？",
                "我张开天眼，却不见一个人影，真是奇特..."
            ]
            return random.choice(templates)
    
    def generate_closing(self, command_type=None):
        """
        生成结束语
        
        Args:
            command_type (str, optional): 命令类型
            
        Returns:
            str: 结束语
        """
        # 根据命令类型生成不同的结束语
        if command_type == "观察":
            closing_phrases = [
                "这便是我所见，天机已泄露，收回神通...",
                "景象已尽收眼底，我的天眼暂且闭合...",
                "已将所见之景告知于你，神通消退...",
                "这般情形我已看穿，神通暂且收回...",
                "物象变化无常，此刻所见已告知于你..."
            ]
        else:
            # 默认结束语
            closing_phrases = [
                "我已完成你的嘱托，还有何事相询？",
                "任务已然完成，可还有其他差遣？",
                "此事已了，还需我做些什么？",
                "我已依你所求而行，可需其他协助？",
                "事情已经处理完毕，还有其他事宜吗？"
            ]
            
        return random.choice(closing_phrases)
