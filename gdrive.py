import os
import hashlib
import mimetypes

import settings
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_script_dir = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(_script_dir, settings.TOKEN_FILE)


def is_authorized() -> bool:
    return os.path.isfile(TOKEN_PATH)


def _load_credentials():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds


def get_service():
    if not is_authorized():
        raise RuntimeError(f"Not authorized. Run authorize_drive.py and copy {settings.TOKEN_FILE} here.")
    creds = _load_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_account_email():
    """Return the linked Drive account's email, or None if unavailable."""
    try:
        service = get_service()
        about = service.about().get(fields="user").execute()
        return about.get("user", {}).get("emailAddress")
    except Exception as exc:
        print(f"Could not fetch Drive account info: {exc}")
        return None


def check_access() -> bool:
    """True if Drive is reachable and usable (creds valid, API responds)."""
    try:
        service = get_service()
        service.files().list(pageSize=1, fields="files(id)").execute()
        return True
    except Exception as exc:
        print(f"Drive access check failed: {exc}")
        return False


def _escape(name: str) -> str:
    return name.replace("\\", "\\\\").replace("'", "\\'")


def ensure_folder(service, name: str, parent_id: str = None) -> str:
    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{_escape(name)}' and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    resp = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]

    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def list_folder_files(service, folder_id: str) -> dict:
    """Return {filename: md5Checksum} for non-folder files already in the folder.
    Used to skip images that were already uploaded successfully."""
    result = {}
    page_token = None
    query = f"'{folder_id}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder'"
    while True:
        resp = service.files().list(
            q=query, spaces="drive",
            fields="nextPageToken, files(name, md5Checksum)",
            pageSize=1000, pageToken=page_token,
        ).execute()
        for f in resp.get("files", []):
            result[f["name"]] = f.get("md5Checksum")
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return result


def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_file(service, filepath: str, folder_id: str, name: str = None) -> str:
    name = name or os.path.basename(filepath)
    mime = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
    meta = {"name": name, "parents": [folder_id]}
    media = MediaFileUpload(filepath, mimetype=mime, resumable=True)
    created = service.files().create(body=meta, media_body=media, fields="id").execute()
    return created["id"]
