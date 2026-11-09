#!/bin/bash
set -euo pipefail
umask 077

V2RAY_BIN=/etc/v2ray/bin/v2ray

# Download v2ray binary if not present
if [[ ! -f "$V2RAY_BIN" ]]; then
    echo ">>> Downloading v2ray binary..."
    case $(uname -m) in
        x86_64)  V2RAY_ARCH=64 ;;
        aarch64) V2RAY_ARCH=arm64-v8a ;;
        *)       echo "Unsupported arch: $(uname -m)"; exit 1 ;;
    esac
    LATEST=$(wget -qO- --timeout=30 --tries=3 \
        "https://api.github.com/repos/v2fly/v2ray-core/releases/latest" | jq -er '.tag_name')
    mkdir -p /etc/v2ray/bin
    wget --timeout=30 --tries=3 -qO /tmp/v2ray.zip \
        "https://github.com/v2fly/v2ray-core/releases/download/${LATEST}/v2ray-linux-${V2RAY_ARCH}.zip"
    # Only publish the binary after all files extract successfully, so retry is safe.
    staging=$(mktemp -d /etc/v2ray/bin/.download.XXXXXX)
    trap 'rm -rf "$staging" /tmp/v2ray.zip' EXIT
    unzip -qo /tmp/v2ray.zip v2ray geoip.dat geosite.dat -d "$staging"
    mv "$staging/geoip.dat" "$staging/geosite.dat" /etc/v2ray/bin/
    chmod +x "$staging/v2ray"
    mv "$staging/v2ray" "$V2RAY_BIN"
    rm -rf "$staging"
    trap - EXIT
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

# Keep the standard config path usable by all existing CLI commands.
bash /etc/v2ray/sh/docker/prepare-config
if [[ ! -f /etc/v2ray/config.json ]]; then
    echo ">>> Creating initial main config..."
    # The existing generator owns the default schema. Start services below once ready.
    bash -c '
        . /etc/v2ray/sh/src/lib.sh
        . /etc/v2ray/sh/src/config.sh
        manage() { :; }
        create config.json
    '
    bash /etc/v2ray/sh/docker/prepare-config
fi

echo ">>> Starting v2ray..."
systemctl start v2ray.service

# Restore subscription service only when previously enabled. Its state has its own volume.
if systemctl is-enabled --quiet v2ray-subscription.service; then
    systemctl start v2ray-subscription.service
fi

if [[ ${1:-serve} == serve ]]; then
    shutdown() {
        systemctl stop v2ray-subscription.service || true
        systemctl stop v2ray.service || true
        exit 0
    }
    trap shutdown TERM INT
    echo '>>> Ready. Manage with: docker compose exec v2ray v2ray'
    # Keep the container available for CLI stop/start/restart; HEALTHCHECK reports failure.
    while :; do
        sleep 1 &
        wait $! || true
    done
fi
exec "$@"
