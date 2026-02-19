# SmartSisi 接口总览与前端对照（通俗版）

生成时间：2026-02-15

## 1. 后端接口总览（比喻版）

### 1.1 GUI Flask（E:\liusisi\SmartSisi\gui\flask_server.py）

#### 1.1.1 现有 GUI 接口

| 接口 | 方法 | 通俗比喻 | 作用/说明 |
| --- | --- | --- | --- |
| `/api/submit` | POST | 把配置变更交给“管家”，让他改账本 | 合并并保存配置片段 |
| `/api/get-data` | POST | 向前台要“当前配置+当前音色” | 读取配置并返回当前音色 |
| `/api/tts/voices` | GET | 看“当前音色” | 返回 `sisi_voice_uri` / `liuye_voice_uri` |
| `/api/tts/voices` | POST | 改“当前音色” | 支持 `role+voice_uri` 或直接传 `sisi_voice_uri/liuye_voice_uri` |
| `/api/config/all` | GET | 盘点“整套仓库” | 返回 `config_json` 与 `system_conf` |
| `/api/config/all` | POST | 整箱搬运/整体替换 | 写入 `config_json` 与 `system_conf` |
| `/api/start-live` | POST | 按下“开机键” | 启动 Sisi 运行态并广播 liveState |
| `/api/stop-live` | POST | 按下“关机键” | 停止 Sisi 运行态并广播 liveState |
| `/api/get_run_status` | POST | 看“指示灯亮不亮” | 查询是否在运行 |
| `/api/send` | POST | 把一句话塞进“投递口” | 发送用户文本输入 |
| `/api/get-msg` | POST | 翻“聊天记录本” | 当前实现多为返回空列表 |
| `/api/get-member-list` | POST | 成员花名册 | 当前实现返回空列表 |
| `/api/adopt_msg` | POST | 给某条消息“盖章入档” | 采纳消息进入 Q&A 等逻辑 |
| `/v1/models` | GET | 菜单板：可用模型清单 | OpenAI 兼容模型列表 |
| `/v1/chat/completions` | POST | 点单窗口：聊天回复 | OpenAI 兼容聊天接口 |
| `/api/send/v1/chat/completions` | POST | 侧门通道：同上 | `/v1/chat/completions` 的别名 |
| `/to_greet` | POST | “打招呼按钮” | 触发打招呼交互 |
| `/to_wake` | POST | “拍肩唤醒” | 设置唤醒标记 |
| `/to_stop_talking` | POST | “打断/止损键” | 触发打断交互 |
| `/transparent_pass` | POST | 透明传声筒 | 透传文本/音频给系统处理 |
| `/api/browser-check` | GET | 进门体检 | 返回浏览器支持情况 |
| `/audio/<filename>` | GET | 音频取件柜 | 取音频文件 |
| `/` | GET/POST | 大厅入口 | 前端入口页 |
| `/setting` | GET | 设置房间 | 设置页 |
| `/<path:path>` | GET | 静态走廊 | 静态资源路由 |

#### 1.1.2 新增 /api/v1（柳叶/模型配置/公会/冒险者）

| 接口 | 方法 | 通俗比喻 | 作用/说明 |
| --- | --- | --- | --- |
| `/api/v1/liuye/health` | GET | 柳叶体检 | 柳叶状态/版本 |
| `/api/v1/liuye/session` | POST | 建会话“房间” | 创建会话 |
| `/api/v1/liuye/session/{session_id}` | GET | 查房 | 获取会话 |
| `/api/v1/liuye/session/{session_id}/turn` | POST | 房间里说一句 | 发送一轮对话 |
| `/api/v1/liuye/tools` | GET | 工具抽屉 | 柳叶工具列表 |
| `/api/v1/liuye/tools/{tool}/metadata` | GET | 工具说明书 | 工具详情 |
| `/api/v1/liuye/invoke/{tool}` | POST | 叫号窗口 | 调用柳叶工具 |
| `/api/v1/liuye/memory/search` | POST | 记忆检索 | 搜索柳叶记忆 |
| `/api/v1/liuye/memory/add` | POST | 记忆存档 | 写入柳叶记忆 |
| `/api/v1/liuye/events/subscribe` | GET(SSE) | 广播频道 | 柳叶事件流（SSE） |
| `/api/v1/models/providers` | GET | 供应商清单 | 从 `system.conf` 聚合 |
| `/api/v1/models/providers` | POST | 供应商入库 | 写入 `system.conf` |
| `/api/v1/models` | GET | 模型清单 | 从 `system.conf` 聚合 |
| `/api/v1/models` | POST | 模型入库 | 写入 `system.conf` |
| `/api/v1/models/aliases` | GET | 别名薄 | 读取 `config.json` 的 `model_aliases` |
| `/api/v1/models/aliases` | POST | 别名登记 | 写入 `model_aliases` |
| `/api/v1/models/aliases/{alias}` | PATCH | 别名修改 | 更新 `model_aliases` |
| `/api/v1/models/validate` | POST | 体检 | 校验别名或供应商 |
| `/api/v1/models/usage` | GET | 用量表 | 当前为空表 |
| `/api/v1/guilds` | GET | 公会名录 | 仅一个主公会 |
| `/api/v1/guilds` | POST | 建公会 | 当前只读（返回冲突） |
| `/api/v1/guilds/{guild_id}` | GET | 公会详情 | 状态摘要 |
| `/api/v1/guilds/{guild_id}` | PATCH | 改公会 | 当前只读（返回冲突） |
| `/api/v1/guilds/{guild_id}/roster` | GET | 花名册 | 成员列表 |
| `/api/v1/guilds/{guild_id}/roster` | POST | 拉人入会 | 当前只读（返回冲突） |
| `/api/v1/guilds/{guild_id}/quests` | GET | 任务看板 | 任务列表 |
| `/api/v1/guilds/{guild_id}/quests` | POST | 发任务 | 提交任务 |
| `/api/v1/guilds/{guild_id}/match` | POST | 分派 | 指定成员派单 |
| `/api/v1/guilds/{guild_id}/events` | GET(SSE) | 公会广播 | 事件流（SSE） |

