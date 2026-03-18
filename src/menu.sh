#!/bin/bash

mainmenu=(
    "添加配置"
    "更改配置"
    "查看配置"
    "删除配置"
    "运行管理"
    "更新"
    "卸载"
    "帮助"
    "其他"
    "关于"
)

show_list() {
    PS3=''
    COLUMNS=1
    select i in "$@"; do echo; done &
    wait
}

# ask input a string or pick a option for list.
ask() {
    local is_ask_set is_opt_msg is_opt_input_msg is_default_arg is_emtpy_exit is_ask_result
    local is_tmp_list=("${is_tmp_list[@]}") # capture caller-provided list, if any
    case $1 in
    set_ss_method)
        is_tmp_list=(${ss_method_list[@]})
        is_default_arg=$is_random_ss_method
        is_opt_msg="\n请选择加密方式:\n"
        is_opt_input_msg="(默认\e[92m $is_default_arg\e[0m):"
        is_ask_set=ss_method
        ;;
    set_header_type)
        is_tmp_list=(${header_type_list[@]})
        is_default_arg=$is_random_header_type
        [[ $(grep -i tcp <<<"$is_new_protocol-$net") ]] && {
            is_tmp_list=(none http)
            is_default_arg=none
        }
        is_opt_msg="\n请选择伪装类型:\n"
        is_opt_input_msg="(默认\e[92m $is_default_arg\e[0m):"
        is_ask_set=header_type
        [[ $is_use_header_type ]] && return
        ;;
    set_protocol)
        is_tmp_list=(${protocol_list[@]})
        [[ $is_no_auto_tls ]] && {
            is_tmp_list=()
            for v in ${protocol_list[@]}; do
                [[ $(grep -i tls$ <<<$v) ]] && is_tmp_list+=($v)
            done
        }
        is_opt_msg="\n请选择协议:\n"
        is_ask_set=is_new_protocol
        ;;
    set_change_list)
        is_tmp_list=()
        for v in ${is_can_change[@]}; do
            is_tmp_list+=("${change_list[$v]}")
        done
        is_opt_msg="\n请选择更改:\n"
        is_ask_set=is_change_str
        is_opt_input_msg=$3
        ;;
    string)
        is_ask_set=$2
        is_opt_input_msg=$3
        ;;
    list)
        is_ask_set=$2
        [[ ! $is_tmp_list ]] && is_tmp_list=($3)
        is_opt_msg=$4
        is_opt_input_msg=$5
        ;;
    get_config_file)
        is_tmp_list=("${is_all_json[@]}")
        is_opt_msg="\n请选择配置:\n"
        is_ask_set=is_config_file
        ;;
    mainmenu)
        is_tmp_list=("${mainmenu[@]}")
        is_ask_set=is_main_pick
        is_emtpy_exit=1
        ;;
    esac
    msg $is_opt_msg
    [[ ! $is_opt_input_msg ]] && is_opt_input_msg="请选择 [\e[91m1-${#is_tmp_list[@]}\e[0m]:"
    [[ $is_tmp_list ]] && show_list "${is_tmp_list[@]}"
    while :; do
        echo -ne $is_opt_input_msg
        read REPLY
        [[ ! $REPLY && $is_emtpy_exit ]] && exit
        [[ ! $REPLY && $is_default_arg ]] && export $is_ask_set=$is_default_arg && break
        if [[ ! $is_tmp_list ]]; then
            [[ $(grep port <<<$is_ask_set) ]] && {
                [[ ! $(is_test port "$REPLY") ]] && {
                    msg "$is_err 请输入正确的端口, 可选(1-65535)"
                    continue
                }
                if [[ $(is_test port_used $REPLY) && $is_ask_set != 'door_port' ]]; then
                    msg "$is_err 无法使用 ($REPLY) 端口."
                    continue
                fi
            }
            [[ $(grep path <<<$is_ask_set) && ! $(is_test path "$REPLY") ]] && {
                [[ ! $tmp_uuid ]] && get_uuid
                msg "$is_err 请输入正确的路径, 例如: /$tmp_uuid"
                continue
            }
            [[ $(grep uuid <<<$is_ask_set) && ! $(is_test uuid "$REPLY") ]] && {
                [[ ! $tmp_uuid ]] && get_uuid
                msg "$is_err 请输入正确的 UUID, 例如: $tmp_uuid"
                continue
            }
            [[ $(grep ^y$ <<<$is_ask_set) ]] && {
                [[ $(grep -i ^y$ <<<"$REPLY") ]] && break
                msg "请输入 (y)"
                continue
            }
            [[ $REPLY ]] && export $is_ask_set=$REPLY && msg "使用: ${!is_ask_set}" && break
        else
            [[ $(is_test number "$REPLY") ]] && is_ask_result=${is_tmp_list[$REPLY - 1]}
            [[ $is_ask_result ]] && export $is_ask_set="$is_ask_result" && msg "选择: ${!is_ask_set}" && break
        fi

        msg "输入${is_err}"
    done
}

# main menu; if no prefer args.
is_main_menu() {
    msg "\n------------- $is_core_name script $is_sh_ver by $author -------------"
    msg "$is_core_ver: $is_core_status"
    msg "Github: $(msg_ul https://github.com/${is_sh_repo})"
    is_main_start=1
    ask mainmenu
    case $REPLY in
    1)
        add
        ;;
    2)
        change
        ;;
    3)
        info
        ;;
    4)
        del
        ;;
    5)
        ask list is_do_manage "启动 停止 重启"
        manage $REPLY &
        msg "\n管理状态执行: $(_green $is_do_manage)\n"
        ;;
    6)
        is_tmp_list=("更新$is_core_name" "更新脚本")
        [[ $is_caddy ]] && is_tmp_list+=("更新Caddy")
        ask list is_do_update null "\n请选择更新:\n"
        update $REPLY
        ;;
    7)
        uninstall
        ;;
    8)
        msg
        load help.sh
        show_help
        ;;
    9)
        ask list is_do_other "启用BBR 查看日志 查看错误日志 测试运行 重装脚本 设置DNS"
        case $REPLY in
        1)
            load bbr.sh
            _try_enable_bbr
            ;;
        2)
            get log
            ;;
        3)
            get logerr
            ;;
        4)
            get test-run
            ;;
        5)
            get reinstall
            ;;
        6)
            load dns.sh
            dns_set
            ;;
        esac
        ;;
    10)
        load help.sh
        about
        ;;
    esac
}
