#!/usr/bin/env python3
"""Watch en vivo: vigila la DB de Mixxx (ro) durante una sesion de DJ en curso.

Detecta pistas anadidas a la playlist de history del dia (en Mixxx 2.5 el
history es automatic y se materializa como una playlist llamada YYYY-MM-DD)
y cambios en library.last_played_at. Append de eventos a data/live_session.jsonl
y re-ingesta uma.db (ingest_mixxx.py --apply) cada REINGEST_segundos.

Uso: python scripts/session_watcher.py          # hasta que se mate el proceso
     --once                                   # un solo ciclo (para probar)
"""

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MIXXX_DB = os.path.expanduser("~/.mixxx/mixxxdb.sqlite")
LOG_PATH = os.path.join(REPO, "data", "live_session.jsonl")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=int, default=20)
    ap.add_argument("--reingest", type=int, default=300)
    args = ap.parse_args()

    today = dt.date.today().isoformat()
    seen_pl = set()      # (playlist, track_id) ya registrados
    seen_play = {}       # track_id -> ultimo last_played_at visto
    last_reingest = 0.0

    def rel(loc):
        try:
            with open(os.path.join(REPO, "api", ".env"), encoding="utf-8") as fh:
                for line in fh:
                    if line.strip().startswith("MUSIC_DIR="):
                        p = line.split("=", 1)[1].strip().strip('"').strip("'").rstrip("/") + "/"
                        return loc[len(p):] if loc.startswith(p) else None
        except FileNotFoundError:
            pass
        return None

    def emit(event):
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    while True:
        try:
            mx = sqlite3.connect(f"file:{MIXXX_DB}?mode=ro", uri=True)
            cur = mx.cursor()
            # 1) filas nuevas en playlists fechadas
            for pl, tid, ts, loc, pos in cur.execute(
                "SELECT p.name, pt.track_id, pt.pl_datetime_added, tl.location, pt.position "
                "FROM PlaylistTracks pt JOIN Playlists p ON p.id=pt.playlist_id "
                "JOIN track_locations tl ON tl.id=pt.track_id "
                "WHERE p.name GLOB '20*'"
            ):
                if (pl, tid) in seen_pl:
                    continue
                seen_pl.add((pl, tid))
                if pl == today or (ts or "").startswith(today):
                    r = rel(loc)
                    if r:
                        emit({"event": "added", "session": pl, "ts": ts,
                              "file": r, "pos": pos})
                        print(f"[{ts}] + {r}", flush=True)
            # 2) last_played_at que avanza (pista terminada de reproducir)
            for tid, played_at, loc in cur.execute(
                "SELECT id, last_played_at, NULL FROM library "
                "WHERE last_played_at IS NOT NULL AND last_played_at LIKE ?||'%'"
            , (today,)):
                if seen_play.get(tid) == played_at:
                    continue
                first = tid not in seen_play
                seen_play[tid] = played_at
                if first:
                    continue
                mxl = mx.execute("SELECT location FROM track_locations WHERE id=?", (tid,)).fetchone()
                r = rel(mxl[0]) if mxl else None
                if r:
                    emit({"event": "played", "ts": played_at, "file": r})
                    print(f"[{played_at}] > {r}", flush=True)
            mx.close()
        except sqlite3.OperationalError as e:
            print("mixxx db bloqueada (la escribe Mixxx):", e, flush=True)

        now = time.time()
        if now - last_reingest >= args.reingest:
            last_reingest = now
            subprocess.run([sys.executable, os.path.join(HERE, "ingest_mixxx.py"), "--apply"],
                           capture_output=True)
            print(f"[{dt.datetime.now():%H:%M:%S}] uma.db re-ingestada", flush=True)
        if args.once:
            break
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
