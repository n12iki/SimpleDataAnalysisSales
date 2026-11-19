#!/bin/bash
# macOS / Linux launcher:  ./launch.sh
cd "$(dirname "$0")"
mkdir -p data
docker compose up -d --build || { docker compose logs --tail 40; exit 1; }
URL="http://localhost:6080/vnc.html?autoconnect=true&resize=scale&reconnect=true"
for i in $(seq 1 60); do curl -s -o /dev/null http://localhost:6080/vnc.html && break; sleep 1; done
(command -v open >/dev/null && open "$URL") || xdg-open "$URL"
