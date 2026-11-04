#!/usr/bin/env python3
"""
Configuración del motor de curación musical
- Rate limits de APIs
- Paths de base de datos
- Configuración de dry-run
"""

# =============================================================================
# CONSTANTES
# =============================================================================

# Rate limits por API
API_RATE_LIMITS = {
    "musicbrainz": {
        "max_requests_per_second": 1,       # 1 req/seg (hard limit)
        "retry_delay": 2,                   # Segundos de espera en error
        "max_retries": 3
    },
    "acousticbrainz": {
        "max_requests_per_second": 2,       # 2 req/seg
        "retry_delay": 1
    },
    "lastfm": {
        "max_requests_per_second": 3,       # 3 req/seg
        "retry_delay": 1
    }
}

# Caché de respuestas API
CACHE_CONFIG = {
    "enabled": True,
    "db_path": "cache/api_responses.db",
    "default_ttl": 3600,  # 1 hora
    "mbid_cache_ttl": 86400  # 24 horas para MBID (más duradero)
}

# Base de datos principal
DATABASE_CONFIG = {
    "path": "data/uma.db",
    "pool_size": 10,
    "pool_recycle": 1800  # 30 minutos
}

# Configuración de dry-run
DRY_RUN_DEFAULT = False  # False por defecto (modo producción)

# Rangos válidos para limpieza
VALID_RANGES = {
    "bpm": (60, 200),      # 60-200 BPM
    "midi_key": (0, 127),  # MIDI 0-127
    "energy": (0.0, 1.0),   # 0-1
    "danceability": (0.0, 1.0),
    "valence": (0.0, 1.0)
}

# Prioridad de fuentes de datos
SOURCE_PRIORITY = [
    "acousticbrainz",  # Más completo
    "lastfm",          # Metadatos básicos
    "musicbrainz",     # Información de pista
    "folder_structure",  # Géneros de carpetas
    "existing_db"      # Datos existentes
]

# Límites de lotes
BATCH_CONFIG = {
    "api_requests": 500,    # Peticiones API por lote
    "database_transactions": 500,  # Transacciones por lote
    "dry_run_batches": 5    # Números de lotes en dry-run
}

# Límites de archivos
FILE_LIMITS = {
    "max_files_per_batch": 100,  # Archivos por lote de procesamiento
    "skip_extensions": {".wav", ".aiff", ".flac"}  # No analizar audio nativo
}