#!/bin/bash
set -e

V2RAY_BIN=/etc/v2ray/bin/v2ray

# Download v2ray binary if not present
if [[ ! -f "$V2RAY_BIN" ]]; then
    echo ">>> Downloading v2ray binary..."
    case $(uname -m) in
        x86_64)  V2RAY_ARCH=64 ;;
        aarch64) V2RAY_ARCH=arm64-v8a ;;
        *)       echo "Unsupported arch: $(uname -m)"; exit 1 ;;
    esac
    LATEST=$(wget -qO- "https://api.github.com/repos/v2fly/v2ray-core/releases/latest" \
        | grep '"tag_name"' | cut -d'"' -f4)
    mkdir -p /etc/v2ray/bin
    wget -qO /tmp/v2ray.zip \
        "https://github.com/v2fly/v2ray-core/releases/download/${LATEST}/v2ray-linux-${V2RAY_ARCH}.zip"
    unzip -qo /tmp/v2ray.zip v2ray geoip.dat geosite.dat -d /etc/v2ray/bin/
    rm /tmp/v2ray.zip
    chmod +x "$V2RAY_BIN"
    echo ">>> $($V2RAY_BIN version | head -n1) installed"
fi

# Create service file skeleton (init.sh checks this for version-based arg patching)
mkdir -p /lib/systemd/system /etc/v2ray/conf /var/log/v2ray
if [[ ! -f /lib/systemd/system/v2ray.service ]]; then
    cat >/lib/systemd/system/v2ray.service <<'EOF'
[Unit]
Description=V2Ray Service

[Service]
ExecStart=/etc/v2ray/bin/v2ray run -config /etc/v2ray/config.json -confdir /etc/v2ray/conf
EOF
fi

# Start v2ray if config already exists (e.g. persistent volume reuse)
if [[ -f /etc/v2ray/config.json ]]; then
    echo ">>> Starting v2ray..."
    nohup "$V2RAY_BIN" run \
        -config /etc/v2ray/config.json \
        -confdir /etc/v2ray/conf \
        >>/var/log/v2ray/access.log 2>>/var/log/v2ray/error.log &
    sleep 0.5
    echo ">>> v2ray started (PID: $(pgrep -f "$V2RAY_BIN" | head -1))"
fi

exec "$@"
