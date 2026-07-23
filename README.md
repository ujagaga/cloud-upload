# Cloud Upload

A small self-hosted image uploader for photographers on the road. It runs on an
**Orange Pi Zero 3W**, reads image files from a plugged-in SD card, and uploads
them **as-is** (no conversion) to Google Drive. You control it from a phone over
Wi-Fi through a simple web page.

It is built for unstable travel conditions — flaky internet and unreliable power:

- The OS boots from a flash drive, which is then unmounted so the system runs
  **entirely in RAM**. Nothing is written to local storage.
- All durable state (your password, options, `token.json`, known WiFi
  networks) is saved locally and copied back onto the boot flash on every
  change, so it survives a reboot even though the OS runs from RAM.
- If Google Drive is not reachable, the app goes **idle** and unmounts the SD
  card so a power cut cannot corrupt its file system.

## How it works

1. On startup the app loads its local settings, then checks whether Google
   Drive is reachable.
   - **Reachable** → *active* mode.
   - **Not reachable** → *idle* mode; the SD card is unmounted and the UI shows
     the reason plus a **Retry** button.
2. In active mode, insert an SD card and press **Upload all** — or turn on
   **auto-upload** in Config to start automatically as soon as a card with
   images is detected, no button press needed.
3. Files already uploaded are detected and skipped, so an interrupted upload can
   be resumed safely (even the next day).

### Uploads

- Files are uploaded unchanged (raw camera formats, JPEG, TIFF, HEIC, …). The
  accepted extensions are configurable in `settings.py` (`IMAGE_EXTENSIONS`).
- **Per-card folder:** images go to a subfolder named after the earliest photo
  date on the card (`YYYY-MM-DD`), nested under a root Drive folder. The earliest
  date is a stable anchor, so resuming an upload always lands in the same folder.
- **Skip already-uploaded:** the app lists the target folder on Drive and skips a
  file when both its name and MD5 checksum already match. The source of truth is
  Drive itself, so this works with no local state across reboots.
- **Auto-upload** (Config page, on by default): starts a run automatically the
  moment a card with images is detected, and hides the **Upload all** button
  while it's on. The app also remembers (in memory only, for as long as the
  process keeps running) which files it already handled this session, so a
  still-inserted card doesn't repeatedly restart a finished run — e.g. after
  navigating between pages. That memory is intentionally lost on a restart;
  Drive's own skip check is the permanent source of truth.
- **Delete after upload** (Config page, off by default): when enabled, each
  file is removed from the SD card once it is confirmed on Drive. Files that
  fail to upload are never deleted. Once a run finishes with this on, the app
  also unmounts the card, same as it does in idle mode, so an unexpected power
  cut afterward can't corrupt its file system.
