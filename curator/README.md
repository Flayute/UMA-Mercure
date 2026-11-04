# 🏛️ UMA Curator: Motor de Inteligencia Aural

El módulo **Curator** es el cerebro de enriquecimiento de metadatos de UMA-Mercure. Su misión es transformar una biblioteca de archivos físicos en una base de datos musical "viva", completando la información que falta mediante el uso de APIs externas de forma ética, eficiente y soberana.

---

## 🛠️ Arquitectura de Curación

El sistema utiliza un **Orquestador Central** que coordina tres fuentes de datos principales para obtener un análisis 360º de cada canción:

1.  **MusicBrainz (El Registro):** Se utiliza para identificar la canción de forma única mediante el **MBID** (MusicBrainz ID). Es la fuente de verdad para el año, el álbum y la versión exacta de la pista.
2.  **AcousticBrainz (El ADN Sónico):** Consulta la base de datos de análisis acústico para obtener datos pre-calculados (BPM reales, Tonalidad/Key, Energía, Danceability y Valence). Ideal para música anterior a 2022.
3.  **Last.fm (El Contexto Social):** Extrae los **Tags** y géneros más populares definidos por la comunidad, permitiendo una clasificación de estilos mucho más flexible y rica que los tags estándar de ID3.

---

## 🚀 Características Clave

- **Soberanía y Respeto (Rate Limiting):** Implementa un limitador de velocidad estricto (1 req/s para MusicBrainz) para evitar bloqueos y ser un "buen ciudadano" en la red.
- **Caché Inteligente:** Todas las respuestas se guardan en una base de datos SQLite local (`cache/api_responses.db`). Si vuelves a analizar una canción, la respuesta es instantánea y no consume datos.
- **Búsqueda Flexible:** Capacidad de encontrar metadatos incluso con nombres de archivos parciales o tags incompletos.
- **Modo Dry-Run:** Permite simular el proceso de curación y generar reportes en CSV antes de aplicar cualquier cambio real a la base de datos `uma.db`.

---

## 📁 Estructura del Módulo

```text
curator/
├── api_clients/         # Clientes especializados para cada API
│   ├── base.py          # Clase base con Rate Limiting y Caché
│   ├── orchestrator.py  # El "Director de Orquesta" (Lógica principal)
│   ├── musicbrainz.py   # Integración con MB
│   ├── acousticbrainz.py# Integración con AB
│   └── lastfm.py        # Integración con Last.fm
├── config.py            # Configuración de límites y rutas
└── main.py              # Script de ejecución para procesamiento por lotes
```

---

## 📋 Próximos Pasos

- **Integración Somática:** Conectar los resultados del orquestador con el script de análisis local para cruzar datos de BPM.
- **Escritura de Tags:** Implementar la inyección de los nuevos metadatos curados directamente en los archivos MP3/M4A (opcional).
- **IA de Resolución:** Usar el modelo 9B para decidir categorías cuando las APIs de Last.fm y MusicBrainz no coincidan.

---

> "Curator no solo busca datos, busca el sentimiento de tu música." 🛡️⚗️🎵
