#!/bin/bash
# Variables are provided by lib.sh (or a caller's isolated test environment).
# shellcheck disable=SC2154

subscription_python() {
    python3 "$is_sh_dir/src/subscription.py" --state-dir "$is_core_dir/subscription" "$@"
}

subscription_prepare_container() {
    local manager
    manager=$(command -v systemctl) || return 1
    # Script-only upgrades leave the image's copied adapters at their old version.
    # Refresh only this project's identifiable wrapper, never the real systemctl.
    if [[ -f $manager ]] && grep -Fqx '# Mock systemctl for Docker environment (no systemd)' "$manager"; then
        install -m 0755 "$is_sh_dir/docker/systemctl" "$manager" || return 1
        install -m 0755 "$is_sh_dir/docker/entrypoint.sh" "${is_container_entrypoint:-/entrypoint.sh}" || return 1
    fi
    return 0
}

subscription_refresh() (
    # Isolate info()'s global variables, and keep failed output private.
    umask 077
    local mode=$1 filename temporary
    case $mode in
    base64) filename=sub.txt ;;
    clash) filename=sub-clash.yaml ;;
    *) warn "订阅格式仅支持 base64 / clash"; return 1 ;;
    esac
    subscription_python validate "$mode" || return 1
    temporary=$(mktemp "$is_core_dir/subscription/.content-XXXXXX") || return 1
    trap 'rm -f -- "$temporary"' EXIT
    # Do not test the subshell as an if-condition: that disables errexit inside it.
    (set -e -o pipefail; _sub_generate "$mode" "$temporary") >/dev/null
    local result=$?
    [[ $result -eq 0 && -s $temporary ]] || { warn "订阅生成失败，保留原内容"; return 1; }
    chmod 600 "$temporary" || return 1
    mv -f -- "$temporary" "$is_core_dir/subscription/$filename" || return 1
)

subscription_setup() {
    [[ $# -eq 1 ]] || { warn "用法: v2ray sub setup https://sub.example.com"; return 1; }
    subscription_python setup "$1" || return 1
    subscription_prepare_container || return 1
    # Removing the previous outputs invalidates the old aliases that point here.
    rm -f -- "$is_core_dir/sub.txt" "$is_core_dir/sub-clash.yaml" || return 1
    load service.sh
    install_subscription_service || return 1
    systemctl restart v2ray-subscription.service || return 1
    systemctl is-active --quiet v2ray-subscription.service || {
        warn "订阅服务未启动，请检查 v2ray sub status"
        return 1
    }
    msg "订阅服务已启动: 127.0.0.1:8787"
    msg "请配置 HTTPS 反向代理 /sub 和 /sub-clash，并删除旧的静态订阅入口及副本。"
    msg "部署说明: $is_sh_dir/docs/subscription.md"
}

subscription_command() {
    if ! command -v python3 >/dev/null 2>&1 ||
        ! python3 -c 'import sys, sqlite3; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
        warn "订阅功能需要 Python 3.8+（含 sqlite3），请安装系统 python3 包后重试。"
        return 1
    fi
    local action=${1:-base64}
    [[ $# -gt 0 ]] && shift
    case $action in
    setup) subscription_setup "$@" ;;
    list | revoke) subscription_python "$action" "$@" ;;
    start | stop | restart | status)
        [[ $# -eq 0 ]] || { warn "服务管理命令不接受额外参数"; return 1; }
        systemctl "$action" v2ray-subscription.service
        ;;
    refresh)
        [[ $# -le 1 ]] || { warn "用法: v2ray sub refresh [base64 | clash]"; return 1; }
        subscription_refresh "${1:-base64}"
        local result=$?
        [[ $result -eq 0 ]] && msg "订阅内容已更新，现有授权与有效期保持不变。"
        return "$result"
        ;;
    base64 | raw | clash | clash-meta | meta | --ttl | --name)
        case $action in
        raw) action=base64 ;;
        clash-meta | meta) action=clash ;;
        --*) set -- "$action" "$@"; action=base64 ;;
        esac
        subscription_python validate "$action" "$@" || return 1
        subscription_refresh "$action"
        local result=$?
        [[ $result -eq 0 ]] || return "$result"
        subscription_python issue "$action" "$@"
        ;;
    *)
        warn "用法: v2ray sub [base64 | clash] [--ttl 7d] [--name 名称]"
        warn "管理命令: setup / refresh / list / revoke / start / stop / restart / status"
        return 1
        ;;
    esac
}
