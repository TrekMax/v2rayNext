# V2Ray 脚本架构总览

## 目录结构

```
v2ray/
├── v2ray.sh              # 运行时入口, 仅 source src/init.sh 并传递参数
├── install.sh            # 一次性安装脚本, 独立运行
├── src/
│   ├── lib.sh            # 公共库: 颜色、工具函数、路径变量
│   ├── init.sh           # 运行时初始化: 检测环境、加载模块、分发命令
│   ├── protocol.sh       # 协议定义、常量、JSON 生成函数
│   ├── menu.sh           # 交互式菜单: ask() / show_list() / is_main_menu()
│   ├── config.sh         # 配置 CRUD: add / change / del / info / get / create
│   ├── cmd.sh            # 命令分发: main() 50+ 命令路由
│   ├── service.sh        # 服务管理: manage / api / uninstall / install_service
│   ├── download.sh       # 下载 & 更新组件
│   ├── caddy.sh          # Caddy 反代 & 自动 TLS
│   ├── log.sh            # 日志管理
│   ├── dns.sh            # DNS 配置
│   ├── bbr.sh            # TCP BBR 优化
│   └── help.sh           # 帮助信息 & 关于
└── .github/workflows/
    └── release.yml       # CI: 打包 V2rayNext_latest.zip 并发布 GitHub Release
```

## 分层架构

```
┌──────────────────────────────────────────────────────┐
│  用户界面层  (menu.sh, help.sh)                       │
│  颜色输出, 错误处理, 交互式菜单                         │
├──────────────────────────────────────────────────────┤
│  命令分发层  (cmd.sh main())                          │
│  路由 50+ 命令到对应处理函数                            │
├──────────────────────────────────────────────────────┤
│  配置管理层  (config.sh)                              │
│  add / change / del / get / create / info            │
│  jq 构建 JSON, 文件读写                               │
├──────────────────────────────────────────────────────┤
│  协议处理层  (protocol.sh)                            │
│  VMess / VLESS / Trojan / SS / Socks / Dokodemo      │
│  按协议生成 JSON 模板                                  │
├──────────────────────────────────────────────────────┤
│  系统集成层                                           │
│  service.sh  服务管理 & systemd unit 生成             │
│  caddy.sh    反代 / TLS 自动化                        │
│  log.sh / dns.sh / bbr.sh  功能模块                   │
├──────────────────────────────────────────────────────┤
│  下载层  (download.sh)                               │
│  GitHub API 查询, 组件下载 & 解压                      │
├──────────────────────────────────────────────────────┤
│  公共库  (lib.sh)                                    │
│  颜色函数, 工具封装, 路径变量, 端口检测                  │
└──────────────────────────────────────────────────────┘
```

## 两条入口路径

### 1. 安装路径 (`bash install.sh`)

```
install.sh
├── 校验环境 (root / 包管理器 / systemd / 架构)
├── 后台并行:
│   ├── install_pkg()  安装依赖包 (wget, unzip)
│   ├── download core  下载 v2ray 二进制
│   ├── download sh    下载脚本包
│   ├── download jq    下载 jq
│   └── get_ip()       获取服务器公网 IP
├── wait → check_status()  检查所有后台任务
├── 解压 & 安装到 /etc/v2ray/
├── 创建 symlink: /usr/local/bin/v2ray → /etc/v2ray/sh/v2ray.sh
├── 添加 bashrc alias
├── load service.sh → install_service()
├── load config.sh → add tcp (创建初始配置)
└── 清理临时目录
```

### 2. 运行路径 (`v2ray [command]`)

```
v2ray.sh
└── source /etc/v2ray/sh/src/init.sh

init.sh
├── source lib.sh        公共库
├── 检测系统环境 & v2ray/caddy 状态
├── load protocol.sh
├── load menu.sh
├── load service.sh
├── load config.sh
├── load cmd.sh
└── main $args → cmd.sh:main()

cmd.sh:main()
├── 无参数 → 显示交互式主菜单 (menu.sh)
└── 有参数 → 分发到对应函数 (50+ 命令)
```

## 模块加载机制

子模块通过 `load()` 函数按需加载:

```bash
load() {
    . "$is_sh_dir/src/$1"
}
```

核心模块在 init.sh 启动时统一加载; `caddy.sh` / `bbr.sh` / `dns.sh` 等功能模块仅在对应命令执行时才加载。

## 文件系统布局 (安装后)

```
/etc/v2ray/
├── config.json                    # 主配置 (log/dns/api/routing/outbounds)
├── conf/
│   ├── VMess-TCP-8080.json        # 各协议 inbound 配置
│   ├── VLESS-WS-TLS-example.com.json
│   └── *-link.json                # 动态端口配置
├── bin/
│   ├── v2ray                      # v2ray 二进制
│   ├── geoip.dat
│   └── geosite.dat
└── sh/                            # 脚本目录 (本仓库内容)
    ├── v2ray.sh
    └── src/*.sh

/etc/caddy/                        # (可选, TLS 协议时安装)
├── Caddyfile
└── TrekMax/*.conf

/var/log/v2ray/
├── access.log
└── error.log

/usr/local/bin/v2ray → /etc/v2ray/sh/v2ray.sh
```

## 外部依赖

| 依赖 | 用途 | 必需 |
|------|------|------|
| wget | 下载文件 | 是 |
| unzip | 解压 v2ray/脚本 zip | 是 |
| jq | JSON 处理 | 是 |
| systemctl | 服务管理 | 是 |
| netstat/ss | 端口占用检测 | 是 |
| qrencode | 生成二维码 | 否 |
| tar | 解压 caddy | TLS 时需要 |
| openssl | 生成 SS2022 密码 | SS2022 时需要 |

## 网络依赖

- `https://api.github.com` — 查询最新版本
- `https://github.com/.../releases` — 下载二进制 & 脚本
- `https://one.one.one.one/cdn-cgi/trace` — 获取服务器公网 IP
