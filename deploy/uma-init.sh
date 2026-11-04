#!/bin/bash

# UMA INIT - Sincronización soberana de rutas
# Este script detecta el disco externo y prepara el entorno UMA

USER_HOME="/home/$USER"
MUSIC_ROOT="$USER_HOME/Música"
SYMLINK_PATH="$MUSIC_ROOT/Seagate_Music"

echo "🛰️ Buscando disco de expansión Seagate..."

# 1. Intentar encontrar el punto de montaje del disco Seagate
SEAGATE_PATH=$(lsblk -o MOUNTPOINTS | grep "Seagate" | head -n 1)

if [ -z "$SEAGATE_PATH" ]; then
    echo "⚠️ No se detectó el disco Seagate montado. UMA solo verá la música local."
else
    echo "✅ Disco detectado en: $SEAGATE_PATH"
    
    # 2. Crear el enlace simbólico si no existe o ha cambiado
    mkdir -p "$MUSIC_ROOT"
    if [ -L "$SYMLINK_PATH" ]; then
        rm "$SYMLINK_PATH"
    fi
    
    ln -s "$SEAGATE_PATH/Music" "$SYMLINK_PATH"
    echo "🔗 Enlace simbólico actualizado: $SYMLINK_PATH -> $SEAGATE_PATH/Music"
fi

# 3. Asegurar que los permisos son correctos
chmod -R 755 "$USER_HOME/Documents/UMA-Mercure/api"

# 4. Notificar a MPD
echo "🔄 Notificando a MPD para actualizar base de datos..."
mpc update

echo "🏁 UMA está listo para la acción."
