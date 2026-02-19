# FRP 主链路 + Tailscale 备用链路方案（Android）

## 1. 目标
- 主链路继续使用公网域名 + FRP：`wss://www.xasia.cc/device`、`wss://www.xasia.cc/control`。
- 备用链路使用 Tailscale，仅在主链路故障时临时启用，不做常驻强依赖。

## 2. 当前主链路（已落地）
1. Android -> `https://www.xasia.cc`。
2. 台湾机 Nginx 将 `/device`、`/control` 反代到 `127.0.0.1:19102`。
3. `frps` 在台湾机监听 `7000`。
4. 本地 Sisi 网关监听 `9102`，`frpc` 将 `9102 -> 19102` 反向映射。

## 3. 备用链路原则（不常驻）
1. 不要求 Tailscale 24x7 常驻作为主入口。
2. 只保留“切换逻辑”和“应急脚本”。
3. 主链路健康时，Android 始终走 `www.xasia.cc`。

## 4. Tailscale 启用条件
- 出现以下任一情况时启用备用链路：
  - `www.xasia.cc/device` 持续 5xx。
  - FRP 控制端口不可用（`7000` 不通）。
  - 本地 `frpc` 无法保持会话。

## 5. 备用链路接入方式

### 5.1 服务端（台湾机）
- 预安装：`tailscale`、`tailscaled`。
- 备用时执行：
  1. `systemctl start tailscaled`
  2. `tailscale up --accept-routes --ssh`
- 验证：`tailscale ip -4`。

### 5.2 本地 Sisi 机器（Windows）
- 预安装 Tailscale 客户端并登录同一 tailnet。
- 备用时执行：
  1. 启动 Tailscale 客户端连接 tailnet。
  2. 保持 Sisi 网关监听 `9102`。

### 5.3 Android
- 备用链路有两种方式：
  1. Android 安装 Tailscale 并加入同一 tailnet，然后把 endpoint 切到 tailnet 地址。
  2. 如果 Android 端不加入 tailnet，则不能直接走纯 Tailscale 私网地址。

## 6. Android 端点策略（建议）
1. 默认 endpoint：
  - `wss://www.xasia.cc/device`
  - `wss://www.xasia.cc/control`
2. 备用 endpoint（手动切换）：
  - `wss://<taiwan-tailnet-ip-or-magicdns>/device`
  - `wss://<taiwan-tailnet-ip-or-magicdns>/control`
3. 回切：主链路恢复后切回 `www.xasia.cc`。

## 7. 运维建议
1. 主链路健康检查：每 60 秒探测 `/device` 与 `/control` 握手结果。
2. 把“主链路失败 -> 启用 Tailscale -> 切 Android endpoint”的流程写成固定 SOP。
3. 不把 Tailscale 当主通道，只做应急绕行。

## 8. 注意事项
1. Tailscale 本质是私网互联，不是公网反代。
2. Android 若不入 tailnet，不能直连 tailnet 地址。
3. 若需要“Android 不装 Tailscale 也能用备用”，应改为备用公网入口（例如第二台 FRP 或备用域名）。
