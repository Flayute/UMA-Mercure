#!/usr/bin/env python3
"""Repara artista/título invertidos en data/uma.db.

Origen del problema: el historial de YouTube (Titulo_Cancion.txt) usa el orden
"Título - Canal"; la DB antigua guardó ese nombre en `filename` y
import_legacy_db.py lo parseó asumiendo "Artista - Título", cruzando los campos
en las pistas descargadas (~500 filas).

La reparación re-deriva artist/title de los tags ID3/Vorbis reales del fichero
(mutagen) y, si no hay tags, del basename del path (que siempre tuvo el orden
correcto "Artista - Título"). Por defecto solo informa; --apply escribe.

Uso:
  python3 scripts/fix_artist_title.py            # dry-run (informativo)
  python3 scripts/fix_artist_title.py --apply    # escribe en la DB
Dependencias: mutagen (usa el venv del analizador o el de la API con mutagen).
"""
import argparse
import os
import sqlite3

from mutagen import File as MutagenFile

DB_DEFAULT = os.path.join(os.path.dirname(__file__), '..', 'data', 'uma.db')


def tags_reales(ruta):
    if not os.path.exists(ruta):
        return None, None
    try:
        mf = MutagenFile(ruta)
        if mf is None:
            return None, None
        t = mf.tags
        if t is None:
            return None, None
        title = artist = None
        for key in ('TITL2ALB', 'TITL', 'title', 'TITLE'):
            try:
                v = t.get(key)
                if v:
                    title = str(v[0] if isinstance(v, list) else v).strip()
                    break
            except Exception:
                pass
        for key in ('TPE1', 'artist', 'ARTIST'):
            try:
                v = t.get(key)
                if v:
                    artist = str(v[0] if isinstance(v, list) else v).strip()
                    break
            except Exception:
                pass
        return artist or None, title or None
    except Exception:
        return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', default=DB_DEFAULT)
    ap.add_argument('--music-root', help='raíz donde resolver file (default: cwd)')
    ap.add_argument('--apply', action='store_true', help='escribir en la DB')
    ap.add_argument('--limit', type=int)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db, timeout=30)
    rows = conn.execute("SELECT id, file, artist, title FROM track_metadata").fetchall()

    cambios = 0
    for rid, rel, artist, title in rows:
        base = os.path.splitext(os.path.basename(rel))[0]
        parts = base.split(' - ', 1)
        base_artist = parts[0].lstrip('0123456789. ') if len(parts) == 2 else None
        base_title = parts[1].strip() if len(parts) == 2 else base

        full = os.path.join(args.music_root or '.', rel)
        tag_artist, tag_title = tags_reales(full)
        best_artist = tag_artist or base_artist
        best_title = tag_title or base_title
        if not best_artist or not best_title:
            continue

        # solo tocar filas donde lo guardado NO concuerda con la mejor fuente
        na, nt = artist or '', title or ''
        if best_artist.lower() in na.lower() and best_title.lower() in nt.lower():
            continue  # ya correcto o mejor información (tags) disponible
        # caso de inversión: lo guardado cruza campo con la mejor fuente
        if na.lower() == best_title.lower() or nt.lower() == best_artist.lower():
            cambios += 1
            print(f"[INVERTIDA] {rel[-60:]}\n   antes: A={na[:45]!r} T={nt[:45]!r}\n   ahora: A={best_artist[:45]!r} T={best_title[:45]!r}")
            if args.apply:
                conn.execute("UPDATE track_metadata SET artist=?, title=? WHERE id=?",
                             (best_artist, best_title, rid))
        elif args.apply and (na == 'Desconocido' or na.lower() not in best_artist.lower()):
            cambios += 1
            conn.execute("UPDATE track_metadata SET artist=?, title=? WHERE id=?",
                         (best_artist, best_title, rid))
        if args.limit and cambios >= args.limit:
            break

    if args.apply:
        conn.commit()
    conn.close()
    print(f"\n{'APLICADO' if args.apply else 'DRY-RUN'}: {cambios} filas{' corregidas' if args.apply else ' a corregir'}")


if __name__ == '__main__':
    main()
