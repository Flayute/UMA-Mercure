import asyncio
import logging
import mimetypes
import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from services.mpd_client import MPDService
from services.llm_agent import LLMAgent
from services.session import SessionService
from core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="UMA Mercure API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

mpd_service = MPDService(host=settings.MPD_HOST, port=settings.MPD_PORT)
llm_agent = LLMAgent()
session_service = SessionService(settings.DB_URL)

@app.on_event("startup")
async def startup_event():
    from models.database import init_db
    init_db()
    try:
        mpd_service.connect()
        logger.info("Conectado a MPD exitosamente.")
        mpd_service.ensure_stream_output()
        logger.info("Salida de stream forzada ON (HDMI OFF).")
    except Exception as e:
        logger.warning(f"Error inicial conectando a MPD: {e}")
    asyncio.create_task(session_service.ticker())
    logger.info("Session ticker iniciado.")

@app.on_event("shutdown")
async def shutdown_event():
    mpd_service.disconnect()

# ── HEALTH ──────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    status = mpd_service.status()
    return {"status": "ok", "mpd_status": status, "llama_local": settings.LLAMA_SERVER_URL, "llama_remote": settings.LLAMA_REMOTE_URL}

# ── ENDPOINTS DIRECTOS (Control Manual / Frontend) ──────────

@app.get("/api/music/play")
def music_play():
    mpd_service.play()
    return {"status": "playing"}

@app.get("/api/music/pause")
def music_pause():
    mpd_service.pause()
    return {"status": "paused"}

@app.get("/api/music/stop")
def music_stop():
    mpd_service.stop()
    return {"status": "stopped"}

@app.post("/api/music/save_playlist")
def save_playlist(name: str = Body(..., embed=True)):
    result = mpd_service.save_playlist(name)
    return {"status": "ok", "name": name}

@app.get("/api/music/next")
def music_next():
    mpd_service.next()
    return {"status": "next_track"}

@app.get("/api/music/previous")
def music_prev():
    mpd_service.previous()
    return {"status": "previous_track"}

@app.get("/api/music/current")
def current_song():
    return mpd_service.current_song()

@app.get("/api/music/playlist")
def get_playlist():
    return mpd_service.get_playlist()

# Biblioteca: leemos del SQLite (uma.db), NO del índice de MPD, para que la web
# funcione también con el HDD desconectado. MPD solo manda la reproducción.
HDD_PATH = settings.MUSIC_DIR

@app.get("/api/music/library")
def get_library(q: str = None, limit: int = 200, offset: int = 0):
    from sqlalchemy import create_engine, or_
    from sqlalchemy.orm import sessionmaker
    from models.database import TrackMetadata
    engine = create_engine(settings.DB_URL)
    session = sessionmaker(bind=engine)()
    query = session.query(TrackMetadata)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            TrackMetadata.artist.ilike(like),
            TrackMetadata.title.ilike(like),
            TrackMetadata.album.ilike(like),
            TrackMetadata.genre.ilike(like),
            TrackMetadata.mood.ilike(like),
            TrackMetadata.keywords.ilike(like),
            TrackMetadata.description.ilike(like),
            TrackMetadata.file.ilike(like),
        ))
    rows = query.order_by(TrackMetadata.artist.asc()).offset(offset).limit(min(limit, 2000)).all()
    result = [{
        "file": r.file, "artist": r.artist, "title": r.title, "album": r.album,
        "genre": r.genre, "bpm": r.bpm, "musical_key": r.musical_key, "bpm_source": r.bpm_source,
        "mood": r.mood, "play_count": r.play_count or 0, "duration": r.duration,
        "description": r.description, "keywords": r.keywords,
    } for r in rows]
    session.close()
    return result

@app.get("/api/music/library/count")
def library_count():
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from models.database import TrackMetadata
    engine = create_engine(settings.DB_URL)
    session = sessionmaker(bind=engine)()
    total = session.query(func.count(TrackMetadata.id)).scalar() or 0
    session.close()
    import os
    try:
        hdd = bool(os.listdir(HDD_PATH))
    except OSError:
        hdd = False
    return {"total": total, "hdd_present": hdd}

@app.get("/api/music/search/{query}")
def search_tracks(query: str):
    return get_library(q=query, limit=100)

@app.get("/api/music/stats")
def get_stats():
    return mpd_service.get_stats()

