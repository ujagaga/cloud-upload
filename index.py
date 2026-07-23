#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pip install flask flask-wtf google-api-python-client google-auth google-auth-oauthlib gunicorn requests
"""

import os
import sys
import threading
import time
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
import wifi

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
        return redirect(url_for('config'))

    if not helper.verify_password(current):
        flash("Current password is wrong.")
        return redirect(url_for('config'))

    try:
        helper.set_password(new)
        flash("Password changed.")
    except Exception as exc:
        flash(f"Could not save password: {exc}")
    return redirect(url_for('config'))


@application.route('/config', methods=['GET'])
@login_required
def config():
    return render_template(
        'config.html',
        title=settings.APP_TITLE,
        delete_after=bool(store.get('delete_after_upload')),
        auto_upload=bool(store.get('auto_upload')),
        drive_authorized=gdrive.is_authorized(),
        drive_email=gdrive.get_account_email() if gdrive.is_authorized() else None,
        notify_on_upload=bool(store.get('notify_on_upload')),
    )


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
        auto_upload=bool(store.get('auto_upload')),
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@application.route('/scan', methods=['GET'])
@login_required
def scan():
    if not appstate.is_active():
        return jsonify({"found": False, "root": None, "count": 0, "idle": True,
                         "mounted": False, "device": None})
    root, images = sdcard.find_card()
    if images:
        return jsonify({"found": True, "root": root, "count": len(images),
                         "mounted": True, "device": appstate.device_of(images[0])})
    return jsonify({"found": False, "root": None, "count": 0,
                     "mounted": False, "device": sdcard.find_unmounted_card()})


@application.route('/mount_card', methods=['POST'])
@login_required
def mount_card():
    devname = os.path.basename(request.form.get('device', ''))
    ok, message = appstate.mount_sd(devname)
    return jsonify({"ok": ok, "message": message})


@application.route('/settings', methods=['POST'])
@login_required
def save_settings():
    try:
        store.set('delete_after_upload', bool(request.form.get('delete_after_upload')))
        store.set('auto_upload', bool(request.form.get('auto_upload')))
        store.set('notify_on_upload', bool(request.form.get('notify_on_upload')))
        flash("Settings saved.")
    except Exception as exc:
        flash(f"Could not save settings: {exc}")
    return redirect(url_for('config'))


@application.route('/start', methods=['POST'])
@login_required
def start():
    if not appstate.is_active():
        flash("Idle: Google Drive not reachable.")
        return redirect(url_for('index'))
    ok, message = processor.start(bool(store.get('delete_after_upload')))
    flash(message)
    return redirect(url_for('index'))


@application.route('/shutdown', methods=['POST'])
@login_required
def shutdown():
    processor.stop_and_wait()
    appstate.unmount_sd()
    ok, message = appstate.power_off()
    if not ok:
        flash(message)
        return redirect(url_for('index'))
    return "Shutting down…"


def _reconnect_and_resume():
    """Retry Drive reachability; on success, remount an unmounted card if
    present and resume any pending upload. Returns (mode, start_result),
    where start_result is processor.start()'s (ok, message), or None if
    still idle."""
    mode = appstate.retry()
    if mode != appstate.MODE_ACTIVE:
        return mode, None

    unmounted = sdcard.find_unmounted_card()
    if unmounted:
        appstate.mount_sd(unmounted)

    result = processor.start(bool(store.get('delete_after_upload')))
    return mode, result


RECONNECT_INTERVAL_SECONDS = 5 * 60


def _periodic_reconnect_loop():
    """While idle, periodically retry Drive so an interrupted upload resumes
    on its own once connectivity (and the card) come back."""
    while True:
        time.sleep(RECONNECT_INTERVAL_SECONDS)
        if not appstate.is_active():
            mode, result = _reconnect_and_resume()
            if mode == appstate.MODE_ACTIVE:
                print(f"Periodic reconnect: Drive reachable. {result[1] if result else ''}")


WIFI_CHECK_INTERVAL_SECONDS = 30
_wifi_ap_started_by_watchdog = False


def _wifi_watchdog_loop():
    """Start the setup AP if the device has no internet at all (no Ethernet,
    no known WiFi) so it's never unreachable in the field. This is a
    separate, lower-level check than Drive reachability — it covers total
    network loss, not just Drive being down."""
    global _wifi_ap_started_by_watchdog
    while True:
        try:
            # Don't fight a connection attempt the user just kicked off.
            if wifi.get_status()['phase'] != 'connecting':
                online = wifi.has_internet()
                if not online and not wifi.is_ap_active():
                    if wifi.auto_connect_known():
                        print("WiFi watchdog: known network in range, attempting to reconnect.")
                    else:
                        ok, msg = wifi.start_ap()
                        _wifi_ap_started_by_watchdog = ok
                        print(f"WiFi watchdog: no internet, started setup AP: {msg}")
                elif online and wifi.is_ap_active() and _wifi_ap_started_by_watchdog:
                    # Came online on its own (e.g. Ethernet plugged back in)
                    # while the watchdog's own AP was up for no reason now.
                    ok, msg = wifi.stop_ap()
                    _wifi_ap_started_by_watchdog = not ok
                wifi.refresh_lcd()
        except Exception as exc:
            print(f"WiFi watchdog error: {exc}")
        time.sleep(WIFI_CHECK_INTERVAL_SECONDS)


@application.route('/wifi', methods=['GET'])
@login_required
def wifi_setup():
    return render_template(
        'wifi.html',
        title=settings.APP_TITLE,
        ap_active=wifi.is_ap_active(),
        networks=wifi.scan_networks(),
    )


@application.route('/wifi/connect', methods=['POST'])
@login_required
def wifi_connect():
    ssid = request.form.get('ssid', '').strip()
    password = request.form.get('password', '')
    if not ssid:
        return jsonify({"ok": False, "message": "No network selected."}), 400
    ok, message = wifi.start_connect(ssid, password)
    return jsonify({"ok": ok, "message": message})


@application.route('/wifi/status', methods=['GET'])
@login_required
def wifi_status():
    return jsonify(wifi.get_status())


@application.route('/retry', methods=['POST'])
@login_required
def retry():
    mode, result = _reconnect_and_resume()
    if mode != appstate.MODE_ACTIVE:
        flash(appstate.get_reason())
    else:
        flash(f"Google Drive reachable. {result[1]}")
    return redirect(url_for('index'))


@application.route('/disconnect_drive', methods=['POST'])
@login_required
def disconnect_drive():
    try:
        os.remove(gdrive.TOKEN_PATH)
    except FileNotFoundError:
        pass
    appstate.retry()
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


@application.route('/drive_status', methods=['GET'])
@login_required
def drive_status():
    return jsonify({"authorized": gdrive.is_authorized()})


wifi.show_starting()

# Decide active/idle at worker startup (single gunicorn worker holds this state).
appstate.startup()

threading.Thread(target=_periodic_reconnect_loop, daemon=True).start()
threading.Thread(target=_wifi_watchdog_loop, daemon=True).start()


if __name__ == "__main__":
    application.run(debug=True, use_reloader=True, port=8000)
