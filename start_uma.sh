#!/bin/bash
echo '🎼 Iniciando UMA-Mercure Node (Satélite de Música)...'
cd /home/<usuario>/UMA-Mercure/api
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
