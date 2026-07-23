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
    from PIL import ImageFont
except ImportError:
    i2c = canvas = sh1106 = ImageFont = None

I2C_PORT = 2
I2C_ADDRESS = 0x3C
LINE_HEIGHT = 12
BIG_LINE_HEIGHT = 16

_device = None
_big_font = None


def _get_device():
    global _device
    if _device is None:
        serial = i2c(port=I2C_PORT, address=I2C_ADDRESS)
        _device = sh1106(serial)
    return _device


BIG_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def _get_big_font():
    global _big_font
    if _big_font is None:
        try:
            _big_font = ImageFont.truetype(BIG_FONT_PATH, 13)
        except OSError:
            _big_font = ImageFont.load_default(size=13)
    return _big_font


def show_lines(*lines):
    """Render up to a handful of short text lines, one per row. A line is
    either a str (default small font) or a (text, "big") tuple for a larger
    font — used for the IP address, which is hard to read at the default
    size. A no-op if luma.oled isn't installed or the display isn't
    actually wired up — this is a convenience readout, never a hard
    dependency."""
    if sh1106 is None:
        return
    try:
        device = _get_device()
        with canvas(device) as draw:
            y = 0
            for line in lines:
                if isinstance(line, tuple):
                    draw.text((0, y), line[0], fill="white", font=_get_big_font())
                    y += BIG_LINE_HEIGHT
                else:
                    draw.text((0, y), line, fill="white")
                    y += LINE_HEIGHT
    except Exception as exc:
        print(f"LCD update failed: {exc}")


def _drive_line(drive_ok, drive_reason):
    return "GDrive: connected" if drive_ok else f"GDrive: {drive_reason or 'idle'}"


def show_ap_screen(ssid, password, ip):
    show_lines("Setup WiFi:", f"SSID: {ssid}", f"Pass: {password}", (ip, "big"))


def show_station_screen(ip, drive_ok, drive_reason=""):
    show_lines("WiFi connected", (ip, "big"), _drive_line(drive_ok, drive_reason))


def show_ethernet_screen(ip, drive_ok, drive_reason=""):
    show_lines("Ethernet connected", (ip, "big"), _drive_line(drive_ok, drive_reason))
