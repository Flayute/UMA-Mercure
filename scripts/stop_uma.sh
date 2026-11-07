#!/usr/bin/env bash
# Detiene la radio UMA Mercure en esta maquina: API web, watchdog del HDD y
# MPD (legado). Pensado para ejecutar por ssh, donde no vienen las variables
# del bus de usuario, por eso se exportan aqui.
#
# Reiniciar cuando quieras:
#   systemctl --user start uma-api mpd && systemctl --user start uma-hdd-watcher.timer
# (con las mismas exportaciones del bus si entras por ssh)

set -eu

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"

for u in uma-api.service uma-hdd-watcher.timer mpd.service; do
    systemctl --user stop "$u"
done

echo "UMA detenido:"
for u in uma-api.service uma-hdd-watcher.timer mpd.service; do
    echo "  $u -> $(systemctl --user is-active "$u" || true)"
done
