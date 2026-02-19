import uuid
from utils import util

class TransitStation:
    def __init__(self):
        """初始化中转站"""
        self.session_id = str(uuid.uuid4())
        self._sisi_core = None  # 使用私有变量存储
        self.states = []
        self.tool_notification_states = []
        self._notification_thread = None
        self._stop_notification = False
        util.log(1, f"[中转站] 初始化完成 (会话ID: {self.session_id})")
        
    @property
    def sisi_core(self):
        """SmartSisi核心的getter方法"""
        return self._sisi_core
        
    @sisi_core.setter 
    def sisi_core(self, core):
        """SmartSisi核心的setter方法，添加验证"""
        if core is not None:
            self._sisi_core = core
            util.log(1, f"[中转站] SmartSisi核心已注册")
        else:
            util.log(2, f"[中转站] 警告: 尝试注册空的SmartSisi核心实例")
            
    def register_sisi_core(self, sisi_core):
        """注册SmartSisi核心实例"""
        self.sisi_core = sisi_core
        return self 