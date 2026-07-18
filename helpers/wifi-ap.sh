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

# Kills by matching the actual config file on the command line, not just a
# PID file — a stale or missing PID file must never leave a previous
# hostapd/dnsmasq instance running underneath a fresh `start`.
stop_ap() {
  pkill -f "hostapd.*$HOSTAPD_CONF" 2>/dev/null || true
  pkill -f "dnsmasq.*$DNSMASQ_CONF" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    pgrep -f "hostapd.*$HOSTAPD_CONF" >/dev/null 2>&1 || pgrep -f "dnsmasq.*$DNSMASQ_CONF" >/dev/null 2>&1 || break
    sleep 0.5
  done
  pkill -9 -f "hostapd.*$HOSTAPD_CONF" 2>/dev/null || true
  pkill -9 -f "dnsmasq.*$DNSMASQ_CONF" 2>/dev/null || true
  rm -f "$HOSTAPD_PID" "$DNSMASQ_PID"
  ip addr flush dev "$IFACE" 2>/dev/null || true
  ip link set "$IFACE" down 2>/dev/null || true
}

case "$ACTION" in
  start)
    SSID="$2"
    PASSWORD="$3"
    if [[ "$SSID" == *$'\n'* || "$PASSWORD" == *$'\n'* ]]; then
      echo "SSID/password cannot contain newlines" >&2
      exit 1
    fi

    # Always start from a known-clean state — never layer a new instance on
    # top of a possibly still-running (or half-dead) previous one.
    stop_ap

    # Drop any client-mode config so it doesn't fight hostapd for the radio.
    rm -f "$NETPLAN_WIFI_FILE"
    netplan apply || true

    rfkill unblock wifi || true
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

    hostapd -B -P "$HOSTAPD_PID" "$HOSTAPD_CONF"
    dnsmasq --conf-file="$DNSMASQ_CONF" --pid-file="$DNSMASQ_PID"
    ;;
  stop)
    stop_ap
    ;;
  status)
    if pgrep -f "hostapd.*$HOSTAPD_CONF" >/dev/null 2>&1; then
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
