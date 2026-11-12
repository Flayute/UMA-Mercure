"""Limpieza conservadora del campo artist: artefactos de canal/VEVO/Official/HD, guiones
finales, 'Feat' colgado, y variantes de V/A. Merge con el nombre canonico si ya existe;
la descripcion canonica gana si existe. Backup antes, verificacion despues."""
import os, re, shutil, sqlite3
import os
D = os.environ.get("UMA_DATA", os.path.expanduser("~/UMA-Mercure/data"))
db = os.path.join(D, "uma.db")
bak = os.path.join(D, "uma.db.bak-before-limpiar-artistas-2026-11-12")
if not os.path.exists(bak):
    shutil.copy2(db, bak)
    print("backup:", bak)

c = sqlite3.connect(db, timeout=30)
c.execute("PRAGMA busy_timeout=30000")

SUF = re.compile(r"(\s+|[-–])?(VEVO|Official Video|Official|Fan Channel|Channel|HD)\s*$", re.I)
DASH = re.compile(r"\s*[-–]\s*$")
# 'ft' solo si va separado (asi 'Bugge Wesseltoft' o 'Holon & Hovercraft' no se cortan)
FEAT = re.compile(r"(\s+|,)\s*(feat\.?|ft\.?|featuring)\s*$", re.I)
# "(Feat Someone)" / "[feat X]" colgado del nombre de artista
PAREN_FEAT = re.compile(r"\s*[\(\[]\s*(feat|ft|featuring)\s+[^\)\]]*[\)\]]\s*$", re.I)

artistas = {r[0] for r in c.execute("SELECT DISTINCT artist FROM track_metadata WHERE artist IS NOT NULL AND artist<>''")}
por_lower = {}
for a in artistas:
    por_lower.setdefault(a.lower(), []).append(a)

def canonico(n):
    """Si el nombre ya existe con otra capitalizacion, usa el que mas filas tenga."""
    variantes = por_lower.get(n.lower())
    if not variantes:
        return n
    if n in variantes:
        return n
    mejor = max(variantes, key=lambda v: c.execute("SELECT COUNT(*) FROM track_metadata WHERE artist=?", (v,)).fetchone()[0])
    return mejor

VA = {"V/A", "Various", "Various Artist", "Various Artists", "VA"}
EXTRA = {"JOKER": "Joker",                       # artefacto del reporte (productor de Bristol)
         "Beastie Boys Make Some Noise Dance Contest HD": "Beastie Boys",
         "LLORCA Official Music Channel": "LLORCA"}
# títulos-artistas de YouTube: cualquier variante de ese nombre va al artista real
PREFIJO = [("Panjabi MC 🔞 Knight Rider", "Panjabi MC")]
SKIP = {"Open Channel"}                          # puede ser un artista real, no un canal

mapa = {}
for a in artistas:
    if a in SKIP:
        continue
    if a in VA:
        mapa[a] = "Various Artists"
        continue
    if a in EXTRA:
        mapa[a] = EXTRA[a]
        continue
    for pref, fijo in PREFIJO:
        if a.startswith(pref):
            mapa[a] = fijo
            break
    if a in mapa:
        continue
    n = a
    while True:
        m = SUF.search(n) or PAREN_FEAT.search(n) or FEAT.search(n) or DASH.search(n)
        if not m:
            break
        nuevo = n[:m.start()].strip(" -–,")
        if not nuevo or nuevo == n:
            break
        n = nuevo
    n = canonico(n)
    if n != a and n:
        mapa[a] = n

print("a renombrar:", len(mapa))
for a, n in list(mapa.items())[:20]:
    print("   -", repr(a)[:48], "->", repr(n)[:38])

import sys
if "dry" in sys.argv:
    print("DRY RUN: no se escribe nada")
    c.close()
    raise SystemExit(0)

hechos = 0
for viejo, nuevo in mapa.items():
    filas_v = c.execute("SELECT id, description, keywords FROM track_metadata WHERE artist=?", (viejo,)).fetchall()
    if not filas_v:
        continue
    canon = c.execute("SELECT description, keywords FROM track_metadata WHERE artist=? AND description IS NOT NULL LIMIT 1", (nuevo,)).fetchone()
    if canon and (canon[0] or "").strip() and canon[0].strip() != "?":
        desc, kw = canon[0], canon[1]
    else:
        desc = kw = None
    for vid, vd, vk in filas_v:
        if canon:
            c.execute("UPDATE track_metadata SET artist=?, description=COALESCE(?, description), keywords=COALESCE(?, keywords) WHERE id=?",
                      (nuevo, desc, kw, vid))
        else:
            c.execute("UPDATE track_metadata SET artist=? WHERE id=?", (nuevo, vid))
        hechos += 1
    if canon and not (canon[0] or "").strip():
        # el canonico no tenia bio: heredar la del alias
        heredar = [f for f in filas_v if (f[1] or "").strip() and f[1].strip() != "?"]
        if heredar:
            c.execute("UPDATE track_metadata SET description=?, keywords=? WHERE artist=? AND (description IS NULL OR description='')",
                      (heredar[0][1], heredar[0][2], nuevo))
    c.commit()

print("filas renombradas:", hechos)
restantes = [a for a in mapa if c.execute("SELECT COUNT(*) FROM track_metadata WHERE artist=?", (a,)).fetchone()[0]]
print("alias que aun quedan (deben ser 0):", len(restantes), restantes[:5])
print("artistas distintos ahora:", c.execute("SELECT COUNT(DISTINCT artist) FROM track_metadata WHERE artist IS NOT NULL AND artist<>''").fetchone()[0])
print("filas totales:", c.execute("SELECT COUNT(*) FROM track_metadata").fetchone()[0])
print("filas con desc real:", c.execute("SELECT COUNT(*) FROM track_metadata WHERE description IS NOT NULL AND description NOT IN ('','?')").fetchone()[0])
print("artistas con desc real:", c.execute("SELECT COUNT(DISTINCT artist) FROM track_metadata WHERE description IS NOT NULL AND description NOT IN ('','?')").fetchone()[0])

print("\ncomprobacion de los 4 del reporte:")
for a in ["HooverphonicVEVO", "Queen Official", "The Five Corners Quintet Feat", "JOKER"]:
    n = c.execute("SELECT COUNT(*) FROM track_metadata WHERE artist=?", (a,)).fetchone()[0]
    print("   ", a, "-> filas restantes:", n)
for a in ["Hooverphonic", "Queen", "The Five Corners Quintet", "Joker", "Various Artists", "Chase & Status", "John Digweed", "St Germain", "Parov Stelar"]:
    r = c.execute("SELECT COUNT(*), MAX(CASE WHEN description IS NOT NULL AND description NOT IN ('','?') THEN 1 ELSE 0 END) FROM track_metadata WHERE artist=?", (a,)).fetchone()
    print("   ", a, "| filas", r[0], "| con bio", "si" if r[1] else "no")
c.close()
