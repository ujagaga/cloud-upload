#!/usr/bin/env python3
"""
One-time Google Drive authorization.

Run this on ANY machine that has a web browser (e.g. your laptop):

    pip install google-auth-oauthlib
    python3 authorize_drive.py

It opens a browser, you grant access, and it writes token.json next to this
script. Copy that token.json to the Orange Pi (same folder as index.py).

Requires a Desktop-app OAuth client (client_secret.json) from the Google Cloud
console. No public HTTPS endpoint is needed: consent uses a localhost redirect.
"""
import os
import settings
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_script_dir = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_PATH = os.path.join(_script_dir, settings.CLIENT_SECRETS_FILE)
TOKEN_PATH = os.path.join(_script_dir, settings.TOKEN_FILE)


def main():
    if not os.path.isfile(CLIENT_SECRETS_PATH):
        raise SystemExit(f"Missing {settings.CLIENT_SECRETS_FILE}. Download a Desktop-app OAuth client first.")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    print(f"Saved {TOKEN_PATH}")
    print("Copy this file to the Pi (same folder as index.py).")


if __name__ == "__main__":
    main()
