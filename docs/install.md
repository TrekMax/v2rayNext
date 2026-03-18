# install.sh — 安装脚本

## 概述

一次性运行的安装脚本, 负责从零搭建整个 v2ray 环境。以 root 身份执行, 支持 Ubuntu/Debian/CentOS。

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `-f, --core-file <path>` | 使用本地 v2ray 压缩包 | `-f /root/v2ray-linux-64.zip` |
| `-l, --local-install` | 从当前目录安装脚本 (开发用) | `-l` |
| `-p, --proxy <addr>` | 通过代理下载 | `-p http://127.0.0.1:2333` |
| `-v, --core-version <ver>` | 指定 v2ray 版本 | `-v v5.4.1` |
| `-h, --help` | 显示帮助 | `-h` |

## 主流程 (`main()`)

```
1. 检测是否已安装 → 已安装则提示用 reinstall
2. 解析命令行参数 (pass_args)
3. 显示欢迎信息
4. 创建临时目录 (mktemp -d)
5. 后台并行任务:
   ├── install_pkg()  安装 wget + unzip
   ├── download core  (如未指定 -f)
   ├── download sh    (如未指定 -l)
   ├── download jq    (如系统无 jq)
   └── get_ip()       获取服务器 IP
6. wait + check_status() 检查所有任务状态
7. 验证 v2ray 压缩包完整性 (如使用 -f)
8. 验证 IP 获取成功
9. 解压脚本 → /etc/v2ray/sh/
10. 解压 v2ray 核心 → /etc/v2ray/bin/
11. 配置 bashrc alias (先去重再追加)
12. 创建 symlink
13. 安装 jq (含完整性校验)
14. 创建 systemd 服务
15. 创建初始 TCP 配置 (load config.sh → add tcp)
16. 清理临时目录
```

## 关键函数

### `install_pkg($packages)`
安装依赖包。接收空格分隔的包名列表, 检测未安装的包并通过 apt-get 或 yum 安装。安装失败时会尝试更新源后重试。

### `download($type)`
下载组件, 支持三种类型:
- `core` — v2ray 二进制 (v2fly/v2ray-core releases)
- `sh` — 脚本包 (TrekMax/v2rayNext releases)
- `jq` — jq 二进制 (jqlang/jq releases)

### `get_ip()`
通过 Cloudflare CDN trace 接口获取服务器公网 IP。先尝试 IPv4, 失败则尝试 IPv6。使用 `grep -oP` 精确提取 IP 地址。

### `check_status()`
检查所有后台任务的状态文件是否生成。如果 wget 尚未安装 (首次运行), 等待 install_pkg 完成后再启动下载任务。

### `pass_args()`
解析命令行参数, 支持 `-f`, `-l`, `-p`, `-v`, `-h`。不允许同时指定 `-f` 和 `-v`。

### `exit_and_del_tmpdir()`
清理临时目录并退出。传入 `ok` 参数表示正常退出, 否则显示错误信息。

## 临时文件结构

```
$tmpdir/                  # mktemp -d 创建
├── tmpcore               # v2ray 下载缓存
├── tmpsh                 # 脚本下载缓存
├── tmpjq                 # jq 下载缓存
├── is_core_ok            # v2ray 下载完成标记 (mv from tmpcore)
├── is_sh_ok              # 脚本下载完成标记
├── is_jq_ok              # jq 下载完成标记
├── is_pkg_ok             # 依赖包安装完成标记
└── testzip/              # v2ray zip 解压测试目录 (-f 模式)
```

## 架构检测

| uname -m | v2ray 架构 | jq 架构 |
|-----------|-----------|---------|
| amd64 / x86_64 | 64 | amd64 |
| aarch64 / armv8 | arm64-v8a | arm64 |

## 注意事项

- 脚本仅在安装时执行一次, 安装后通过 `v2ray` 命令管理
- 下载任务通过 `&` 后台并行执行, `wait` 等待全部完成
- `check_status()` 存在递归调用: 首次无 wget 时先装 wget, 再递归调用自身启动下载
- jq 安装前会执行 `--version` 验证二进制完整性
