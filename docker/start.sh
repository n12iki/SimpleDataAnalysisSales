#!/bin/bash
# Starts a virtual desktop, exposes it on :6080 (browser), then runs the Tk app.
# When the app window is closed, this script ends and the container stops.
set -e

Xvfb :1 -screen 0 "${RESOLUTION}" -nolisten tcp >/dev/null 2>&1 &
until [ -S /tmp/.X11-unix/X1 ]; do sleep 0.1; done

fluxbox >/dev/null 2>&1 &
x11vnc -display :1 -forever -shared -nopw -quiet -rfbport 5900 -localhost >/dev/null 2>&1 &
websockify --web /usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

# Run from /data so the "Browse..." dialog opens in the mounted data folder
cd /data
python /app/gui_app.py
