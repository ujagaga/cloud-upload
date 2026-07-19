"""Small SSD1306 128x64 I2C OLED status display.

Wired to the 26-pin header's I2C3 label (PH4/PH5), enabled via the
`i2c3-ph` device tree overlay (see README) — shows up as /dev/i2c-2.
Purely a convenience readout: the app works fine with no display attached,
so every call here fails silently rather than raising.
"""
try:
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import sh1106
except ImportError:
    i2c = canvas = sh1106 = None

I2C_PORT = 2
I2C_ADDRESS = 0x3C
LINE_HEIGHT = 12

_device = None


def _get_device():
    global _device
    if _device is None:
        serial = i2c(port=I2C_PORT, address=I2C_ADDRESS)
        _device = sh1106(serial)
    return _device


def show_lines(*lines):
    """Render up to a handful of short text lines, one per row. A no-op if
    luma.oled isn't installed or the display isn't actually wired up —
    this is a convenience readout, never a hard dependency."""
    if sh1106 is None:
        return
    try:
        device = _get_device()
        with canvas(device) as draw:
            y = 0
            for line in lines:
                draw.text((0, y), line, fill="white")
                y += LINE_HEIGHT
    except Exception as exc:
        print(f"LCD update failed: {exc}")


def show_ap_screen(ssid, password, ip):
    show_lines("Setup WiFi:", f"SSID: {ssid}", f"Pass: {password}", f"IP: {ip}")


def show_station_screen(ip, drive_ok, drive_reason=""):
    drive_line = "Drive: connected" if drive_ok else f"Drive: {drive_reason or 'idle'}"
    show_lines("WiFi connected", f"IP: {ip}", drive_line)
