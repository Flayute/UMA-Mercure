"""Sesiones de reproducción multi-dispositivo (sin MPD): cada sesión tiene su
cola y su reloj en SQLite; los navegadores se unen por defecto a la sesión
'main' y pueden bifurcarla ('fork') para reproducir en paralelo sin molestar.
Cada navegador reproduce el archivo real vía HTTP Range y sincroniza su
posición con el snapshot de SU sesión."""
import asyncio
import logging
import os
import random
import secrets
import time
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from core.config import settings
from models.database import TrackMetadata, RadioQueue, SessionState

logger = logging.getLogger("uvicorn.error")  # para que el journal vea info/warning

DEFAULT_DURATION = 300.0  # fallback mientras ffprobe no haya rellenado duration


class SessionService:
    DEFAULT = "main"

    def __init__(self, db_path: str):
        from models.database import make_engine
        self.engine = make_engine(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self.db_path = db_path

    # ── estado ────────────────────────────────────────────────
    def _row(self, s, sid):
        row = s.query(SessionState).filter_by(sid=sid).first()
        if not row:
            row = SessionState(sid=sid, state="stop", queue_index=0, offset=0.0,
                               started_at=0.0, shuffle=1, repeat=1)
            s.add(row)
            s.commit()
        return row

    @staticmethod
    def _pos(row):
        return row.offset + (time.time() - row.started_at) if row.state == "play" else row.offset

    def position(self, sid=DEFAULT):
        s = self.Session()
        pos = self._pos(self._row(s, sid))
        s.close()
        return pos

    def snapshot(self, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        total = s.query(func.count(RadioQueue.id)).filter(RadioQueue.sid == sid).scalar() or 0
        cur = s.query(RadioQueue).filter_by(sid=sid, pos=row.queue_index).first() if total else None
        file = cur.file if cur else None
        track = s.query(TrackMetadata).filter_by(file=file).first() if file else None
        dur = (track.duration if track and track.duration else DEFAULT_DURATION)
        pos = self._pos(row)
        snap = {
            "sid": sid,
            "state": row.state if file else "stop",
            "file": file,
            "artist": track.artist if track else None,
            "title": track.title if track else None,
            "duration": dur,
            "position": min(pos, dur) if file else 0.0,
            "queue_index": row.queue_index,
            "queue_len": total,
            "shuffle": bool(row.shuffle),
            "repeat": bool(row.repeat),
        }
        s.close()
        return snap

    def list_sessions(self):
        s = self.Session()
        out = []
        for row in s.query(SessionState).order_by(SessionState.id).all():
            total = s.query(func.count(RadioQueue.id)).filter(RadioQueue.sid == row.sid).scalar() or 0
            cur = s.query(RadioQueue).filter_by(sid=row.sid, pos=row.queue_index).first() if total else None
            track = s.query(TrackMetadata).filter_by(file=cur.file).first() if cur else None
            out.append({
                "sid": row.sid,
                "state": row.state,
                "title": track.title if track else None,
                "artist": track.artist if track else None,
                "queue_len": total,
                "queue_index": row.queue_index,
            })
        s.close()
        return {"sessions": out}

    def queue_view(self, sid=DEFAULT, limit=200):
        s = self.Session()
        row = self._row(s, sid)
        rows = (s.query(RadioQueue, TrackMetadata)
                .outerjoin(TrackMetadata, RadioQueue.file == TrackMetadata.file)
                .filter(RadioQueue.sid == sid)
                .order_by(RadioQueue.pos).limit(limit).all())
        items = [{"index": r0.pos, "file": r0.file,
                  "artist": tm.artist if tm else None,
                  "title": tm.title if tm else None} for r0, tm in rows]
        s.close()
        return {"current_index": row.queue_index, "items": items}

    # ── acciones ──────────────────────────────────────────────
    def _set_queue(self, s, sid, files):
        s.query(RadioQueue).filter(RadioQueue.sid == sid).delete()
        for i, f in enumerate(files):
            s.add(RadioQueue(sid=sid, pos=i, file=f))
        s.commit()

    def play_file(self, file, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        self._set_queue(s, sid, [file])
        row.queue_index = 0
        row.offset = 0.0
        row.started_at = time.time()
        row.state = "play"
        s.commit()
        s.close()
        return True

    def add_files(self, files, sid=DEFAULT):
        s = self.Session()
        self._row(s, sid)
        base = s.query(func.max(RadioQueue.pos)).filter(RadioQueue.sid == sid).scalar()
        base = (base + 1) if base is not None else 0
        for i, f in enumerate(files[:2000]):
            s.add(RadioQueue(sid=sid, pos=base + i, file=f))
        s.commit()
        s.close()
        return True

    def shuffle_all(self, sid=DEFAULT):
        s = self.Session()
        files = [r[0] for r in s.query(TrackMetadata.file).order_by(func.random()).all()]
        random.shuffle(files)
        row = self._row(s, sid)
        self._set_queue(s, sid, files)
        row.shuffle, row.repeat = 1, 1
        row.queue_index = 0
        row.offset = 0.0
        row.started_at = time.time()
        row.state = "play"
        s.commit()
        s.close()
        return len(files)

    def load_playlist(self, files, shuffle=False, sid=DEFAULT):
        """Cola nueva desde resultados (smart_playlist) y reproduce."""
        s = self.Session()
        if shuffle:
            files = list(files)
            random.shuffle(files)
        row = self._row(s, sid)
        self._set_queue(s, sid, files)
        row.queue_index = 0
        row.offset = 0.0
        row.started_at = time.time()
        row.state = "play"
        s.commit()
        s.close()
        return len(files)

    def fork(self, from_sid=DEFAULT):
        """Nueva sesión independiente que copia la cola y la posición actual."""
        s = self.Session()
        src = self._row(s, from_sid)
        new_sid = secrets.token_hex(4)
        rows = s.query(RadioQueue).filter(RadioQueue.sid == from_sid).order_by(RadioQueue.pos).all()
        for r in rows:
            s.add(RadioQueue(sid=new_sid, pos=r.pos, file=r.file))
        s.add(SessionState(sid=new_sid, state=src.state, queue_index=src.queue_index,
                           offset=self._pos(src), started_at=time.time(),
                           shuffle=src.shuffle, repeat=src.repeat))
        s.commit()
        s.close()
        logger.info(f"Sesión bifurcada: {from_sid} → {new_sid} ({len(rows)} pistas)")
        return new_sid

    def play(self, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        if row.state != "play":
            row.started_at = time.time()
            row.state = "play"
            s.commit()
        s.close()
        return True

    def pause(self, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        if row.state == "play":
            row.offset += time.time() - row.started_at
            row.state = "pause"
            s.commit()
        s.close()
        return True

    def stop(self, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        row.offset = 0.0
        row.started_at = 0.0
        row.state = "stop"
        s.commit()
        s.close()
        return True

    def seek(self, seconds, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        row.offset = max(0.0, float(seconds))
        if row.state == "play":
            row.started_at = time.time()
        s.commit()
        s.close()
        return True

    def _advance(self, s, row):
        """Pista terminada de SU sesión: suma play_count y pasa a la siguiente."""
        sid = row.sid
        cur = s.query(RadioQueue).filter_by(sid=sid, pos=row.queue_index).first()
        if cur:
            tm = s.query(TrackMetadata).filter_by(file=cur.file).first()
            if tm:
                tm.play_count = (tm.play_count or 0) + 1
                tm.last_played = datetime.now().isoformat()
        total = s.query(func.count(RadioQueue.id)).filter(RadioQueue.sid == sid).scalar() or 0
        nxt = row.queue_index + 1
        if nxt >= total:
            if row.repeat:
                nxt = 0
            else:
                row.state = "stop"
                row.offset = 0.0
                row.queue_index = 0
                s.commit()
                return
        row.queue_index = nxt
        row.offset = 0.0
        row.started_at = time.time()
        s.commit()

    def next(self, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        was_playing = row.state == "play"
        if not was_playing:
            row.state = "play"
        self._advance(s, row)
        if not was_playing:
            row = self._row(s, sid)
            row.started_at = time.time()
            s.commit()
        s.close()
        return True

    def previous(self, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        total = s.query(func.count(RadioQueue.id)).filter(RadioQueue.sid == sid).scalar() or 0
        if row.queue_index > 0:
            row.queue_index -= 1
        elif row.repeat and total > 0:
            row.queue_index = total - 1
        row.offset = 0.0
        row.started_at = time.time() if row.state == "play" else 0.0
        s.commit()
        s.close()
        return True

    def play_index(self, index, sid=DEFAULT):
        s = self.Session()
        row = self._row(s, sid)
        row.queue_index = max(0, int(index))
        row.offset = 0.0
        row.started_at = time.time()
        row.state = "play"
        s.commit()
        s.close()
        return True

    def drop_session(self, sid):
        """Elimina una sesión paralela (nunca 'main')."""
        if sid == self.DEFAULT:
            return False
        s = self.Session()
        s.query(SessionState).filter(SessionState.sid == sid).delete()
        s.query(RadioQueue).filter(RadioQueue.sid == sid).delete()
        s.commit()
        s.close()
        return True

    # ── reloj ─────────────────────────────────────────────────
    async def ticker(self):
        """Avanza pistas de TODAS las sesiones activas cuando la posición supera
        la duración y salta archivos inexistentes (p. ej. HDD desconectado)."""
        while True:
            try:
                s = self.Session()
                for row in s.query(SessionState).filter(SessionState.state == "play").all():
                    cur = s.query(RadioQueue).filter_by(sid=row.sid, pos=row.queue_index).first()
                    if cur is None:
                        row.state = "stop"
                        s.commit()
                        continue
                    tm = s.query(TrackMetadata).filter_by(file=cur.file).first()
                    dur = tm.duration if tm and tm.duration else DEFAULT_DURATION
                    pos = self._pos(row)
                    full = os.path.join(settings.MUSIC_DIR, cur.file)
                    if not os.path.exists(full):
                        logger.warning(f"Sesión {row.sid}: archivo inexistente, salto: {cur.file}")
                        self._advance(s, row)
                    elif pos >= dur:
                        logger.info(f"Sesión {row.sid}: fin de pista → {cur.file}")
                        self._advance(s, row)
                s.close()
            except Exception as e:
                logger.error(f"Session ticker error: {e}")
            await asyncio.sleep(2)