@app.get("/api/music/db/stats")
def db_stats():
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from models.database import TrackMetadata
    engine = create_engine(settings.DB_URL)
    session = sessionmaker(bind=engine)()
    total = session.query(func.count(TrackMetadata.id)).scalar() or 0
    never = session.query(func.count(TrackMetadata.id)).filter(
        TrackMetadata.play_count == 0).scalar() or 0
    avg_bpm = session.query(func.avg(TrackMetadata.bpm)).scalar()
    top = session.query(TrackMetadata.artist, func.sum(TrackMetadata.play_count)).group_by(
        TrackMetadata.artist).order_by(func.sum(TrackMetadata.play_count).desc()).limit(5).all()
    session.close()
    return {
        "total": total,
        "never_played": never,
        "avg_bpm": round(float(avg_bpm or 0), 1),
        "top_artists": [{"artist": a, "plays": int(p or 0)} for a, p in top],
    }

@app.post("/api/music/volume/{value}")
def set_volume(value: int):
    mpd_service.set_volume(max(0, min(100, value)))
    return {"volume": value}

@app.post("/api/music/play_file")
def play_file(payload: dict = Body(...)):
    file_path = payload.get("file")
    if file_path:
        mpd_service.play_file(file_path)
        st = mpd_service.status()
        if st.get("error"):
            return {"status": "error", "file": file_path, "message": st["error"]}
        return {"status": "playing", "file": file_path}
    return {"status": "error", "message": "No file specified"}

@app.post("/api/music/add_file")
def add_file(payload: dict = Body(...)):
    """Añade una pista a la cola sin limpiarla."""
    file_path = payload.get("file")
    if not file_path:
        return {"status": "error", "message": "No file specified"}
    mpd_service.add_file(file_path)
    return {"status": "ok", "file": file_path,
            "playlistlength": mpd_service.status().get("playlistlength")}

@app.post("/api/music/add_files")
def add_files(payload: dict = Body(...)):
    """Añade varias pistas a la cola (hasta 2000). Sirve para mandar a MPD
    los resultados cargados en el Catálogo."""
    files = payload.get("files") or []
    if not isinstance(files, list) or not files:
        return {"status": "error", "message": "No files specified"}
    files = [f for f in files if isinstance(f, str)][:2000]
    mpd_service.add_files(files)
    return {"status": "ok", "added": len(files),
            "playlistlength": mpd_service.status().get("playlistlength")}

@app.post("/api/music/shuffle_all")
def shuffle_all():
    """Modo radio: biblioteca completa en aleatorio con repetición, y reproduce."""
    mpd_service.shuffle_all()
    return {"status": "playing",
            "playlistlength": mpd_service.status().get("playlistlength")}

@app.get("/api/music/output/{output_id}/{state}")
def toggle_output(output_id: int, state: int):
    mpd_service.toggle_output(output_id, bool(state))
    return {"status": "success", "output": output_id, "enabled": bool(state)}

# ── SESIÓN: reproducción web multi-dispositivo (sin MPD) ─────
# La cola vive en radio_queue (por sid), el reloj en session_state (por sid).
# Todos los navegadores se unen por defecto a 'main'; POST /api/session/fork
# bifurca la sesión actual (copia cola + posición) para reproducir en paralelo.

def _sid(sid: str = "main") -> str:
    return sid or "main"

@app.get("/api/session")
def session_snapshot(sid: str = "main"):
    return session_service.snapshot(_sid(sid))

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

@app.get("/api/session.rss")
def session_rss(request: Request, sid: str = "main"):
    """Feed RSS mínimo con la pista actual — para widgets nativos de Android."""
    base_url = str(request.base_url)
    snap = session_service.snapshot(_sid(sid))
    playing = snap.get("state") == "play"
    label = f"{snap.get('artist') or '?'} — {snap.get('title') or snap.get('file') or 'sin pista'}"
    desc = (f"{'SONANDO' if playing else snap.get('state', '?').upper()} · "
            f"{int(snap.get('position') or 0)}s / {int(snap.get('duration') or 0)}s · "
            f"cola {snap.get('queue_index', 0)}/{snap.get('queue_len', 0)}")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        '<title>UMA Mercure</title>'
        f'<link>{_esc(str(base_url))}</link>'
        '<description>Radio personal UMA Mercure</description>'
        f'<item><title>{_esc(label)}</title>'
        f'<description>{_esc(desc)}</description>'
        '<guid>uma-current</guid></item>'
        '</channel></rss>'
    )
    return Response(content=xml, media_type="application/rss+xml")

