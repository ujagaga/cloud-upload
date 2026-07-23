"""Durable app state, persisted to a local JSON file.

The OS runs from RAM, so every save also copies the file onto the boot
flash (same mechanism as token.json/known_networks.json) to survive a
reboot.
"""
import json
import os

import settings

_script_dir = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(_script_dir, settings.SETTINGS_FILE)

DEFAULTS = {
    "password_hash": None,
    "delete_after_upload": False,
    "auto_upload": True,
    "notify_email": "",
    "smtp_server": "",
    "smtp_port": "",
    "smtp_user": "",
    "smtp_pass": "",
}

_data = dict(DEFAULTS)
_loaded = False


def is_loaded() -> bool:
    return _loaded


def load():
    """Load settings from the local file into memory, if present."""
    global _data, _loaded
    data = dict(DEFAULTS)
    if os.path.isfile(STORE_PATH):
        with open(STORE_PATH) as f:
            remote = json.load(f)
        if isinstance(remote, dict):
            data.update(remote)
    _data = data
    _loaded = True


def save():
    """Write the current settings to the local file and the boot flash."""
    with open(STORE_PATH, "w") as f:
        json.dump(_data, f)

    # Same reason token.json needs this: the OS runs from RAM, so anything
    # written at runtime needs a copy on the boot flash to survive a reboot.
    import appstate
    ok, msg = appstate.persist_file_to_flash(STORE_PATH, settings.FLASH_SETTINGS_DEST, "settings")
    print(f"Flash persist: {msg}")


def get(key, default=None):
    return _data.get(key, default)


def set(key, value):
    """Update a value in memory and persist to the local file."""
    _data[key] = value
    save()
