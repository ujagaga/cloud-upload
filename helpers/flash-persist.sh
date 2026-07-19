#!/usr/bin/env bash
#
# Copies a file onto the boot flash so it survives a reboot in RAM-only
# mode. Mounts the flash device read-write, copies, syncs, unmounts again.
#
# Usage: flash-persist.sh <flash_device> <mountpoint> <src_abspath> <dest_relpath>

set -euo pipefail

DEVICE="$1"
MOUNTPOINT="$2"
SRC="$3"
DEST_RELPATH="$4"

mkdir -p "$MOUNTPOINT"
mount -o rw "$DEVICE" "$MOUNTPOINT"
trap 'umount "$MOUNTPOINT" 2>/dev/null || true' EXIT

DEST="$MOUNTPOINT/$DEST_RELPATH"
mkdir -p "$(dirname "$DEST")"
cp "$SRC" "$DEST"
sync
