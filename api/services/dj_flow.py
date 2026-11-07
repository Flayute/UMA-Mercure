"""Scoring de "flow" DJ: candidatos que encajan con la pista que suena.

El perfil se deriva del historial REAL de sesiones (tabla dj_history,
ingestada desde Mixxx): las transiciones medidas son 86% con |delta BPM| <= 6
(mediana delta 0: mezclas a mismo tempo) y solo 20% compat Camelot estricta.
Por eso el scoring es BPM-primario y la clave musical es bonus, nunca filtro.
"""

import random
from sqlalchemy import text

DEFAULT_SID = "main"


def current_track(engine, sid=DEFAULT_SID):
    """(file, artist, title, bpm, musical_key, genre) de la pista actual o None."""
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT m.file, m.artist, m.title, m.bpm, m.musical_key, m.genre "
            "FROM session_state s JOIN radio_queue q "
            "  ON q.sid = s.sid AND q.pos = s.queue_index "
            "LEFT JOIN track_metadata m ON m.file = q.file "
            "WHERE s.sid = :sid"
        ), {"sid": sid}).fetchone()
    return row


def taste_maps(engine):
    """Señales de gusto: pistas por sesion pasada, crates y veces pinchadas."""
    hist = {}
    crates = set()
    plays = {}
    with engine.connect() as conn:
        for f, n in conn.execute(text(
                "SELECT file, COUNT(*) FROM dj_history GROUP BY file")):
            hist[f] = n
        for (f,) in conn.execute(text("SELECT DISTINCT file FROM dj_crates")):
            crates.add(f)
        for f, p in conn.execute(text(
                "SELECT file, play_count FROM track_metadata WHERE play_count > 0")):
            plays[f] = p
    return {"hist": hist, "crates": crates, "plays": plays}


def played_today(engine, sid=DEFAULT_SID):
    """Pistas ya sonadas hoy (sesion en curso + history de hoy): no repetir."""
    files = set()
    with engine.connect() as conn:
        for (f,) in conn.execute(text(
                "SELECT file FROM radio_queue WHERE sid = :sid"), {"sid": sid}):
            files.add(f)
        for (f,) in conn.execute(text(
                "SELECT DISTINCT file FROM dj_history WHERE added_at >= date('now')")):
            files.add(f)
        for (f,) in conn.execute(text(
                "SELECT file FROM track_metadata WHERE last_played >= date('now')")):
            files.add(f)
    return files


def _bpm_score(cur, cand):
    if not cur or not cand:
        return 0.35  # sin dato: neutro, no penaliza
    d = abs(cand - cur)
    if d <= 2:
        return 1.0
    if d <= 4:
        return 0.85
    if d <= 6:
        return 0.7
    if d <= 10:
        return 0.45
    if d <= 14:
        return 0.25
    if abs(cand - cur * 2) <= 6 or abs(cand - cur / 2) <= 6:
        return 0.25  # salto de octava (doble/mitad): valido pero nunca preferido
    return 0.05


def _cam_num(key):
    """'9A' -> 9; None si no es notacion Camelot."""
    if not key or len(key) < 2:
        return None
    try:
        return int(key[:-1])
    except ValueError:
        return None


def _key_score(cur, cand):
    if not cur or not cand:
        return 0.4
    if cur == cand:
        return 0.9
    a, b = _cam_num(cur), _cam_num(cand)
    if a is None or b is None:
        return 0.2
    diff = (b - a) % 12
    if diff in (1, 11):
        return 0.8   # vecinos en la rueda de quintas
    if a == b:
        return 0.7   # mismo numero, relativo menor/mayor
    if diff in (2, 10):
        return 0.35
    return 0.1


def score_track(current, cand, taste, played_today_set):
    """current: fila de current_track(); cand: TrackMetadata. Devuelve float 0..1."""
    _, c_artist, _, c_bpm, c_key, _ = current
    bpm_s = _bpm_score(c_bpm, cand.bpm)
    key_s = _key_score(c_key, cand.musical_key)
    hist = taste["hist"].get(cand.file, 0)
    crate = 1 if cand.file in taste["crates"] else 0
    plays = taste["plays"].get(cand.file, 0)
    taste_s = min(1.0, 0.45 * min(hist / 3.0, 1.0) + 0.25 * crate + 0.3 * min(plays / 4.0, 1.0))
    if cand.file in played_today_set:
        nov = 0.0
    else:
        nov = max(0.0, 1.0 - min(0.5, plays / 20.0))
    if c_artist and cand.artist and cand.artist.lower() == c_artist.lower():
        nov *= 0.4
    return 0.5 * bpm_s + 0.15 * key_s + 0.25 * taste_s + 0.1 * nov


def rank_candidates(current, candidates, taste, played_today_set, limit):
    """Ordena por score (desempate aleatorio) y devuelve las mejores `limit` rutas."""
    scored = [(score_track(current, c, taste, played_today_set) + random.uniform(0, 0.02),
               c.file) for c in candidates]
    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored[:limit]]
