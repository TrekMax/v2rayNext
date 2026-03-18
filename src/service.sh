#!/bin/bash

# --- systemd service installation ---

install_service() {
    case $1 in
    xray | v2ray)
        is_doc_site=https://xtls.github.io/
        [[ $1 == 'v2ray' ]] && is_doc_site=https://www.v2fly.org/
        cat >/lib/systemd/system/$is_core.service <<<"
[Unit]
Description=$is_core_name Service
Documentation=$is_doc_site
After=network.target nss-lookup.target

[Service]
#User=nobody
User=root
NoNewPrivileges=true
ExecStart=$is_core_bin run -config $is_config_json -confdir $is_conf_dir
Restart=on-failure
RestartPreventExitStatus=23
LimitNPROC=10000
LimitNOFILE=1048576
PrivateTmp=true
ProtectSystem=full
#CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
#AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target"
        ;;
    caddy)
        cat >/lib/systemd/system/caddy.service <<<"
#https://github.com/caddyserver/dist/blob/master/init/caddy.service
[Unit]
Description=Caddy
Documentation=https://caddyserver.com/docs/
After=network.target network-online.target
Requires=network-online.target

[Service]
Type=notify
User=root
Group=root
ExecStart=$is_caddy_bin run --environ --config $is_caddyfile --adapter caddyfile
ExecReload=$is_caddy_bin reload --config $is_caddyfile --adapter caddyfile
TimeoutStopSec=5s
LimitNPROC=10000
LimitNOFILE=1048576
PrivateTmp=true
ProtectSystem=full
#AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target"
        ;;
    esac

    # enable, reload
    systemctl enable $1
    systemctl daemon-reload
}

# --- manage run status ---

manage() {
    [[ $is_dont_auto_exit ]] && return
    case $1 in
    1 | start)
        is_do=start
        is_do_msg=启动
        is_test_run=1
        ;;
    2 | stop)
        is_do=stop
        is_do_msg=停止
        ;;
    3 | r | restart)
        is_do=restart
        is_do_msg=重启
        is_test_run=1
        ;;
    *)
        is_do=$1
        is_do_msg=$1
        ;;
    esac
    case $2 in
    caddy)
        is_do_name=$2
        is_run_bin=$is_caddy_bin
        is_do_name_msg=Caddy
        ;;
    *)
        is_do_name=$is_core
        is_run_bin=$is_core_bin
        is_do_name_msg=$is_core_name
        ;;
    esac
    systemctl $is_do $is_do_name
    [[ $is_test_run && ! $is_new_install ]] && {
        sleep 2
        if [[ ! $(pgrep -f $is_run_bin) ]]; then
            is_run_fail=${is_do_name_msg,,}
            [[ ! $is_no_manage_msg ]] && {
                msg
                warn "($is_do_msg) $is_do_name_msg 失败"
                _yellow "检测到运行失败, 自动执行测试运行."
                get test-run
                _yellow "测试结束, 请按 Enter 退出."
            }
        fi
    }
}

# --- use api add or del inbounds ---

api() {
    [[ $is_core_ver_lt_5 ]] && {
        warn "$is_core_ver 版本不支持使用 API 操作. 请升级内核版本: $is_core update core"
        is_api_fail=1
        return
    }
    [[ ! $1 ]] && err "无法识别 API 的参数."
    [[ $is_core_stop ]] && {
        warn "$is_core_name 当前处于停止状态."
        is_api_fail=1
        return
    }
    case $1 in
    add)
        is_api_do=adi
        ;;
    del)
        is_api_do=rmi
        ;;
    s)
        is_api_do=stats
        ;;
    t | sq)
        is_api_do=statsquery
        ;;
    esac
    [[ ! $is_api_do ]] && is_api_do=$1
    [[ ! $is_api_port ]] && {
        is_api_port=$(jq '.inbounds[] | select(.tag == "api") | .port' $is_config_json)
        [[ $? != 0 ]] && {
            warn "读取 API 端口失败, 无法使用 API 操作."
            return
        }
    }
    $is_core_bin api $is_api_do --server=127.0.0.1:$is_api_port ${@:2}
    [[ $? != 0 ]] && {
        is_api_fail=1
    }
}

# --- uninstall ---

uninstall() {
    if [[ $is_caddy ]]; then
        is_tmp_list=("卸载 $is_core_name" "卸载 ${is_core_name} & Caddy")
        ask list is_do_uninstall
    else
        ask string y "是否卸载 ${is_core_name}? [y]:"
    fi
    manage stop &>/dev/null
    manage disable &>/dev/null
    rm -rf $is_core_dir $is_log_dir $is_sh_bin /lib/systemd/system/$is_core.service
    sed -i "/$is_core/d" /root/.bashrc
    # uninstall caddy; 2 is ask result
    if [[ $REPLY == '2' ]]; then
        manage stop caddy &>/dev/null
        manage disable caddy &>/dev/null
        rm -rf $is_caddy_dir $is_caddy_bin /lib/systemd/system/caddy.service
    fi
    [[ $is_install_sh ]] && return # reinstall
    _green "\n卸载完成!"
    msg "脚本哪里需要完善? 请反馈"
    msg "反馈问题) $(msg_ul https://github.com/${is_sh_repo}/issues)\n"
}
