# SISI系统 Redis服务（便携式方案）

## ✅ 已实施特性

### 🎯 自动启动
- **启动SISI系统时自动启动Redis**
- 无需手动操作，main.py会自动检查并启动
- 已运行时自动跳过，避免重复启动

### 📦 便携式设计
- **所有Redis文件保存在项目内**（`SmartSisi/services/redis/`）
- **数据文件在项目内**（`sisi_redis.rdb`, `sisi_redis.aof`）
- **配置文件在项目内**（`redis_sisi.conf`）
- **迁移时复制整个项目即可**，无需重新配置

### 💾 资源配置
- **内存限制**：256MB（可在`redis_sisi.conf`中调整`maxmemory`）
- **端口**：6379（本地回环，不对外）
- **持久化**：RDB + AOF双重保障
- **淘汰策略**：allkeys-lru（内存满时自动清理最少使用的键）

## 📊 资源占用
- **内存**：实际占用50-100MB（限制256MB）
- **CPU**：几乎无感知（待机<1%）
- **磁盘**：数据文件通常<50MB

## 🔧 技术细节

### 启动流程
1. `main.py`启动时调用`_ensure_redis_running()`
2. 检查Redis是否已运行（`PING`测试）
3. 未运行则启动`redis-server.exe`，加载`redis_sisi.conf`
4. 等待最多5秒确认启动成功
5. 设置环境变量`REDIS_URL=redis://127.0.0.1:6379/0`

### 日志位置
- **Redis日志**：`SmartSisi/services/redis/redis_sisi.log`
- **SISI启动日志**：控制台输出

### 数据持久化
- **RDB快照**：每15分钟（如有1个写入）+ 每5分钟（如有10个写入）+ 每1分钟（如有10000个写入）
- **AOF日志**：每次写操作追加到`sisi_redis.aof`

## 🚀 验证方法

### 手动测试Redis
```powershell
# 测试连接
python -c "import redis; print(redis.Redis().ping())"

# 写入和读取
python -c "import redis; r=redis.Redis(); r.set('test','OK'); print(r.get('test'))"
```

### 查看Redis进程
```powershell
Get-Process redis-server
```

### 查看日志
```powershell
Get-Content SmartSisi\services\redis\redis_sisi.log -Tail 30
```

## 📌 迁移指南

### 方案A：整个项目迁移
直接复制整个`E:\liusisi`目录到新机器，Redis数据自动随项目走。

### 方案B：只迁移Redis数据
1. 复制`SmartSisi/services/redis/sisi_redis.rdb`
2. 复制`SmartSisi/services/redis/sisi_redis.aof`
3. 在新机器上启动SISI，Redis会自动加载这些数据

## ⚙️ 配置调整

### 修改内存限制
编辑`redis_sisi.conf`：
```conf
maxmemory 512mb  # 改为512MB
```

### 修改持久化频率
编辑`redis_sisi.conf`：
```conf
save 60 1  # 每1分钟至少1次写入时保存
```

## 🔒 安全说明
- **仅本地访问**：`bind 127.0.0.1`，不对外开放
- **无密码**：仅本机访问，无需密码
- **防火墙无影响**：不监听外网端口

## 🆚 为什么不用Docker/WSL
- **16GB内存环境**：Docker额外占用500MB-1GB
- **便携性**：原生exe文件，迁移时复制即可
- **启动速度**：<1秒启动，Docker需5-10秒
- **依赖最小化**：无需安装Docker/WSL

## 📅 Redis版本信息
- **版本**：5.0.14.1 (2022年发布)
- **稳定性**：生产级稳定版本
- **兼容性**：完全兼容Redis协议
- **维护状态**：社区活跃维护

## 🌐 现代化替代方案参考
虽然Redis 5.0.14已足够稳定且功能完备，如需最新特性可考虑：
- **Redis 7.x**（2024最新，但Windows官方不支持）
- **Valkey**（AWS分支，2024年推出，Linux优先）
- **Dragonfly**（高性能替代，2025年活跃，需Docker）

**当前方案结论**：Redis 5.0.14在SISI场景下完全够用，无需升级。
