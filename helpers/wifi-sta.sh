#!/usr/bin/env bash
#
# Directly controls wlan0 station (client) mode via a dedicated wpa_supplicant
# instance + dhcpcd for addressing — no Netplan/systemd-networkd involvement.
# This device only ever runs this one app, so bypassing Netplan's whole-
# system reconciliation (the suspected cause of repeated full-device
# lockups when toggling wlan0 through it) in favor of direct, narrow control
# of just this one interface is simpler and safer here.
#
# Usage: wifi-sta.sh start <path-to-wpa_supplicant.conf> | stop | status

set -euo pipefail

IFACE="wlan0"
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant-cloudupload.conf"
WPA_PID="/run/cloudupload-wpa_supplicant.pid"

stop_sta() {
  pkill -f "dhcpcd.*$IFACE" 2>/dev/null || true
  pkill -f "wpa_supplicant.*$WPA_CONF" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    pgrep -f "wpa_supplicant.*$WPA_CONF" >/dev/null 2>&1 || break
    sleep 0.5
  done
  pkill -9 -f "wpa_supplicant.*$WPA_CONF" 2>/dev/null || true
  rm -f "$WPA_PID"
  ip addr flush dev "$IFACE" 2>/dev/null || true
  ip link set "$IFACE" down 2>/dev/null || true
}

case "$1" in
  start)
    SRC_CONF="$2"

    # Release the radio from AP mode first — mutually exclusive on this
    # hardware. Both scripts run as root already, so a plain call, no sudo.
    /usr/local/bin/wifi-ap.sh stop

    # Always start from a known-clean state — never layer a new instance on
    # top of a possibly still-running (or half-dead) previous one.
    stop_sta

    mkdir -p "$(dirname "$WPA_CONF")"
    install -m 600 "$SRC_CONF" "$WPA_CONF"

    rfkill unblock wifi || true
    ip link set "$IFACE" up

    wpa_supplicant -B -i "$IFACE" -c "$WPA_CONF" -D nl80211 -P "$WPA_PID"
    # -b: background immediately rather than blocking on its own carrier/
    # lease timeout — the caller polls for the resulting IP independently.
    dhcpcd -b "$IFACE"
    ;;
  stop)
    stop_sta
    ;;
  status)
    if pgrep -f "wpa_supplicant.*$WPA_CONF" >/dev/null 2>&1; then
      echo "active"
    else
      echo "inactive"
    fi
    ;;
  *)
    echo "Usage: $0 start <path-to-conf> | stop | status" >&2
    exit 1
    ;;
esac
