#!/bin/bash

# UMA SETUP - Instalador de servicios soberanos
# Ejecutar este script en la Pi 500 para dejar todo configurado.

echo "🚀 Configurando servicios UMA Mercure..."

# 1. Copiar archivos de servicio a la carpeta de systemd del usuario
mkdir -p ~/.config/systemd/user
cp systemd/uma-llama.service ~/.config/systemd/user/
cp systemd/uma-api.service ~/.config/systemd/user/

# 2. Recargar daemon de systemd
systemctl --user daemon-reload

# 3. Habilitar servicios para que arranquen al inicio
systemctl --user enable uma-llama.service
systemctl --user enable uma-api.service

# 4. Dar permisos de ejecución al script de init
chmod +x ../uma-init.sh

echo "✅ Servicios instalados y habilitados."
echo "💡 Recuerda ejecutar './uma-init.sh' antes de arrancar los servicios por primera vez."
