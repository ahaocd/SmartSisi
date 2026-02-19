# 柳叶交互测试矩阵（系统化）

## 1. 测试目标
- 聊天独立性：不触发工具时，柳叶回复不依赖公会链路健康。
- 工具真实性：出现“已提交/已执行”时必须有对应审计证据。
- 双通道能力：聊天回复与公会事件互不阻塞。
- 中断控制：可在任意时刻停止当前回复、停止任务、解散公会。

## 2. 分层测试

### L0 合同层（离线）
- 文件：
  - `tests/test_liuye_timing_contract.py`
  - `tests/test_liuye_guild_interaction_contract.py`
  - `tests/test_guild_contract_force_stop.py`
- 断言：
  - 状态机合法（pending/running/completed/failed/aborted）
  - 文案与事实一致（无“口头提交”）
  - trace_id/correlation_id 完整透传

### L1 时序层（离线模拟）
- 用例：
  - A1 纯聊天：无工具调用，直接返回
  - A2 委托任务：先 ACK，再出现提交事件
  - A3 打断：中途 cancel 后不再追加旧输出
  - A4 离线公会：返回“已入队待恢复”，不谎称执行中
- 指标：
  - `ack_latency_ms`
  - `first_event_ms`
  - `interrupt_to_stop_ms`

### L2 在线探针（5000 服务）
- 脚本：`tests/liuye_runtime_probe.py`
- 命令：
  - `python tests/liuye_runtime_probe.py --base-url http://127.0.0.1:5000 --skip-liuye-turn --report-json runtime/liuye_probe_skip_turn_now.json`
  - `python tests/liuye_runtime_probe.py --base-url http://127.0.0.1:5000 --report-json runtime/liuye_probe_full_now.json`
- 输出：
  - HTTP 可用性
  - SSE 首包延迟
  - turn 路由超时率

## 3. 回归门禁阈值
- `turn_timeout_rate < 1%`
- `ack_p95_ms < 500`
- `sse_first_event_p95_ms < 300`
- `false_commit_rate = 0`
- `interrupt_to_stop_p95_ms < 300`

## 4. 关键场景清单
- S1：纯聊天（不应出现任何任务事件）
- S2：明确委托公会（必须出现 submit_task 审计）
- S3：公会离线时委托（应返回入队态）
- S4：任务执行中收到新用户输入（柳叶可继续对话）
- S5：用户强制停止单任务（状态改为 aborted）
- S6：用户解散公会（所有活动任务停止，公会 idle）
- S7：角色切换 handoff（交接信息进入柳叶消息构建链路）

## 5. 记录与追踪
- 每次探针落盘 JSON 到 `runtime/`。
- 每次线上故障必须附：
  - 日志片段（时间戳）
  - 对应 trace_id/correlation_id
  - 复现步骤
