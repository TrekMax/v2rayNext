#!/bin/bash

# lib.sh is sourced by v2ray.sh before this file

is_caddy_bin=/usr/local/bin/caddy
is_caddy_dir=/etc/caddy
is_caddy_repo=caddyserver/caddy
is_caddyfile=$is_caddy_dir/Caddyfile
is_caddy_conf=$is_caddy_dir/$author
is_caddy_service=$(systemctl list-units --full -all | grep caddy.service)
is_http_port=80
is_https_port=443
is_pkg="wget unzip jq qrencode"

# core ver
is_core_ver=$($is_core_bin version | head -n1 | cut -d " " -f1-2)

if [[ $(grep -o ^[0-9] <<<${is_core_ver#* }) -lt 5 ]]; then
    # core version less than 5, e.g, v4.45.2
    is_core_ver_lt_5=1
    if [[ $(grep 'run -config' /lib/systemd/system/v2ray.service) ]]; then
        sed -i 's/run //' /lib/systemd/system/v2ray.service
        systemctl daemon-reload
    fi
else
    is_with_run_arg=run
    if [[ ! $(grep 'run -config' /lib/systemd/system/v2ray.service) ]]; then
        sed -i 's/-config/run -config/' /lib/systemd/system/v2ray.service
        systemctl daemon-reload
    fi
fi

if [[ $(pgrep -f $is_core_bin) ]]; then
    is_core_status=$(_green running)
else
    is_core_status=$(_red_bg stopped)
    is_core_stop=1
fi
if [[ -f $is_caddy_bin && -d $is_caddy_dir && $is_caddy_service ]]; then
    is_caddy=1
    # fix caddy run; ver >= 2.8.2
    [[ ! $(grep '\-\-adapter caddyfile' /lib/systemd/system/caddy.service) ]] && {
        load service.sh
        install_service caddy
        systemctl restart caddy &
    }
    is_caddy_ver=$($is_caddy_bin version | head -n1 | cut -d " " -f1)
    is_tmp_http_port=$(grep -E '^ {2,}http_port|^http_port' $is_caddyfile | grep -E -o [0-9]+)
    is_tmp_https_port=$(grep -E '^ {2,}https_port|^https_port' $is_caddyfile | grep -E -o [0-9]+)
    [[ $is_tmp_http_port ]] && is_http_port=$is_tmp_http_port
    [[ $is_tmp_https_port ]] && is_https_port=$is_tmp_https_port
    if [[ $(pgrep -f $is_caddy_bin) ]]; then
        is_caddy_status=$(_green running)
    else
        is_caddy_status=$(_red_bg stopped)
        is_caddy_stop=1
    fi
fi

load protocol.sh
load menu.sh
load service.sh
load config.sh
load cmd.sh

[[ ! $args ]] && args=main
main $args