- **Email notifications** (Config page, off by default): when
  **Automatically send email when upload is finished** is on, a summary
  email (files uploaded/skipped/deleted/failed) is sent once a run finishes,
  to the email address the linked Google Drive account is bound to. Uses the
  `SMTP_SERVER` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` settings in
  `settings.py`; a failed send is logged but never interrupts the upload.

### Access control

Single user, protected by a password.

- `INITIAL_PASSWORD` in `settings.py` is used until you set a password in the UI.
- The password you set is stored (hashed) locally, so it survives reboots.
- `MASTER_PASSWORD` in `settings.py` is a recovery override that always works,
  including in idle mode. It is never stored and never changes through the UI.

### Config page

Reached via the gear icon on the home page:

- **Google Drive account** — shows the linked account's email, with a button
  to disconnect it (deletes `token.json` and sends you to the authorize page
  to link a different account).
- **WiFi** — link to the WiFi setup page below.
- **Upload options** — the auto-upload and delete-after-upload toggles above,
  plus **Automatically send email when upload is finished** (see Email
  notifications below).
- **Change password** — with a show/hide button on each field.

### WiFi setup

The device needs *some* network to be reachable at all, but on-site it may
have no known WiFi and no Ethernet. `/wifi` (linked from Config, and reachable
directly if the device is offline — see below) handles getting it online:

1. **No internet at all** (checked separately from Drive reachability, every
   30 seconds): the device starts its own access point (`WIFI_AP_SSID`/
   `WIFI_AP_PASSWORD` in `settings.py`) so you can connect a phone to it
   directly and reach `/wifi` at `192.168.4.1`.
2. The page shows nearby networks (captured in one scan right before the AP
   started — see the note on scanning below) and a form to enter a network's
   name/password manually if it's not listed or the list is stale.
3. Submitting a network switches `wlan0` to station mode and tries it for up
   to `WIFI_CONNECT_TIMEOUT` seconds (default 30). On success it's saved to
   `known_networks.json` for next time. On failure/timeout, the device
   **reverts to its own access point automatically** — a wrong password or a
   network that goes out of range can't strand you without another way in.
4. Once connected, previously-seen networks are tried again automatically
   the next time the device has no internet (`known_networks.json`, ordered
   by most-recently-used first) — no need to redo setup every time it moves
   between the same locations.

**Hardware note:** this radio can only run in *one* mode at a time — either
the setup access point or a station (client) connection, never both
(`iw list`'s interface combinations cap `{managed, AP}` at 1 total). So
connecting to a chosen network always drops the setup AP, and scanning while
a phone is connected to that AP isn't possible without disconnecting it —
which is why the network list is captured once, just before the AP comes up,
rather than refreshed live while you're connected to it.

`wlan0` is controlled directly (a dedicated `wpa_supplicant` instance +
`dhcpcd`), not through Netplan — deliberately, since Netplan's `apply`
reconfigures every managed interface it knows about, not just the one that
changed, and repeatedly caused full-device lockups when used to toggle this
radio. Ethernet is unaffected either way; its Netplan config only ever
matches `"e*"` interfaces and none of the WiFi tooling touches it.

Once connected, the device also enables mDNS on `wlan0`, so you can reach it
at `<hostname>.local` instead of hunting for whatever IP the network handed
out (`hostnamectl hostname` shows the device's hostname).

### LCD status display

Optional: a small I2C OLED (128x64, SH1106 controller) wired to the 26-pin
header's I2C3 label (PH4/PH5), enabled via the `i2c3-ph` device tree overlay.
Purely a convenience readout — the app works fine with no display attached.

- **Setup AP active:** the AP's SSID, password, and IP.
- **WiFi/Ethernet connected:** the device's IP (in a larger font — the
  default is hard to read at this size) and Google Drive's connection status.
- **Upload in progress:** `<done>/<total> in <N>min`, updated after every
  file, plus a bytes-uploaded percentage as the bottom row. That percentage
  stays on screen — as the bottom row — even after the display moves on to
  the next WiFi/Ethernet/AP screen, until the next upload updates it.

`install.sh` installs `i2c-tools` (for the `i2c` group new devices are
granted) and `fonts-dejavu-core` (for a crisper IP-address font), and adds
`overlays=i2c3-ph` to `/boot/armbianEnv.txt` if it isn't there yet — **a
reboot is required** the first time before `/dev/i2c-2` exists.

### Shutdown button

The home page's power icon (confirmation required) stops any in-progress
upload, unmounts the SD card, and powers the device off — the safe way to
pull power on a device that otherwise runs from RAM with no shutdown
sequence of its own.

## Setup

### 1. Google Drive access

Uploads use the `drive.file` scope (per-file access — no Google verification
required). In the [Google Cloud console](https://console.cloud.google.com/):
enable the **Google Drive API**, configure the **OAuth consent screen** and
**publish the app** to *In production* (so the refresh token does not expire).

There are two ways to obtain the `token.json` credential.

**A. On-device, from your phone (recommended).** Uses the OAuth *device flow* —
no browser or cable needed on the device.

1. Create an **OAuth client ID** of type **TVs and Limited Input devices** and
   download it as `client_secret.json` into the app directory.
2. Open the app, go to **Authorize Google Drive**, press **Start**. It shows a
   short code and a link.
3. On your phone, open the link, sign in, and enter the code. The device picks up
   the token automatically and switches to active.

If `FLASH_DEVICE` is configured (see below), the new `token.json` is written back
to the boot flash so it survives a reboot; otherwise the page offers it as a
download to copy onto the flash yourself.

**B. On a laptop (alternative).** Uses a loopback browser flow.

1. Create an **OAuth client ID** of type **Desktop app**, download as
   `client_secret.json`.
2. On any machine with a browser:
   ```bash
   pip install google-auth-oauthlib
   python3 authorize_drive.py
   ```
   Grant access. This writes `token.json`.
3. Copy `client_secret.json` and `token.json` into the app directory on the device.

### 2. Configuration

```bash
cp settings.py.example settings.py
```

Edit `settings.py` and set at least:

- `INITIAL_PASSWORD`, `MASTER_PASSWORD`
- `APP_SECRET_KEY` (a long random string)
- `DRIVE_FOLDER_NAME` (the root Drive folder for uploads)
- `FLASH_DEVICE` / `FLASH_MOUNTPOINT` / `FLASH_TOKEN_DEST` /
  `FLASH_KNOWN_NETWORKS_DEST` / `FLASH_SETTINGS_DEST` — needed so `token.json`,
  `known_networks.json`, and the local settings file survive a reboot once the
  OS runs from RAM; each is copied back to the boot flash on every change.
  Leave `FLASH_DEVICE` empty to instead download `token.json` manually (none
  of these will survive a reboot in that case).
- `WIFI_AP_SSID` / `WIFI_AP_PASSWORD` — the setup access point's own name/
  password (see WiFi setup above). Defaults work fine; change the password
  from the default if the device will be used somewhere with strangers in
  range.
- `SMTP_SERVER` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` — only needed if you
  turn on the "Automatically send email when upload is finished" option.

