# 订阅访问控制实施计划

> 按 executing-plans 流程在当前会话内逐项实施，使用测试驱动开发和完成前验证。

**Goal:** 为两种订阅格式提供独立授权、到期拒绝和即时撤销，替代匿名静态文件。

**Architecture:** Bash 继续解析现有节点并原子发布私有订阅文件；Python 3 标准库服务管理 SQLite 授权并校验每次 HTTP 下载；systemd/Docker 管理服务，公网由 HTTPS 反向代理接入。

**Tech Stack:** Bash 4+、jq、Python 3.8+、SQLite、Nginx/Caddy。

## 全局约束

- 不兼容旧匿名链接；删除旧输出文件，不猜测修改外部虚拟主机。
- 默认有效期 7d，允许正整数 s/m/h/d，最大 365d。
- 256 位随机凭证，数据库只存 SHA-256 摘要；按格式绑定、每次检查过期/撤销。
- 私有目录 0700、文件 0600；监听 127.0.0.1:8787；不开放 HTTP 管理接口。
- 禁用响应缓存和凭证日志；坏状态拒绝访问；更换文件内容不延长授权。

## Task 1: 授权存储、CLI 与 HTTP 校验

Files: 新增 `src/subscription.py`、`tests/test_subscription.py`。

Interfaces: Python CLI 使用 `--state-dir DIR` 后跟 `setup ORIGIN / validate FORMAT [--ttl TTL --name NAME] / issue FORMAT [--ttl TTL --name NAME] / list / revoke ID / serve`；内部 `Store.issue(mode, ttl, name)` 返回授权及一次性明文 token，`Store.authorized(token, mode, now=None)` 每次读取数据库。

- [x] 先写失败用例：真实临时目录、真实 SQLite、真实回环 HTTP；合法请求 200，匿名/错误/跨格式/重复参数 403，未知路由 404。
- [x] 执行 `python3 -m unittest discover -s tests -v`，确认功能缺失导致失败。
- [x] 实现输入验证、事务发放/撤销、文件权限、只读下载、精确到期判断和不泄漏信息的错误处理。
- [x] 增加边界测试：365d/0d/负数、origin 注入、丢失/损坏数据库、到期瞬间、重启、单条撤销、HEAD/no-store。
- [x] 重跑测试通过。

## Task 2: Bash 订阅命令及原子发布

Files: 新增 `src/subscription.sh`、`tests/test_subscription_shell.py`；修改 `src/config.sh`、`src/cmd.sh`、`v2ray.sh`、`src/init.sh`。

Interfaces: `sub "$@"` 按需加载新模块，`subscription_command "$@"` 分发；`_sub_generate MODE FILE` 仅生成订阅内容，`subscription_refresh MODE` 在私有目录临时生成后替换。

- [x] 先写 CLI 集成测试：隔离的临时配置与节点，失败生成不覆盖旧内容、不发授权，空/不支持配置失败，带空格名称完整传递。
- [x] 运行测试证明缺少新命令/行为。
- [x] 拆出生成逻辑，只修改本任务需要的错误返回；使用子 Shell 隔离旧 info() 的全局变量。
- [x] 在签发前验证所有参数；refresh 成功后 issue；setup 删除旧文件，未配置不生成匿名输出。
- [x] 使用 Bash 4+ 运行集成测试及语法检查。

## Task 3: 服务与部署生命周期

Files: 修改 `src/service.sh`、`src/download.sh`、`Dockerfile`、`docker/systemctl`、`docker/entrypoint.sh`、`docker-compose.yml`；新增/扩展生命周期测试。

- [x] 测试订阅服务与 core 服务操作互不影响，启动恢复保留授权，systemd unit 可用。
- [x] setup 检查 Python/sqlite、创建 unit 并启用服务；Docker 包装器精确匹配服务名，维护独立 PID/启用标记。
- [x] 容器增加 Python 和订阅状态 volume；入口恢复已启用服务；更新重启已启用服务，卸载停止并禁用服务。
- [x] 执行针对性 ShellCheck、Bash 语法、Compose 配置验证；有运行时则执行 Linux 容器测试。

## Task 4: 文档、发布与最终验收

Files: 修改 `README.md`、`src/help.sh`、`docs/modules.md`、`docs/architecture.md`、`docs/docker.md`；新增 `docs/subscription.md` 和测试 CI。

- [x] 文档给出 setup、两种格式创建、更新、撤销及 HTTPS 反代的可复制命令。
- [x] Nginx/Caddy 示例仅转发两个固定路由、禁缓存/访问日志，明确删除所有旧静态副本。
- [x] 加入默认 Linux CI 测试；升级脚本版本；更新设计/计划状态。
- [x] 最终执行 `python3 -m unittest discover -s tests -v`、`bash -n`、针对性 ShellCheck、`git diff --check`，逐条核对设计。
- [x] 报告通过项及 Docker/systemd、远端 HTTPS、客户端导入的实测边界。

## 验证结果

2026-11-09：订阅功能初验时，24 项本地测试、Bash 语法、针对性 ShellCheck、Python 编译、Compose 配置解析与 diff 检查通过。代码审查发现的结构错误发布问题已复现、修复并加入回归测试。后续容器验证见 [Docker 部署](../../docker.md#开发验证)。systemd 仅验证单元生成；远端 CI、HTTPS 与实际客户端验收未执行。修改保留在本地 feat/subscription-access 分支，未推送。
