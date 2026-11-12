"""Puebla fx_queue con los packs de efectos/SFX. No borra nada de track_metadata."""
import sqlite3, re

import os
DB = os.environ.get("UMA_DB", os.path.expanduser("~/UMA-Mercure/data/uma.db"))
PATRON = re.compile(r"(SDU_|_FX_|FX_Loop|_Loop_|one_shot|Samples?/|Loops?/|Stems?/|_BPM|AAC_|DAT2_|Syn_Bass)", re.I)

c = sqlite3.connect(DB)
c.execute("CREATE TABLE IF NOT EXISTS fx_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, file TEXT UNIQUE)")
rows = c.execute("SELECT file, duration FROM track_metadata WHERE artist IS NULL OR artist='' OR artist='Desconocido'").fetchall()
fx = [f for f, d in rows if PATRON.search(f or "") or (d or 0) < 120]
print("efectos detectados:", len(fx))
for i in range(0, len(fx), 500):
    c.executemany("INSERT OR IGNORE INTO fx_queue (file) VALUES (?)", [(f,) for f in fx[i:i + 500]])
    c.commit()
print("filas en fx_queue:", c.execute("SELECT COUNT(*) FROM fx_queue").fetchone()[0])
print("filas de musica restantes:", c.execute("SELECT COUNT(*) FROM track_metadata WHERE file NOT IN (SELECT file FROM fx_queue)").fetchone()[0])
c.close()
