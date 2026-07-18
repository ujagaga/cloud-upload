# Cloud Upload

A small self-hosted image uploader for photographers on the road. It runs on an
**Orange Pi Zero 3W**, reads image files from a plugged-in SD card, and uploads
them **as-is** (no conversion) to Google Drive. You control it from a phone over
Wi-Fi through a simple web page.

It is built for unstable travel conditions — flaky internet and unreliable power:

- The OS boots from a flash drive, which is then unmounted so the system runs
  **entirely in RAM**. Nothing is written to local storage.
- All durable state (your password, options) lives in Google Drive, not on the
  device. It is downloaded at startup and written back on every change.
- If Google Drive is not reachable, the app goes **idle** and unmounts the SD
  card so a power cut cannot corrupt its file system.

## How it works

1. On startup the app checks whether Google Drive is reachable.
   - **Reachable** → *active* mode; settings are loaded from Drive.
   - **Not reachable** → *idle* mode; the SD card is unmounted and the UI shows
     the reason plus a **Retry** button.
2. In active mode, insert an SD card and press **Upload all**. Every image on
   the card is uploaded to a per-card folder in Drive.
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
- **Delete after upload** (optional, off by default): when enabled, each file is
  removed from the SD card once it is confirmed on Drive. Files that fail to
  upload are never deleted.

### Access control

Single user, protected by a password.

- `INITIAL_PASSWORD` in `settings.py` is used until you set a password in the UI.
- The password you set is stored (hashed) in Drive, so it survives reboots.
- `MASTER_PASSWORD` in `settings.py` is a recovery override that always works,
  including in idle mode. It is never stored and never changes through the UI.

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
   download it as `client_secret.json` into `server/`.
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
3. Copy `client_secret.json` and `token.json` into `server/` on the device.

### 2. Configuration

```bash
cd server
cp settings.py.example settings.py
```

Edit `settings.py` and set at least:

- `INITIAL_PASSWORD`, `MASTER_PASSWORD`
- `APP_SECRET_KEY` (a long random string)
- `DRIVE_FOLDER_NAME` (the root Drive folder for uploads)
- `FLASH_DEVICE` / `FLASH_MOUNTPOINT` / `FLASH_TOKEN_DEST` — only needed if you
  authorize on-device (method A) and want the token saved to the boot flash
  automatically. Leave `FLASH_DEVICE` empty to instead download the token and
  copy it manually.

### 3. Install and run

```bash
cd server
./install.sh
```

This installs dependencies into a virtualenv and sets up a systemd service that
starts the server on boot. To run it by hand instead:

```bash
./run_server.sh          # gunicorn on port 8010
```

Then open `http://<device-ip>:8010` from your phone.

## Project layout

```
server/
  index.py            Flask app: routes, auth, mode gating
  appstate.py         active/idle mode, Drive reachability, SD unmount, flash persist
  store.py            durable settings, persisted to Drive as JSON
  gdrive.py           Google Drive: auth, folders, upload, dedup, JSON I/O
  deviceauth.py       on-device Google authorization (OAuth device flow)
  sdcard.py           detect the SD card, list images, derive folder name
  processor.py        background worker: scan → upload → (optional) delete
  helper.py           password verify/set
  authorize_drive.py  alternative one-time OAuth helper (run on a laptop)
  settings.py         configuration (not committed)
  templates/ static/  web UI
  install.sh          dependency install + systemd service
  run_server.sh       start gunicorn
  helpers/
    sd-automount.sh          mount an SD card partition under /media on insert
                             (uses systemd-mount, not raw mount — see below)
    99-sdcard-automount.rules  udev rule invoking sd-automount.sh on add/remove
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
  service).
- On startup the app makes a live Drive API call to decide active vs. idle; on a
  dead link it waits for the HTTP timeout before falling back to idle.
- The refresh token in `token.json` is read fresh at each boot. If Google ever
  rotates it, update `token.json` on the flash image.
