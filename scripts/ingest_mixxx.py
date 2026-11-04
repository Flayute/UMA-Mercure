#!/usr/bin/env python3
"""Ingestia datos DJ de Mixxx a la DB de UMA (uma.db).

Fuente: la DB de Mixxx (~/.mixxx/mixxxdb.sqlite) se abre SIEMPRE en modo
read-only. Mezcla dos cosas:

1. METADATOS REALES -> track_metadata: bpm, clave musical (convertida a
   notacion Camelot), genero (solo si esta vacio), play_count y last_played
   desde el registro de reproduccion de Mixxx. Sobrescribe bpm/musical_key
   existentes porque los valores viejos fueron alucinados por un tagger LLM.
2. HISTORIA DJ -> tablas nuevas en uma.db:
     dj_history  : tracklists reales de sesion (playlists con nombre fechado
                   tipo '2026-02-07 #2', con posicion y hora de anadido)
     dj_crates   : pertenencias de crate (file, crate)
     dj_cues     : hot cues / loops guardados (puntos de mezcla reales)

Uso:
    python scripts/ingest_mixxx.py            # dry-run: informa, no escribe
    python scripts/ingest_mixxx.py --apply    # escribe en data/uma.db

Reejecutable: las tablas dj_* se reconstruyen completas en cada --apply; los
UPDATE de track_metadata solo tocan filas donde Mixxx tiene valor real.
"""

import argparse
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_UMA_DB = os.path.join(REPO, "data", "uma.db")
DEFAULT_MIXXX_DB = os.path.expanduser("~/.mixxx/mixxxdb.sqlite")

# Clave Mixxx (nota+modo) -> Camelot. 8A=Am, 8B=C, rueda por quintas.
CAMELOT = {
    "Am": "8A", "C": "8B",
    "Em": "9A", "G": "9B",
    "Bm": "10A", "D": "10B",
    "F#m": "11A", "A": "11B",
    "C#m": "12A", "E": "12B",
    "G#m": "1A", "Abm": "1A", "G#": "1B", "Ab": "1B",
    "D#m": "2A", "Ebm": "2A", "D#": "2B", "Eb": "2B",
    "A#m": "3A", "Bbm": "3A", "A#": "3B", "Bb": "3B",
    "Fm": "4A", "F": "4B",
    "Cm": "5A", "Cb": "5B", "B": "5B",
    "Gm": "6A", "Gb": "6B", "F#": "6B",
    "Dm": "7A", "Db": "7B", "C#": "7B",
}

# Tipos de cue de Mixxx (enum CueType): 1 hot cue, 2 cue point de guia,
# 4 beatgrid, 6/7/8 intro/outro+loops automaticos. Se guardan crudos.
CUE_TYPES_KEPT = {1, 2, 6, 7, 8}  # el beatgrid (4) no aporta estilo DJ


def music_dir():
    """Raiz de la fonoteca: env MUSIC_DIR o el api/.env del repo."""
    d = os.environ.get("MUSIC_DIR")
    if d:
        return d.rstrip("/") + "/"
    env_path = os.path.join(REPO, "api", ".env")
    try:
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith("MUSIC_DIR="):
                    d = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return d.rstrip("/") + "/"
    except FileNotFoundError:
        pass
    sys.exit("No puedo determinar MUSIC_DIR (define el env o crea api/.env)")


