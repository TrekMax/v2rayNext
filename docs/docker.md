# Docker 部署

## 原理

容器基于 Ubuntu 22.04，使用 `/usr/local/bin/systemctl` mock 脚本替代 systemd，将 `systemctl start/stop/restart v2ray.service` 映射为对 v2ray 进程的直接管理（nohup / pkill）。v2ray 二进制在容器首次启动时自动下载，通过 volume 持久化，无需重复下载。

## 文件说明

```
Dockerfile             # 镜像定义
docker-compose.yml     # Compose 部署配置
docker/
├── systemctl          # systemctl mock，按服务名分发
├── subscription-service # 独立管理订阅进程、PID 与启用状态
└── entrypoint.sh      # 容器入口：下载二进制、创建 service 骨架、启动 v2ray
```

## 快速开始

### 方式一：docker compose（推荐）

```bash
# 构建并进入容器
docker compose run --rm v2ray

# 首次进入后添加一个配置，开始测试
v2ray add tcp
```

### 方式二：docker run

```bash
# 构建镜像
docker build -t v2raynext .

# 运行容器（交互模式）
docker run -it --rm \
  --network host \
  -v v2ray-bin:/etc/v2ray/bin \
  -v v2ray-conf:/etc/v2ray/conf \
  -v v2ray-subscription:/etc/v2ray/subscription \
  v2raynext
```

## 测试流程

```bash
# 进入容器后：

# 添加配置
v2ray add tcp

# 查看配置
v2ray info

# 查看状态（通过 pgrep 检测 v2ray 进程）
v2ray status

# 查看日志
v2ray log

# 更改端口
v2ray port <config-name> auto

# 删除配置
v2ray del <config-name>
```

## 注意事项

- **TLS 协议不可用**：WS-TLS / H2-TLS / gRPC-TLS 需要域名解析和 Caddy，容器内不支持
- **非 TLS 协议均可测试**：VMess-TCP / VMess-mKCP / VMess-QUIC / Shadowsocks / Socks 等
- **network_mode: host**：容器直接使用宿主机网络，v2ray 监听的端口在宿主机上可以直接访问
- **二进制持久化**：`v2ray-bin` volume 保存已下载的 v2ray 二进制，重建容器无需重新下载
- **订阅持久化**：`v2ray-subscription` 保存授权、内容和启用状态，容器重启后恢复已启用的订阅服务
- **订阅 HTTPS**：服务只监听 `127.0.0.1:8787`，Linux host 网络下可由宿主机 Nginx/Caddy 反代；详见[订阅部署说明](subscription.md)
- **旧镜像升级**：推荐重建镜像以安装 Python 依赖。仅更新脚本时，需先安装 Python 3.8+；`sub setup` 会刷新本项目的 systemctl 包装器和 `/entrypoint.sh`，避免旧包装器误操作核心服务。重建容器仍需基于新镜像，并保留订阅卷

## 排查问题

```bash
# 查看 v2ray 进程
pgrep -a v2ray

# 查看错误日志
cat /var/log/v2ray/error.log

# 手动启动 v2ray（调试用）
/etc/v2ray/bin/v2ray run -config /etc/v2ray/config.json -confdir /etc/v2ray/conf

# 测试配置文件语法
v2ray test
```
