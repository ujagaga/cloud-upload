import os
from datetime import datetime

import settings


def _candidate_roots():
    """Yield likely mount points under the configured scan paths.

    Removable media typically mounts as /media/<label>, /media/<user>/<label>
    or /run/media/<user>/<label>, so we look one and two levels deep.
    """
    roots = []
    for base in settings.SD_SCAN_PATHS:
        if not os.path.isdir(base):
            continue
        for entry in os.scandir(base):
            if not entry.is_dir():
                continue
            roots.append(entry.path)
            # one level deeper (e.g. /media/<user>/<label>)
            try:
                for sub in os.scandir(entry.path):
                    if sub.is_dir():
                        roots.append(sub.path)
            except PermissionError:
                continue
    return roots


def list_images(root: str):
    exts = tuple(e.lower() for e in settings.IMAGE_EXTENSIONS)
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.lower().endswith(exts):
                found.append(os.path.join(dirpath, name))
    found.sort()
    return found


def find_card():
    """Return (root, image_paths) for the first mount that contains images,
    else (None, [])."""
    for root in _candidate_roots():
        images = list_images(root)
        if images:
            return root, images
    return None, []


def derive_folder_name(paths):
    """Deterministic per-card folder name from the earliest image date. Earliest
    date is the most stable anchor, so resuming (even after adding later shots)
    still maps to the same folder."""
    earliest = min(os.path.getmtime(p) for p in paths)
    return datetime.fromtimestamp(earliest).strftime(settings.FOLDER_DATE_FORMAT)
