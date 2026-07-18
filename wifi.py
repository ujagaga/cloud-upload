"""WiFi provisioning: fall back to a setup access point when there's no
internet, let the user pick a network from their phone, then switch wlan0 to
station mode and join it.

AP and station mode are mutually exclusive on this hardware (single radio,
`iw list`'s interface combinations cap {managed, AP} at 1 total — no
concurrent AP+STA), so this is always a sequential hand-off: connecting to a
chosen network drops the setup AP, and a failed connection attempt reverts
back to it rather than leaving the device unreachable.

Scanning has the same one-radio limitation: a phone associated to the setup
AP would be disconnected mid-scan if we tried to rescan live, since scanning
briefly takes the radio off the AP's channel. So the network list is
captured once, automatically, right before the AP starts (nothing is
connected to it yet at that point) and served from cache while the AP is up.
When the AP isn't running (e.g. reconfiguring over Ethernet), scans happen
live instead, since nothing is at risk of being disconnected.
"""
import json
import os
import subprocess
import tempfile
import threading
import time

import requests
import settings

_lock = threading.Lock()
_state = {"phase": "idle", "message": "", "ssid": ""}
_last_scan = []


def get_status():
    with _lock:
        return dict(_state)


def has_internet(timeout=3) -> bool:
    try:
        requests.get("https://connectivitycheck.gstatic.com/generate_204", timeout=timeout)
        return True
    except requests.RequestException:
        return False


def _wlan0_connected() -> bool:
    """True once wlan0 itself has a real (non-link-local) IPv4 address —
    checked instead of generic internet reachability, because this device
    may also have Ethernet, which would make a generic check succeed
    regardless of whether the wlan0 connection attempt itself worked."""
    try:
        r = subprocess.run(["ip", "-4", "-o", "addr", "show", "wlan0"],
                            capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return " inet " in r.stdout and "169.254." not in r.stdout


def is_ap_active() -> bool:
    try:
        r = subprocess.run(
            ["sudo", "-n", "/usr/local/bin/wifi-ap.sh", "status"],
            capture_output=True, text=True,
        )
        return r.stdout.strip() == "active"
    except FileNotFoundError:
        return False


def _live_scan():
    """Actually run `iw scan`. Only safe to call when nothing is currently
    associated to an AP on this radio."""
    try:
        r = subprocess.run(
            ["sudo", "-n", "/usr/local/bin/wifi-scan.sh"],
            capture_output=True, text=True, timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []

    networks = {}
    ssid = None
    signal = None
    secured = False
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("BSS "):
            ssid, signal, secured = None, None, False
        elif line.startswith("signal:"):
            try:
                signal = float(line.split(":", 1)[1].strip().split()[0])
            except (IndexError, ValueError):
                signal = None
        elif line.startswith("SSID:"):
            ssid = line.split(":", 1)[1].strip()
        elif line.startswith("capability:") and "Privacy" in line:
            secured = True
        elif line.startswith("RSN:") or line.startswith("WPA:"):
            secured = True

        if ssid:
            existing = networks.get(ssid)
            if not existing or (signal is not None and signal > existing["signal"]):
                networks[ssid] = {"ssid": ssid, "signal": signal if signal is not None else -100, "secured": secured}

    return sorted(networks.values(), key=lambda n: n["signal"], reverse=True)


def scan_networks():
    """Live scan when it's safe to (no one connected to our AP); otherwise
    the list captured just before the AP came up."""
    global _last_scan
    if is_ap_active():
        return _last_scan
    _last_scan = _live_scan()
    return _last_scan


def start_ap():
    global _last_scan
    ssid = settings.WIFI_AP_SSID
    password = settings.WIFI_AP_PASSWORD
    if any(c in ssid + password for c in "\n\r"):
        raise ValueError("WIFI_AP_SSID/WIFI_AP_PASSWORD cannot contain newlines.")

    # Last chance to scan before hostapd claims the radio.
    _last_scan = _live_scan()

    r = subprocess.run(
        ["sudo", "-n", "/usr/local/bin/wifi-ap.sh", "start", ssid, password],
        capture_output=True, text=True,
    )
    return r.returncode == 0, (r.stdout.strip() or r.stderr.strip() or "Started setup AP.")


def stop_ap():
    r = subprocess.run(
        ["sudo", "-n", "/usr/local/bin/wifi-ap.sh", "stop"],
        capture_output=True, text=True,
    )
    return r.returncode == 0, (r.stdout.strip() or r.stderr.strip() or "Stopped setup AP.")


def _write_netplan_wifi(ssid, password):
    # Valid JSON is valid YAML flow syntax, so json.dumps() gives safe
    # escaping (quotes, unicode, special characters) with no YAML library.
    access_point = {ssid: ({"password": password} if password else {})}
    content = (
        "network:\n"
        "  version: 2\n"
        "  wifis:\n"
        "    wlan0:\n"
        "      dhcp4: true\n"
        f"      access-points: {json.dumps(access_point)}\n"
    )
    fd, path = tempfile.mkstemp(prefix="cloudupload-wifi-", suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


def _connect_worker(ssid, password, timeout):
    tmp_path = _write_netplan_wifi(ssid, password)
    try:
        r = subprocess.run(
            ["sudo", "-n", "/usr/local/bin/wifi-connect.sh", "apply", tmp_path],
            capture_output=True, text=True,
        )
    finally:
        os.remove(tmp_path)

    if r.returncode != 0:
        start_ap()
        with _lock:
            _state.update(phase="failed", message=r.stderr.strip() or "Failed to apply WiFi configuration.")
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _wlan0_connected():
            # So the device can be found at a fixed hostname afterward
            # instead of hunting for whatever IP this network handed out.
            subprocess.run(["sudo", "-n", "resolvectl", "mdns", "wlan0", "yes"],
                            capture_output=True, text=True)
            with _lock:
                _state.update(phase="connected", message=f"Connected to {ssid}.")
            return
        time.sleep(2)

    # Didn't come online in time — revert so the user isn't locked out.
    subprocess.run(["sudo", "-n", "/usr/local/bin/wifi-connect.sh", "revert"],
                    capture_output=True, text=True)
    start_ap()
    with _lock:
        _state.update(phase="failed",
                       message=f"Could not connect to {ssid} within {timeout}s. Reverted to setup AP.")


def start_connect(ssid, password, timeout=None):
    """Kick off a connection attempt in the background (this can take up to
    WIFI_CONNECT_TIMEOUT seconds — too long to block a request). Poll
    get_status() for the result."""
    with _lock:
        if _state["phase"] == "connecting":
            return False, "Already attempting a connection."
        _state.update(phase="connecting", message=f"Connecting to {ssid}…", ssid=ssid)

    timeout = timeout or settings.WIFI_CONNECT_TIMEOUT
    threading.Thread(target=_connect_worker, args=(ssid, password, timeout), daemon=True).start()
    return True, "Started."


def disconnect():
    subprocess.run(["sudo", "-n", "/usr/local/bin/wifi-connect.sh", "revert"],
                    capture_output=True, text=True)