def rel_path(location, prefix):
    if location.startswith(prefix):
        return location[len(prefix):]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true",
                    help="escribe en uma.db (por defecto solo informa)")
    ap.add_argument("--mixxx-db", default=DEFAULT_MIXXX_DB)
    ap.add_argument("--uma-db", default=DEFAULT_UMA_DB)
    args = ap.parse_args()

    prefix = music_dir()
    mx = sqlite3.connect(f"file:{args.mixxx_db}?mode=ro", uri=True)
    mx.row_factory = sqlite3.Row
    uma = sqlite3.connect(args.uma_db, timeout=30)
    uma.execute("PRAGMA busy_timeout=15000")

    # id Mixxx -> path relativo uma.db
    id2rel = {}
    for r in mx.execute("SELECT id, location FROM track_locations"):
        rel = rel_path(r["location"], prefix)
        if rel:
            id2rel[r["id"]] = rel

    # ---- 1. metadatos reales hacia track_metadata
    upd_bpm = upd_key = upd_genre = upd_play = 0
    meta_updates = []  # (bpm|None, camelot|None, genre|None, plays|None, played_at|None, rel)
    seen = set()
    # library.location es una FK a track_locations.id, no la ruta
    for r in mx.execute(
        "SELECT tl.location AS loc, l.artist, l.genre, l.bpm, l.key, "
        "l.timesplayed, l.last_played_at "
        "FROM library l JOIN track_locations tl ON tl.id = l.location"
    ):
        rel = rel_path(r["loc"], prefix)
        if rel is None or rel in seen:
            continue
        seen.add(rel)
        bpm = float(r["bpm"]) if r["bpm"] and r["bpm"] > 0 else None
        camelot = CAMELOT.get(r["key"] or "")
        genre = (r["genre"] or "").strip() or None
        plays = int(r["timesplayed"] or 0) or None
        meta_updates.append((bpm, camelot, genre, plays, r["last_played_at"], rel))

    existing = {row[0]: row for row in uma.execute(
        "SELECT file, bpm, musical_key, genre, play_count FROM track_metadata")}
    applied = []
    for bpm, camelot, genre, plays, played_at, rel in meta_updates:
        if rel not in existing:
            continue
        cur_bpm, cur_key, cur_genre, cur_plays = existing[rel][1:5]
        sets, vals = [], []
        if bpm is not None and bpm != cur_bpm:
            sets.append("bpm=?"); vals.append(bpm); upd_bpm += 1
        if camelot is not None and camelot != cur_key:
            sets.append("musical_key=?"); vals.append(camelot); upd_key += 1
        if genre is not None and not cur_genre:
            sets.append("genre=?"); vals.append(genre); upd_genre += 1
        if plays is not None and (cur_plays or 0) < plays:
            sets.append("play_count=?"); vals.append(plays)
            if played_at:
                sets.append("last_played=?"); vals.append(played_at)
            upd_play += 1
        if sets:
            vals.append(rel)
            applied.append((f"UPDATE track_metadata SET {', '.join(sets)} WHERE file=?", vals))

    # ---- 2. tablas dj_*
    hist = []  # (session, added_at, pos, file)
    for r in mx.execute(
        "SELECT p.name AS s, pt.position AS pos, pt.pl_datetime_added AS ts, "
        "tl.location AS loc "
        "FROM PlaylistTracks pt JOIN Playlists p ON p.id=pt.playlist_id "
        "JOIN track_locations tl ON tl.id=pt.track_id "
        "WHERE p.name GLOB '20*' ORDER BY p.name, pt.position"
    ):
        rel = rel_path(r["loc"], prefix)
        if rel:
            hist.append((r["s"], r["ts"], r["pos"], rel))

    crates = []
    for r in mx.execute(
        "SELECT c.name AS crate, tl.location AS loc FROM crate_tracks ct "
        "JOIN crates c ON c.id=ct.crate_id JOIN track_locations tl ON tl.id=ct.track_id"
    ):
        rel = rel_path(r["loc"], prefix)
        if rel:
            crates.append((r["crate"], rel))

    cues = []
    for r in mx.execute(
        "SELECT tl.location AS loc, cu.type AS type, cu.position AS pos, "
        "cu.length AS len, cu.label AS label FROM cues cu "
        "JOIN track_locations tl ON tl.id=cu.track_id WHERE cu.type IN ({})".format(
            ",".join(str(t) for t in sorted(CUE_TYPES_KEPT)))
    ):
        rel = rel_path(r["loc"], prefix)
        if rel:
            cues.append((rel, r["type"], r["pos"], r["len"], r["label"]))

    hist_days = len({h[0].split(" #")[0] for h in hist})
    print(f"mixxx->uma: {len(id2rel)} pistas mapeadas")
    print(f"track_metadata: UPDATEs bpm={upd_bpm} musical_key={upd_key} "
          f"genre={upd_genre} play_count={upd_play}  ({len(applied)} sentencias)")
    print(f"dj_history: {len(hist)} filas ({hist_days} dias de sesion)")
    print(f"dj_crates: {len(crates)} filas")
    print(f"dj_cues: {len(cues)} filas")

    if not args.apply:
        print("dry-run: nada escrito. Usa --apply para escribir.")
        return

    cur = uma.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS dj_history (
        session TEXT NOT NULL, added_at TEXT, pos INTEGER, file TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS dj_crates (
        crate TEXT NOT NULL, file TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS dj_cues (
        file TEXT NOT NULL, cue_type INTEGER, position REAL, length REAL, label TEXT)""")
    cur.execute("DELETE FROM dj_history")
    cur.execute("DELETE FROM dj_crates")
    cur.execute("DELETE FROM dj_cues")
    cur.executemany("INSERT INTO dj_history VALUES (?,?,?,?)", hist)
    cur.executemany("INSERT INTO dj_crates VALUES (?,?)", crates)
    cur.executemany("INSERT INTO dj_cues VALUES (?,?,?,?,?)", cues)
    for sql, vals in applied:
        cur.execute(sql, vals)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dj_history_file ON dj_history(file)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dj_crates_file ON dj_crates(file)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dj_cues_file ON dj_cues(file)")
    uma.commit()
    print("aplicado y confirmado.")


if __name__ == "__main__":
    main()
