# 台湾服务器 FRP 内网穿透部署记录（2026-02-20）

## 1. 最终结论（说人话）
- 你要的“网站内网穿透”方案已经按 `FRP` 落地到台湾机。
- 服务端 `frps` 已部署并稳定运行，公网端口 `7000` 已打开。
- 站点 `www.xasia.cc` 已加入 `/device`、`/control` 反代到 `127.0.0.1:19102`。
- 本地 `frpc` 的配置和启动脚本已准备好。
- 目前业务链路还差最后一步：你本地 `9102` 网关没运行，所以现在访问 `/device` 会 `502`。

## 2. 这次确认的架构与技术栈
- 系统：Ubuntu 24.04.1 LTS（台湾机）
- Web 层：Nginx（80/443）
- 业务容器：WordPress + MySQL（Docker Compose）
- 隧道层：FRP（本次新增）
  - `frps`：台湾机
  - `frpc`：你本地 Windows（SmartSisi 所在机器）
- 本地网关：`gateway.app.ws_gateway_server`，默认监听 `9102`

## 3. 失败记录（排查过程）
1. `mcp-ssh-manager` 的 `npm run test-connection` 是坏脚本。
- 现象：`package.json` 有脚本，但 `tools/test-connection.py` 不存在。
- 处理：改用仓库内 `SSHManager` + debug 脚本做真实连通和探测。

2. 自动化脚本初版多次被 `Node 模板字符串 ${...}` 吃掉。
- 现象：shell 脚本中的 `${VAR}` 被 JS 当插值解析，报语法错。
- 处理：改用占位符后再替换回 `$`，脚本恢复可执行。

3. nginx 备份文件放错目录导致配置检测失败。
- 现象：备份文件写进 `/etc/nginx/sites-enabled/`，触发 `duplicate default server`。
- 处理：把备份移动到 `/etc/nginx/backup/`，`nginx -t` 恢复通过并成功 reload。

4. `frpc.local.toml` 初版编码导致 frpc 解析失败。
- 现象：`json: cannot unmarshal string into Go value of type v1.ClientConfig`。
- 原因：文件带 BOM（UTF-8 BOM）。
- 处理：改为 ASCII 重写配置，frpc 正常启动。

5. 业务端口未起导致入口 502。
- 现象：`https://www.xasia.cc/device` 返回 `502 Bad Gateway`。
- 根因：本机 `9002/9003/9102` 都未监听。

## 4. 成功步骤（已完成）
1. 完成磁盘应急清理（前置保障）。
- `/` 可用空间：`395MB -> 2.5GB`
- 关键清理：journal、nginx access 日志、docker json 日志、apt cache、disabled snap、npm/next 缓存。

2. Docker 日志限额已生效。
- 修改文件：`/root/wordpress/docker-compose.yml`
- 配置：`max-size=20m`, `max-file=3`
- 结果：两个容器日志不再无限增长。

3. 台湾机 `frps` 已部署并开机自启。
- 二进制：`/opt/sisi-frp/bin/frps`
- 配置：`/opt/sisi-frp/conf/frps.toml`
- systemd：`/etc/systemd/system/frps.service`
- 版本：`v0.67.0`
- 验证：`7000` 对公网 `open`

4. 网站反代规则已落地。
- 文件：`/etc/nginx/sites-enabled/xasia-with-ssl.conf`
- 插入标记：`SISI-FRP-GATEWAY-BEGIN/END`
- 路由：
  - `/device -> http://127.0.0.1:19102`
  - `/control -> http://127.0.0.1:19102`

5. 本地 `frpc` 侧已就绪。
- 目录：`E:\liusisi\SmartSisi\gateway\ops\frp`
- 文件：
  - `frpc.exe`
  - `frpc.example.toml`
  - `frpc.local.toml`
  - `run-frpc.ps1`
  - `stop-frpc.ps1`
- 安全：`frpc.local.toml` 已加入 `.gitignore`。

6. 增加“随 Sisi 生命周期启动/停止 frpc”逻辑（不做机器级常驻）。
- 代码：`core/sisi_booter.py`
- 配置键（`system.conf`）：
  - `frp_client_auto_launch_enabled`
  - `frp_client_exe_path`
  - `frp_client_config_path`
  - `frp_client_extra_args`
- 行为：`start()` 时拉起 frpc；`stop()` 时回收 frpc 进程。

## 5. 当前未完成项（最后 1 步）
- 若本地业务网关未启动（`9002/9003/9102` 没监听），公网入口仍会返回 5xx。
- 处理方式：先启动本地后端与网关，再拉起 frpc。

## 6. 现在怎么一键跑通
1. 启动本地后端（9002/9003）。
- 具体进程按你的 SmartSisi 实际启动方式拉起。

2. 启动本地 WS 网关（9102）。
```powershell
cd E:\liusisi\SmartSisi
.\gateway\ops\run_ws_gateway.ps1
```

3. 启动 frpc。
```powershell
cd E:\liusisi\SmartSisi\gateway\ops\frp
.\run-frpc.ps1
```

4. 验证。
```powershell
curl.exe -I https://www.xasia.cc/device --max-time 10
curl.exe -I https://www.xasia.cc/control --max-time 10
```

## 7. 回滚与止损
- 停止本地 frpc：
```powershell
cd E:\liusisi\SmartSisi\gateway\ops\frp
.\stop-frpc.ps1
```
- 删除 nginx 新增规则：删除 `SISI-FRP-GATEWAY-BEGIN/END` 代码块后 `nginx -t && systemctl reload nginx`。
- 停止 frps：`systemctl stop frps`（需要时再 `disable`）。

## 8. 本次产物清单
- 本地：
  - `E:\liusisi\SmartSisi\gateway\ops\frp\frpc.example.toml`
  - `E:\liusisi\SmartSisi\gateway\ops\frp\frpc.local.toml`
  - `E:\liusisi\SmartSisi\gateway\ops\frp\run-frpc.ps1`
  - `E:\liusisi\SmartSisi\gateway\ops\frp\stop-frpc.ps1`
  - `E:\liusisi\SmartSisi\core\sisi_booter.py`
  - `E:\liusisi\SmartSisi\gateway\README.md`
  - `E:\liusisi\SmartSisi\docs\2026-02-20-frp-primary-tailscale-fallback-plan.md`
  - `E:\liusisi\SmartSisi\docs\2026-02-20-taiwan-frp-deploy-report.md`
  - `E:\liusisi\SmartSisi\.gitignore`（追加 FRP 本地敏感文件忽略规则）
- 远端（台湾机）：
  - `/opt/sisi-frp/bin/frps`
  - `/opt/sisi-frp/conf/frps.toml`
  - `/etc/systemd/system/frps.service`
  - `/etc/nginx/sites-enabled/xasia-with-ssl.conf`
  - `/etc/nginx/backup/xasia-with-ssl.conf.bak-sisi-gw-20260219214056`
