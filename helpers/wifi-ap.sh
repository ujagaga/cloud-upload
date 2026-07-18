#!/usr/bin/env bash
#
# Toggles a WiFi setup access point on wlan0 (hostapd + dnsmasq), used when
# the device has no other way online. AP mode and station (client) mode are
# mutually exclusive on this hardware — one radio, no concurrent AP+STA
# (`iw list`'s interface combinations cap {managed, AP} at 1 total) — so
# starting the AP always means station mode is down, and vice versa.
#
# Usage: wifi-ap.sh start <ssid> <password> | stop | status

set -euo pipefail

ACTION="$1"
IFACE="wlan0"
AP_IP="192.168.4.1"
HOSTAPD_CONF="/etc/hostapd/hostapd-cloudupload.conf"
DNSMASQ_CONF="/etc/dnsmasq-cloudupload.conf"
HOSTAPD_PID="/run/cloudupload-hostapd.pid"
DNSMASQ_PID="/run/cloudupload-dnsmasq.pid"
NETPLAN_WIFI_FILE="/etc/netplan/90-cloud-upload-wifi.yaml"

case "$ACTION" in
  start)
    SSID="$2"
    PASSWORD="$3"
    if [[ "$SSID" == *$'\n'* || "$PASSWORD" == *$'\n'* ]]; then
      echo "SSID/password cannot contain newlines" >&2
      exit 1
    fi

    # Drop any client-mode config so it doesn't fight hostapd for the radio.
    rm -f "$NETPLAN_WIFI_FILE"
    netplan apply || true

    rfkill unblock wifi || true
    ip link set "$IFACE" down || true
    ip addr flush dev "$IFACE" || true
    ip link set "$IFACE" up
    ip addr add "$AP_IP/24" dev "$IFACE"

    mkdir -p "$(dirname "$HOSTAPD_CONF")"
    cat > "$HOSTAPD_CONF" <<EOF
interface=$IFACE
driver=nl80211
ssid=$SSID
hw_mode=g
channel=6
auth_algs=1
wpa=2
wpa_passphrase=$PASSWORD
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

    cat > "$DNSMASQ_CONF" <<EOF
interface=$IFACE
bind-interfaces
except-interface=lo
dhcp-range=192.168.4.10,192.168.4.50,12h
dhcp-option=3,$AP_IP
dhcp-option=6,$AP_IP
EOF

    # Stale process from a previous run that didn't get stopped cleanly.
    [ -f "$HOSTAPD_PID" ] && kill "$(cat "$HOSTAPD_PID")" 2>/dev/null || true
    [ -f "$DNSMASQ_PID" ] && kill "$(cat "$DNSMASQ_PID")" 2>/dev/null || true

    hostapd -B -P "$HOSTAPD_PID" "$HOSTAPD_CONF"
    dnsmasq --conf-file="$DNSMASQ_CONF" --pid-file="$DNSMASQ_PID"
    ;;
  stop)
    if [ -f "$DNSMASQ_PID" ]; then
      kill "$(cat "$DNSMASQ_PID")" 2>/dev/null || true
      rm -f "$DNSMASQ_PID"
    fi
    if [ -f "$HOSTAPD_PID" ]; then
      kill "$(cat "$HOSTAPD_PID")" 2>/dev/null || true
      rm -f "$HOSTAPD_PID"
    fi
    sleep 1
    ip addr flush dev "$IFACE" || true
    ip link set "$IFACE" down || true
    ;;
  status)
    if [ -f "$HOSTAPD_PID" ] && kill -0 "$(cat "$HOSTAPD_PID")" 2>/dev/null; then
      echo "active"
    else
      echo "inactive"
    fi
    ;;
  *)
    echo "Usage: $0 start <ssid> <password> | stop | status" >&2
    exit 1
    ;;
esac
