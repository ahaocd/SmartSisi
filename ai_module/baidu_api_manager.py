import os
import time
import base64
import logging
import requests
import cv2
from utils import util, config_util

class BaiduAPIManager:
    """百度API管理类"""
    _instance = None
    
    def __init__(self):
        self.access_token = None
        self.token_expire_time = 0
        self.api_cache = {}
        self.cache_expire = 300  # 缓存有效期5分钟
        
    @staticmethod
    def get_instance():
        if BaiduAPIManager._instance is None:
            BaiduAPIManager._instance = BaiduAPIManager()
        return BaiduAPIManager._instance
        
    def get_access_token(self):
        """获取access token"""
        try:
            # 检查token是否有效
            if self.access_token and time.time() < self.token_expire_time:
                return self.access_token
                
            # 加载配置
            config_util.load_config()
            if not all([config_util.baidu_body_app_id, 
                       config_util.baidu_body_api_key,
                       config_util.baidu_body_secret_key]):
                util.log(1, "[x] 百度API配置不完整")
                return None
                
            # 请求新token
            host = f'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={config_util.baidu_body_api_key}&client_secret={config_util.baidu_body_secret_key}'
            response = requests.get(host)
            
            if response.status_code == 200:
                result = response.json()
                if 'access_token' in result:
                    self.access_token = result['access_token']
                    # token有效期30天，提前1天过期
                    self.token_expire_time = time.time() + 29 * 24 * 3600
                    return self.access_token
                    
            util.log(1, f"[x] Token获取失败: {response.text}")
            return None
            
        except Exception as e:
            util.log(1, f"[x] Token获取异常: {str(e)}")
            return None
            
    def call_api(self, endpoint, image_base64, extra_params=None):
        """调用百度API，带有更完善的错误处理和重试机制"""
        try:
            # 获取token
            token = self.get_access_token()
            if not token:
                util.log(1, "[API] 无法获取访问令牌，API调用失败")
                return None
            
            # 检查缓存
            cache_key = f"{endpoint}_{hash(image_base64)}"
            if cache_key in self.api_cache:
                cache_entry = self.api_cache[cache_key]
                if time.time() - cache_entry['timestamp'] < self.cache_expire:
                    util.log(1, f"[API] 使用缓存结果: {endpoint}")
                    return cache_entry['result']
                else:
                    # 缓存过期，删除
                    del self.api_cache[cache_key]
                
            # 构建请求
            url = f"https://aip.baidubce.com{endpoint}?access_token={token}"
            params = {"image": image_base64}
            if extra_params:
                params.update(extra_params)
                
            # 发送请求，增加重试和超时控制
            max_retries = 3
            retry_delay = 1
            response = self._make_api_call(url, params, max_retries, retry_delay)
            
            if not response:
                util.log(1, f"[API] 调用失败: {endpoint}")
                return None
                
            if response.get('status') == 'success':
                # 缓存结果
                self.api_cache[cache_key] = {
                    'result': response,
                    'timestamp': time.time()
                }
                
                # 如果缓存太大，清理最旧的条目
                if len(self.api_cache) > 100:
                    oldest_key = min(self.api_cache.keys(), key=lambda k: self.api_cache[k]['timestamp'])
                    del self.api_cache[oldest_key]
                    
                return response
            else:
                util.log(1, f"[API] 调用返回错误: {response.get('message', 'Unknown error')}")
                return None
                
        except Exception as e:
            util.log(1, f"[API] 调用异常: {str(e)}")
            import traceback
            util.log(1, traceback.format_exc())
        return None
        
    def _make_api_call(self, url, params, max_retries=3, retry_delay=1):
        """执行API调用，带有超时和重试机制"""
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        
        for attempt in range(max_retries):
            try:
                # 增加超时设置，连接超时3秒，读取超时10秒
                response = requests.post(
                    url, 
                    data=params,
                    headers=headers,
                    timeout=(3.0, 10.0)
                )
                
                # 检查响应状态
                if response.status_code == 200:
                    result = response.json()
                    if 'error_code' in result and result['error_code'] != 0:
                        util.log(1, f"[API] 错误码: {result['error_code']}, 错误信息: {result.get('error_msg', '未知错误')}")
                        # 某些错误码可能表示需要重试
                        if result['error_code'] in [18, 19, 110, 111]:  # 这些是常见的临时错误码
                            continue
                        return {'status': 'error', 'message': result.get('error_msg', '未知错误'), 'code': result['error_code']}
                    return {'status': 'success', 'data': result}
                elif response.status_code == 401:
                    # 认证失败，可能是token过期
                    util.log(1, "[API] 认证失败，尝试刷新token...")
                    self.access_token = None  # 清除token以便重新获取
                    self.token_expire_time = 0
                    if attempt < max_retries - 1:  # 如果不是最后一次尝试
                        token = self.get_access_token()  # 重新获取token
                        if token:
                            # 更新URL中的token
                            url = url.split('access_token=')[0] + f'access_token={token}'
                            continue
                else:
                    util.log(1, f"[API] HTTP错误: {response.status_code}, 响应: {response.text}")
                    
            except requests.exceptions.Timeout:
                util.log(1, f"[API] 请求超时 (尝试 {attempt+1}/{max_retries})")
            except requests.exceptions.ConnectionError:
                util.log(1, f"[API] 连接错误 (尝试 {attempt+1}/{max_retries})")
            except Exception as e:
                util.log(1, f"[API] 请求异常: {str(e)} (尝试 {attempt+1}/{max_retries})")
                
            # 等待后重试，使用指数退避策略
            if attempt < max_retries - 1:  # 如果不是最后一次尝试
                wait_time = retry_delay * (2 ** attempt)  # 指数退避
                util.log(1, f"[API] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                
        return None
        
    def process_image(self, image):
        """图像预处理，优化图像质量和大小"""
        try:
            if image is None:
                util.log(1, "[x] 图像处理失败: 输入图像为空")
                return None
                
            # 检查图像尺寸和通道
            if len(image.shape) != 3 or image.shape[2] != 3:
                util.log(1, f"[x] 图像格式异常: shape={image.shape}")
                return None
                
            # 图像增强
            # 1. 调整亮度和对比度
            alpha = 1.2  # 对比度
            beta = 10    # 亮度
            enhanced = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)
            
            # 2. 降噪（如果需要）
            # enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 10, 10, 7, 21)
            
            # 3. 压缩图片 - 自适应大小
            max_size = 1024
            h, w = enhanced.shape[:2]
            
            # 只有当图像尺寸大于最大尺寸时才调整
            if max(h, w) > max_size:
                scale = max_size / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                enhanced = cv2.resize(enhanced, (new_w, new_h))
                util.log(1, f"[图像] 调整大小: {w}x{h} -> {new_w}x{new_h}")
            
            # 4. 转base64，控制编码质量
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]  # 90% 质量的JPEG
            _, img_encoded = cv2.imencode('.jpg', enhanced, encode_param)
            
            if img_encoded is None or len(img_encoded) == 0:
                util.log(1, "[x] 图像编码失败")
                return None
                
            base64_data = base64.b64encode(img_encoded.tobytes()).decode()
            
            # 记录处理后的图像大小
            kb_size = len(base64_data) / 1024
            util.log(1, f"[图像] 处理完成, 大小: {kb_size:.2f} KB")
            
            return base64_data
            
        except Exception as e:
            util.log(1, f"[x] 图像处理异常: {str(e)}")
            import traceback
            util.log(1, traceback.format_exc())
            return None
        
    def detect_body(self, image_base64):
        """人体检测与属性识别"""
        try:
            # 调用API
            result = self.call_api("/rest/2.0/image-classify/v1/body_analysis", image_base64)
            if not result:
                return None
                
            # 提取人数
            person_info = result.get("person_info", [])
            person_count = len(person_info)
            
            # 处理每个人的信息
            persons = []
            for person in person_info:
                # 提取属性
                attributes = person.get("attributes", {})
                
                # 基本属性
                basic = {
                    "gender": attributes.get("gender", {}).get("name", "unknown"),
                    "age": attributes.get("age", {}).get("name", "unknown"),
                    "upper_wear": attributes.get("upper_wear", {}).get("name", "unknown"),
                    "upper_color": attributes.get("upper_color", {}).get("name", "unknown"),
                    "lower_wear": attributes.get("lower_wear", {}).get("name", "unknown"),
                    "lower_color": attributes.get("lower_color", {}).get("name", "unknown")
                }
                
                # 行为属性
                behaviors = {
                    "smoking": attributes.get("smoke", {}).get("name", "no") == "yes",
                    "calling": attributes.get("cellphone", {}).get("name", "no") == "yes",
                    "carrying": attributes.get("carrying_item", {}).get("name", "no") == "yes",
                    "umbrella": attributes.get("umbrella", {}).get("name", "no") == "yes"
                }
                
                # 姿态属性
                pose = {
                    "standing": attributes.get("is_standing", {}).get("name", "no") == "yes",
                    "sitting": attributes.get("is_sitting", {}).get("name", "no") == "yes",
                    "orientation": attributes.get("orientation", {}).get("name", "unknown")
                }
                
                persons.append({
                    "basic": basic,
                    "behaviors": behaviors,
                    "pose": pose,
                    "location": person.get("location", {}),
                    "body_parts": person.get("body_parts", {})
                })
            
            # 记录日志
            util.log(1, f"[API] 检测到 {person_count} 个人")
            if person_count > 0:
                util.log(1, f"[API] 人物属性: {persons[0]['basic']}")
            
            return {
                "person_count": person_count,
                "persons": persons,
                "raw_result": result  # 保留原始数据以备用
            }
            
        except Exception as e:
            util.log(1, f"[错误] 人体检测失败: {str(e)}")
            return None
        
    def detect_gesture(self, image_base64):
        """手势识别"""
        return self.call_api("/rest/2.0/image-classify/v1/gesture", image_base64)
        
    def analyze_hand(self, image_base64):
        """手部关键点分析"""
        return self.call_api("/rest/2.0/image-classify/v1/hand_analysis", image_base64)
        
    def analyze_image(self, image_base64):
        """统一的图像分析入口，优化并发处理和错误处理"""
        if not image_base64:
            util.log(1, "[API] 图像数据为空，无法分析")
            return None
            
        try:
            util.log(1, "[API] 开始全面图像分析...")
            results = {}
            
            # 创建异步任务
            import concurrent.futures
            
            # 定义API调用函数
            def call_body_api():
                util.log(1, "[API] 调用人体检测和属性识别...")
                return ("body_analysis", self.call_api("/rest/2.0/image-classify/v1/body_analysis", image_base64))
                
            def call_gesture_api():
                util.log(1, "[API] 调用手势识别...")
                return ("gesture", self.call_api("/rest/2.0/image-classify/v1/gesture", image_base64))
                
            def call_hand_api():
                util.log(1, "[API] 调用手部关键点识别...")
                return ("hand", self.call_api("/rest/2.0/image-classify/v1/hand_analysis", image_base64))
                
            def call_keypoint_api():
                util.log(1, "[API] 调用人体关键点识别...")
                return ("keypoint", self.call_api("/rest/2.0/image-classify/v1/body_analysis", image_base64, {"type": "keypoint"}))
                
            def call_crowd_api():
                util.log(1, "[API] 调用人流量统计...")
                return ("crowd", self.call_api("/rest/2.0/image-classify/v1/body_num", image_base64))
            
            # 并发执行API调用
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # 提交所有任务
                future_to_api = {
                    executor.submit(call_body_api): "body",
                    executor.submit(call_gesture_api): "gesture",
                    executor.submit(call_hand_api): "hand",
                    # 下面两个API可能不是每次都需要调用，可以按需添加
                    # executor.submit(call_keypoint_api): "keypoint",
                    # executor.submit(call_crowd_api): "crowd"
                }
                
                # 收集结果
                for future in concurrent.futures.as_completed(future_to_api):
                    api_name = future_to_api[future]
                    try:
                        key, result = future.result()
                        if result:
                            results[key] = result
                            
                            # 根据API类型记录特定信息
                            if key == "body_analysis" and "person_info" in result.get("data", {}):
                                person_count = len(result["data"]["person_info"])
                                util.log(1, f"[API] 检测到 {person_count} 个人体")
                            elif key == "gesture" and "result" in result.get("data", {}):
                                gesture_count = len(result["data"]["result"])
                                util.log(1, f"[API] 检测到 {gesture_count} 个手势")
                            elif key == "hand" and "hand_info" in result.get("data", {}):
                                hand_count = len(result["data"]["hand_info"])
                                util.log(1, f"[API] 检测到 {hand_count} 只手")
                    except Exception as e:
                        util.log(1, f"[API] {api_name} 处理结果异常: {str(e)}")
            
            # 在需要时顺序调用其他API
            if "body_analysis" in results and results["body_analysis"].get("data", {}).get("person_num", 0) > 0:
                # 如果检测到人，可能需要调用关键点API
                key, result = call_keypoint_api()
                if result:
                    results[key] = result
                    
                # 如果有多人，可能需要调用人流量统计
                if results["body_analysis"].get("data", {}).get("person_num", 0) > 1:
                    key, result = call_crowd_api()
                    if result:
                        results[key] = result
                        person_num = result.get("data", {}).get("person_num", 0)
                        util.log(1, f"[API] 统计到 {person_num} 人")
            
            util.log(1, "[API] 图像分析完成")
            return results
            
        except Exception as e:
            util.log(1, f"[错误] 图像分析失败: {str(e)}")
            import traceback
            util.log(1, traceback.format_exc())
            return None
