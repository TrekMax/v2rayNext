# 订阅与节点格式

本文描述 v5.1.0 当前实现。部署与授权管理见[订阅授权与部署](subscription.md)。以下域名、IP、UUID 和密码均为示例，尖括号表示需要替换的内容。

## 订阅地址

| 类型 | 生成命令 | 地址格式 | HTTP 响应类型 |
|------|----------|----------|---------------|
| Base64（默认） | `v2ray sub base64 --ttl 7d` | `https://sub.example.com/sub?token=<授权码>` | `text/plain; charset=utf-8` |
| Clash | `v2ray sub clash --ttl 30d` | `https://sub.example.com/sub-clash?token=<授权码>` | `application/yaml; charset=utf-8` |

授权码由 32 字节密码学安全随机数生成，编码为 43 个 URL 安全字符，字符范围为 `A-Z`、`a-z`、`0-9`、`_`、`-`。创建时输出完整链接，客户端需保留 `?token=...`。

有效期和撤销状态保存在服务器数据库中，不放在 URL 参数里。默认有效期为 7 天，最大 365 天；每次下载都会校验。授权与订阅格式绑定，不能把同一条链接的 `/sub` 改成 `/sub-clash` 来获取另一种格式。

## Base64 订阅内容

响应正文是所有可生成的节点链接按行拼接后，整体进行一次 Base64 编码的字符串：

```text
Base64(节点链接1 + "\n" + 节点链接2 + "\n" + ...)
```

解码后的结构为每行一个节点：

```text
vmess://<节点JSON的Base64编码>
vless://<UUID>@<域名>:443?encryption=none&security=tls&type=ws&host=<域名>&path=%2Fproxy#<名称>
trojan://<密码>@<域名>:443?encryption=none&security=tls&type=ws&host=<域名>&path=%2Fproxy#<名称>
ss://<加密方式:密码的Base64编码>@<地址>:<端口>#<名称>
socks://<用户名:密码的Base64编码>@<地址>:<端口>#<名称>
```

这是格式示意，实际只包含当前配置中能够生成链接的节点。v2rayN/v2rayNG 使用此 Base64 订阅入口。Base64 是编码，不是加密。

## 单个节点链接

### VMess

VMess 链接为 `vmess://` 加节点 JSON 的 Base64 编码。因此在 Base64 订阅中，先解码整份订阅，再解码某条 VMess 链接的内容，才能看到节点 JSON。

TCP 节点的 JSON 示例：

```json
{
  "v": 2,
  "ps": "v2rayNext-tcp-203.0.113.8",
  "add": "203.0.113.8",
  "port": "12345",
  "id": "11111111-2222-3333-4444-555555555555",
  "aid": "0",
  "net": "tcp",
  "type": "none",
  "path": ""
}
```

| 字段 | 含义 |
|------|------|
| `v` | 分享链接格式版本 |
| `ps` | 节点名称 |
| `add` / `port` | 服务器地址 / 端口 |
| `id` | 节点 UUID |
| `aid` | alterId，当前输出 `0` |
| `net` | 传输方式，如 `tcp`、`ws`、`grpc`、`h2` |
| `type` | TCP 等传输的伪装类型 |
| `path` | 随传输变化；WS/H2 路径、gRPC 服务名或当前 mKCP 输出的 seed |
| `host` / `tls` | TLS 节点输出的域名和 TLS 标记 |

不同传输输出的字段有所不同，以上 JSON 对应普通 TCP，不是所有传输共用的完整字段集合。

### VLESS 与 Trojan

两者都使用 URI 字段直接表达服务器和传输参数：VLESS 的认证部分为 UUID，Trojan 的认证部分为密码。当前 TLS 示例使用 `security=tls`，`type=ws` 表示 WebSocket，`path=%2Fproxy` 对应 `/proxy`；gRPC 使用 `type=grpc` 和 `serviceName` 参数。

VLESS Reality 示例模板：

```text
vless://<UUID>@<地址>:<端口>?encryption=none&security=reality&flow=xtls-rprx-vision&type=tcp&sni=<SNI>&pbk=<公钥>&fp=ios#<名称>
```

### Shadowsocks 与 Socks

当前生成器将认证部分进行 Base64 编码，服务器地址和端口保留在 URI 中：

```text
ss://Base64(加密方式:密码)@地址:端口#名称
socks://Base64(用户名:密码)@地址:端口#名称
```

这里的 `Base64(...)` 表示编码运算，不是实际链接中的字面文字。

## Clash 订阅内容

Clash 入口直接返回 YAML，不做外层 Base64 编码。每个节点是 `proxies` 数组中的一个对象，同时包含代理组和规则。单个 VMess TCP 节点组成的完整输出示例：

```yaml
port: 7890
socks-port: 7891
allow-lan: true
mode: rule
log-level: info

proxies:
  - name: 'VMess-TCP-12345'
    type: vmess
    server: '203.0.113.8'
    port: 12345
    uuid: '11111111-2222-3333-4444-555555555555'
    alterId: 0
    cipher: auto
    udp: true

proxy-groups:
  - name: Proxy
    type: select
    proxies:
      - 'VMess-TCP-12345'
      - DIRECT

rules:
  - GEOIP,CN,DIRECT
  - MATCH,Proxy
```

TLS、WS、gRPC、H2、Reality 等节点会按实际协议附加相应字段。无法转换成 Clash 格式的节点会跳过；如果没有可用节点，生成失败，不签发新授权。

## 授权名称、节点名称与连接凭据

- `v2ray sub --name phone` 中的 `phone` 是授权管理名称，用于 `sub list`，不会改写订阅中的节点名称。
- Base64 节点名称由现有 URL 生成器按 `v2rayNext-<传输>-<地址或域名>` 等形式生成，VMess 放在 `ps`，其他链接放在 `#` 后。
- Clash 节点名称取配置文件名去掉 `.json`，例如 `VMess-TCP-12345.json` 对应 `VMess-TCP-12345`。
- 订阅 `token` 控制是否允许下载；节点 UUID／密码控制代理连接。订阅过期或撤销不会修改节点凭据，也不会自动停用已导入的节点。
- 同一格式的所有有效授权读取同一份最新成功生成的内容，不为每个授权分配独立节点。

实现入口：[订阅服务](../src/subscription.py)、[订阅命令](../src/subscription.sh)、[节点链接及 YAML 生成器](../src/config.sh)。
