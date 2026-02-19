"""
Agent UI Professional - 专业级对话界面
提供与 Agent 交互的完整 UI 面板
"""

import os
import sys
import subprocess
import time
import logging
import requests
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局变量
a2a_process: Optional[subprocess.Popen] = None
agent_instance = None


def start_a2a_server():
    """启动A2A服务器（如未运行）"""
    global a2a_process
    
    print("\n🚀 检查A2A服务器状态...")
    
    # 先检查是否已运行
    try:
        response = requests.get("http://localhost:8001/a2a/health", timeout=2)
        if response.status_code == 200:
            print("✅ A2A服务器已在运行")
            return True
    except:
        pass
    
    # 未运行，尝试启动
    print("⏳ 启动A2A服务器...")
    try:
        # 修复：使用llm目录下的轻量级a2a_server_main.py
        a2a_server_path = project_root / "llm" / "a2a_server_main.py"
        
        if not a2a_server_path.exists():
            print(f"❌ A2A服务器文件不存在: {a2a_server_path}")
            return False
        
        # 启动子进程（避免PIPE阻塞，输出丢弃到DEVNULL）
        creation_flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        a2a_process = subprocess.Popen(
            [sys.executable, str(a2a_server_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(project_root),
            creationflags=creation_flags
        )

        # 可配置超时（秒），默认120；可通过环境变量 A2A_STARTUP_TIMEOUT 覆盖
        try:
            startup_timeout = int(os.environ.get('A2A_STARTUP_TIMEOUT', '120'))
        except Exception:
            startup_timeout = 120

        deadline = time.time() + startup_timeout
        print(f"   正在等待A2A服务器启动（超时 {startup_timeout}s）...")

        # 先探测端口可用性，再调用健康检查
        def port_open(host: str, port: int) -> bool:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            try:
                s.connect((host, port))
                return True
            except Exception:
                return False
            finally:
                try:
                    s.close()
                except Exception:
                    pass

        last_log = 0
        while time.time() < deadline:
            # 1) 端口开放即说明Uvicorn已启动
            if port_open('127.0.0.1', 8001):
                try:
                    response = requests.get("http://localhost:8001/a2a/health", timeout=2)
                    if response.status_code == 200:
                        print("✅ A2A服务器启动成功")
                        return True
                except Exception:
                    pass
            # 每2秒打印一次“等待中...”
            now = time.time()
            if now - last_log >= 2:
                remaining = int(deadline - now)
                print(f"   等待中... 剩余{remaining}s")
                last_log = now
            time.sleep(0.5)

        print(f"❌ A2A服务器启动超时（已等待{startup_timeout}s）")
        return False
        
    except Exception as e:
        print(f"❌ 启动A2A服务器失败: {e}")
        return False


def initialize_agent():
    """初始化Agent实例"""
    global agent_instance
    
    print("\n🤖 初始化Agent...")
    try:
        from llm.agent.sisi_agent import SisiAgentCore
        agent_instance = SisiAgentCore()
        print("✅ Agent初始化成功")
        return True
    except Exception as e:
        print(f"❌ Agent初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# 创建FastAPI应用
app = FastAPI(title="Agent UI Professional")


@app.get("/", response_class=HTMLResponse)
async def get_ui():
    """返回UI页面"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Chat UI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #f5f5f5;
            color: #1a1a1a;
            height: 100vh;
            overflow: hidden;
        }
        
        .container {
            display: flex;
            height: 100vh;
        }
        
        /* 主对话区域 */
        .main-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #ffffff;
        }
        
        /* 顶部标题栏 */
        .header {
            padding: 20px 24px;
            background: #ffffff;
            border-bottom: 1px solid #e5e5e5;
        }
        
        .header h1 {
            font-size: 20px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        /* 对话区域 */
        .chat-area {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        
        .chat-area::-webkit-scrollbar {
            width: 8px;
        }
        
        .chat-area::-webkit-scrollbar-track {
            background: #f5f5f5;
        }
        
        .chat-area::-webkit-scrollbar-thumb {
            background: #d0d0d0;
            border-radius: 4px;
        }
        
        .chat-area::-webkit-scrollbar-thumb:hover {
            background: #b0b0b0;
        }
        
        /* 消息气泡 */
        .message {
            max-width: 800px;
            margin-bottom: 8px;
        }
        
        .message.user {
            align-self: flex-end;
            margin-left: auto;
        }
        
        .message.assistant {
            align-self: flex-start;
        }
        
        .message-header {
            font-size: 13px;
            color: #666;
            margin-bottom: 6px;
            font-weight: 500;
        }
        
        .message-content {
            padding: 12px 16px;
            border-radius: 12px;
            line-height: 1.6;
            word-wrap: break-word;
            word-break: break-word;
            white-space: pre-wrap;
            overflow-wrap: break-word;
        }
        
        .message.user .message-content {
            background: #2563eb;
            color: #ffffff;
        }
        
        .message.assistant .message-content {
            background: #f8f8f8;
            color: #1a1a1a;
            border: 1px solid #e5e5e5;
        }
        
        /* Markdown样式 */
        .message-content h1,
        .message-content h2,
        .message-content h3 {
            margin: 12px 0 8px 0;
            color: #1a1a1a;
        }
        
        .message-content h1 {
            font-size: 1.5em;
        }
        
        .message-content h2 {
            font-size: 1.3em;
        }
        
        .message-content h3 {
            font-size: 1.1em;
        }
        
        .message-content p {
            margin: 8px 0;
        }
        
        .message-content strong {
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .message-content em {
            font-style: italic;
        }
        
        .message-content code {
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: "Consolas", "Monaco", monospace;
            font-size: 0.9em;
            color: #d73a49;
        }
        
        .message-content pre {
            background: #f6f8fa;
            padding: 12px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 12px 0;
            border: 1px solid #e1e4e8;
        }
        
        .message-content pre code {
            background: none;
            padding: 0;
            color: #24292e;
        }
        
        .message-content ul,
        .message-content ol {
            margin: 8px 0;
            padding-left: 24px;
        }
        
        .message-content li {
            margin: 4px 0;
        }
        
        .message-content a {
            color: #60a5fa;
            text-decoration: none;
        }
        
        .message-content a:hover {
            text-decoration: underline;
        }
        
        .message-content blockquote {
            border-left: 3px solid #d0d0d0;
            padding-left: 12px;
            margin: 12px 0;
            color: #666;
        }
        
        /* 工具调用卡片 */
        .tool-call {
            background: #f8f8f8;
            border: 1px solid #e5e5e5;
            border-radius: 8px;
            padding: 12px;
            margin: 8px 0;
            font-size: 13px;
        }
        
        .tool-call-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
            color: #2563eb;
            font-weight: 500;
        }
        
        .tool-call-name {
            font-family: "Consolas", "Monaco", monospace;
        }
        
        .tool-call-result {
            color: #666;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        /* 加载动画 */
        .loading-indicator {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            background: #f8f8f8;
            border-radius: 12px;
            max-width: 800px;
            border: 1px solid #e5e5e5;
        }
        
        .loading-dots {
            display: flex;
            gap: 4px;
        }
        
        .loading-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #60a5fa;
            animation: loading-pulse 1.4s ease-in-out infinite;
        }
        
        .loading-dot:nth-child(2) {
            animation-delay: 0.2s;
        }
        
        .loading-dot:nth-child(3) {
            animation-delay: 0.4s;
        }
        
        @keyframes loading-pulse {
            0%, 80%, 100% {
                opacity: 0.3;
                transform: scale(0.8);
            }
            40% {
                opacity: 1;
                transform: scale(1);
            }
        }
        
        .loading-text {
            color: #666;
            font-size: 14px;
        }
        
        /* 输入区域 */
        .input-area {
            padding: 20px 24px;
            background: #ffffff;
            border-top: 1px solid #e5e5e5;
            min-height: 88px;
            flex-shrink: 0;
        }
        
        .input-container {
            max-width: 800px;
            margin: 0 auto;
            display: flex;
            gap: 12px;
            align-items: flex-end;
        }
        
        #messageInput {
            flex: 1;
            padding: 12px 16px;
            background: #ffffff;
            border: 1px solid #d0d0d0;
            border-radius: 12px;
            color: #1a1a1a;
            font-size: 15px;
            font-family: inherit;
            resize: vertical;
            min-height: 48px;
            max-height: 150px;
            line-height: 1.5;
        }
        
        #messageInput:focus {
            outline: none;
            border-color: #2563eb;
            background: #ffffff;
        }
        
        #sendButton {
            padding: 12px 24px;
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
            flex-shrink: 0;
        }
        
        #sendButton:hover:not(:disabled) {
            background: #1d4ed8;
        }
        
        #sendButton:disabled {
            background: #d0d0d0;
            color: #999;
            cursor: not-allowed;
        }
        
        /* 右侧状态面板 */
        .inspector-panel {
            width: 320px;
            background: #f8f8f8;
            border-left: 1px solid #e5e5e5;
            padding: 24px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }
        
        .inspector-panel::-webkit-scrollbar {
            width: 6px;
        }
        
        .inspector-panel::-webkit-scrollbar-track {
            background: #f8f8f8;
        }
        
        .inspector-panel::-webkit-scrollbar-thumb {
            background: #d0d0d0;
            border-radius: 3px;
        }
        
        .inspector-section {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .inspector-title {
            font-size: 13px;
            font-weight: 600;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .status-item {
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 12px;
            background: #ffffff;
            border-radius: 8px;
            border: 1px solid #e5e5e5;
        }
        
        .status-label {
            font-size: 12px;
            color: #666;
            font-weight: 500;
        }
        
        .status-value {
            font-size: 14px;
            color: #1a1a1a;
            word-wrap: break-word;
            word-break: break-word;
            white-space: pre-wrap;
            line-height: 1.5;
        }
        
        .status-value.active {
            color: #60a5fa;
            font-weight: 500;
        }
        
        .status-value.success {
            color: #10b981;
        }
        
        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }
        
        .status-indicator.pending {
            background: #6b7280;
        }
        
        .status-indicator.active {
            background: #60a5fa;
            animation: pulse 2s ease-in-out infinite;
        }
        
        .status-indicator.complete {
            background: #10b981;
        }
        
        @keyframes pulse {
            0%, 100% {
                opacity: 1;
            }
            50% {
                opacity: 0.5;
            }
        }
        
        .tool-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        
        .tool-item {
            padding: 8px 12px;
            background: #ffffff;
            border-radius: 6px;
            font-size: 13px;
            color: #1a1a1a;
            border: 1px solid #e5e5e5;
            font-family: "Consolas", "Monaco", monospace;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- 主对话区域 -->
        <div class="main-area">
            <!-- 顶部标题 -->
            <div class="header">
                <h1>Agent Chat</h1>
            </div>
            
            <!-- 对话区域 -->
            <div class="chat-area" id="chatArea">
                <div class="message assistant">
                    <div class="message-header">Assistant</div>
                    <div class="message-content">你好！我是你的智能助手。有什么我可以帮助你的吗？</div>
                </div>
            </div>
            
            <!-- 输入区域 -->
            <div class="input-area">
                <div class="input-container">
                    <textarea 
                        id="messageInput" 
                        placeholder="输入消息..."
                        rows="1"
                        onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault(); sendMessage();}"
                        oninput="this.style.height='auto'; this.style.height=Math.min(this.scrollHeight,150)+'px';"
                        autocomplete="off"
                    ></textarea>
                    <button id="sendButton" type="button" onclick="sendMessage()">发送</button>
                </div>
            </div>
        </div>
        
        <!-- 右侧状态面板 -->
        <div class="inspector-panel">
            <!-- 处理阶段 -->
            <div class="inspector-section">
                <div class="inspector-title">处理阶段</div>
                <div class="status-item">
                    <div class="status-label">初始处理</div>
                    <div class="status-value" id="statusStart">
                        <span class="status-indicator pending"></span>等待中
                    </div>
                </div>
                <div class="status-item">
                    <div class="status-label">中间处理</div>
                    <div class="status-value" id="statusMiddle">
                        <span class="status-indicator pending"></span>等待中
                    </div>
                </div>
                <div class="status-item">
                    <div class="status-label">最终优化</div>
                    <div class="status-value" id="statusFinal">
                        <span class="status-indicator pending"></span>等待中
                    </div>
                </div>
            </div>
            
            <!-- 性能信息 -->
            <div class="inspector-section">
                <div class="inspector-title">性能信息</div>
                <div class="status-item">
                    <div class="status-label">响应时间</div>
                    <div class="status-value" id="responseTime">-</div>
                </div>
            </div>
            
            <!-- 工具调用 -->
            <div class="inspector-section">
                <div class="inspector-title">工具调用</div>
                <div class="tool-list" id="toolsList">
                    <div style="color: #666; font-size: 13px;">暂无工具调用</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const chatArea = document.getElementById('chatArea');
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        
        // 调试：检查元素是否正确获取
        console.log('chatArea:', chatArea);
        console.log('messageInput:', messageInput);
        console.log('sendButton:', sendButton);
        
        // 自动滚动到底部
        function scrollToBottom() {
            chatArea.scrollTop = chatArea.scrollHeight;
        }
        
        // 重置状态面板
        function resetStatus() {
            document.getElementById('statusStart').innerHTML = '<span class="status-indicator pending"></span>等待中';
            document.getElementById('statusMiddle').innerHTML = '<span class="status-indicator pending"></span>等待中';
            document.getElementById('statusFinal').innerHTML = '<span class="status-indicator pending"></span>等待中';
            document.getElementById('responseTime').textContent = '-';
            document.getElementById('toolsList').innerHTML = '<div style="color: #666; font-size: 13px;">暂无工具调用</div>';
        }
        
        // 更新状态面板
        function updateStatus(phase, status, text = '') {
            const element = document.getElementById(`status${phase}`);
            if (element) {
                let indicator = 'pending';
                let className = '';
                
                if (status === 'active') {
                    indicator = 'active';
                    className = 'active';
                    text = text || '处理中...';
                } else if (status === 'complete') {
                    indicator = 'complete';
                    className = 'success';
                    text = text || '完成';
                }
                
                element.innerHTML = `<span class="status-indicator ${indicator}"></span>${text}`;
                element.className = `status-value ${className}`;
            }
        }
        
        // 更新工具列表
        function updateTools(tools) {
            const toolsList = document.getElementById('toolsList');
            if (tools && tools.length > 0) {
                toolsList.innerHTML = tools.map(tool => 
                    `<div class="tool-item">${tool}</div>`
                ).join('');
            }
        }
        
        // 简化渲染为纯文本，避免正则解析导致脚本中断
        function renderMarkdown(text) {
            return text;
        }
        
        // 生成简短摘要（用于右侧阶段展示）
        function brief(text, maxLen = 120) {
            if (!text) return '';
            const t = String(text).replace(/\s+/g, ' ').trim();
            return t.length > maxLen ? t.slice(0, maxLen - 1) + '…' : t;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // 添加消息到对话区
        function addMessage(role, content, isHtml = false) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}`;
            
            const headerDiv = document.createElement('div');
            headerDiv.className = 'message-header';
            headerDiv.textContent = role === 'user' ? 'You' : 'Assistant';
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            
            // 清理内容：移除XML标签（thinking/answer/tool等）
            let cleanContent = String(content);
            
            // 1. 移除<thinking>标签
            cleanContent = cleanContent.replace(/<thinking>[^]*?<\/thinking>/gi, '');
            
            // 2. 提取<answer>标签内容
            const answerMatch = cleanContent.match(/<answer>([^]*?)<\/answer>/i);
            if (answerMatch) {
                cleanContent = answerMatch[1];
            }
            
            // 3. 移除所有残留的XML标签
            cleanContent = cleanContent.replace(/<[^>]+>/g, '');
            
            // 4. 清理多余空白并去除首尾空白
            cleanContent = cleanContent.trim();
            
            // 5. 如果内容为空，显示提示
            if (!cleanContent) {
                cleanContent = '（响应内容为空）';
            }
            
            if (isHtml) {
                contentDiv.innerHTML = cleanContent;
            } else {
                // 纯文本渲染，确保无语法/正则风险
                contentDiv.textContent = renderMarkdown(cleanContent);
            }
            
            messageDiv.appendChild(headerDiv);
            messageDiv.appendChild(contentDiv);
            chatArea.appendChild(messageDiv);
            
            scrollToBottom();
        }
        
        // 添加加载指示器
        function addLoadingIndicator(phase = 'start') {
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'message assistant';
            loadingDiv.id = 'loadingIndicator';
            
            const headerDiv = document.createElement('div');
            headerDiv.className = 'message-header';
            headerDiv.textContent = 'Assistant';
            
            const loadingContent = document.createElement('div');
            loadingContent.className = 'loading-indicator';
            
            let text = '正在思考...';
            if (phase === 'middle') {
                text = '正在处理...';
            } else if (phase === 'final') {
                text = '正在优化回答...';
            }
            
            loadingContent.innerHTML = `
                <div class="loading-dots">
                    <div class="loading-dot"></div>
                    <div class="loading-dot"></div>
                    <div class="loading-dot"></div>
                </div>
                <div class="loading-text" id="loadingText">${text}</div>
            `;
            
            loadingDiv.appendChild(headerDiv);
            loadingDiv.appendChild(loadingContent);
            chatArea.appendChild(loadingDiv);
            
            scrollToBottom();
        }
        
        // 更新加载指示器文本
        function updateLoadingText(phase) {
            const loadingText = document.getElementById('loadingText');
            if (loadingText) {
                if (phase === 'middle') {
                    loadingText.textContent = '正在处理...';
                } else if (phase === 'final') {
                    loadingText.textContent = '正在优化回答...';
                }
            }
        }
        
        // 移除加载指示器
        function removeLoadingIndicator() {
            const loadingDiv = document.getElementById('loadingIndicator');
            if (loadingDiv) {
                loadingDiv.remove();
            }
        }
        
        // 发送消息
        async function sendMessage() {
            console.log('sendMessage被调用');
            const message = messageInput.value.trim();
            console.log('消息内容:', message);
            if (!message) {
                console.log('消息为空，返回');
                return;
            }
            
            // 禁用输入
            messageInput.disabled = true;
            sendButton.disabled = true;
            
            // 显示用户消息
            addMessage('user', message);
            messageInput.value = '';
            
            // 重置状态面板
            resetStatus();
            
            // 显示加载动画
            addLoadingIndicator('start');
            updateStatus('Start', 'active');
            
            const startTime = Date.now();
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: message }),
                });
                
                if (!response.ok) {
                    throw new Error('请求失败');
                }
                
                const data = await response.json();
                
                // 计算响应时间
                const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
                document.getElementById('responseTime').textContent = `${elapsed}s`;
                
                // 🔧 统一从 /api/states 获取所有状态信息（避免重复代码）
                try {
                    const statesResp = await fetch('/api/states');
                    if (statesResp.ok) {
                        const s = await statesResp.json();
                        const os = s.optimized_states || {};

                        // 阶段文本（取摘要显示到右侧面板）
                        const startText  = brief(os.start);
                        const middleText = brief(os.middle);
                        const finalText  = brief(os.final);

                        if (os.start)  { updateStatus('Start',  'complete', startText  || '已完成'); updateLoadingText('middle'); updateStatus('Middle', 'active'); }
                        if (os.middle) { updateStatus('Middle', 'complete', middleText || '已完成'); updateLoadingText('final');  updateStatus('Final',  'active'); }
                        if (os.final)  { updateStatus('Final',  'complete', finalText  || '已完成'); }

                        // 工具列表（只从 /api/states 获取）
                        if (Array.isArray(s.tools_used) && s.tools_used.length) {
                            updateTools(s.tools_used);
                        }

                        // 主响应为空：优先用 middle 兜底，其次 final，再其次后端final_text
                        if (!data.response || !String(data.response).trim()) {
                            const fallback = (os.middle || os.final || s.final_text || '').toString().trim();
                            if (fallback) {
                                addMessage('assistant', fallback);
                            }
                        }
                    }
                } catch (e) {
                    console.error('中转站拉取失败:', e);
                }
                
                // 移除加载动画
                console.log('准备移除加载动画');
                removeLoadingIndicator();
                console.log('加载动画已移除');
                
                // 显示回复
                console.log('data.response:', data.response);
                console.log('准备调用addMessage');
                if (data.response) {
                    addMessage('assistant', data.response);
                    console.log('addMessage已调用（有response）');
                } else {
                    addMessage('assistant', '抱歉，我无法生成回复。');
                    console.log('addMessage已调用（无response）');
                }
                
            } catch (error) {
                console.error('发送消息失败:', error);
                removeLoadingIndicator();
                addMessage('assistant', '抱歉，发生了错误: ' + error.message);
                resetStatus();
            } finally {
                // 恢复输入
                messageInput.disabled = false;
                sendButton.disabled = false;
                messageInput.focus();
            }
        }
        
        // 确保内联事件可访问全局函数
        window.sendMessage = sendMessage;

        // 事件监听
        console.log('准备绑定事件监听器');
        if (sendButton) {
            sendButton.addEventListener('click', () => {
                console.log('发送按钮被点击');
                sendMessage();
            });
            console.log('发送按钮事件监听器已绑定');
        } else {
            console.error('发送按钮元素未找到！');
        }
        
        if (messageInput) {
            messageInput.addEventListener('keydown', (e) => {
                console.log('键盘按下:', e.key);
                if (e.key === 'Enter' && !e.shiftKey) {
                    console.log('回车键触发发送');
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            // 自动调整textarea高度
            messageInput.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 150) + 'px';
            });
            
            console.log('输入框事件监听器已绑定');
        } else {
            console.error('输入框元素未找到！');
        }
        
        // 初始化时滚动到底部
        scrollToBottom();
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@app.post("/api/chat")
async def chat(request: Request):
    """处理对话请求"""
    try:
        data = await request.json()
        user_message = data.get("message", "")
        
        if not user_message:
            return JSONResponse(
                status_code=400,
                content={"error": "消息不能为空"}
            )
        
        if not agent_instance:
            return JSONResponse(
                status_code=500,
                content={"error": "Agent未初始化"}
            )
        
        # 调用Agent
        logger.info(f"收到用户消息: {user_message}")
        
        try:
            # 🔧 简化：直接调用sisi_agent.invoke，它内部已处理所有清洗逻辑
            result = agent_instance.invoke(user_message, uid=0)
            logger.info(f"[/api/chat] sisi_agent.invoke返回: {result}")

            # sisi_agent返回(response_text, response_type)元组
            response_text = ""
            if isinstance(result, tuple) and len(result) >= 1:
                response_text = str(result[0])
            else:
                response_text = str(result)
            
            logger.info(f"[/api/chat] 提取response_text: '{response_text[:100]}'")

            # 🔧 简化：所有状态信息由前端通过 /api/states 获取，避免重复
            return JSONResponse(content={
                "response": response_text
            })
        
        except Exception as e:
            logger.error(f"Agent调用失败: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"error": f"Agent调用失败: {str(e)}"}
            )
            
    except Exception as e:
        logger.error(f"处理请求失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/states")
async def get_states():
    """直接返回中转站的阶段状态、最终文本和工具列表（尽量不依赖优化站）。"""
    try:
        tools_used = []
        optimized_states = {}
        final_text = ""

        try:
            from llm.transit_station import get_transit_station
            station = get_transit_station()

            # 阶段内容：优先optimized，其次LG快照
            optimized_states = station.get_all_optimized_contents() or {}
            logger.info(f"[/api/states] optimized_states: {optimized_states}")

            # final文本兜底：优先 optimized.final / lg_snapshot.final，其次最近final状态
            final_text = optimized_states.get("final") or ""
            if not final_text:
                finals = station.get_states_by_stage("final")
                if finals:
                    final_text = str(finals[-1].get("content", ""))
                    logger.info(f"[/api/states] final_text从final状态提取: {final_text[:50]}")
            else:
                logger.info(f"[/api/states] final_text从optimized_states: {final_text[:50]}")
        except Exception as e:
            logger.warning(f"读取中转站状态失败: {e}")

        # 工具列表暂时从optimized_states无法得出，保留空数组，后续若需要可从日志或队列补集
        response_data = {
            "optimized_states": optimized_states,
            "final_text": final_text,
            "tools_used": tools_used
        }
        logger.info(f"[/api/states] 返回给前端: {response_data}")
        return JSONResponse(content=response_data)
    except Exception as e:
        logger.error(f"[/api/states] 异常: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  Agent UI Professional 启动中...")
    print("=" * 60)
    
    
    # 1. 启动A2A（如未运行则自启动）
    print("\n⚙️ [1/3] 检查A2A服务器...")
    if not start_a2a_server():
        print("❌ 无法启动A2A服务器，程序退出")
        return
    
    # 2. 初始化Agent
    print("\n⚙️ [2/3] 初始化Agent...")
    if not initialize_agent():
        print("❌ 无法初始化Agent，程序退出")
        return
    
    # 3. 启动UI服务器
    print("\n⚙️ [3/3] 启动UI服务器...")
    print("\n" + "=" * 60)
    print("✅ 所有服务启动成功！")
    print("\n🌐 访问地址: http://localhost:8080")
    print("=" * 60)
    print("\n💡 提示:")
    print("  - 在浏览器中打开上述地址即可使用")
    print("  - 按 Ctrl+C 停止服务")
    print("\n" + "=" * 60 + "\n")
    
    try:
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=8080,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n\n👋 正在关闭服务...")
    finally:
        # 清理A2A进程
        global a2a_process
        if a2a_process:
            try:
                a2a_process.terminate()
                a2a_process.wait(timeout=5)
                print("✅ A2A服务器已关闭")
            except:
                a2a_process.kill()
                print("⚠️ 强制关闭A2A服务器")


if __name__ == "__main__":
    main()

