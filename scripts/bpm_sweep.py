"""Barrido de BPM real con librosa sobre las pistas que no tienen bpm.

Se ejecuta EN LA Pi (es donde esta montado el Seagate). Lee la cola de
data/bpm-pending.json, analiza cada fichero y hace UPDATE directo en uma.db con
bpm_source='librosa'. Guarda el progreso en data/bpm-sweep-progress.json para
poder reanudar si se corta. Los ficheros ilegibles o sin beat se anotan y siguen.

Uso: python3 bpm_sweep.py [--limit N] [--dry]
"""
import json, os, sqlite3, sys, time, traceback

DB = os.environ.get("UMA_DB", os.path.expanduser("~/UMA-Mercure/data/uma.db"))
ROOT = os.environ.get("MUSIC_DIR", "/media/USUARIO/Seagate Expansion Drive/")
PENDING = os.environ.get("UMA_PENDING", os.path.expanduser("~/UMA-Mercure/data/bpm-pending.json"))
PROG = os.environ.get("UMA_PROG", os.path.expanduser("~/UMA-Mercure/data/bpm-sweep-progress.json"))
if not os.path.exists(PROG):
    PROG = os.path.expanduser("~/UMA-Mercure/data/bpm-sweep-progress.json")

import librosa

limit = None
dry = "--dry" in sys.argv
for i, a in enumerate(sys.argv):
    if a == "--limit":
        limit = int(sys.argv[i + 1])

pending = json.load(open(PENDING))
done = {}
if os.path.exists(PROG):
    done = json.load(open(PROG))
todo = [f for f in pending if f not in done]
if limit:
    todo = todo[:limit]
print("pendientes:", len(pending), "| ya hechos:", len(done), "| a procesar ahora:", len(todo), flush=True)

conn = sqlite3.connect(DB, timeout=90)
conn.execute('PRAGMA busy_timeout=90000')
t0 = time.time()
ok = miss = err = 0
for i, f in enumerate(todo):
    path = ROOT + f
    try:
        if not os.path.isfile(path):
            done[f] = {"status": "no_file"}
            miss += 1
        else:
            y, sr = librosa.load(path, sr=22050, mono=True, duration=90)
            # en librosa 1.x beat_track devuelve (tempo, beats); el tempo puede venir como array 0-d
            temp_val = librosa.beat.beat_track(y=y, sr=sr)[0]
            try:
                tempo = float(temp_val.item() if hasattr(temp_val, "item") else temp_val)
            except Exception:
                import numpy as _np
                tempo = float(_np.asarray(temp_val).reshape(-1)[0])
            if not tempo or tempo != tempo:
                done[f] = {"status": "no_beat"}
                miss += 1
            else:
                while tempo < 60:
                    tempo *= 2
                while tempo > 200:
                    tempo /= 2
                if dry:
                    print("  DRY %-70s %.2f" % (f[-70:], tempo), flush=True)
                else:
                    conn.execute("UPDATE track_metadata SET bpm=?, bpm_source='librosa' WHERE file=?",
                                 (round(tempo, 2), f))

                done[f] = {"status": "ok", "bpm": round(tempo, 2)}
                ok += 1
    except Exception as ex:
        done[f] = {"status": "error", "msg": str(ex)[:120]}
        err += 1
        if err <= 5:
            print("  ERR %s: %s" % (f[-60:], str(ex)[:90]), flush=True)
    conn.commit()
    if (i + 1) % 10 == 0:
        conn.commit()
        json.dump(done, open(PROG, "w"))
        el = time.time() - t0
        rate = (i + 1) / el
        print("[%d/%d] ok %d sin-beat %d err %d | %.2f s/pista | ETA %.0f min" %
              (i + 1, len(todo), ok, miss, err, el / (i + 1), (len(todo) - i - 1) * (el / (i + 1)) / 60), flush=True)

conn.commit()
json.dump(done, open(PROG, "w"))
q = lambda s: conn.execute(s).fetchone()[0]
print("FIN ok %d | sin beat/no existe %d | errores %d" % (ok, miss, err), flush=True)
print("bpm>0 en DB:", q("SELECT COUNT(*) FROM track_metadata WHERE bpm>0"),
      "| librosa:", q("SELECT COUNT(*) FROM track_metadata WHERE bpm_source='librosa'"), flush=True)