@app.get("/api/sessions")
def sessions_list():
    return session_service.list_sessions()

@app.get("/api/session/queue")
def session_queue(sid: str = "main", limit: int = 200, offset: int = 0):
    return session_service.queue_view(_sid(sid), limit=min(2000, max(1, limit)), offset=max(0, offset))

@app.post("/api/session/fork")
def session_fork(sid: str = "main"):
    new_sid = session_service.fork(_sid(sid))
    return {"status": "forked", "sid": new_sid, "session": session_service.snapshot(new_sid)}

@app.post("/api/session/drop")
def session_drop(sid: str):
    if sid == "main":
        return {"status": "error", "message": "la sesión main no se elimina"}
    ok = session_service.drop_session(sid)
    return {"status": "ok" if ok else "error"}

@app.post("/api/session/play_file")
def session_play_file(payload: dict = Body(...), sid: str = "main"):
    f = payload.get("file")
    if not f:
        return {"status": "error", "message": "No file specified"}
    session_service.play_file(f, _sid(sid))
    return {"status": "playing", "file": f}

@app.post("/api/session/add_files")
def session_add_files(payload: dict = Body(...), sid: str = "main"):
    files = payload.get("files") or []
    if not isinstance(files, list) or not files:
        return {"status": "error", "message": "No files specified"}
    files = [f for f in files if isinstance(f, str)][:2000]
    session_service.add_files(files, _sid(sid))
    snap = session_service.snapshot(_sid(sid))
    return {"status": "ok", "added": len(files), "queue_len": snap["queue_len"]}

@app.post("/api/session/shuffle_all")
def session_shuffle_all(sid: str = "main"):
    n = session_service.shuffle_all(_sid(sid))
    return {"status": "playing", "queue_len": n}

@app.post("/api/session/play")
def session_play(sid: str = "main"):
    session_service.play(_sid(sid))
    return {"status": session_service.snapshot(_sid(sid))["state"]}

@app.post("/api/session/pause")
def session_pause(sid: str = "main"):
    session_service.pause(_sid(sid))
    return {"status": session_service.snapshot(_sid(sid))["state"]}

@app.post("/api/session/stop")
def session_stop(sid: str = "main"):
    session_service.stop(_sid(sid))
    return {"status": "stop"}

@app.post("/api/session/next")
def session_next(sid: str = "main"):
    session_service.next(_sid(sid))
    return {"status": "next_track", "session": session_service.snapshot(_sid(sid))}

@app.post("/api/session/previous")
def session_previous(sid: str = "main"):
    session_service.previous(_sid(sid))
    return {"status": "previous_track", "session": session_service.snapshot(_sid(sid))}

@app.post("/api/session/seek")
def session_seek(payload: dict = Body(...), sid: str = "main"):
    seconds = payload.get("seconds", 0)
    session_service.seek(seconds, _sid(sid))
    return {"status": "ok", "position": seconds}

@app.post("/api/session/play_index")
def session_play_index(payload: dict = Body(...), sid: str = "main"):
    idx = payload.get("index", 0)
    session_service.play_index(int(idx), _sid(sid))
    return {"status": "playing", "session": session_service.snapshot(_sid(sid))}

# ── STREAMING DIRECTO DE ARCHIVOS (Range para seek) ──────────

# formatos que ningún navegador puede decodificar → transcode ffmpeg a MP3
TRANSCODE_EXTS = {'.wma', '.ape', '.wv', '.w64'}

@app.get("/api/music/stream")
def stream_file(file: str):
    root = Path(settings.MUSIC_DIR).resolve()
    target = (root / file).resolve()
    if not str(target).startswith(str(root) + os.sep):
        return JSONResponse({"error": "ruta fuera de la biblioteca"}, status_code=400)
    if not target.is_file():
        return JSONResponse({"error": "archivo no encontrado"}, status_code=404)
    if target.suffix.lower() in TRANSCODE_EXTS:
        proc = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(target),
             "-vn", "-c:a", "libmp3lame", "-b:a", "160k", "-f", "mp3", "pipe:1"],
            stdout=subprocess.PIPE)
        def gen():
            try:
                yield from proc.stdout
            finally:
                if proc.poll() is None:
                    proc.terminate()
        return StreamingResponse(gen(), media_type="audio/mpeg")
    media_type = mimetypes.guess_type(str(target))[0] or "audio/mpeg"
    return FileResponse(target, media_type=media_type)

# ── ENDPOINT DE IA (Lenguaje Natural → Acción) ──────────────

