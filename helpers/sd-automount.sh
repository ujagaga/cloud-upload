#!/usr/bin/env bash
#
# Mounts/unmounts SD card partitions under /media so sdcard.py (SD_SCAN_PATHS)
# can find them. Invoked by udev on partition add/remove — see
# 99-sdcard-automount.rules. Usage: sd-automount.sh add|remove <devname>
# (devname is a kernel name like mmcblk0p1, passed via udev %k).

set -euo pipefail

ACTION="$1"
DEVNAME="$2"
DEVICE="/dev/$DEVNAME"

# MOUNT_USER is written by install.sh into this config file (the user the
# app's systemd service runs as), so mounted cards are readable/writable by it.
[ -f /etc/sd-automount.conf ] && source /etc/sd-automount.conf
MOUNT_USER="${MOUNT_USER:-root}"
UID_NUM="$(id -u "$MOUNT_USER")"
GID_NUM="$(id -g "$MOUNT_USER")"

LABEL="$(blkid -s LABEL -o value "$DEVICE" 2>/dev/null || true)"
MOUNT_POINT="/media/${LABEL:-$DEVNAME}"

case "$ACTION" in
  add)
    FSTYPE="$(blkid -s TYPE -o value "$DEVICE" 2>/dev/null || true)"
    mkdir -p "$MOUNT_POINT"
    # systemd-udevd's seccomp filter blocks the mount(2) syscall directly, so
    # RUN+= scripts must ask systemd itself to mount (via a transient unit)
    # instead of calling mount/umount.
    case "$FSTYPE" in
      vfat|exfat)
        systemd-mount --no-block -o "uid=${UID_NUM},gid=${GID_NUM},umask=000" "$DEVICE" "$MOUNT_POINT"
        ;;
      *)
        systemd-mount --no-block "$DEVICE" "$MOUNT_POINT"
        chown "${UID_NUM}:${GID_NUM}" "$MOUNT_POINT"
        ;;
    esac
    ;;
  remove)
    # A udev "remove" event (device physically pulled) often finds the mount
    # already gone — that's still success. Only a mountpoint that's still
    # actually mounted after the attempt counts as a real failure.
    if systemd-umount "$MOUNT_POINT" 2>/dev/null || ! mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
      rmdir "$MOUNT_POINT" 2>/dev/null || true
    else
      echo "Failed to unmount $MOUNT_POINT" >&2
      exit 1
    fi
    ;;
  *)
    echo "Usage: $0 add|remove <devname>" >&2
    exit 1
    ;;
esac
