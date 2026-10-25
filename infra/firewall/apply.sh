#!/usr/bin/env bash
# Block cloud metadata + private nets from sandbox bridge egress (host-level).
set -euo pipefail
# Link-local metadata
iptables -C DOCKER-USER -d 169.254.169.254 -j DROP 2>/dev/null || \
  iptables -I DOCKER-USER -d 169.254.169.254 -j DROP
# Private nets (adjust for your VPC)
for cidr in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
  iptables -C DOCKER-USER -d "$cidr" -j DROP 2>/dev/null || \
    iptables -I DOCKER-USER -d "$cidr" -j DROP
done
echo "firewall rules applied"
