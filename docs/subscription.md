# 订阅授权与部署

## 工作方式

订阅地址、Base64 编码层级、各协议节点链接和 Clash YAML 示例见[订阅与节点格式](subscription-format.md)。

`v2ray sub` 为每条链接生成独立的 256 位随机授权码。服务端保存摘要、有效期和撤销状态，每次下载都检查。Base64 和 Clash 授权绑定各自格式，不能通过修改 URL 路径切换格式。

完整 URL 是访问凭证，拿到完整链接的人在有效期内也能下载。到期和撤销只阻止后续订阅下载，不撤回已保存的节点，不会断开代理连接。若节点凭据本身已经泄漏，还需要更换相应 UUID/密码。

## 初始化

需要 Bash 4+、已有 V2Ray 节点、Python 3.8+（含 sqlite3），以及指向服务器的 HTTPS 域名。Debian/Ubuntu 可用 `apt-get install python3` 安装依赖；Docker 镜像已包含 Python。

```bash
v2ray sub setup https://sub.example.com
v2ray sub status
```

setup 保存域名并启动 `v2ray-subscription.service`，仅监听 `127.0.0.1:8787`。地址必须是 HTTPS origin，可带端口，例如 `https://sub.example.com:8443`，不能带路径、账号、查询参数。重复 setup 保留现有授权。

setup 不修改已有 Nginx/Caddy 配置，也不自动申请该域名的证书。完成下面的 HTTPS 配置后，生成的公网链接才可使用。8787 为本机后端端口，不需要开放防火墙或 Docker 端口映射；反向代理需与服务处于同一网络命名空间。

## 配置 HTTPS

任选 Nginx 或 Caddy。使用独立订阅子域名可以避免与代理协议的 WS/gRPC 路径冲突。该 Python 服务只承担本机下载校验，公网连接、TLS、请求缓冲和连接限制交给反向代理。

### Nginx

在已有证书的 HTTPS `server` 中添加两个精确匹配的 location，替换同路径旧规则：

```nginx
location = /sub {
    access_log off;
    error_log /dev/null;
    proxy_cache off;
    proxy_no_cache 1;
    proxy_buffering off;
    proxy_pass http://127.0.0.1:8787;
    limit_except GET { deny all; }
}

location = /sub-clash {
    access_log off;
    error_log /dev/null;
    proxy_cache off;
    proxy_no_cache 1;
    proxy_buffering off;
    proxy_pass http://127.0.0.1:8787;
    limit_except GET { deny all; }
}
```

运行 `nginx -t` 后重新加载 Nginx。HEAD 随 GET 一同允许。关闭这两个路由的访问/错误日志是为了避免查询串中的授权码进入日志；可通过本机服务状态排查后端问题。上层 CDN/WAF 同样必须绕过订阅缓存并关闭查询串记录。参考 [Nginx 反向代理文档](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)。

### Caddy

独立站点示例（域名解析及 80/443 端口需满足自动 HTTPS 条件）：

```caddyfile
sub.example.com {
    log {
        output discard
    }
    @subscription path /sub /sub-clash
    handle @subscription {
        reverse_proxy 127.0.0.1:8787
    }
    handle {
        respond 404
    }
}
```

项目管理的 Caddy 可将该站点保存为 `/etc/caddy/sites/subscription.conf`，现有主配置需含 `import /etc/caddy/sites/*.conf`。执行 `caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` 后运行 `v2ray restart caddy`。如使用其他 Caddy 安装，按其服务管理方式重新加载。

站点日志配置只关闭访问日志。Caddy 的运行时错误日志可能包含请求 URI；需要在现有全局 logger 中排除 `http.log.error`，避免后端不可用时记录 token。默认 logger 示例：

```caddyfile
{
    log default {
        exclude http.log.error
    }
}
```

