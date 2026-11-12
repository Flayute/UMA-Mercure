"""Pilot real: iTunes Search API (gratis, sin key) sobre pistas reales de la fonoteca.
Mide cuantas encuentra y que genero devuelve Apple."""
import json, re, sqlite3, time, unicodedata, urllib.parse, urllib.request

def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if c.isalnum() or c == " ")
    return re.sub(r"\s+", " ", s).strip()

def similar(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    return len(ta & tb) >= max(1, min(len(ta), len(tb)) - 1)

def itunes(term):
    url = "https://itunes.apple.com/search?term=" + urllib.parse.quote(term) + "&entity=musicTrack&limit=3"
    req = urllib.request.Request(url, headers={"User-Agent": "uma-radio-fonoteca/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read()).get("results", [])

c = sqlite3.connect(os.environ.get("UMA_DB", os.path.expanduser("~/UMA-Mercure/data/uma.db")))
filas = c.execute("""SELECT artist, title, genre FROM track_metadata
                     WHERE file NOT IN (SELECT file FROM fx_queue)
                       AND artist NOT IN ('Desconocido','') AND artist IS NOT NULL
                       AND title IS NOT NULL AND title<>'' AND duration>100
                     ORDER BY play_count DESC NULLS LAST, RANDOM() LIMIT 25""").fetchall()
print("muestra:", len(filas))

encontradas = 0
generos = {}
for artist, title, genre_actual in filas:
    term = "%s %s" % (artist, title)
    try:
        res = itunes(term)
    except Exception as e:
        print("  ! %s -> fallo %s" % (term[:40], e)); time.sleep(0.6); continue
    hit = next((r for r in res if similar(title, r.get("trackName")) and similar(artist.split("(")[0], r.get("artistName"))), None)
    time.sleep(0.55)
    if hit:
        encontradas += 1
        g = hit.get("primaryGenreName") or "?"
        generos[g] = generos.get(g, 0) + 1
        print("  OK %-34s | db: %-18s | apple: %-18s | %s" % (("%s - %s" % (artist, title))[:34], (genre_actual or "-")[:18], g, hit.get("collectionName", "")[:28]))
    else:
        print("  -- %-34s | db: %-18s | 0 coincidencias (%s resultados)" % (("%s - %s" % (artist, title))[:34], (genre_actual or "-")[:18], len(res)))

print("\nencontradas: %d/%d (%.0f%%)" % (encontradas, len(filas), 100 * encontradas / len(filas)))
print("generos apple devueltos:", generos)
