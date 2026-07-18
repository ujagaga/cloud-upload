import os
import threading

import settings
import sdcard
import gdrive

_lock = threading.Lock()
_thread = None

# Files (path, size, mtime) already uploaded or confirmed-on-Drive during this
# process's lifetime. RAM only, by design: a restart is allowed to forget it
# and fall back to Drive's own skip check, but while the process is up this
# stops a still-inserted card from re-running (and clobbering the last
# summary) every time auto-upload retriggers.
_handled_files = set()


def _fingerprint(path):
    try:
        st = os.stat(path)
        return (path, st.st_size, st.st_mtime)
    except OSError:
        return (path, None, None)

_state = {
    "running": False,
    "total": 0,
    "done": 0,          # uploaded + skipped + failed
    "uploaded": 0,
    "skipped": 0,
    "deleted": 0,       # source files removed from card after confirmed upload
    "current": "",
    "folder": "",
    "transferred": [],  # names uploaded this run
    "errors": [],       # "filename: reason"
    "finished": False,
    "message": "",
}


def get_status():
    with _lock:
        status = dict(_state)
        status["errors"] = list(_state["errors"])
        status["transferred"] = list(_state["transferred"])
        status["remaining"] = _state["total"] - _state["done"]
        status["authorized"] = gdrive.is_authorized()
        return status


def _reset(total, folder, message=""):
    _state.update({
        "running": True,
        "total": total,
        "done": 0,
        "uploaded": 0,
        "skipped": 0,
        "deleted": 0,
        "current": "",
        "folder": folder,
        "transferred": [],
        "errors": [],
        "finished": False,
        "message": message,
    })


def _worker(images, folder_name, delete_after):
    try:
        service = gdrive.get_service()
        root_id = gdrive.ensure_folder(service, settings.DRIVE_FOLDER_NAME)
        folder_id = gdrive.ensure_folder(service, folder_name, parent_id=root_id)
        existing = gdrive.list_folder_files(service, folder_id)

        for src in images:
            name = os.path.basename(src)
            with _lock:
                _state["current"] = name

            confirmed = False  # file is safely on Drive -> eligible for deletion
            try:
                # Skip only when an identical file is already there.
                if name in existing and existing[name] and existing[name] == gdrive.file_md5(src):
                    with _lock:
                        _state["skipped"] += 1
                    confirmed = True
                else:
                    gdrive.upload_file(service, src, folder_id, name=name)
                    existing[name] = None  # avoid re-checking within this run
                    with _lock:
                        _state["uploaded"] += 1
                        _state["transferred"].append(name)
                    confirmed = True
            except Exception as exc:
                print(f"Failed uploading {src}: {exc}")
                with _lock:
                    _state["errors"].append(f"{name}: {exc}")
            finally:
                with _lock:
                    _state["done"] += 1

            if confirmed:
                with _lock:
                    _handled_files.add(_fingerprint(src))

            # Only remove from the card once the file is confirmed on Drive.
            if confirmed and delete_after:
                try:
                    os.remove(src)
                    with _lock:
                        _state["deleted"] += 1
                except OSError as exc:
                    print(f"Failed deleting {src}: {exc}")
                    with _lock:
                        _state["errors"].append(f"{name}: delete failed: {exc}")

        with _lock:
            deleted_note = f", {_state['deleted']} deleted" if delete_after else ""
            _state["message"] = (
                f"Done. {_state['uploaded']} uploaded, {_state['skipped']} skipped"
                f"{deleted_note}, {len(_state['errors'])} failed."
            )
    except Exception as exc:
        print(f"Upload aborted: {exc}")
        with _lock:
            _state["message"] = f"Aborted: {exc}"
    finally:
        with _lock:
            _state["running"] = False
            _state["current"] = ""
            _state["finished"] = True


def start(delete_after=False):
    """Scan the card and upload every image, skipping ones already in the folder.
    If delete_after, remove each source file once it is confirmed on Drive.
    Returns (ok, message)."""
    global _thread

    with _lock:
        if _state["running"]:
            return False, "Already running."

    if not gdrive.is_authorized():
        return False, "Google Drive not authorized. See authorize_drive.py."

    root, images = sdcard.find_card()
    if not images:
        return False, "No SD card with images found."

    with _lock:
        pending = [p for p in images if _fingerprint(p) not in _handled_files]
    if not pending:
        return False, "All images from this card were already uploaded this session."

    folder_name = sdcard.derive_folder_name(images)

    with _lock:
        _reset(len(pending), folder_name,
                message=f"Uploading {len(pending)} images from {root} to folder '{folder_name}'.")

    _thread = threading.Thread(target=_worker, args=(pending, folder_name, delete_after), daemon=True)
    _thread.start()
    return True, f"Started uploading {len(pending)} images to '{folder_name}'."
