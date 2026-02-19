def send_notification(self, content, content_type="text", metadata=None, for_optimization=True):
    """发送一条主动通知到中转站
    
    Args:
        content: 通知内容
        content_type: 内容类型，默认"text"，可选"event", "audio", "image"等
        metadata: 额外元数据
        for_optimization: 是否需要经过优化站优化，默认True
        
    Returns:
        bool: 是否成功发送
    """
    try:
        # 添加日志
        util.log(1, f"[{self.get_tool_name()}] 发送通知: {str(content)[:50]}..., 类型: {content_type}")
        
        # 获取中转站实例 - 使用全局函数确保获取相同实例
        from llm.transit_station import get_transit_station
        transit = get_transit_station()
        
        # 输出中转站实例信息，用于调试
        util.log(1, f"[{self.get_tool_name()}] 使用中转站实例ID: {transit.session_id}")
        
        # 构建通知对象
        notification = {
            "source_tool": self.get_tool_name(),
            "content": content,
            "content_type": content_type,
            "for_optimization": for_optimization,
            "timestamp": time.time()
        }
        
        # 添加元数据
        if metadata and isinstance(metadata, dict):
            notification.update(metadata)
            
        # 将通知添加到中转站的通知队列
        transit.tool_notification_states.append(notification)
        
        # 主动触发处理前检查SmartSisi核心状态
        if transit.sisi_core is None:
            util.log(2, f"[{self.get_tool_name()}] 警告: 中转站SmartSisi核心未注册，通知可能无法被处理")
        
        return True
    except Exception as e:
        util.log(2, f"[{self.get_tool_name()}] 发送通知异常: {str(e)}")
        return False 