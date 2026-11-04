# README-UI — cómo funciona la interfaz de UMA Mercure

Documento de trabajo (2026-11-04, actualizado tras la arquitectura B). Para
continuar el desarrollo desde un Hermes local en esta Pi sin pasar por SSH.
Si algo manda mal, busca aquí antes de tocar código.

## Arquitectura B: la web reproduce SIN MPD (decisión 2026-11-04)

MPD seguía siendo un daemon de sesión única: una cola global, un volumen global,
stream httpd sin seek y puerto vivo solo mientras reproduce — incompatible con
"escuchar desde cualquier dispositivo de la red Tailscale". La web ahora usa:

- **Cola compartida** en SQLite (`radio_queue`, id 1-based).
- **Reloj del servidor** en SQLite (`session_state`, fila única id=1):
  posición = `offset + now - started_at` cuando state=play. Todos los
  dispositivos ven la misma posición; el ticker de la API avanza pistas.
- **Cada navegador es su propio reproductor**: carga el archivo real vía
  `GET /api/music/stream?file=...` (HTTP Range → seek instantáneo) y sincroniza
  su `<audio>` contra el snapshot de sesión (deriva >1.5s → corrige).
- **Volumen local por dispositivo** (localStorage `uma-volume`), no global.

MPD queda como reproductor local heredado (salidas alsa/pulse por mpc) y como
índice de referencia, pero el flujo web no lo usa. `mpc` sigue disponible para
sonar por el altavoz del Pi.

## Stack y puertos

| Pieza | Qué es | Puerto | Unit systemd |
|---|---|---|---|
| Web UI | React compilada (vite) servida por FastAPI | 8000 | `uma-api.service` (usuario) |
| API | FastAPI + uvicorn, `api/main.py` + sesión SQLite | 8000 (misma) | idem |
| MPD | legado: reproductor local del Pi, índice | 6600 | `mpd.service` (usuario) |
| Stream httpd | MPD → MP3 128k (lame) — YA no lo usa la web | 8010 | dentro de mpd |
| Cerebro LLM | llama-server LFM3-Omni-2B-Q4_K_M en el rig (GPU GRE) | 8081 | `uma-brain.service` en el RIG, no aquí |
| Qdrant | corre pero SIN usar en UMA aún | 6333/6334 | aparte |

Acceso desde fuera: Tailscale — **la URL buena ahora es HTTPS**:
`https://<host>.<tailnet>.ts.net/` (tailscale serve → proxy a
127.0.0.1:8000; certificado Let's Encrypt válido en todos los dispositivos del
tailnet; el WS hace handshake 101 a través del proxy). `http://<ip-tailscale>:8000`
sigue vivo pero los navegadores NO registran el service worker ni permiten
instalar la PWA en http. Si se rompe el serve: `tailscale serve status`,
`tailscale serve --https=443 off` y de nuevo `tailscale serve --bg 8000`
(requiere `sudo tailscale set --operator=<usuario>`, hecho ya).

## Sesiones múltiples (multiusuario)

- Todos los dispositivos se unen por defecto a la sesión **`main`** (reproducción
  compartida: una radio). El botón **🍴** en el Reproductor bifurca
  (`POST /api/session/fork?sid=main`): copia cola y posición en una sesión nueva
  (sid aleatorio, guardado en localStorage `uma-sid`) y ese dispositivo queda
  independiente — pausar/siguiente/cola propios sin afectar a los demás. El botón
  **↩** vuelve a la radio común.
- Cada sesión = fila en `session_state` (sid) + filas en `radio_queue` (sid, pos
  0-based). El ticker avanza TODAS las sesiones en play. WS `/ws/status?sid=...`
  manda el snapshot de esa sesión. `GET /api/sessions` lista todas;
  `POST /api/session/drop?sid=` elimina una paralela (main no se puede borrar).
- El chat de IA opera sobre `main` (sid por defecto en session_service).
- play_count se comparte entre sesiones (suma la biblioteca, no por oyente).

## PWA instalable (Android/desktop)

