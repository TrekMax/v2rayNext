# 模块文档

## src/lib.sh — 公共库

所有模块的基础依赖, 由 `init.sh` 在加载其他模块前首先 source。

### 颜色输出

```bash
_red()  _blue()  _cyan()  _green()  _yellow()  _magenta()  _red_bg()
```

### 错误 & 警告

```bash
err()   # 输出错误并 exit 1 (除非 $is_dont_auto_exit 已设置)
warn()  # 仅输出警告, 不退出
msg()   # echo -e 封装
```

### 文件操作封装

```bash
_rm()    → rm -rf
_cp()    → cp -rf
_sed()   → sed -i
_mkdir() → mkdir -p
```

### 工具函数

```bash
get_uuid()       # 从 /proc/sys/kernel/random/uuid 生成 UUID
load()           # 按需加载 src/ 下的子模块
_wget()          # wget 封装, 支持 $proxy 环境变量
is_port_used()   # 检查端口是否已被占用 (netstat/ss)
is_test()        # 输入校验: number / port / port_used / domain / path / uuid
```

### 路径变量

| 变量 | 值 |
|------|----|
| `is_core_dir` | `/etc/v2ray` |
| `is_core_bin` | `/etc/v2ray/bin/v2ray` |
| `is_conf_dir` | `/etc/v2ray/conf` |
| `is_sh_dir` | `/etc/v2ray/sh` |
| `is_config_json` | `/etc/v2ray/config.json` |
| `is_sh_bin` | `/usr/local/bin/v2ray` |

---

## src/protocol.sh — 协议定义 & JSON 生成

### 数据定义

- `protocol_list` — 17 种支持的协议
- `ss_method_list` — SS 加密方式: aes-128-gcm, aes-256-gcm, chacha20-ietf-poly1305
- `header_type_list` — 伪装类型: none, srtp, utp, wechat-video, dtls, wireguard
- `servername_list` — REALITY SNI 候选域名列表
- `CHANGE_*` 常量 — 16 种修改类型的命名常量 (替代数字索引)

### 函数

#### `get_pbk()`
调用 `v2ray x25519` 生成 REALITY 密钥对, 结果存入 `$is_private_key` / `$is_public_key`。

#### `build_protocol_json(proto)`
主入口, 根据协议名分派到各个 helper:

**协议 helpers**: `_set_protocol_vmess/vless/trojan/ss/door/http/socks`

**传输层 helpers**: `_set_transport_tcp/kcp/quic/ws/grpc/h2/reality`

每个 helper 设置 `$json_str` 和 `$is_stream` 变量, 供 `config.sh` 的 `create` 函数使用。

---

## src/menu.sh — 交互式菜单

### 函数

#### `show_list(items...)`
用 bash `select` 以单列格式显示选项列表。

#### `ask(type, ...args)`
通用交互式输入函数。支持的 type:

| type | 说明 |
|------|------|
| `string` | 输入字符串, 带格式校验 (port/path/uuid) |
| `list` | 从列表中选择 |
| `set_protocol` | 选择协议 |
| `set_ss_method` | 选择 SS 加密方式 |
| `set_header_type` | 选择伪装类型 |
| `set_change_list` | 选择更改项 |
| `get_config_file` | 选择已有配置文件 |
| `mainmenu` | 显示主菜单 |

所有内部变量均为 `local`, 不污染全局命名空间。

#### `is_main_menu()`
10 项主菜单: 添加 / 更改 / 查看 / 删除 / 运行管理 / 更新 / 卸载 / 帮助 / 其他 / 关于

---

## src/config.sh — 配置 CRUD

### 函数

#### `add(protocol, ...args)`
添加新协议配置:
1. 解析协议类型
2. 分配端口、UUID、密码
3. TLS 协议 → 检测/安装 Caddy → 验证域名解析
4. 调用 `build_protocol_json` 生成 JSON
5. 写入配置文件
6. 配置 Caddy 反代 (如需要)
7. 重启服务或 API 热加载

#### `change(config_name, option, value)`
修改已有配置, 支持 16 种修改类型 (由 `CHANGE_*` 常量标识):

