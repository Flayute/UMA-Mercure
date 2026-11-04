# 🎵 UMA Mercure: Sistema Aural Soberano

UMA (Universal Music Agent) es el componente de inteligencia ambiental del ecosistema Mercure. Diseñado para ofrecer una experiencia musical privada, local y gobernada por IA, UMA transforma una biblioteca masiva de archivos físicos en un servicio de streaming personal inteligente.

---

## 🚀 Hitos Alcanzados (Fase de Sintonización)

- **Indexación Masiva:** Integración exitosa de **14.179 canciones** desde disco externo Seagate via symlinks optimizados.
- **Curación Inteligente (9B Power):** Implementación de un agente Qwen 9B con libertad de razonamiento ("Thinking Mode") para descubrimiento musical.
- **Arquitectura de Doble Capa:**
    - **Control Directo:** Formulario soberano para selección técnica (BPM, Género, Novedad).
    - **Visor de Razonamiento:** Ventana dedicada estilo CAMS para ver las propuestas y el pensamiento de la IA.
- **Algoritmo de Novedad:** Priorización automática de temas con bajo `play_count` para "limpiar" y redescubrir la biblioteca.
- **Sincronización en Tiempo Real:** Visor de cola de reproducción (`Current Queue`) sincronizado con MPD cada 3s.

---

## 🛠️ Arquitectura Mercure

```text
UMA-Mercure/
├── api/                # Backend FastAPI (Gateway entre Web, IA y MPD)
│   ├── core/           # Configuración y seguridad
│   ├── services/       # Lógica de MPD, Agente LLM y Base de Datos
│   └── models/         # Modelos GGUF de IA y Esquemas SQL
├── web/                # Frontend React (Rich Aesthetics Dashboard)
│   ├── src/components/ # Player, Chat, Queue Viewer, Reasoning Viewer
│   └── index.css       # Diseño Dark Mode Premium (Glassmorphism)
├── scripts/            # Herramientas de migración y re-mapeo de rutas
├── data/               # uma.db (Cerebro de metadatos: 14k+ registros)
└── deploy/             # Scripts de despliegue para Raspberry Pi 500
```

---

## 🧠 Decisiones Técnicas

| Componente | Razón |
|---|---|
| **MPD + Lame** | Streaming MP3 universal para móviles y bajo consumo (<20MB RAM). |
| **SQLite + SQLAlchemy** | Persistencia de metadatos (BPM, Mood) para búsquedas instantáneas. |
| **Flex-Search Engine** | Búsqueda multicanal (Etiquetas + Rutas + Mood) para cubrir temas sin tags. |
| **PlayCount Tracker** | Sistema de memoria persistente para evitar la fatiga auditiva. |
| **Reasoning Viewer** | Desacoplamiento del pensamiento de la IA del control del player para estabilidad. |

---

## 🗺️ Roadmap Completado

- [x] Indexación y reparación de rutas para 14k temas.
- [x] Backend FastAPI con control de reproducción y WebSocket.
- [x] Agente LLM 9B con soporte de Razonamiento (Thinking).
- [x] Frontend React Dashboard con diseño premium.
- [x] Generador de Listas Inteligente con prioridad de novedad.
- [x] Visor de Respuestas dedicado (estilo CAMS).
- [x] Visor de Cola de Reproducción en tiempo real.
- [x] Plan de despliegue automatizado para Raspberry Pi 500.

---

> "UMA Mercure: Porque tu música es tuya, y tu DJ también." 🛡️⚗️🎵

---

**Documentación de la UI y operación (actualizada 2026-11-04): ver [README-UI.md](README-UI.md).**
