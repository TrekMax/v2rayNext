# Docker 部署

推荐在 Linux 服务器上使用 Docker Compose。镜像基于 Ubuntu 22.04，包含 Bash、Python 3、jq 等依赖；首次启动自动下载 V2Ray 核心和 geo 数据。首次下载需要访问 GitHub，后续启动使用数据卷中的已有文件。

## 全新部署

在项目目录运行：

```bash
docker compose up -d --build
docker compose logs -f v2ray
```

出现 `Ready` 后即可使用管理命令。`logs -f` 可按 Ctrl+C 退出，不会停止服务。

```bash
# 添加节点（也可不加 auto，交互选择参数）
docker compose exec v2ray v2ray add tcp auto

# 查看节点和核心状态
docker compose exec v2ray v2ray info
docker compose exec v2ray v2ray status
docker compose ps

# 初始化订阅服务
docker compose exec v2ray v2ray sub setup https://sub.example.com

# 配好 HTTPS 反向代理后，再创建订阅链接
docker compose exec v2ray v2ray sub --ttl 7d --name phone
```

首次启动会生成主配置，核心随容器启动；节点通过 `add` 添加。默认命令为后台服务入口 `serve`，不依赖 TTY 或保持 Bash 终端打开。需要容器终端时运行 `docker compose exec v2ray bash`。

订阅网关只监听 `127.0.0.1:8787`，Linux host 网络下由宿主机 Nginx/Caddy 提供 HTTPS。不要开放 8787 公网端口，反代示例和旧匿名入口清理见[订阅部署说明](subscription.md)。

## 数据持久化

| Compose 卷 | 容器路径 | 内容 |
| --- | --- | --- |
| `v2ray-bin` | `/etc/v2ray/bin` | 核心二进制、geoip.dat、geosite.dat |
| `v2ray-conf` | `/etc/v2ray/conf` | 节点 inbound 配置 |
| `v2ray-state` | `/etc/v2ray/state` | 主配置 config.json：DNS、路由、API 端口等 |
| `v2ray-subscription` | `/etc/v2ray/subscription` | 授权数据库、订阅内容、启用状态 |
| `v2ray-log` | `/var/log/v2ray` | 核心日志 |

`/etc/v2ray/config.json` 是指向 `state/config.json` 的软链接，现有 CLI 命令照常读写。主配置权限为 0600，状态目录为 0700。重启、更新镜像和重建容器均保留以上数据；不要挂载整个 `/etc/v2ray` 或 `/etc/v2ray/sh`，否则旧脚本会覆盖镜像里的新版本。

`docker compose down` 保留命名卷；`docker compose down -v` 会删除数据。更新时需沿用原 Compose 项目名和卷名（通常保持同一项目目录，或始终使用相同的 `-p`）。不要同时启动两个容器读写同一组卷。卷的生命周期参见 [Docker 官方说明](https://docs.docker.com/engine/storage/volumes/)。

## 后续更新和运行状态

```bash
docker compose up -d --build

# 重启容器，恢复核心及已启用的订阅服务
docker compose restart v2ray

# 直接检查进程；不依赖 CLI 的异步输出
docker compose exec v2ray systemctl is-active v2ray.service
docker compose exec v2ray systemctl is-active v2ray-subscription.service

# 查看日志
docker compose logs --tail 100 v2ray
docker compose exec v2ray tail -n 100 /var/log/v2ray/error.log
docker compose exec v2ray tail -n 100 /etc/v2ray/subscription/service.log
```

容器使用进程管理包装器替代 systemd，分别管理核心和订阅服务；停止其中一个不会误杀另一个。Compose 的 `init: true` 回收退出的子进程，容器收到停止信号时结束两个服务。进程管理方式参见 [Docker 官方说明](https://docs.docker.com/engine/containers/multi-service_container/)。

健康检查每 30 秒检查核心；订阅服务已启用时还检查其进程和匿名请求是否返回 403。首次下载有 5 分钟健康检查宽限期。核心或已启用的订阅服务被手动停止后，容器会变为 `unhealthy`，可用 `v2ray start` 或 `v2ray sub start` 恢复。订阅 `disable` 会持久化禁用状态，核心随容器启动。

健康检查只报告状态，不自动重启进程；`restart: unless-stopped` 针对容器退出。服务异常后先查看日志、修复配置，再执行 `docker compose restart v2ray`。初始化或服务启动失败会使入口退出，日志包含原因。

## 不使用 Compose

```bash
docker build -t v2raynext .
docker run -d --init --name v2rayNext --restart unless-stopped \
  --network host \
  -v v2ray-bin:/etc/v2ray/bin \
  -v v2ray-conf:/etc/v2ray/conf \
  -v v2ray-state:/etc/v2ray/state \
  -v v2ray-subscription:/etc/v2ray/subscription \
  -v v2ray-log:/var/log/v2ray \
  v2raynext
docker exec -it v2rayNext v2ray add tcp auto
```

Compose 的实际卷名通常带项目名前缀；从 Compose 切换至 `docker run` 时需填入原实际卷名。

## 网络与功能范围

- 默认 `network_mode: host` 面向 Linux 服务器，节点端口直接使用宿主机网络。公网访问需按节点端口配置服务器防火墙。
- Docker Desktop 与 Linux 宿主网络行为不同。本地测试可使用隔离 bridge 网络，在容器内检查网关；不能据此认定宿主机或公网可访问。
- 镜像不包含 Caddy，容器内自动 TLS 安装流程不属于此部署方案；节点 WS/H2/gRPC TLS 需要单独规划反向代理和证书。订阅 HTTPS 同样由外部反代提供。

## 开发验证

```bash
# 不依赖 Docker 的单元及进程测试
python3 -m unittest discover -s tests -v

# 真实镜像：使用唯一测试项目、隔离网络和临时卷，结束时只删除测试资源
docker build -t v2raynext:test .
V2RAY_DOCKER_IMAGE=v2raynext:test \
  python3 -m unittest discover -s tests -p test_docker_integration.py -v
```

真实容器测试覆盖默认后台启动、首次主配置、CLI 添加节点/修改 DNS、订阅授权、独立启停和健康检查、删除重建后内容与授权状态恢复、损坏配置拒绝启动。未设置 `V2RAY_DOCKER_IMAGE` 时跳过容器测试。GitHub Actions 单独配置 Docker 验证任务。

2026-11-09 本地验证：Docker Desktop 的 Linux arm64 环境、Ubuntu 22.04 镜像、V2Ray 5.53.0；27 项单元/HTTP/进程测试与 1 项真实容器完整流程测试通过。真实测试使用隔离 bridge 网络，没有验证公网 HTTPS、Linux 宿主机 host 网络或客户端订阅导入；GitHub Actions 新任务尚未远端执行。