def _criterios_del_mensaje(msg: str) -> dict:
    """Lee cantidad y BPM directamente del texto del usuario. El modelo pequeno
    alucina bpm/mood y no siempre devuelve 'limit', asi que el texto manda."""
    import re as _re
    import unicodedata as _ud
    m = _ud.normalize("NFD", (msg or "").lower())
    m = "".join(c for c in m if c.isalnum() or c in " -:")
    m = _ud.normalize("NFC", m)
    out = {}
    mc = _re.search(r"(\d{1,3})\s*(?:canciones|cancion|temas|tema|pistas|pista|tracks|piezas)", m)
    if not mc:
        mc = _re.search(r"unas?\s+(\d{1,3})", m)
    if mc:
        out["limit"] = max(1, min(400, int(mc.group(1))))
    mr = _re.search(r"(\d{2,3})\s*(?:y|a|-|al)\s*(\d{2,3})\s*(?:bpm|pulsaciones|golpes)", m)
    if not mr:
        mr = _re.search(r"entre\s+(\d{2,3})\s+y\s+(\d{2,3})", m)
    if mr:
        lo, hi = sorted((int(mr.group(1)), int(mr.group(2))))
        out["bpm_min"], out["bpm_max"] = lo, hi
    else:
        mb = _re.search(r"(\d{2,3})\s*(?:bpm|pulsaciones|golpes)", m)
        if mb:
            out["bpm"] = int(mb.group(1))
    return out


@app.get("/api/session/fx_queue")
def session_fx_queue():
    """Cola de efectos/SFX (packs de libreria) separada de la musica."""
    return {"files": session_service.fx_queue()}


