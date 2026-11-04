#!/bin/bash
# UMA watchdog: detecta la conexión del Seagate y refresca el índice de MPD.
# Corre como unit de usuario (uma-hdd-watcher) cada 60s vía timer.
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$BASE_DIR/api/.env" ] && . "$BASE_DIR/api/.env"
MD="${MUSIC_DIR:-/media/Seagate Expansion Drive}"
STATE="$BASE_DIR/data/.hdd_state"
LOG="$BASE_DIR/data/hdd_watchdog.log"
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

if [ -d "$MD" ] && [ -n "$(ls -A "$MD" 2>/dev/null | head -1)" ]; then
    if [ "$(cat "$STATE" 2>/dev/null)" != "present" ]; then
        echo "$(date '+%F %T') HDD detectado — indexando MPD carpeta a carpeta..." >> "$LOG"
        cd "$MD" || exit 1
        for d in *; do
            case "$d" in
                "\$RECYCLE.BIN"|.dtrash|.fseventsd|.Spotlight-V100) continue ;;
            esac
            mpc update "$d" >/dev/null 2>&1
        done
        sleep 120
        SONGS=$(mpc stats 2>/dev/null | awk '/^Songs:/ {print $2}')
        echo "$(date '+%F %T') índice actualizado: $SONGS canciones en MPD" >> "$LOG"
        echo "present" > "$STATE"
    fi
else
    if [ "$(cat "$STATE" 2>/dev/null)" != "absent" ]; then
        echo "$(date '+%F %T') HDD ausente (la web sigue sirviendo la DB)" >> "$LOG"
        echo "absent" > "$STATE"
    fi
fi