| 常量 | 说明 |
|------|------|
| `CHANGE_PROTOCOL` | 更改协议 |
| `CHANGE_PORT` | 更改端口 |
| `CHANGE_HOST` | 更改域名 |
| `CHANGE_PATH` | 更改路径 |
| `CHANGE_PASSWORD` | 更改密码 |
| `CHANGE_UUID` | 更改 UUID |
| `CHANGE_METHOD` | 更改加密方式 |
| `CHANGE_HEADER_TYPE` | 更改伪装类型 |
| `CHANGE_DOOR_ADDR` | 更改目标地址 |
| `CHANGE_DOOR_PORT` | 更改目标端口 |
| `CHANGE_KEY` | 更改密钥 |
| `CHANGE_SNI` | 更改 SNI |
| `CHANGE_DYNAMIC_PORT` | 更改动态端口 |
| `CHANGE_PROXY_SITE` | 更改伪装网站 |
| `CHANGE_KCP_SEED` | 更改 mKCP seed |
| `CHANGE_SOCKS_USER` | 更改用户名 |

#### `del(config_name)`
删除配置文件, 清理 Caddy 配置, 热卸载 inbound (v5+) 或重启服务。

#### `info(config_name)`
显示配置详情: 协议、地址、端口、UUID/密码、URL、二维码。

#### `sub(mode)`
生成订阅链接。遍历 `/etc/v2ray/conf/` 下所有 inbound 配置 (动态端口 link 文件除外), 按订阅格式输出。

`mode` 可选:
- `base64` (默认) — 收集各配置的代理 URL, 按行拼接后 base64 编码, 保存至 `/etc/v2ray/sub.txt`
- `clash` — 生成 Clash YAML 订阅, 保存至 `/etc/v2ray/sub-clash.yaml`

不支持当前订阅格式的协议会自动跳过并提示。例如 Dokodemo-Door、HTTP、mKCP、QUIC、动态端口配置不会出现在 Clash 订阅中。

**订阅文件格式** (`/etc/v2ray/sub.txt`):
```
base64(
  vmess://...
  ss://...
  trojan://...
  ...
)
```

客户端 (V2RayN / Shadowrocket / Clash 等) 可直接导入订阅 URL 或订阅文件内容。若需通过 HTTP 对外暴露, 可用 Nginx/Caddy 静态托管 `/etc/v2ray/sub.txt`。

**Clash 订阅文件** (`/etc/v2ray/sub-clash.yaml`) 结构示意:
```yaml
port: 7890
socks-port: 7891
allow-lan: true
mode: rule
log-level: info
proxies:
  - name: 'example'
    type: vmess
    ...
proxy-groups:
  - name: Proxy
    type: select
    proxies:
      - 'example'
      - DIRECT
rules:
  - GEOIP,CN,DIRECT
  - MATCH,Proxy
```

#### `get(subcommand, ...args)`
多功能内部函数:
- `get file $name` — 查找配置文件
- `get info $file` — 解析 JSON 配置到变量
- `get addr` — 获取服务器地址
- `get port` — 随机生成可用端口
- `get $command` — 执行 download/install-caddy 等

#### `create(type, ...args)`
- `create server` — 写入 inbound JSON 到 conf/
- `create client` — 生成客户端 outbound JSON
- `create caddy` — 生成 Caddy 站点配置
- `create config.json` — 生成主配置文件

### 配置文件格式

**inbound 配置** (`/etc/v2ray/conf/*.json`):
```json
{
  "inbounds": [{
    "tag": "VMess-TCP-8080.json",
    "port": 8080,
    "listen": "0.0.0.0",
    "protocol": "vmess",
    "settings": { "clients": [{ "id": "uuid" }] },
    "streamSettings": { "network": "tcp" },
    "sniffing": { "enabled": true, "destOverride": ["http", "tls"] }
  }]
}
```

**主配置** (`/etc/v2ray/config.json`):
```json
{
  "log": { "loglevel": "warning" },
  "dns": {},
  "api": { "tag": "api", "services": ["HandlerService"] },
  "routing": { "rules": [...] },
  "inbounds": [{ "tag": "api", "protocol": "dokodemo-door" }],
  "outbounds": [{ "protocol": "freedom" }, { "protocol": "blackhole" }]
}
```

