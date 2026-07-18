FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iperf3 \
        iproute2 \
        iptables \
        iputils-ping \
        procps \
        python3 \
        python3-pip \
        python3-venv \
        tcpdump \
    && rm -rf /var/lib/apt/lists/*

COPY . /opt/leo-replay

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -e /opt/leo-replay

WORKDIR /opt/leo-replay
CMD ["sleep", "infinity"]
