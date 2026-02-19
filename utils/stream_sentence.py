import threading
import functools
import queue
import time
from typing import Optional, Any

def synchronized(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return func(self, *args, **kwargs)
    return wrapper

class SentenceCache:
    def __init__(self, max_sentences):
        self.lock = threading.Lock()
        self.buffer = [None] * max_sentences
        self.max_sentences = max_sentences
        self.writeIndex = 0
        self.readIndex = 0
        self.idle = 0

    @synchronized
    def write(self, sentence):
        # 如果缓冲区已满，则无法写入
        if self.idle == self.max_sentences:
            print("缓存区不够用")
            return False
        self.buffer[self.writeIndex] = sentence
        self.writeIndex = (self.writeIndex + 1) % self.max_sentences
        self.idle += 1
        return True

    @synchronized
    def read(self):
        # 如果缓冲区为空，没有可读的句子
        if self.idle == 0:
            return None
        sentence = self.buffer[self.readIndex]
        self.buffer[self.readIndex] = None
        self.readIndex = (self.readIndex + 1) % self.max_sentences
        self.idle -= 1
        return sentence

    @synchronized
    def clear(self):
        self.buffer = [None] * self.max_sentences
        self.writeIndex = 0
        self.readIndex = 0
        self.idle = 0

# 添加音频优先级队列管理器
class AudioPriorityQueue:
    """音频优先级队列管理器 - 统一管理所有音频播放任务"""
    
    def __init__(self, max_size: int = 50):
        self.queue = queue.PriorityQueue(maxsize=max_size)
        self.lock = threading.Lock()
        self.running = True
        
    def add_task(self, priority: int, audio_file: str, text: str = "", is_agent: bool = False) -> bool:
        """添加音频播放任务到队列
        Args:
            priority: 优先级，数字越大优先级越高
            audio_file: 音频文件路径
            text: 文本内容
            is_agent: 是否为agent生成的音频
        Returns:
            bool: 是否成功添加
        """
        try:
            # 转换优先级以适应Python队列（数字越小优先级越高）
            queue_priority = 100 - priority
            
            task = {
                'priority': priority,
                'audio_file': audio_file,
                'text': text,
                'is_agent': is_agent,
                'timestamp': time.time()
            }
            
            self.queue.put((queue_priority, task))
            return True
        except queue.Full:
            print(f"[音频队列] 队列已满，无法添加任务: {text[:30]}...")
            return False
        except Exception as e:
            print(f"[音频队列] 添加任务失败: {e}")
            return False
    
    def get_next_task(self, timeout: float = 1.0) -> Optional[dict]:
        """获取下一个音频播放任务
        Args:
            timeout: 超时时间（秒）
        Returns:
            dict: 任务信息或None
        """
        try:
            queue_priority, task = self.queue.get(timeout=timeout)
            return task
        except queue.Empty:
            return None
    
    def put(self, item, block=True, timeout=None):
        """向队列添加任务"""
        return self.queue.put(item, block, timeout)
    
    def get(self, block=True, timeout=None):
        """获取队列任务"""
        if block or timeout is not None:
            queue_priority, task = self.queue.get(block=block, timeout=timeout)
            return task
        else:
            queue_priority, task = self.queue.get(block=False)
            return task
    
    def clear(self):
        """清空队列"""
        with self.lock:
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break
    
    def get_nowait(self):
        """非阻塞获取队列任务"""
        queue_priority, task = self.queue.get_nowait()
        return task
    
    def task_done(self):
        """标记任务完成"""
        return self.queue.task_done()
    
    def join(self):
        """等待所有任务完成"""
        return self.queue.join()
    
    def size(self) -> int:
        """获取队列大小"""
        return self.queue.qsize()
    
    def qsize(self) -> int:
        """获取队列大小（兼容旧接口）"""
        return self.queue.qsize()
    
    def empty(self) -> bool:
        """检查队列是否为空"""
        return self.queue.empty()
    
    def stop(self):
        """停止队列"""
        self.running = False
        # 添加毒丸消息以停止处理线程
        try:
            self.queue.put((-999, None))
        except:
            pass

if __name__ == '__main__':
    cache = SentenceCache(3)
    cache.write("这是第一句话。")
    cache.write("这是第二句话。")
    print(cache.read())  # 读出第一句话
    cache.write("这是第三句话。")
    print(cache.read())  # 读出第二句话
    print(cache.read())  # 读出第三句话
    print(cache.read())  # 无内容，返回None