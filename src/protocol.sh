#!/bin/bash

protocol_list=(
    VMess-TCP
    VMess-mKCP
    VMess-QUIC
    VMess-H2-TLS
    VMess-WS-TLS
    VMess-gRPC-TLS
    VLESS-H2-TLS
    VLESS-WS-TLS
    VLESS-gRPC-TLS
    Trojan-H2-TLS
    Trojan-WS-TLS
    Trojan-gRPC-TLS
    Shadowsocks
    VMess-TCP-dynamic-port
    VMess-mKCP-dynamic-port
    VMess-QUIC-dynamic-port
    Socks
)
ss_method_list=(
    aes-128-gcm
    aes-256-gcm
    chacha20-ietf-poly1305
)
header_type_list=(
    none
    srtp
    utp
    wechat-video
    dtls
    wireguard
)

info_list=(
    "协议 (protocol)"
    "地址 (address)"
    "端口 (port)"
    "用户ID (id)"
    "传输协议 (network)"
    "伪装类型 (type)"
    "伪装域名 (host)"
    "路径 (path)"
    "传输层安全 (TLS)"
    "mKCP seed"
    "密码 (password)"
    "加密方式 (encryption)"
    "链接 (URL)"
    "目标地址 (remote addr)"
    "目标端口 (remote port)"
    "流控 (flow)"
    "SNI (serverName)"
    "指纹 (Fingerprint)"
    "公钥 (Public key)"
    "用户名 (Username)"
)
change_list=(
    "更改协议"
    "更改端口"
    "更改域名"
    "更改路径"
    "更改密码"
    "更改 UUID"
    "更改加密方式"
    "更改伪装类型"
    "更改目标地址"
    "更改目标端口"
    "更改密钥"
    "更改 SNI (serverName)"
    "更改动态端口"
    "更改伪装网站"
    "更改 mKCP seed"
    "更改用户名 (Username)"
)
servername_list=(
    www.amazon.com
    www.microsoft.com
    www.apple.com
    dash.cloudflare.com
    dl.google.com
    aws.amazon.com
)

# CHANGE_* named constants (replace numeric 0-15 indices)
CHANGE_PROTOCOL=0
CHANGE_PORT=1
CHANGE_HOST=2
CHANGE_PATH=3
CHANGE_PASSWORD=4
CHANGE_UUID=5
CHANGE_METHOD=6
CHANGE_HEADER_TYPE=7
CHANGE_DOOR_ADDR=8
CHANGE_DOOR_PORT=9
CHANGE_KEY=10
CHANGE_SNI=11
CHANGE_DYNAMIC_PORT=12
CHANGE_PROXY_SITE=13
CHANGE_KCP_SEED=14
CHANGE_SOCKS_USER=15

