# V2Ray 脚本

最好用的 V2Ray 一键安装脚本 & 管理脚本

## 特点

- 快速安装，零学习成本
- 自动化 TLS
- 使用 API 热加载配置
- 兼容 V2Ray 命令
- 强大的快捷参数
- 支持所有常用协议
- 一键添加 Shadowsocks / VMess / VLESS / Trojan / Socks
- 一键生成订阅链接，支持所有主流客户端导入
- 一键启用 BBR、更改伪装网站、修改任意参数

## 安装

```bash
bash <(wget -qO- https://github.com/TrekMax/v2rayNext/raw/main/install.sh)
```

## 帮助

```
v2ray help
```

```
V2Ray script by TrekMax
Usage: v2ray [options]... [args]...

基本:
   v, version                                      显示当前版本
   ip                                              返回当前主机的 IP
   get-port                                        返回一个可用的端口

一般:
   a, add [protocol] [args... | auto]              添加配置
   c, change [name] [option] [args... | auto]      更改配置
   d, del [name]                                   删除配置**
   i, info [name]                                  查看配置
   qr [name]                                       二维码信息
   url [name]                                      URL 信息
   sub                                             生成订阅链接 (所有配置 base64)
   log                                             查看日志
   logerr                                          查看错误日志

更改:
   dp, dynamicport [name] [start | auto] [end]     更改动态端口
   full [name] [...]                               更改多个参数
   id [name] [uuid | auto]                         更改 UUID
   host [name] [domain]                            更改域名
   port [name] [port | auto]                       更改端口
   path [name] [path | auto]                       更改路径
   passwd [name] [password | auto]                 更改密码
   type [name] [type | auto]                       更改伪装类型
   method [name] [method | auto]                   更改加密方式
   seed [name] [seed | auto]                       更改 mKCP seed
   new [name] [...]                                更改协议
   web [name] [domain]                             更改伪装网站

进阶:
   dns [...]                                       设置 DNS
   dd, ddel [name...]                              删除多个配置**
   fix [name]                                      修复一个配置
   fix-all                                         修复全部配置
   fix-caddyfile                                   修复 Caddyfile
   fix-config.json                                 修复 config.json

管理:
   un, uninstall                                   卸载
   u, update [core | sh | dat | caddy] [ver]       更新
   U, update.sh                                    更新脚本
   s, status                                       运行状态
   start, stop, restart [caddy]                    启动, 停止, 重启
   t, test                                         测试运行
   reinstall                                       重装脚本

测试:
   client [name]                                   显示用于客户端 JSON
   debug [name]                                    显示 debug 信息
   gen [...]                                       同等于 add, 但只显示 JSON, 不创建文件
   genc [name]                                     显示客户端部分 JSON
   no-auto-tls [...]                               同等于 add, 但禁止自动配置 TLS
   xapi [...]                                      同等于 v2ray api, 使用当前运行的服务

其他:
   bbr                                             启用 BBR
   bin [...]                                       运行 V2Ray 命令
   api, convert, tls, run, uuid  [...]             兼容 V2Ray 命令
   h, help                                         显示此帮助界面

** 谨慎使用 del, ddel, 此选项会直接删除配置, 无需确认
```

## 支持的协议

| 协议 | 需要 TLS | 需要 Caddy |
|------|----------|------------|
| VMess-TCP | 否 | 否 |
| VMess-mKCP | 否 | 否 |
| VMess-QUIC | 否 | 否 |
| VMess-H2-TLS | 是 | 是 |
| VMess-WS-TLS | 是 | 是 |
| VMess-gRPC-TLS | 是 | 是 |
| VLESS-H2-TLS | 是 | 是 |
| VLESS-WS-TLS | 是 | 是 |
| VLESS-gRPC-TLS | 是 | 是 |
| Trojan-H2-TLS | 是 | 是 |
| Trojan-WS-TLS | 是 | 是 |
| Trojan-gRPC-TLS | 是 | 是 |
| Shadowsocks | 否 | 否 |
| VMess-TCP-dynamic-port | 否 | 否 |
| VMess-mKCP-dynamic-port | 否 | 否 |
| VMess-QUIC-dynamic-port | 否 | 否 |
| Socks | 否 | 否 |

## 订阅链接

执行以下命令生成订阅内容：

```bash
v2ray sub
```

订阅文件保存在 `/etc/v2ray/sub.txt`，内容为所有代理配置 URL 的 base64 编码，可直接导入 V2RayN、Shadowrocket、Clash 等客户端。

若需通过 HTTP 对外暴露，可用 Nginx 或 Caddy 静态托管该文件：

```nginx
location /sub {
    alias /etc/v2ray/sub.txt;
}
```

## 反馈

https://github.com/TrekMax/v2rayNext/issues
