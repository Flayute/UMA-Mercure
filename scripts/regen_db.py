#!/usr/bin/env python3
"""Regenera track_metadata desde MPD (lsinfo "/" recursivo con tags reales en 0.24).
play_counts desde el backup. Fallback: nombre 'Artista - Título'."""
import socket, sqlite3, os

import os
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(_BASE, "data", "uma.db")
BAK = os.path.join(_BASE, "data", "uma.db.bak-regen")
EXCLUDE_ROOT = {"$RECYCLE.BIN", ".dtrash", ".fseventsd", ".Spotlight-V100"}
AUDIO = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav", ".wma", ".aiff", ".ape", ".mpc", ".mka"}

class MPD:
    def __init__(self, host="127.0.0.1", port=6600):
        self.s = socket.create_connection((host, port), timeout=60)
        self.buf = b""
        self._readline()
    def _readline(self):
        while b"\n" not in self.buf:
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode("utf-8", "replace")
    def cmd(self, command):
        self.s.sendall((command + "\n").encode("utf-8"))
        out = []
        while True:
            line = self._readline()
            if line.startswith("OK"):
                return out
            if line.startswith("ACK"):
                raise RuntimeError(line)
            out.append(line)

def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

mpd = MPD()
lines = mpd.cmd('listallinfo ""')

files = {}  # path -> tags dict
cur = None
for line in lines:
    if line.startswith("file: "):
        cur = line[6:]
        files[cur] = {}
    elif ": " in line and cur is not None:
        k, v = line.split(": ", 1)
        files[cur][k.lower()] = v

audio = {}
for f, t in files.items():
    parts = f.split("/")
    if parts[0] in EXCLUDE_ROOT:
        continue
    ext = os.path.splitext(f)[1].lower()
    if ext not in AUDIO:
        continue
    audio[f] = t
print(f"files totales: {len(files)}, audio: {len(audio)}, con artist tag: {sum(1 for t in audio.values() if t.get('artist'))}")

con = sqlite3.connect(DB)
c = con.cursor()
cols = [r[1] for r in c.execute("PRAGMA table_info(track_metadata)")]

plays = {}
bc = sqlite3.connect(BAK).cursor()
for fn, pc in bc.execute("SELECT file, play_count FROM track_metadata WHERE play_count > 0"):
    base = os.path.basename(fn)
    plays[base] = max(plays.get(base, 0), pc or 0)
print("play_counts del backup:", len(plays))

c.execute("DELETE FROM track_metadata")
inserted = tagged = 0
for f, t in audio.items():
    base = os.path.splitext(os.path.basename(f))[0]
    artist = t.get("artist")
    title = t.get("title")
    if artist and not title:
        title = base
    if not artist and " - " in base:
        artist, title = [p.strip() for p in base.split(" - ", 1)]
    if not artist:
        artist = "Desconocido"
    if not title:
        title = base
    if t.get("artist"):
        tagged += 1
    row = {
        "file": f, "artist": artist, "title": title,
        "album": t.get("album"), "genre": t.get("genre"),
        "bpm": None, "mood": None, "musical_key": None, "energy": None,
        "play_count": plays.get(os.path.basename(f), 0),
    }
    names = [col for col in cols if col in row and col != "id"]
    c.execute(f"INSERT INTO track_metadata ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
              [row[n] for n in names])
    inserted += 1
con.commit()
total = c.execute("SELECT COUNT(*) FROM track_metadata").fetchone()[0]
known = c.execute("SELECT COUNT(*) FROM track_metadata WHERE artist != 'Desconocido'").fetchone()[0]
genre = c.execute("SELECT COUNT(*) FROM track_metadata WHERE genre IS NOT NULL").fetchone()[0]
plays_n = c.execute("SELECT COUNT(*) FROM track_metadata WHERE play_count > 0").fetchone()[0]
print(f"inserted={inserted} total={total} artist_ok={known} genre_ok={genre} plays_ok={plays_n} tags_reales={tagged}")
for r in c.execute("SELECT artist, title FROM track_metadata WHERE artist LIKE '%Gramatik%' OR title LIKE '%Gramatik%' LIMIT 3"):
    print("sample:", r)
for r in c.execute("SELECT artist, title, genre FROM track_metadata WHERE genre IS NOT NULL LIMIT 3"):
    print("genre sample:", r)
con.close()