is_random_ss_method=${ss_method_list[$(shuf -i 0-${#ss_method_list[@]} -n1) - 1]}
is_random_header_type=${header_type_list[$(shuf -i 1-5 -n1)]} # random dont use none
is_random_servername=${servername_list[$(shuf -i 0-${#servername_list[@]} -n1) - 1]}

get_pbk() {
    is_tmp_pbk=($($is_core_bin x25519 | sed 's/.*://'))
    is_private_key=${is_tmp_pbk[0]}
    is_public_key=${is_tmp_pbk[1]}
}

# --- Protocol JSON generation helpers ---

# Set authentication/settings JSON for each protocol family
_set_protocol_vmess() {
    is_protocol=vmess
    if [[ $is_dynamic_port ]]; then
        is_server_id_json='settings:{clients:[{id:'\"$uuid\"'}],detour:{to:'\"$is_config_name-link.json\"'}}'
    else
        is_server_id_json='settings:{clients:[{id:'\"$uuid\"'}]}'
    fi
    is_client_id_json='settings:{vnext:[{address:'\"$is_addr\"',port:'"$port"',users:[{id:'\"$uuid\"'}]}]}'
}

_set_protocol_vless() {
    is_protocol=vless
    is_server_id_json='settings:{clients:[{id:'\"$uuid\"'}],decryption:"none"}'
    is_client_id_json='settings:{vnext:[{address:'\"$is_addr\"',port:'"$port"',users:[{id:'\"$uuid\"',encryption:"none"}]}]}'
    if [[ $is_reality ]]; then
        is_server_id_json='settings:{clients:[{id:'\"$uuid\"',flow:"xtls-rprx-vision"}],decryption:"none"}'
        is_client_id_json='settings:{vnext:[{address:'\"$is_addr\"',port:'"$port"',users:[{id:'\"$uuid\"',encryption:"none",flow:"xtls-rprx-vision"}]}]}'
    fi
}

_set_protocol_trojan() {
    is_protocol=trojan
    [[ ! $trojan_password ]] && trojan_password=$uuid
    is_server_id_json='settings:{clients:[{password:'\"$trojan_password\"'}]}'
    is_client_id_json='settings:{servers:[{address:'\"$is_addr\"',port:'"$port"',password:'\"$trojan_password\"'}]}'
    is_trojan=1
}

_set_protocol_ss() {
    is_protocol=shadowsocks
    net=ss
    [[ ! $ss_method ]] && ss_method=$is_random_ss_method
    [[ ! $ss_password ]] && {
        ss_password=$uuid
        [[ $(grep 2022 <<<$ss_method) ]] && ss_password=$(get ss2022)
    }
    is_client_id_json='settings:{servers:[{address:'\"$is_addr\"',port:'"$port"',method:'\"$ss_method\"',password:'\"$ss_password\"',}]}'
    json_str='settings:{method:'\"$ss_method\"',password:'\"$ss_password\"',network:"tcp,udp"}'
}

_set_protocol_door() {
    is_protocol=dokodemo-door
    net=door
    json_str='settings:{port:'"$door_port"',address:'\"$door_addr\"',network:"tcp,udp"}'
}

_set_protocol_http() {
    is_protocol=http
    net=http
    json_str='settings:{"timeout": 233}'
}

_set_protocol_socks() {
    is_protocol=socks
    net=socks
    [[ ! $is_socks_user ]] && is_socks_user=TrekMax
    [[ ! $is_socks_pass ]] && is_socks_pass=$uuid
    json_str='settings:{auth:"password",accounts:[{user:'\"$is_socks_user\"',pass:'\"$is_socks_pass\"'}],udp:true,ip:"0.0.0.0"}'
}

# Set transport layer JSON
_set_transport_tcp() {
    net=tcp
    [[ ! $header_type ]] && header_type=none
    is_stream='streamSettings:{network:"tcp",tcpSettings:{header:{type:'\"$header_type\"'}}}'
    json_str=''"$is_server_id_json"','"$is_stream"''
}

_set_transport_kcp() {
    net=kcp
    [[ ! $header_type ]] && header_type=$is_random_header_type
    [[ ! $is_no_kcp_seed && ! $kcp_seed ]] && kcp_seed=$uuid
    is_stream='streamSettings:{network:"kcp",kcpSettings:{seed:'\"$kcp_seed\"',header:{type:'\"$header_type\"'}}}'
    json_str=''"$is_server_id_json"','"$is_stream"''
}

_set_transport_quic() {
    net=quic
    [[ ! $header_type ]] && header_type=$is_random_header_type
    is_stream='streamSettings:{network:"quic",quicSettings:{header:{type:'\"$header_type\"'}}}'
    json_str=''"$is_server_id_json"','"$is_stream"''
}

_set_transport_ws() {
    net=ws
    [[ ! $path ]] && path="/$uuid"
    is_stream='streamSettings:{network:"ws",security:'\"$is_tls\"',wsSettings:{path:'\"$path\"',headers:{Host:'\"$host\"'}}}'
    json_str=''"$is_server_id_json"','"$is_stream"''
}

_set_transport_grpc() {
    net=grpc
    [[ ! $path ]] && path="$uuid"
    [[ $path ]] && path=$(sed 's#/##g' <<<$path)
    is_stream='streamSettings:{network:"grpc",grpc_host:'\"$host\"',security:'\"$is_tls\"',grpcSettings:{serviceName:'\"$path\"'}}'
    json_str=''"$is_server_id_json"','"$is_stream"''
}

_set_transport_h2() {
    net=h2
    [[ ! $path ]] && path="/$uuid"
    is_stream='streamSettings:{network:"h2",security:'\"$is_tls\"',httpSettings:{path:'\"$path\"',host:['\"$host\"']}}'
    json_str=''"$is_server_id_json"','"$is_stream"''
}

_set_transport_reality() {
    net=reality
    [[ ! $is_servername ]] && is_servername=$is_random_servername
    [[ ! $is_private_key ]] && get_pbk
    is_stream='streamSettings:{network:"tcp",security:"reality",realitySettings:{dest:'\"${is_servername}\:443\"',serverNames:['\"${is_servername}\"',""],publicKey:'\"$is_public_key\"',privateKey:'\"$is_private_key\"',shortIds:[""]}}'
    if [[ $is_client ]]; then
        is_stream='streamSettings:{network:"tcp",security:"reality",realitySettings:{serverName:'\"${is_servername}\"',"fingerprint": "ios",publicKey:'\"$is_public_key\"',"shortId": "","spiderX": "/"}}'
    fi
    json_str=''"$is_server_id_json"','"$is_stream"''
}

# Main protocol JSON builder: dispatches to helpers above
# Usage: build_protocol_json <protocol-net-string>
build_protocol_json() {
    get addr # get host or server ip
    is_lower=${1,,}
    net=
    case $is_lower in
    vmess*)
        _set_protocol_vmess
        ;;
    vless*)
        _set_protocol_vless
        ;;
    trojan*)
        _set_protocol_trojan
        ;;
    shadowsocks*)
        _set_protocol_ss
        ;;
    dokodemo-door*)
        _set_protocol_door
        ;;
    *http*)
        _set_protocol_http
        ;;
    *socks*)
        _set_protocol_socks
        ;;
    *)
        err "无法识别协议: $is_config_file"
        ;;
    esac
    [[ $net ]] && return # if net exist, dont need more json args
    case $is_lower in
    *tcp*)
        _set_transport_tcp
        ;;
    *kcp* | *mkcp)
        _set_transport_kcp
        ;;
    *quic*)
        _set_transport_quic
        ;;
    *ws* | *websocket)
        _set_transport_ws
        ;;
    *grpc* | *gun)
        _set_transport_grpc
        ;;
    *h2* | *http*)
        _set_transport_h2
        ;;
    *reality*)
        _set_transport_reality
        ;;
    *)
        err "无法识别传输协议: $is_config_file"
        ;;
    esac
}
