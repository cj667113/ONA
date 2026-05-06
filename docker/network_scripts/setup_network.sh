#!/bin/bash
set -euo pipefail

# Enable IP forwarding
echo "1" > /proc/sys/net/ipv4/ip_forward || true

# Load required kernel modules
for module in ip_tables iptable_nat iptable_mangle nf_nat nf_conntrack xt_addrtype xt_connmark xt_mark xt_statistic; do
  modprobe "$module" || true
done

# Keep the container running
exec "$@"