提示：`guild_id` 来自 `config.json` 的 `attribute.name` 首字母缩写（如“柳思思” -> `lss`），前端以接口返回的 ID 为准。

提示：`/v1/models` 已改为**动态**：从 `system.conf` 的 `*_llm_model` 和 `config.json` 的 `model_aliases` 拼出列表。
| `/api/v1/adventurers` | GET | 冒险者名录 | 成员列表 |
| `/api/v1/adventurers` | POST | 新增冒险者 | 当前只读（返回冲突） |
| `/api/v1/adventurers/{id}` | GET | 冒险者档案 | 成员详情 |
| `/api/v1/adventurers/{id}` | PATCH | 改档案 | 当前只读（返回冲突） |
| `/api/v1/adventurers/{id}/status` | GET | 状态灯 | 当前状态 |
| `/api/v1/adventurers/{id}/invoke` | POST | 叫他干活 | 提交任务给该冒险者 |
| `/api/v1/adventurers/{id}/skills` | GET | 技能牌 | 技能列表 |
| `/api/v1/adventurers/{id}/skills` | POST | 装技能 | 当前只读（返回冲突） |
| `/api/v1/adventurers/{id}/memory/search` | POST | 记忆检索 | 共享记忆搜索 |
| `/api/v1/adventurers/{id}/memory/add` | POST | 记忆存档 | 共享记忆写入 |
| `/api/v1/adventurers/{id}/sessions` | GET | 任务/会话 | 该成员的任务记录 |

### 1.2 WebSocket 推送通道（E:\liusisi\SmartSisi\core\wsa_server.py）

| 通道 | 端口 | 通俗比喻 | 说明 |
| --- | --- | --- | --- |
| `ws://<host>:10003` | 10003 | 广播喇叭 | Web UI 推送 `deviceList/voiceList/liveState/panelMsg/panelReply` 等 |
| `ws://<host>:10002` | 10002 | 人类专线 | HumanServer 通道 |
| `ws://<host>:10000` | 10000 | 演练场 | TestServer 通道 |

### 1.3 A2A FastAPI（E:\liusisi\SmartSisi\llm\a2a\a2a_server.py / llm\a2a_server_main.py）

| 接口 | 方法 | 通俗比喻 | 作用/说明 |
| --- | --- | --- | --- |
| `/.well-known/agent.json` | GET | 电子名片 | Agent 描述信息 |
| `/a2a/health` | GET | 体检报告 | 健康检查 |
| `/a2a/discover` | GET | 黄页 | 服务发现 |
| `/a2a/jsonrpc` | POST | 总机 | JSON-RPC 入口 |
| `/a2a/route/query` | POST | 路线询问台 | 路由查询 |
| `/a2a/invoke/{tool_name}` | POST | 叫号窗口 | 调用工具 |
| `/a2a/tool/{tool_name}/metadata` | GET | 说明书 | 工具元数据 |
| `/a2a/task/subscribe/{task_id}` | GET | 任务广播 | SSE 订阅任务进度 |
| `/a2a/task/{tool_name}/{task_id}` | GET | 任务查询 | 查询任务状态 |
| `/a2a/test/sse` | GET | 练习场 | SSE 测试 |
| `/a2a/test/simple-sse` | GET | 练习场 | SSE 测试 |
| `/a2a/test/direct-sse` | GET | 练习场 | SSE 测试 |
| `/a2a/sse-test/{test_type}` | GET | 练习场 | SSE 测试 |
| `/a2a/task/subscribe/test_json_to_sse` | GET | 练习场 | SSE 测试 |

