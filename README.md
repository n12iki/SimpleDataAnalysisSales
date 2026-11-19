# Sales & Inventory Analysis — Docker edition

The app is a Tkinter desktop program. Inside Docker it runs on a virtual screen that is
streamed to your **web browser** (noVNC), so it looks and behaves the same on Windows, macOS and Linux.

## One-time setup (Windows)
1. Install **Docker Desktop** (https://www.docker.com/products/docker-desktop/) and start it once.
2. Double-click **`Create Desktop Shortcut.bat`** -> a "Sales Analysis" icon appears on your Desktop.
3. Copy your Excel file into the **`data`** folder of this project.

## Every day
Double-click the **Sales Analysis** desktop icon. It starts Docker if needed, builds/starts the
container (first run: a few minutes) and opens your browser on http://localhost:6080.
In the app click **Browse...** — it opens in `data`, so pick your Excel file there.

Closing the dashboard window stops the container automatically.
`Stop Sales Analysis.bat` stops it manually.

## macOS / Linux
`./launch.sh`

## Notes
- Do not move the project folder after creating the shortcut (re-run the shortcut script if you do).
- The container only listens on 127.0.0.1, so other computers on your network cannot reach it.
- Edited the code? Just launch again; the image is rebuilt automatically (cached, so it's quick).
