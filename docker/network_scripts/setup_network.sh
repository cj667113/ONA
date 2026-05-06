#!/bin/bash
set -euo pipefail

# Enable IP forwarding
echo "1" > /proc/sys/net/ipv4/ip_forward || true

# Load required kernel modules
for module in ip_tables iptable_nat nf_nat nf_conntrack nf_conntrack_ftp; do
  modprobe "$module" || true
done

# Keep the container running
exec "$@"
