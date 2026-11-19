FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    MPLCONFIGDIR=/tmp/matplotlib \
    DISPLAY=:1 \
    RESOLUTION=1600x900x24

# Tk runtime + a virtual screen (Xvfb) + window manager + VNC -> browser (noVNC)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libtk8.6 libtcl8.6 \
        xvfb x11vnc fluxbox novnc websockify \
        fonts-dejavu-core fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY docker/fonts.conf /etc/fonts/local.conf

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fail the build early if Tk is missing; strip Windows line endings from the shell script
RUN python -c "import tkinter" \
    && sed -i 's/\r$//' docker/start.sh \
    && chmod +x docker/start.sh

EXPOSE 6080
CMD ["/app/docker/start.sh"]
