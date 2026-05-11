#!/bin/bash
set -euo pipefail

# Enable IP forwarding
echo "1" > /proc/sys/net/ipv4/ip_forward || true

# Load required kernel modules
modules=(ip_tables iptable_nat iptable_mangle nf_nat nf_conntrack xt_addrtype xt_connmark xt_mark xt_statistic)
kernel_modules_dir="/lib/modules/$(uname -r)"

if [[ -d "$kernel_modules_dir" ]]; then
  missing_modules=()
  for module in "${modules[@]}"; do
    if lsmod | awk '{print $1}' | grep -qx "$module"; then
      continue
    fi
    if ! modprobe -q "$module" 2>/dev/null; then
      missing_modules+=("$module")
    fi
  done

  if [[ ${#missing_modules[@]} -gt 0 ]]; then
    echo "Warning: unable to load optional netfilter modules: ${missing_modules[*]}" >&2
    echo "If iptables rules fail, load these modules on the Docker host or verify the matching kernel module packages are installed." >&2
  fi
else
  echo "Warning: $kernel_modules_dir is not available inside the container; skipping explicit netfilter module loading." >&2
  echo "If iptables rules fail, mount /lib/modules read-only into the container or load the modules on the Docker host." >&2
fi

# Keep the container running
exec "$@"