### 3. Install and run

```bash
./install.sh
```

This installs dependencies into a virtualenv and sets up a systemd service that
starts the server on boot. To run it by hand instead:

```bash
./run_server.sh          # gunicorn on port 80
```

Then open `http://<device-ip>` from your phone. Port 80 needs
`CAP_NET_BIND_SERVICE`; `install.sh`'s systemd unit grants it via
`AmbientCapabilities` so the service doesn't need to run as root.

## Project layout

```
index.py            Flask app: routes, auth, mode gating
appstate.py         active/idle mode, Drive reachability, SD mount/unmount, flash persist
store.py            durable settings, persisted to a local file + boot flash
gdrive.py           Google Drive: auth, account info, folders, upload, dedup
deviceauth.py       on-device Google authorization (OAuth device flow)
sdcard.py           detect the SD card (mounted and unmounted), list images, derive folder name
processor.py        background worker: scan → upload → (optional) delete → (optional) unmount
helper.py           password verify/set
notify.py           email notification to the Drive account's address when an upload finishes
lcd.py              optional I2C OLED status display (WiFi/Ethernet/AP/upload-progress screens)
authorize_drive.py  alternative one-time OAuth helper (run on a laptop)
wifi.py             WiFi setup AP, scan, connect/disconnect, known-network auto-reconnect
settings.py         configuration (not committed)
templates/ static/  web UI (home, config, authorize, sign-in, WiFi setup pages)
install.sh          dependency install + systemd service + SD automount + WiFi + LCD + sudoers rules
run_server.sh       start gunicorn
known_networks.json      known WiFi networks (priority-ordered, most recent first) — runtime, not committed
image_uploader_settings.json  durable settings (see store.py) — runtime, not committed
helpers/
  sd-automount.sh            mount an SD card partition under /media on insert or on
                             demand (uses systemd-mount, not raw mount — see below)
  99-sdcard-automount.rules  udev rule invoking sd-automount.sh on add/remove
  wifi-ap.sh                 start/stop the WiFi setup access point (hostapd + dnsmasq)
  wifi-sta.sh                start/stop wlan0 station mode (dedicated wpa_supplicant + dhcpcd)
  wifi-scan.sh               scan for nearby WiFi networks
  flash-persist.sh           copy a file onto the boot flash (token.json, known_networks.json, settings)
```

