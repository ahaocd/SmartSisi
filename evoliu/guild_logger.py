#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒险者公会日志适配器
统一写入 SmartSisi/logs 的主日志文件（避免单独的 guild_logs 目录和独立文件）。
"""

from datetime import datetime

from utils import util


class GuildLogger:
    """公会日志（写入主日志，带统一前缀）"""

    _PREFIX = "[公会]"

    def __init__(self):
        util.log(1, f"{self._PREFIX} 日志已接入主日志目录 SmartSisi/logs")

    def info(self, msg: str):
        util.log(1, f"{self._PREFIX} {msg}")

    def warning(self, msg: str):
        util.log(2, f"{self._PREFIX} {msg}")

    def error(self, msg: str):
        util.log(3, f"{self._PREFIX} {msg}")

    def debug(self, msg: str):
        util.log(0, f"{self._PREFIX} {msg}")
    
    def section(self, title: str):
        """记录章节标题"""
        self.info("")
        self.info("=" * 80)
        self.info(title)
        self.info("=" * 80)
    
    def subsection(self, title: str):
        """记录子章节标题"""
        self.info("")
        self.info(f"--- {title} ---")
    
    def task_submitted(self, task_id: str, description: str, member: str):
        """记录任务提交"""
        self.subsection(f"任务提交: {task_id}")
        self.info(f"  描述: {description}")
        self.info(f"  执行者: {member}")
    
    def task_progress(self, task_id: str, progress_type: str, progress: str):
        """记录任务进度"""
        self.info(f"[进度] {task_id} - {progress_type}: {progress}")
    
    def task_completed(self, task_id: str, result_preview: str):
        """记录任务完成"""
        self.subsection(f"任务完成: {task_id}")
        self.info(f"  结果预览: {result_preview[:200]}...")
    
    def task_failed(self, task_id: str, error: str):
        """记录任务失败"""
        self.subsection(f"任务失败: {task_id}")
        self.error(f"  错误: {error}")
    
    def openclaw_event(self, event_type: str, data: dict):
        """记录OpenClaw事件"""
        self.info(f"[OpenClaw] {event_type}: {str(data)[:200]}")
    
    def liuye_interaction(self, user_input: str, liuye_response: str):
        """记录柳叶交互"""
        self.subsection("柳叶交互")
        self.info(f"  用户: {user_input[:100]}...")
        self.info(f"  柳叶: {liuye_response[:100]}...")


# 全局单例
_guild_logger = None


def get_guild_logger() -> GuildLogger:
    """获取公会日志器单例"""
    global _guild_logger
    if _guild_logger is None:
        _guild_logger = GuildLogger()
    return _guild_logger


if __name__ == "__main__":
    # 测试
    logger = get_guild_logger()
    logger.section("测试开始")
    logger.task_submitted("task_001", "测试任务", "openclaw")
    logger.task_progress("task_001", "thinking", "正在思考...")
    logger.task_completed("task_001", "任务完成，结果是...")
