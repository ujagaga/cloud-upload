"""Durable app state, persisted to Google Drive as a single JSON file.

The OS runs stateless in RAM, so Drive is the only place settings survive a
reboot. Loaded once at startup; every change is written straight back to Drive.
"""
import settings
import gdrive

DEFAULTS = {
    "password_hash": None,
    "delete_after_upload": False,
    "auto_upload": True,
}

_data = dict(DEFAULTS)
_loaded = False


def is_loaded() -> bool:
    return _loaded


def load():
    """Download settings from Drive into memory. Raises on Drive failure."""
    global _data, _loaded
    service = gdrive.get_service()
    root_id = gdrive.ensure_folder(service, settings.DRIVE_FOLDER_NAME)
    remote = gdrive.read_json(service, settings.SETTINGS_FILE, root_id)

    data = dict(DEFAULTS)
    if isinstance(remote, dict):
        data.update(remote)
    _data = data
    _loaded = True


def save():
    """Upload the current settings to Drive. Raises on Drive failure."""
    service = gdrive.get_service()
    root_id = gdrive.ensure_folder(service, settings.DRIVE_FOLDER_NAME)
    gdrive.write_json(service, settings.SETTINGS_FILE, root_id, _data)


def get(key, default=None):
    return _data.get(key, default)


def set(key, value):
    """Update a value in memory and persist to Drive."""
    _data[key] = value
    save()
