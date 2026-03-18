# src/init.sh — 运行时初始化

## 概述

`v2ray.sh` 入口文件 source 此脚本。负责:
1. 加载公共库 (`lib.sh`)
2. 检测系统环境 & 服务状态
3. 加载核心模块并分发命令

## 初始化流程

```
1. source lib.sh            公共库 (颜色、工具函数、路径变量)
2. 检测包管理器 (apt-get / yum)
3. 检测架构 (amd64 / arm64)
4. 检测 v2ray core 版本
   - v5+ 使用 `run` 参数, v4 不使用
   - 自动修复 systemd service 文件 (如有必要)
5. 检测 v2ray 运行状态 (running / stopped)
6. 检测 Caddy 是否安装及运行状态
   - 读取 Caddyfile 中的 http_port / https_port
   - 自动修复 caddy >= 2.8.2 的 --adapter 参数
7. load protocol.sh
8. load menu.sh
9. load service.sh
10. load config.sh
11. load cmd.sh
12. main $args
```

## 关键变量

| 变量 | 值 | 说明 |
|------|------|------|
| `is_core_ver` | 如 `V2Ray 5.x.x` | core 版本字符串 |
| `is_core_status` | running / stopped | core 运行状态 |
| `is_core_stop` | 1 / unset | core 是否已停止 |
| `is_caddy` | 1 / unset | Caddy 是否已安装 |
| `is_caddy_ver` | 如 `v2.8.x` | Caddy 版本 |
| `is_caddy_status` | running / stopped | Caddy 运行状态 |
| `is_http_port` | 默认 80 | 从 Caddyfile 读取 |
| `is_https_port` | 默认 443 | 从 Caddyfile 读取 |
| `is_with_run_arg` | `run` / unset | v5+ 启动参数 |
