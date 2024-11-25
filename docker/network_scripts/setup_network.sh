#!/bin/bash

# Enable IP forwarding
echo "1" > /proc/sys/net/ipv4/ip_forward

# Load required kernel modules
modprobe ip_tables
modprobe ip_conntrack
modprobe ip_conntrack_irc
modprobe ip_conntrack_ftp

# Unload unwanted modules
modprobe -r iptable_filter iptable_nat iptable_mangle iptable_raw iptable_security

# Keep the container running
exec "$@"