---

## src/cmd.sh — 命令分发

`main()` 函数, 路由 50+ 命令到对应处理函数。

### 主要命令组

| 命令 | 函数 | 说明 |
|------|------|------|
| `a, add` | `add` | 添加配置 |
| `c, change` | `change` | 修改配置 |
| `d, del` | `del` | 删除配置 |
| `i, info` | `info` | 查看配置 |
| `sub, subscription` | `sub` | 生成订阅链接 / Clash 订阅 |
| `port/host/path/...` | `change` | 快捷修改 |
| `s, status` | — | 查看服务状态 |
| `start/stop/restart` | `manage` | 启停服务 |
| `u, update` | `update` | 更新组件 |
| `un, uninstall` | `uninstall` | 卸载 |
| `dns/bbr/log/...` | 各模块函数 | 功能命令 |
| `api/bin/uuid/...` | v2ray 二进制 | 透传命令 |

---

## src/service.sh — 服务管理

### 函数

#### `install_service(name)`
生成并安装 systemd unit 文件到 `/lib/systemd/system/`。

**v2ray 服务**: `ExecStart = $is_core_bin run -config $is_config_json -confdir $is_conf_dir`

**caddy 服务**: `ExecStart = $is_caddy_bin run --environ --config $is_caddyfile --adapter caddyfile`

#### `manage(action, service)`
systemctl 封装, 支持 start/stop/restart/enable/disable, 可指定 caddy 服务。

#### `api(action, ...args)`
v5+ API 热加载, 无需重启即可添加/删除 inbound。

#### `uninstall()`
完整卸载: 停止服务、删除文件、清理 alias。

---

## src/download.sh — 下载 & 更新

#### `get_latest_version(type)`
查询 GitHub API 获取最新版本号。支持: core, sh, caddy。

#### `download(type, version)`

| type | 下载源 | 安装位置 |
|------|--------|----------|
| `core` | v2fly/v2ray-core releases | `/etc/v2ray/bin/` |
| `sh` | TrekMax/v2rayNext releases | `/etc/v2ray/sh/` |
| `dat` | Loyalsoldier/v2ray-rules-dat | `/etc/v2ray/bin/*.dat` |
| `caddy` | caddyserver/caddy releases | `/usr/local/bin/caddy` |

---

## src/caddy.sh — Caddy 反代 & 自动 TLS

为 TLS 类协议 (WS-TLS, H2-TLS, gRPC-TLS) 提供 Caddy 反向代理, 自动申请和续期 TLS 证书。

#### `caddy_config(type)`

| type | 说明 |
|------|------|
| `new` | 创建主 Caddyfile |
| `*ws*` | WebSocket 反代: `reverse_proxy 127.0.0.1:{port}` |
| `*h2*` | HTTP/2 反代: `reverse_proxy h2c://127.0.0.1:{port}` |
| `*grpc*` | gRPC 反代: `reverse_proxy h2c://127.0.0.1:{port}` |
| `proxy` | 上游代理站点配置 |

---

## src/log.sh — 日志管理

#### `log_set(level)`

| level | 说明 |
|-------|------|
| `debug` | 调试级别 |
| `info` | 信息级别 |
| `warning` | 警告级别 (默认) |
| `error` | 仅错误 |
| `none` | 关闭日志 |
| `del` | 清空日志文件 |

---

## src/dns.sh — DNS 配置

#### `dns_set(preset)`

| 预设 | DNS 服务器 |
|------|-----------|
| `11, 1111` | Cloudflare 1.1.1.1 |
| `88, 8888` | Google 8.8.8.8 |
| `gg, google` | Google DoH |
| `cf, cloudflare` | Cloudflare DoH |
| `nosex, family` | Cloudflare 家庭版 |
| `none` | 禁用 DNS |

---

## src/bbr.sh — TCP BBR 优化

#### `_try_enable_bbr()`
检查内核版本 (需要 4.9+), 满足条件则启用 BBR 拥塞控制算法。

---

## src/help.sh — 帮助 & 关于

#### `show_help(topic)`
按主题显示帮助信息, 涵盖所有命令的用法说明。

#### `about()`
显示项目信息: 作者、网站、Telegram、GitHub 链接。