## Notes and limitations

- Runs as a **single** gunicorn worker (`-w 1`); the active/idle state and
  upload progress live in one process.
- Unmounting the SD card uses `udisksctl` (falls back to `umount`). This works
  without root for auto-mounted removable media; other mount setups may need a
  sudoers rule.
- **SD card automount:** `install.sh` installs `helpers/sd-automount.sh` to
  `/usr/local/bin` and `helpers/99-sdcard-automount.rules` to
  `/etc/udev/rules.d`, so inserting an SD card mounts it under
  `/media/<label-or-devname>` (matching `sdcard.py`'s `SD_SCAN_PATHS`) even on
  a headless box with no desktop session. It mounts via `systemd-mount` rather
  than the plain `mount` command — `systemd-udevd`'s seccomp filter blocks the
  `mount(2)` syscall for scripts it runs directly, so a raw `mount` call fails
  silently. The mount owner/group is read from `/etc/sd-automount.conf`
  (`MOUNT_USER=...`, written by `install.sh` with the user running the
  service). The udev rule matches any `sd[a-z][0-9]` device — on boards where
  the root filesystem is itself `/dev/sda1`, that also mounts the root disk a
  second time under `/media`; `sdcard.py` explicitly excludes whatever device
  backs `/` from scanning, so it's never mistaken for a card.
- **Manual mount button:** the home page shows the SD card's mount status
  (device name included) and, if a card is plugged in but not mounted, a
  **Mount** button that calls the same `sd-automount.sh` helper as the udev
  rule. This needs `install.sh`'s narrowly-scoped `NOPASSWD` sudoers rule
  (`/etc/sudoers.d/sd-automount`, one exact command only) so the app's own
  service user can run it as root; re-run `install.sh` after upgrading if the
  button doesn't work.
- On startup the app makes a live Drive API call to decide active vs. idle; on a
  dead link it waits for the HTTP timeout before falling back to idle.
- The refresh token in `token.json` is read fresh at each boot. If Google ever
  rotates it, update `token.json` on the flash image.
- **WiFi is checked separately from Drive.** A background loop checks general
  internet reachability (any interface) every 30 seconds and only steps in —
  trying known networks, then falling back to the setup AP — when there's
  none at all. So on a device that also has working Ethernet, the WiFi
  fallback/auto-reconnect logic never triggers, by design; it only matters
  when WiFi is the sole way online.
- All of the WiFi scripts (`wifi-ap.sh`, `wifi-sta.sh`, `wifi-scan.sh`) and
  `flash-persist.sh` need `install.sh`'s narrowly-scoped `NOPASSWD` sudoers
  rules (`/etc/sudoers.d/cloud-upload-wifi`, `/etc/sudoers.d/flash-persist`)
  to run as root from the app's unprivileged service user — same pattern as
  the SD automount button. Re-run `install.sh` after upgrading if WiFi setup
  or flash persistence stop working.
- `install.sh` masks the system `wpa_supplicant.service` (previously driven by
  Netplan) and removes any leftover `/etc/netplan/90-cloud-upload-wifi.yaml`
  from an older install, since the app now runs its own dedicated
  `wpa_supplicant` instance for `wlan0` instead.
- The systemd unit starts `After=network.target`, not
  `network-online.target` — the latter waits for full connectivity, which
  can stall boot for minutes on Ethernet with no cable plugged in. The app
  handles having no network at boot on its own (idle mode, WiFi setup AP).
- **Boot media matters.** If the OS boots from a USB flash drive, prefer a
  plain USB2.0 drive. Some USB3.2 drives fail the USB2.0 high-speed ("chirp")
  handshake on this board's controller and fall back to full-speed
  (12 Mb/s instead of 480 Mb/s), which can add tens of seconds to every boot
  loading the kernel/initrd. Check actual link speed at the U-Boot prompt with
  `usb tree`.