@app.post("/api/chat")
async def chat_command(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"message": "Invalid JSON"}, status_code=400)

    chat_sid = _sid(payload.get("sid") if isinstance(payload.get("sid"), str) else "main")
    user_message = payload.get("message", "")
    logger.info(f"DEBUG: Mensaje de usuario: {user_message}")

    # 1. Extraer intención
    intent: dict
    if user_message.startswith("FORM_ACTION:"):
        intent = payload.get("direct_params", {})
        if not isinstance(intent, dict):
            intent = {"action": "error", "message": "Invalid params format"}
    else:
        intent = llm_agent.parse_intent(user_message)

    logger.info(f"DEBUG: Intención extraída: {intent}")

    # Corrección flow: el modelo pequeño inventa criterios ante peticiones de
    # "algo que encaje ahora". Si el mensaje habla de continuidad y no menciona
    # un BPM explicito, se descarta el bpm alucinado (el genero se conserva).
    if intent.get("action") == "smart_playlist" and not user_message.startswith("FORM_ACTION:"):
        import re as _re
        m = user_message.lower()
        if _re.search(r"encaje|encaja|flow|sigue|siguiente|despu[eé]s|continu|ahora|sonando", m) \
                and not _re.search(r"\d{2,3}\s*bpm|bpm\s*\d{2,3}", m):
            params = intent.get("params") or {}
            if not isinstance(params, dict):
                params = {}
            import unicodedata as _ud
            def _acento(t):
                t = _ud.normalize("NFD", t)
                return "".join(c for c in t if c.isalnum() and not _ud.category(c).startswith("M"))
            m_norm = _acento(m)
            changed = params.pop("bpm", None) is not None
            for campo in ("genre", "mood"):
                v = params.get(campo)
                if v and _acento(str(v)).lower() not in m_norm:
                    params.pop(campo); changed = True
            if changed:
                intent["params"] = params
                logger.info(f"DEBUG: criterios alucinados eliminados para peticion de flow: {intent}")

    # 2. Ejecutar acción mapeada
    action = intent.get("action", "")
    response_msg = "Comando no comprendido."

    try:
        if action == "play":
            session_service.play(chat_sid)
            response_msg = "▶️ Reproducción iniciada."
        elif action == "pause":
            session_service.pause(chat_sid)
            response_msg = "⏸️ Música pausada."
        elif action == "stop":
            session_service.stop(chat_sid)
            response_msg = "⏹️ Reproducción detenida."
        elif action == "next":
            session_service.next(chat_sid)
            response_msg = "⏭️ Siguiente pista."
        elif action == "previous":
            idx = session_service.snapshot(chat_sid)["queue_index"]
            session_service.play_index(max(0, idx - 1), chat_sid)
            response_msg = "⏮️ Pista anterior."
        elif action == "play_target":
            target = intent.get("target", "")
            from sqlalchemy import create_engine, or_
            from sqlalchemy.orm import sessionmaker
            from models.database import TrackMetadata
            engine = create_engine(settings.DB_URL)
            session = sessionmaker(bind=engine)()
            like = f"%{target}%"
            hit = session.query(TrackMetadata).filter(or_(
                TrackMetadata.artist.ilike(like),
                TrackMetadata.title.ilike(like),
            )).first()
            if hit:
                session_service.play_file(hit.file, chat_sid)
                response_msg = f"Reproduciendo: {hit.artist or '?'} - {hit.title or hit.file}"
            else:
                response_msg = f"No encontré '{target}' en la biblioteca local."
            session.close()
        elif action == "volume":
            vol = intent.get("value", 50)
            mpd_service.set_volume(int(vol))
            response_msg = f"Volumen ajustado a {vol}%."
        elif action == "smart_playlist":
            import random
            params = intent.get("params", {})
            if not isinstance(params, dict):
                params = {}
            if not user_message.startswith("FORM_ACTION:"):
                # el texto del usuario manda sobre lo que el modelo invento
                detectados = _criterios_del_mensaje(user_message)
                for clave in ("bpm", "bpm_min", "bpm_max"):
                    if clave not in detectados:
                        params.pop(clave, None)
                        intent.pop("limit", None)
                params.update(detectados)
                import unicodedata as _ud2
                def _sin_acento(t):
                    t = _ud2.normalize("NFD", str(t).lower())
                    return "".join(c for c in t if c.isalnum() and not _ud2.category(c).startswith("M"))
                msg_norm = _sin_acento(user_message)
                if params.get("mood") and _sin_acento(params["mood"]) not in msg_norm:
                    params.pop("mood")
                intent["params"] = params
                logger.info(f"DEBUG: criterios normalizados: {intent}")
            from sqlalchemy import or_, func
            from sqlalchemy.orm import sessionmaker
            from models.database import TrackMetadata, make_engine
            from services.dj_flow import current_track, taste_maps, played_today, rank_candidates

            engine = make_engine(settings.DB_URL)
            Session = sessionmaker(bind=engine)
            session = Session()

            query = session.query(TrackMetadata)
            # genero y mood van en UN solo OR: si se filtran en AND, un mood que no
            # existe como tag vacia la lista (pasaba con 'trip hop relajado')
            estilos = [v for v in (params.get("genre"), params.get("mood")) if v]
            if estilos:
                conds = []
                for v in estilos:
                    like = f"%{v}%"
                    conds += [
                        TrackMetadata.genre.ilike(like),
                        TrackMetadata.mood.ilike(like),
                        TrackMetadata.file.ilike(like),
                        TrackMetadata.keywords.ilike(like),
                        TrackMetadata.description.ilike(like),
                    ]
                query = query.filter(or_(*conds))
            if params.get("bpm_min") or params.get("bpm_max"):
                lo = params.get("bpm_min") or 0
                hi = params.get("bpm_max") or 999
                try:
                    query = query.filter(TrackMetadata.bpm.between(float(lo) - 2, float(hi) + 2))
                except (TypeError, ValueError):
                    pass
            elif params.get("bpm"):
                bpm = params["bpm"]
                # ventana amplia: el scoring de flow decide el orden, no el filtro
                query = query.filter(TrackMetadata.bpm.between(bpm-25, bpm+25))

            raw_limit = params.get("limit") or intent.get("limit") or 20
            try:
                limit_val = max(1, min(400, int(float(raw_limit))))
            except (TypeError, ValueError):
                limit_val = 20
            pool = query.order_by(func.random()).limit(max(400, limit_val * 4)).all()

            # fuera los packs de samples/SFX: no son canciones, contaminan las listas
            import re as _re_sfx
            patron_sfx = _re_sfx.compile(
                r"(SDU_|_FX_|FX_Loop|_Loop_|one_shot|Samples?/|Loops?/|Stems?/|_BPM|_bpm)", _re_sfx.I)
            def _es_sample(t):
                # pack de samples/SFX: el patron de fichero solo descarta si ademas
                # no tiene nombre de artista o dura como un loop (<2 min). asi una
                # cancion real guardada en una carpeta 'Samples' se conserva.
                art = (t.artist or "").strip().lower()
                sin_nombre = (not art) or art in ("desconocido", "unknown", "n/a", "va", "various artists")
                corta = (t.duration or 0) < 120
                if patron_sfx.search(t.file or ""):
                    return sin_nombre or corta
                return sin_nombre and (t.duration or 0) < 100
            pool = [t for t in pool if not _es_sample(t)]

            cur = current_track(engine)
            if pool and cur and cur[3]:
                taste = taste_maps(engine)
                today = played_today(engine)
                files = rank_candidates(cur, pool, taste, today, limit_val)
                n = session_service.load_playlist(files, shuffle=False, sid=chat_sid)
                if estilos:
                    response_msg = (
                        f"Lista de {n} canciones de {' / '.join(estilos)}, ordenadas para "
                        f"encajar con {cur[1] or '?'} - {cur[2] or cur[0]} (tempo y clave compatibles)."
                    )
                else:
                    response_msg = (
                        f"Flow DJ: {n} pistas ordenadas para encajar con "
                        f"{cur[1] or '?'} - {cur[2] or cur[0]} (tempo y clave compatibles)."
                    )
            elif pool:
                scored = sorted(pool, key=lambda t: (t.play_count or 0) + random.uniform(0, 1))
                n = session_service.load_playlist([t.file for t in scored[:limit_val]], shuffle=False, sid=chat_sid)
                estilo = params.get("genre") or params.get("mood") or "tus criterios"
                response_msg = f"Lista de {n} canciones de {estilo} cargada y sonando (priorizando temas menos escuchados)."
            else:
                response_msg = "No encontré nada que encaje exactamente con esos parámetros en la biblioteca."
            session.close()
        elif action == "propose_playlist":
            params = intent.get("params", {})
            from sqlalchemy import create_engine, func, or_
            from sqlalchemy.orm import sessionmaker
            from models.database import TrackMetadata

            engine = create_engine(settings.DB_URL)
            Session = sessionmaker(bind=engine)
            session = Session()

            query = session.query(TrackMetadata)
            if params.get("genre"):
                g = f"%{params['genre']}%"
                query = query.filter(or_(
                    TrackMetadata.genre.ilike(g),
                    TrackMetadata.mood.ilike(g),
                    TrackMetadata.file.ilike(g)
                ))
            if params.get("mood"):
                m = f"%{params['mood']}%"
                query = query.filter(or_(
                    TrackMetadata.mood.ilike(m),
                    TrackMetadata.file.ilike(m)
                ))
            if params.get("bpm"):
                query = query.filter(TrackMetadata.bpm.between(params['bpm']-15, params['bpm']+15))

            results = query.order_by(TrackMetadata.play_count.asc(), func.random()).limit(10).all()

            if results:
                list_str = "\n".join([f"- {r.artist or '?'} - {r.title or r.file}" for r in results])
                response_msg = f"**Propuesta de Selección UMA:**\n\nHe seleccionado estos 10 temas que encajan con tu búsqueda:\n\n{list_str}\n\n¿Quieres que los cargue todos o prefieres ajustar algo?"
            else:
                response_msg = "No encontré temas que encajen para hacerte una propuesta ahora mismo."
            session.close()
        elif action == "shuffle_all":
            n = session_service.shuffle_all()
            response_msg = f"Radio completa: {n} pistas en aleatorio, sonando."
        else:
            response_msg = f"Acción '{action}' no reconocida."

    except Exception as e:
        logger.error(f"Error ejecutando acción {action}: {e}")
        response_msg = f"Error técnico: {str(e)}"

    return {
        "intent": intent,
        "message": response_msg
    }

# ── WEBSOCKET (estado de la SESIÓN en tiempo real) ───────────

@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    sid = websocket.query_params.get("sid", "main") or "main"
    await websocket.accept()
    try:
        while True:
            try:
                snap = session_service.snapshot(sid)
                await websocket.send_json({
                    "status": {
                        "state": snap["state"],
                        "elapsed": snap["position"],
                        "playlistlength": str(snap["queue_len"]),
                        "song": str(snap["queue_index"]),
                        "error": None,
                    },
                    "current": {
                        "file": snap["file"],
                        "artist": snap["artist"],
                        "title": snap["title"],
                        "duration": snap["duration"],
                    },
                    "session": snap,
                })
            except Exception as e:
                await websocket.send_json({
                    "status": {"error": str(e)},
                    "current": {"error": str(e)},
                })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("Cliente WebSocket desconectado.")
    except Exception as e:
        logger.error(f"Error crítico en WebSocket: {e}")

# Servir frontend
frontend_path = os.path.join(os.path.dirname(__file__), "../web/dist")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
