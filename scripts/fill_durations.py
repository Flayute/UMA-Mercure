#!/usr/bin/env python3
"""Rellena track_metadata.duration con ffprobe (para el reloj de la sesión).
Reejecutable: solo procesa filas con duration NULL."""
import os
import sqlite3
import subprocess
import sys
import time

DB = os.path.join(os.path.dirname(__file__), "..", "data", "uma.db")
# Ruta de música: env MUSIC_DIR (api/.env) o placeholder por defecto
MD = os.environ.get("MUSIC_DIR", "")
if not MD:
    _envp = os.path.join(os.path.dirname(__file__), "..", "api", ".env")
    if os.path.exists(_envp):
        with open(_envp) as _f:
            MD = dict(l.split("=", 1) for l in _f.read().splitlines() if "=" in l).get("MUSIC_DIR", "")
MD = MD or "/media/<usuario>/Seagate Expansion Drive"

def main():
    db = sqlite3.connect(DB, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=20000")
    rows = db.execute("select id, file from track_metadata where duration is null").fetchall()
    t0 = time.time()
    done = skipped = 0
    for rid, f in rows:
        full = os.path.join(MD, f)
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", full],
                capture_output=True, text=True, timeout=15)
            d = float(out.stdout.strip())
            db.execute("update track_metadata set duration=? where id=?", (d, rid))
            done += 1
        except Exception:
            skipped += 1
        if done % 500 == 0:
            db.commit()
            print(f"{done} rellenadas · {skipped} omitidas · {time.time()-t0:.0f}s", flush=True)
    db.commit()
    print(f"done: {done} rellenadas, {skipped} omitidas, {time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