将此 `log` 段合并到已有全局块，不能创建第二个全局块；它会关闭默认 logger 中所有站点的 HTTP 运行时错误日志，其他运行时日志保留。如果另有接收 HTTP 错误的自定义 logger，也需排除该命名空间。不要启用包含订阅请求的 DEBUG 日志。参考 [Caddy 访问日志](https://caddyserver.com/docs/caddyfile/directives/log)和[全局日志配置](https://caddyserver.com/docs/caddyfile/options#log)。

## 创建、更新与撤销

```bash
# 默认 Base64、7 天；名称可含空格
v2ray sub --name "我的手机"

# Clash YAML，30 天
v2ray sub clash --ttl 30d --name desktop

# 查看授权 ID、名称、格式、UTC 创建/到期时间、状态
v2ray sub list

# 撤销单条授权，其他授权不受影响
v2ray sub revoke <授权ID>

# 添加/删除/修改节点之后更新对应格式内容，不延长任何授权
v2ray sub refresh base64
v2ray sub refresh clash
```

有效期允许正整数加 `s/m/h/d`，最长 365 天。输出的 URL 只显示一次；数据库不保存授权码明文，所以不能找回，遗失时重新创建并撤销旧授权。所有授权能下载对应格式的全部节点，不按授权分配不同节点。每个格式共享最新成功生成的文件。

Clash 支持常见 VMess TCP/WS/gRPC/H2、VLESS WS/gRPC/H2/Reality、Trojan WS/gRPC、Shadowsocks、Socks。mKCP、QUIC、动态端口和其他不支持的配置会跳过；没有可用配置或读取失败时保持上一份内容，不发放授权。

## 旧链接迁移

本版本不保留匿名访问。升级后执行 setup，它会删除 `/etc/v2ray/sub.txt` 和 `/etc/v2ray/sub-clash.yaml`，以后不再生成这两个文件。还需在实际部署中完成以下操作：

1. 移除旧的 Nginx `alias`、Caddy `file_server` 或其他匿名下载路由。
2. 删除曾复制到 Web 根目录/对象存储的订阅副本，清除 CDN 缓存。
3. 不要将 `/etc/v2ray/subscription/` 静态暴露；目录权限 0700，文件 0600，服务进程由 root 读取。
4. 检查所有旧地址不再返回节点内容，再将新链接导入客户端。

仓库无法自动定位服务器上任意自定义静态目录及缓存，因此 setup 成功不等同于所有外部旧入口已关闭。

## 持久化与生命周期

状态目录 `/etc/v2ray/subscription/` 包含 `config.json`、`tokens.sqlite3`、两种订阅文件。有效期使用服务器 Unix 时间，确保系统时间同步。服务重启或脚本更新不重置有效期/撤销状态。备份恢复旧数据库会恢复当时的授权状态，因此应连同撤销记录一起妥善备份。

```bash
v2ray sub start
v2ray sub stop
v2ray sub restart
v2ray sub status
# systemd 日志
journalctl -u v2ray-subscription.service -n 50 --no-pager
```

stop 仅停止服务，不取消开机启动。Linux 可用 `systemctl disable v2ray-subscription.service` 禁用自动启动。Docker 的 systemctl 包装器也支持这个命令，并通过状态目录中的 enabled 标记跨容器重建保存。

Compose 已添加 `v2ray-subscription` 卷。自行 docker run 时添加 `-v v2ray-subscription:/etc/v2ray/subscription`。Linux `--network host` 下，宿主机 Nginx/Caddy 可以连接服务的 loopback；其他网络方式需要将反向代理放在同一网络命名空间。不要将后端改成公网监听。

后台启动使用 `docker compose up -d --build`，再通过 `docker compose exec v2ray v2ray sub setup https://sub.example.com` 初始化。主配置另存于 `v2ray-state` 卷，完整步骤见 [Docker 部署](docker.md)。

## 验证与故障排查

```bash
# 匿名下载应为 403，不能返回节点内容
curl -I https://sub.example.com/sub
curl -I https://sub.example.com/sub-clash

# 旧静态文件地址应失败（通常 404）
curl -I https://sub.example.com/sub.txt
curl -I https://sub.example.com/sub-clash.yaml
```

将新创建的链接导入客户端，确认更新成功，再撤销该授权并验证更新被拒绝。可用 `--ttl 5s` 创建短期测试授权，等待到期后验证拒绝。缺失/错误/过期/撤销/跨格式授权均返回 403；未知路由返回 404；有效授权对应内容丢失、为空或数据库损坏返回 503。所有后端响应均带 `Cache-Control: no-store`。

Docker 服务日志在 `/etc/v2ray/subscription/service.log`，不记录 URL。后端端口冲突、Python 依赖缺失、数据库错误会使启动或操作失败；修复后运行 `v2ray sub restart`。setup 未完成时不会退回生成匿名文件。

开发测试：

```bash
python3 -m unittest discover -s tests -v
for file in v2ray.sh src/*.sh docker/*; do
    bash -n "$file"
done
shellcheck -S warning src/subscription.sh docker/*
git diff --check
```

生成集成测试需要 Bash 4+、jq、GNU base64；macOS 可通过 `V2RAY_TEST_BASH=/path/to/bash` 指定 Bash，通过已安装的 `gbase64` 使用 GNU 行为。真实公网 HTTPS 和客户端导入需要在目标服务器单独验收。

### 订阅功能初次验证（2026-11-09）

- macOS arm64、Python 3.15.2、临时构建的 Bash 5.3.0：24 项自动化测试通过，包含真实回环 HTTP、SQLite、订阅生成和独立进程启停。
- 覆盖非法 JSON、合法 JSON 的错误结构、未知协议/传输导致的发布失败；失败时保留已有内容且不新增授权。
- 全部 Shell 文件语法检查、订阅模块及容器脚本的 ShellCheck、Python 编译、Compose 配置解析、`git diff --check` 通过。
- 此次订阅功能初验未启动 Docker；后续 Docker 修复的验证见 [Docker 部署](docker.md#开发验证)。systemd 单元只验证生成，没有在 Linux systemd 上启动。新增 Linux CI 尚未远端执行。
- 公网域名/证书、Nginx/Caddy 实际配置、外部旧入口清理和客户端导入未执行，按上述部署步骤验收。
