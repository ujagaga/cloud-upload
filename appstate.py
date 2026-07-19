"""Runtime mode: active when Drive is reachable, otherwise idle.

On idle the SD card is unmounted so an unstable power supply can't corrupt its
file system while the device can do no useful work.
"""
import os
import shutil
import subprocess

import settings
import gdrive
import store
import sdcard

MODE_ACTIVE = "active"
MODE_IDLE = "idle"

_mode = MODE_IDLE
_reason = "Starting up…"


def get_mode():
    return _mode


def get_reason():
    return _reason


def is_active():
    return _mode == MODE_ACTIVE


def device_of(path):
    """Device backing the filesystem that path lives on. --target resolves
    any path within a mount (not just its exact mountpoint), since sdcard's
    scan root can be a parent directory one level above the real mount."""
    try:
        out = subprocess.run(
            ["findmnt", "--target", path, "-no", "SOURCE"],
            capture_output=True, text=True,
        )
        return out.stdout.strip() or None
    except FileNotFoundError:
        return None


def _mountpoint_of(path):
    """Real mountpoint that path lives on (may differ from sdcard's scan
    root, which can be a parent directory one level above the real mount)."""
    try:
        out = subprocess.run(
            ["findmnt", "--target", path, "-no", "TARGET"],
            capture_output=True, text=True,
        )
        return out.stdout.strip() or None
    except FileNotFoundError:
        return None


def unmount_sd(hint_path=None):
    """Flush and unmount the SD card if present. Returns (ok, message).

    hint_path (optional): a directory already known to be on the card, used
    when sdcard.find_card() can't locate it by scanning for images — e.g.
    right after a delete-after-upload run removed every file, leaving
    nothing to scan for even though the mount itself is still there."""
    if hint_path and os.path.isdir(hint_path):
        mountpoint = _mountpoint_of(hint_path) or hint_path
        dev = device_of(hint_path)
    else:
        root, images = sdcard.find_card()
        if not root:
            return True, "No SD card mounted."
        mountpoint = _mountpoint_of(images[0]) or root
        dev = device_of(images[0])

    subprocess.run(["sync"], check=False)
    devname = os.path.basename(dev) if dev else None

    # Tried in order: udisksctl (works unprivileged on a desktop session, but
    # isn't installed on a headless box like the Orange Pi); the same
    # sudoers-granted helper mount_sd() uses (works on a plain systemd
    # service, no desktop session); plain umount as a last resort.
    cmds = []
    if dev:
        cmds.append(["udisksctl", "unmount", "--no-user-interaction", "-b", dev])
    if devname:
        cmds.append(["sudo", "-n", "/usr/local/bin/sd-automount.sh", "remove", devname])
    cmds.append(["umount", mountpoint])

    for cmd in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                return True, f"Unmounted {mountpoint}."
        except FileNotFoundError:
            continue

    return False, f"Failed to unmount {mountpoint}."


def mount_sd(devname):
    """Mount an SD card partition by kernel name (e.g. mmcblk0p1) via the same
    helper the udev automount rule uses. Returns (ok, message). Needs the
    sudoers rule install.sh sets up for this exact command."""
    if not devname:
        return False, "No unmounted card detected."
    try:
        r = subprocess.run(
            ["sudo", "-n", "/usr/local/bin/sd-automount.sh", "add", devname],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return False, "Automount helper not installed. Run install.sh."

    if r.returncode == 0:
        return True, f"Mounted {devname}."
    return False, r.stderr.strip() or f"Failed to mount {devname}."


def persist_file_to_flash(src, dest_relpath, label):
    """Copy src onto the boot flash at dest_relpath so it survives a reboot
    in RAM-only mode. Remounts the flash read-write, copies, syncs, unmounts
    again. Returns (ok, msg). Needs root / a sudoers rule for mount+umount
    of FLASH_DEVICE."""
    if not settings.FLASH_DEVICE:
        return False, "Flash persist not configured (FLASH_DEVICE empty)."
    if not os.path.isfile(src):
        return False, f"No {label} to persist."

    mp = settings.FLASH_MOUNTPOINT
    dest = os.path.join(mp, dest_relpath)

    try:
        os.makedirs(mp, exist_ok=True)
        r = subprocess.run(["mount", "-o", "rw", settings.FLASH_DEVICE, mp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False, f"Could not mount flash: {r.stderr.strip()}"
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            subprocess.run(["sync"], check=False)
        finally:
            subprocess.run(["umount", mp], capture_output=True, text=True)
    except Exception as exc:
        return False, f"Flash persist failed: {exc}"

    return True, f"Saved {label} to flash."


def persist_token_to_flash():
    return persist_file_to_flash(gdrive.TOKEN_PATH, settings.FLASH_TOKEN_DEST, "token.json")


def _go_idle(reason):
    global _mode, _reason
    _mode = MODE_IDLE
    _reason = reason
    ok, msg = unmount_sd()
    print(f"IDLE: {reason} | {msg}")


def startup():
    """Decide the mode: load settings from Drive (active) or unmount and idle."""
    global _mode, _reason

    if not gdrive.is_authorized():
        _go_idle(f"No Google Drive credentials ({settings.TOKEN_FILE}).")
        return

    if not gdrive.check_access():
        _go_idle("No Google Drive access.")
        return

    try:
        store.load()
    except Exception as exc:
        _go_idle(f"Failed to load settings from Drive: {exc}")
        return

    _mode = MODE_ACTIVE
    _reason = ""
    print("ACTIVE: Drive reachable, settings loaded.")


def retry():
    """Re-attempt reaching Drive (e.g. after connectivity returns)."""
    startup()
    return _mode