- `web/public/manifest.webmanifest` (standalone, tema #0a0a0f, 3 iconos) +
  `web/public/sw.js` (app shell: cachea UI; NO intercepta /api ni /ws — audio y
  estado siempre en vivo) + registro en main.jsx. Iconos generados con
  `rsvg-convert` desde `web/public/icons/icon.svg` (¡no usar ImageMagick `convert`
  para SVG: renderiza borroso!).
- Instalación: abrir la URL HTTPS en el navegador → menú "Instalar aplicación"
  (Chrome) / "Instalar" (Firefox Android ≥136). El HTTPS de tailscale serve es
  lo que lo habilita (los SW exigen contexto seguro).

## Unidades y reinicios (IMPORTANTE: son de USUARIO)

```bash
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
systemctl --user restart mpd uma-api
systemctl --user status uma-hdd-watcher.timer
```
- `sudo systemctl restart mpd` FALLA ("bind :6600 already in use") — el unit de
  sistema está disabled; usa siempre `--user`.
- Linger está habilitado: las units sobreviven sin sesión de login.

## Config de MPD (solo para el reproductor legado)

- `/etc/mpd.conf`: `music_directory "/media/<usuario>/Seagate Expansion Drive/"`,
  salidas alsa (HDMI) y pulse (Bluetooth) con `mixer_type "software"`.
  Backup original: `/etc/mpd.conf.bak-20261102`.
- `/etc/mpd_local.conf` (incluido vía `include_optional`): salida `httpd` + `lame`
  en 8010 (legacy).

## El HDD (Seagate, NTFS) y sus trampas

- La ruta de montaje debe llamarse EXACTAMENTE `Seagate Expansion Drive`. Si existe
  cualquier stub con ese nombre, udisks monta como `...Drive1` y MPD ve 0 ficheros.
- `udisksctl mount` por ssh falla (polkit sin tty). Montaje manual que funciona:
  `sudo mount -t ntfs3 -o rw,nosuid,nodev,relatime,uid=1000,gid=1000,iocharset=utf8 /dev/sdb1 "/media/<usuario>/Seagate Expansion Drive"`
- fstab: entrada por `UUID=<uuid>` con espacios escapados `\040` y `nofail`.
- Watchdog: timer `uma-hdd-watcher.timer` (cada 60s) → `scripts/hdd_watcher.sh`.
  Detecta aparición/desaparición, reindexa MPD **carpeta a carpeta**, escribe en
  `data/hdd_watchdog.log` y lleva el estado en `data/.hdd_state`. El ticker de
  sesión salta archivos inexistentes si el HDD desaparece.

## Data: SQLite `data/uma.db` (modo WAL)

- Tabla `track_metadata`: file (ruta relativa a `MUSIC_DIR`), artist, title,
  album, genre, bpm, musical_key, energy, mood, play_count, last_played,
  **duration** (segundos, rellenada 2026-11-04 con `scripts/fill_durations.py`:
  14.628/14.860 filas; 232 ilegibles por ffprobe quedan NULL → fallback 300s).
- `radio_queue`: cola de reproducción (id 1-based == posición). `session_state`:
  fila única con el reloj (state, queue_index, offset, started_at, shuffle, repeat).
- Regeneración de `track_metadata`: `scripts/regen_db.py` (habla con MPD vía
  socket 6600; comando clave `listallinfo ""`). Backup pre-regen:
  `data/uma.db.bak-regen-20261104`.
- BUG HISTÓRICO (arreglado por la regen): artist/title INTERCAMBIADOS en muchas
  filas; secuela ~1.047 ficheros sin ID3 con heurística "Artista - Título".
  Arreglo definitivo: MusicBrainz Picard / curator.
- `bpm` y `mood` NULL a propósito (alucinaciones del llm_tagger viejo).
- **WAL + busy_timeout**: `models/database.py::make_engine()` fija
  `PRAGMA journal_mode=WAL` y `busy_timeout=15000` en cada conexión. Sin esto,
  ticker + filler + API provocaban `database is locked` (500 en `/api/session/seek`).
  El cambio de journal a WAL se hizo con el filler parado.
- No hay CLI `sqlite3` instalada; usa `python3 -c "import sqlite3..."`.

## API (FastAPI, `api/main.py`) — v0.3.0

Sesión (el flujo web real, verificado 2026-11-04):

| Endpoint | Notas |
|---|---|
| `GET /api/session` | snapshot: state, file, artist, title, duration, position, queue_index, queue_len, shuffle, repeat |
| `GET /api/session/queue?limit=` | cola (primeras 200 por defecto) + current_index |
| `POST /api/session/play_file` `{file}` | cola de 1 pista y play |
| `POST /api/session/add_files` `{files:[...]}` | añade en bloque (máx 2000 por llamada) |
| `POST /api/session/shuffle_all` | radio: cola aleatoria de las 14.860 pistas + play |
| `POST /api/session/play_index` `{index}` | saltar a pista de la cola |
| `POST /api/session/play|pause|stop|next|previous` | transporte compartido |
| `POST /api/session/seek` `{seconds}` | mueve el reloj del servidor |
| `GET /api/music/stream?file=...` | archivo real con HTTP Range (206); rutas fuera de `MUSIC_DIR` → 400 |
| `WS /ws/status` | snapshot de sesión cada segundo |

Catálogo/IA (sin cambios): `GET /api/music/library` (SQLite ilike, limit 2000),
`/api/music/library/count` (`{total, hdd_present}`), `/api/music/db/stats`,
`POST /api/chat` (intents play/pause/stop/next/previous/play_target/smart_playlist/
shuffle_all van a `session_service` desde 2026-11-04).

Endpoints MPD heredados (`/api/music/play_file`, `add_file(s)`, `shuffle_all`,
`volume`, `output`, playlist/transporte) siguen montados pero la UI ya no los usa.

### Códec vs navegador (trampa nueva de la arquitectura B)

El navegador decodifica lo que soporte, no MPD:
- `.mp3 .flac .ogg .opus .wav` → OK en cualquier navegador moderno (verificado).
- `.m4a/.aac` (AAC-LC, 3.907 ficheros) → OK en Chrome/Safari/Firefox reales.
  El **HeadlessChrome de prueba NO trae AAC** (`FFmpegDemuxer: no supported
  streams`) — no es un bug del servidor, no lo uses para validar m4a.
- `.wma .ape .wv` (54 ficheros) → la API los transcode on-the-fly a MP3 160k
  con ffmpeg (`TRANSCODE_EXTS` en main.py; sin Range, sin seek). Verificado.
- Fichero corrupto/ilegible → el Player emite `POST /api/session/next` al
  primer error con ese file (auto-skip, una vez por pista).

## UI (`web/`, React + vite)

Fuente en `web/src/`, build en `web/dist/` (FastAPI la sirve con StaticFiles).
Rebuild: `cd web && npm run build` (el hash del bundle cambia; FastAPI sirve el
nuevo sin reiniciar la API).

Componentes:
- `App.jsx` — layout + `HddBanner` (poll `/api/music/library/count` cada 30s).
- `components/Player.jsx` — sesión: `<audio src="/api/music/stream?file=...">`,
  sigue play/pause del snapshot, corrige deriva >1.5s, seek al clicar la barra
  (`POST /api/session/seek`), volumen local por dispositivo, auto-skip en error.
  Autoplay bloqueado hasta el primer gesto en la página.
- `components/Catalog.jsx` — buscador del catálogo SQLite (14.860), badges,
  paginación 100 + "Cargar más". Clic en fila = `/api/session/play_file`;
  "+ cola" = `add_files`; "📋 A la cola (N)" = añade las pistas cargadas aquí a
  la cola de sesión (resultado en el Visor de Razonamiento); "🔀 Radio completa"
  = `/api/session/shuffle_all`.
- `components/Library.jsx` — la COLA DE SESIÓN (poll `/api/session/queue` 3s,
  primeras 200 visibles); clic en fila = `play_index`.
- `components/Stats.jsx` — stats MPD + `/api/music/db/stats`.
- `components/Chat.jsx` + `SmartPlaylistForm.jsx` → `POST /api/chat`; resultado
  vía `CustomEvent('uma-ai-response')` → `ResponseViewer.jsx`.
- `hooks/usePlayerStatus.js` — socket `/ws/status` (status, current, connected).

## Backups y pendientes

- Backups: `api/main.py.bak-20261102`, `/etc/mpd.conf.bak-20261102`,
  `data/uma.db.bak-regen-20261104`. No hay git — primer candidato: `git init`.
- Pendientes razonables: locutor virtual (LFM3 presenta la pista vía WS/TTS),
  "más como esta" (embeddings → Qdrant), metadata real (Picard/curator),
  regenerar bpm/mood con análisis de audio, y decidir qué hacer con los 232
  ficheros ilegibles por ffprobe (probablemente truncados/corruptos).