### 1.4 OpenAI 兼容 API（E:\liusisi\SmartSisi\utils\openai_api\api_server.py）

| 接口 | 方法 | 通俗比喻 | 作用/说明 |
| --- | --- | --- | --- |
| `/health` | GET | 体检单 | 健康检查 |
| `/v1/models` | GET | 菜单板 | 模型列表 |
| `/v1/completions` | POST | 旧式点单 | Completion 接口 |
| `/v1/chat` | POST | 简易聊天口 | Chat 接口 |
| `/v1/chat/completions` | POST | 标准点单 | Chat Completions |
| `/v1/embeddings` | POST | 贴标签机 | 向量化接口 |

### 1.5 语音克隆 Flask（E:\liusisi\SmartSisi\llm\a2a\tools\voice_clone_flask.py）

| 接口 | 方法 | 通俗比喻 | 作用/说明 |
| --- | --- | --- | --- |
| `/` | GET | 工作台入口 | 语音克隆页面 |
| `/api/voices` | GET | 音色货架 | 语音列表 |
| `/api/upload` | POST | 投料口 | 上传素材 |
| `/api/tts` | POST | 开始生产 | 文本转语音 |
| `/api/stt` | POST | 反向机 | 语音转文字 |
| `/audio/<filename>` | GET | 成品取件 | 拉取生成音频 |
| `/api/delete` | POST | 清库存 | 删除素材/音频 |
| `/api/davinci/config` | GET/POST | 调参面板 | 配置 Davinci |
| `/api/davinci/status` | GET | 状态灯 | Davinci 状态 |
| `/api/davinci/import` | POST | 导入箱 | Davinci 导入 |
| `/api/ai_optimize` | POST | 润色机 | AI 优化 |
| `/api/prompts` | GET/POST | 提示词仓 | 提示词读写 |
| `/api/config` | GET/POST | 总开关 | 全局配置读写 |

### 1.6 Socket 桥接（E:\liusisi\SmartSisi\socket_bridge_service.py）

| 通道 | 端口 | 通俗比喻 | 说明 |
| --- | --- | --- | --- |
| `ws://<host>:9001` | 9001 | 中转站 | WebSocket ? TCP(10001) 桥接 |

## 2. 前端接口现状（按“实际调用”与“仅封装”区分）

来源：`E:\liusisi\SmartSisi\gui\frontend\src` 实际引用扫描结果

### 2.1 前端实际调用（UI 里真实触发）

| 接口/通道 | 方法 | 前端位置 | 用途 |
| --- | --- | --- | --- |
| `/api/config/all` | GET | `gui/frontend/src/main.js` | 启动时拉取后端配置 |
| `/api/config/all` | POST | `gui/frontend/src/components/LeftDrawer.vue` | 全量保存配置 |
| `/api/submit` | POST | `gui/frontend/src/components/LeftDrawer.vue` | 增量提交配置 |
| `/api/start-live` | POST | `gui/frontend/src/components/ChatComposer.vue` | 进入运行态 |
| `/api/stop-live` | POST | `gui/frontend/src/components/ChatComposer.vue` | 退出运行态 |
| `/api/get_run_status` | POST | `gui/frontend/src/main.js` | 同步运行状态 |
| `/api/send/v1/chat/completions` | POST | `gui/frontend/src/components/ChatComposer.vue` | 发送用户输入（带 model） |
| `/v1/models` | GET | `gui/frontend/src/components/ChatComposer.vue` | 拉取模型列表 |
| `/to_wake` | POST | `gui/frontend/src/components/LeftDrawer.vue` | 触发唤醒 |
| `/to_stop_talking` | POST | `gui/frontend/src/components/ChatComposer.vue` | 打断当前输出 |
| `ws://<host>:10003` | WS | `gui/frontend/src/api/wsBridge.js` | 设备/音色/状态/回复推送 |

### 2.2 前端仅封装（当前未被 UI 调用）

说明：以下接口在 `gui/frontend/src/api/sisiApi.js` 有封装，但 UI 里未引用；`apiConsole.js` 里也仅是“待用动作清单”，未接 UI。

| 接口 | 方法 | 前端封装位置 | 备注 |
| --- | --- | --- | --- |
| `/api/get-data` | POST | `gui/frontend/src/api/sisiApi.js` | 封装存在，未见 UI 调用 |
| `/api/get-msg` | POST | `gui/frontend/src/api/sisiApi.js` | 同上 |
| `/api/adopt_msg` | POST | `gui/frontend/src/api/sisiApi.js` | 同上 |
| `/api/get-member-list` | POST | `gui/frontend/src/api/sisiApi.js` | 同上 |
| `/api/browser-check` | GET | `gui/frontend/src/api/sisiApi.js` | 同上 |
| `/v1/chat/completions` | POST | `gui/frontend/src/api/sisiApi.js` | 同上 |
| `/api/send` | POST | `gui/frontend/src/api/sisiApi.js` | 同上 |
| `/to_greet` | POST | `gui/frontend/src/api/sisiApi.js` | 同上 |
| `/transparent_pass` | POST | `gui/frontend/src/api/sisiApi.js` | 同上 |

