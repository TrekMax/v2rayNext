FROM ubuntu:22.04

LABEL maintainer="TrekMax <https://github.com/TrekMax/v2rayNext>"

ENV DEBIAN_FRONTEND=noninteractive

# Install script dependencies
RUN apt-get update && apt-get install -y \
        wget curl unzip jq qrencode net-tools iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Copy project files into script directory
COPY . /etc/v2ray/sh/

# Set up script entry point
RUN chmod +x /etc/v2ray/sh/v2ray.sh \
    && ln -sf /etc/v2ray/sh/v2ray.sh /usr/local/bin/v2ray

# Install mock systemctl (replaces systemd for Docker)
RUN install -m 0755 /etc/v2ray/sh/docker/systemctl /usr/local/bin/systemctl

# Install entrypoint
RUN install -m 0755 /etc/v2ray/sh/docker/entrypoint.sh /entrypoint.sh

# Common proxy ports
EXPOSE 1080 2333 10000-10010

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]
