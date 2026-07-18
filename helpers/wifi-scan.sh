#!/usr/bin/env bash
#
# Scans for WiFi networks on wlan0 and prints raw `iw scan` output for
# wifi.py to parse. Needs root (iw scan requires it), and needs wlan0
# administratively up — harmless to bring up even while it's not associated
# to anything.
#
# Usage: wifi-scan.sh

set -euo pipefail

IFACE="wlan0"

ip link set "$IFACE" up 2>/dev/null || true
iw dev "$IFACE" scan
