#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pip install flask flask-wtf google-api-python-client google-auth google-auth-oauthlib gunicorn requests
"""

import os
import sys
from functools import wraps

from flask import (Flask, render_template, request, flash, redirect, session,
                   make_response, jsonify, url_for, send_file)
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

import settings
import helper
import store
import appstate
import gdrive
import deviceauth
import sdcard
import processor

sys.path.insert(0, os.path.dirname(__file__))
current_path = os.path.dirname(os.path.realpath(__file__))

application = Flask(__name__, static_url_path='/static', static_folder='static')
application.wsgi_app = ProxyFix(application.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
application.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_NAME=settings.APP_NAME,
    SECRET_KEY=settings.APP_SECRET_KEY,
    WTF_CSRF_SECRET_KEY=settings.APP_SECRET_KEY,
    WTF_CSRF_SSL_STRICT=False,          # LAN device served over plain HTTP
    PERMANENT_SESSION_LIFETIME=settings.MAX_COOKIE_AGE,
)
csrf = CSRFProtect(application)


# ---------------------- Auth ----------------------
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get('authed'):
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapper


@application.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if helper.verify_password(password):
            session.permanent = True
            session['authed'] = True
            return redirect(url_for('index'))
        flash("Wrong password.")
        return redirect(url_for('login'))

    if session.get('authed'):
        return redirect(url_for('index'))

    return render_template('signin.html', title=settings.APP_TITLE)


@application.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@application.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current = request.form.get('current_password', '')
    new = request.form.get('new_password', '')

    if not new:
        flash("New password cannot be empty.")
        return redirect(url_for('index'))

    if not appstate.is_active():
        flash("Cannot save: Google Drive not reachable.")
        return redirect(url_for('index'))

    if not helper.verify_password(current):
        flash("Current password is wrong.")
        return redirect(url_for('index'))

    try:
        helper.set_password(new)
        flash("Password changed.")
    except Exception as exc:
        flash(f"Could not save password to Drive: {exc}")
    return redirect(url_for('index'))


# ---------------------- Main UI ----------------------
@application.route('/', methods=['GET'])
@login_required
def index():
    resp = make_response(render_template(
        'home.html',
        title=settings.APP_TITLE,
        mode=appstate.get_mode(),
        idle_reason=appstate.get_reason(),
        drive_authorized=gdrive.is_authorized(),
        drive_folder=settings.DRIVE_FOLDER_NAME,
        delete_after=bool(store.get('delete_after_upload')),
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@application.route('/scan', methods=['GET'])
@login_required
def scan():
    if not appstate.is_active():
        return jsonify({"found": False, "root": None, "count": 0, "idle": True})
    root, images = sdcard.find_card()
    return jsonify({"found": bool(images), "root": root, "count": len(images)})


@application.route('/settings', methods=['POST'])
@login_required
def save_settings():
    if not appstate.is_active():
        flash("Cannot save: Google Drive not reachable.")
        return redirect(url_for('index'))
    try:
        store.set('delete_after_upload', bool(request.form.get('delete_after_upload')))
        flash("Settings saved.")
    except Exception as exc:
        flash(f"Could not save settings to Drive: {exc}")
    return redirect(url_for('index'))


@application.route('/start', methods=['POST'])
@login_required
def start():
    if not appstate.is_active():
        flash("Idle: Google Drive not reachable.")
        return redirect(url_for('index'))
    ok, message = processor.start(bool(store.get('delete_after_upload')))
    flash(message)
    return redirect(url_for('index'))


@application.route('/retry', methods=['POST'])
@login_required
def retry():
    mode = appstate.retry()
    flash("Google Drive reachable." if mode == appstate.MODE_ACTIVE else appstate.get_reason())
    return redirect(url_for('index'))


# ---------------------- On-device Google authorization ----------------------
@application.route('/authorize', methods=['GET'])
@login_required
def authorize():
    return render_template(
        'authorize.html',
        title=settings.APP_TITLE,
        authorized=gdrive.is_authorized(),
        flash_configured=bool(settings.FLASH_DEVICE),
    )


@application.route('/authorize/start', methods=['POST'])
@login_required
def authorize_start():
    ok, message = deviceauth.start()
    return jsonify({"ok": ok, "message": message, **deviceauth.get_status()})


@application.route('/authorize/status', methods=['GET'])
@login_required
def authorize_status():
    return jsonify(deviceauth.get_status())


@application.route('/authorize/token', methods=['GET'])
@login_required
def authorize_token():
    if not gdrive.is_authorized():
        return "No token yet.", 404
    return send_file(gdrive.TOKEN_PATH, as_attachment=True, download_name='token.json')


@application.route('/status', methods=['GET'])
@login_required
def status():
    return jsonify(processor.get_status())


# Decide active/idle at worker startup (single gunicorn worker holds this state).
appstate.startup()


if __name__ == "__main__":
    application.run(debug=True, use_reloader=True, port=8000)