## 3. 对照表（后端已加 vs 前端未接）

### 3.1 新增 /api/v1 接口对照（用于逐步对齐）

| 接口 | 后端状态 | 前端状态 | 备注 |
| --- | --- | --- | --- |
| `/api/v1/liuye/*` | 已加 | 未接 | 新柳叶接口族 |
| `/api/v1/models/*` | 已加 | 未接 | 模型配置接口族 |
| `/api/v1/guilds/*` | 已加 | 未接 | 冒险者公会接口族 |
| `/api/v1/adventurers/*` | 已加 | 未接 | 冒险者接口族 |

### 3.2 现有 GUI 接口对照（已对齐=UI 实际调用）

| 接口族 | 后端状态 | 前端状态 |
| --- | --- | --- |
| `/api/config/all` | 已有 | 已接 |
| `/api/submit` | 已有 | 已接 |
| `/api/start-live` | 已有 | 已接 |
| `/api/stop-live` | 已有 | 已接 |
| `/api/get_run_status` | 已有 | 已接 |
| `/api/send/v1/chat/completions` | 已有 | 已接 |
| `/to_wake` | 已有 | 已接 |
| `/to_stop_talking` | 已有 | 已接 |
| `ws://<host>:10003` | 已有 | 已接 |

## 4. 前端接入规则（必须遵守）

任何新接口接入前端时，必须配置一个**简洁、直观、易懂**的 UI 文案标签（1-3 个词为佳）。

示例：
- `/api/start-live` -> “启动”
- `/api/stop-live` -> “停止”
- `/api/config/all` -> “配置”
- `/api/v1/guilds/{id}/quests` -> “任务”

## 5. 前端对接清单（一步一步，按你的说法）

说明：下面是“该接哪个接口”的清单，不改前端代码，只是对齐路线图。

### 5.1 模型相关（你说的“思考/快速/模型选择”）

| 前端动作 | 对接接口 | 形象比喻 | 说明 | UI 小字 |
| --- | --- | --- | --- | --- |
| 选择模型列表 | `/v1/models` | “菜单板” | 拉取可选模型清单 | 当前模型名 |
| 思考 | `/api/send/v1/chat/completions` | “深思按钮” | `model=4.1THINK` | 思考 |
| 快速 | `/api/send/v1/chat/completions` | “快递按钮” | `model=4.1fast` | 快速 |

补充：前端会把“思考/快速”写入 `llm_model`（`4.1THINK` / `4.1fast`），并通过 `/api/send/v1/chat/completions` 发送，后端会用 `config.json` 的 `model_aliases` 映射到实际模型（例如 `grok-4.1-thinking` / `grok-4.1-fast`）。

规则：前端只显示“思考/快速/当前模型名”，具体供应商和路由由后端决定，避免以后换供应商时改 UI。

### 5.2 公会与冒险者（按面板顺序对接）

| 前端动作 | 对接接口 | 形象比喻 | 说明 | UI 小字 |
| --- | --- | --- | --- | --- |
| 公会状态 | `/api/v1/guilds` | “公会总览牌” | 当前只有一个公会 | 公会 |
| 公会详情 | `/api/v1/guilds/{guild_id}` | “公会档案” | 运行/待办摘要 | 详情 |
| 公会任务列表 | `/api/v1/guilds/{guild_id}/quests` (GET) | “任务看板” | 任务列表 | 任务 |
| 公会发任务 | `/api/v1/guilds/{guild_id}/quests` (POST) | “发委托” | 提交任务 | 发任务 |
| 冒险者列表 | `/api/v1/adventurers` | “花名册” | 成员列表 | 冒险者 |
| 冒险者档案 | `/api/v1/adventurers/{id}` | “档案卡” | 详情 | 档案 |
| 冒险者状态 | `/api/v1/adventurers/{id}/status` | “状态灯” | 运行状态 | 状态 |
| 冒险者技能 | `/api/v1/adventurers/{id}/skills` | “技能牌” | 技能列表 | 技能 |
| 冒险者调用 | `/api/v1/adventurers/{id}/invoke` | “派单按钮” | 提交任务给他 | 派单 |

提示：`{guild_id}` 和 `{id}` 由接口返回值决定，前端只用返回的 ID，不要硬编码。
| `/api/send` | POST | `gui/frontend/src/api/sisiApi.js` | 封装存在，未见 UI 调用 |
