"""On-device Google authorization via the OAuth 2.0 device flow (RFC 8628).

The phone visits a Google URL and enters a short code; this device polls Google,
receives the refresh token, writes token.json, persists it to the boot flash, and
switches the app to active. No redirect URI, no browser on the device.

Requires a "TVs and Limited Input devices" OAuth client (CLIENT_SECRETS_FILE).
"""
import os
import json
import time
import threading

import requests

import settings
import gdrive
import appstate

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

_script_dir = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_PATH = os.path.join(_script_dir, settings.CLIENT_SECRETS_FILE)

_lock = threading.Lock()
_thread = None

# status: idle | pending | success | denied | expired | error
_state = {
    "status": "idle",
    "user_code": "",
    "verification_url": "",
    "message": "",
}


def get_status():
    with _lock:
        return dict(_state)


def _client_creds():
    with open(CLIENT_SECRETS_PATH) as f:
        data = json.load(f)
    node = data.get("installed") or data.get("web") or data
    return node["client_id"], node["client_secret"]


def _write_token(access_token, refresh_token, client_id, client_secret):
    # authorized_user format that Credentials.from_authorized_user_file expects.
    data = {
        "token": access_token,
        "refresh_token": refresh_token,
        "token_uri": TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": gdrive.SCOPES,
    }
    with open(gdrive.TOKEN_PATH, "w") as f:
        json.dump(data, f)


def _poll(device_code, interval, deadline, client_id, client_secret):
    while time.time() < deadline:
        time.sleep(interval)
        try:
            r = requests.post(TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": device_code,
                "grant_type": GRANT_TYPE,
            }, timeout=30)
            body = r.json()
        except Exception as exc:
            print(f"Device poll error: {exc}")
            continue

        if r.status_code == 200:
            _write_token(body["access_token"], body["refresh_token"], client_id, client_secret)
            ok, msg = appstate.persist_token_to_flash()
            appstate.retry()
            with _lock:
                _state["status"] = "success"
                _state["message"] = msg if ok else f"Authorized. {msg} Save token.json manually."
            return

        err = body.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err == "access_denied":
            with _lock:
                _state["status"] = "denied"
                _state["message"] = "Access was denied."
            return
        # expired_token or anything else
        with _lock:
            _state["status"] = "error" if err != "expired_token" else "expired"
            _state["message"] = body.get("error_description", err or "Unknown error")
        return

    with _lock:
        _state["status"] = "expired"
        _state["message"] = "Code expired. Start again."


def start():
    """Request a device code and begin polling. Returns (ok, message)."""
    global _thread

    with _lock:
        if _state["status"] == "pending":
            return True, "Authorization already in progress."

    if not os.path.isfile(CLIENT_SECRETS_PATH):
        return False, f"Missing {settings.CLIENT_SECRETS_FILE}."

    try:
        client_id, client_secret = _client_creds()
        r = requests.post(DEVICE_CODE_URL, data={
            "client_id": client_id,
            "scope": " ".join(gdrive.SCOPES),
        }, timeout=30)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:
        return False, f"Could not start authorization: {exc}"

    interval = int(d.get("interval", 5))
    deadline = time.time() + int(d.get("expires_in", 1800))
    # Google returns verification_url; some responses use verification_uri.
    url = d.get("verification_url") or d.get("verification_uri")

    with _lock:
        _state.update({
            "status": "pending",
            "user_code": d["user_code"],
            "verification_url": url,
            "message": "",
        })

    _thread = threading.Thread(
        target=_poll,
        args=(d["device_code"], interval, deadline, client_id, client_secret),
        daemon=True,
    )
    _thread.start()
    return True, "Authorization started."
