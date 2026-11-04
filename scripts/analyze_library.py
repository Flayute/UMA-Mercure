#!/usr/bin/env python3
"""Analizador masivo de metadatos para la fonoteca (UMА Mercure).

Recorre una carpeta de música y por cada pista:
  - limpia el nombre (ruido de YouTube/quality tags), opcionalmente renombra;
  - detecta BPM, clave musical (nota + modo + notación Camelot) y energía
    usando librosa sobre una ventana representativa;
  - escribe tags permanentes (TBPM/TKEY/COMM en MP3, bpm/initialkey en FLAC),
    opcionalmente;
  - guarda el resultado en SQLite y en un CSV.

Herencia: "SCRIPT_DE_ANALISIS_TOTAL.py" pulido a lo largo de meses; esta
versión añade resume, modo dry-run, Camelot, detección major/minor, conexión
única a DB y flags explícitos para las operaciones destructivas.

Dependencias: pip install librosa mutagen pandas numpy
Reproductor DJ: las claves Camelot (1A-13A / 1B-13B) permiten mezclas
compatibles (mismo número = mezcla segura, +1 = transición ascendente).

Uso:
  python3 scripts/analyze_library.py --folder /media/user/Music
  python3 scripts/analyze_library.py --folder ... --resume --limit 500
  python3 scripts/analyze_library.py --folder ... --rename --convert --tags
"""
import argparse
import os
import re
import sqlite3
import subprocess
import sys
import time

from mutagen.id3 import ID3, TKEY, TBPM, COMM
from mutagen.flac import FLAC

AUDIO_EXTS = ('.mp3', '.flac', '.wav', '.aif', '.aiff', '.m4a', '.aac',
              '.ogg', '.opus', '.webm', '.wma', '.mka')
NATIVE_EXTS = ('.mp3', '.flac', '.wav', '.aif', '.aiff', '.m4a', '.aac',
               '.ogg', '.opus')
SESSION_SECONDS = 660  # pistas más largas se tratan como sesiones/mixes

NOTAS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
# Camelot: la rueda avanza por quintas (C=8B, G=9B... Am=8A...)
CAMELOT_MAJOR = {'C': '8B', 'G': '9B', 'D': '10B', 'A': '11B', 'E': '12B', 'B': '1B',
                 'F#': '2B', 'C#': '3B', 'G#': '4B', 'D#': '5B', 'A#': '6B', 'F': '7B'}
CAMELOT_MINOR = {'A': '8A', 'E': '9A', 'B': '10A', 'F#': '11A', 'C#': '12A', 'G#': '1A',
                 'D#': '2A', 'A#': '3A', 'F': '4A', 'C': '5A', 'G': '6A', 'D': '7A'}
# Perfiles Krumhansl-Schmuckler (tonalidad)
PROFILE_MAJOR = [6.35, 2.23, 1.55, 0.71, 1.18, 1.35, 1.05, 1.55, 0.90, 0.61, 0.49, 0.04]
PROFILE_MINOR = [6.33, 0.68, 1.04, 0.70, 0.79, 1.17, 0.51, 0.93, 0.67, 1.11, 0.93, 0.52]


def init_db(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''CREATE TABLE IF NOT EXISTS songs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE,
        path TEXT UNIQUE,
        bpm INTEGER,
        key TEXT,
        camelot TEXT,
        energy TEXT,
        llm_context TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_filename ON songs(filename)')
    conn.commit()
    return conn


def load_done(conn):
    """Paths ya analizados (para --resume)."""
    return {r[0] for r in conn.execute("SELECT path FROM songs")}


def save_to_db(conn, filename, path, bpm, key, camelot, energy):
    ctx = f"Song: {filename}. BPM {bpm}, Key {key}, Camelot {camelot}, Energy {energy}."
    conn.execute(
        'INSERT OR REPLACE INTO songs (filename, path, bpm, key, camelot, energy, llm_context) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (filename, path, int(bpm) if str(bpm).isdigit() else 0, key, camelot, energy, ctx))


def limpiar_nombre_logica(nombre_archivo):
    """Limpia ruido de YouTube/quality tags conservando la extensión."""
    nombre, ext = os.path.splitext(nombre_archivo)
    nombre = re.sub(r'[\(\[].*?\d+kbit_.*?[\)\]]', '', nombre)
    nombre = re.sub(r'\(1080p.*?128kbit_AAC\)', '', nombre)
    nombre = re.sub(r'\s*\(?Official\s*(Audio|Video|Music Video)?\)?', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\s*-\s*Topic', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'[-_][a-zA-Z0-9_-]{11}$', '', nombre)  # ids de YouTube
    nombre = re.sub(r'https?://\S+', '', nombre)
    nombre = re.sub(r'\s+', ' ', nombre).strip()
    nombre = re.sub(r'\s*-\s*$', '', nombre)
    return f"{nombre}{ext}"


def detectar_clave(chroma_mean):
    """Krumhansl-Schmuckler sobre chroma: nota + modo + Camelot."""
    import numpy as np
    best = None
    for i in range(12):
        corr_maj = float(np.dot(np.roll(chroma_mean, i), PROFILE_MAJOR))
        corr_min = float(np.dot(np.roll(chroma_mean, i), PROFILE_MINOR))
        if best is None or max(corr_maj, corr_min) > best[0]:
            best = (max(corr_maj, corr_min), NOTAS[i], 'major' if corr_maj > corr_min else 'minor')
    _, nota, modo = best
    camelot = CAMELOT_MAJOR[nota] if modo == 'major' else CAMELOT_MINOR[nota]
    key = f"{nota} {modo}"
    return key, camelot


def analizar_pista(ruta, attempt=1):
    """BPM, clave (nota+modo+Camelot) y energía sobre una ventana de 45s."""
    import librosa
    import numpy as np
    try:
        duracion = librosa.get_duration(path=ruta)
        if duracion > SESSION_SECONDS:
            return "SESSION", "SESSION", "SESSION", "SESSION"

        offsets = [30, 60, 90]
        offset = offsets[attempt - 1] if attempt <= len(offsets) else 30
        if duracion < offset + 45:
            offset = 0

        y, sr = librosa.load(ruta, duration=45, offset=offset)
        if len(y) == 0 or np.max(np.abs(y)) < 1e-4:
            if attempt < 3 and duracion > 120:
                return analizar_pista(ruta, attempt + 1)
            return None, None, None, None

        bpm = None
        try:
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            if np.mean(onset_env) < 0.1:
                if attempt < 3:
                    return analizar_pista(ruta, attempt + 1)
                return "AMBIENT", "AMBIENT", "AMBIENT", "AMBIENT"
            tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            bpm_val = float(np.mean(tempo))
            if not np.isnan(bpm_val):
                # colapsa octavas a rango DJ útil (70-180)
                while bpm_val > 180:
                    bpm_val /= 2
                while bpm_val < 70:
                    bpm_val *= 2
                bpm = round(bpm_val)
        except Exception:
            return None, None, None, None

        key, camelot = None, None
        try:
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr, bins_per_octave=12)
            key, camelot = detectar_clave(np.mean(chroma, axis=1))
        except Exception:
            pass

        energy = "Unknown"
        try:
            avg_rms = float(np.mean(librosa.feature.rms(y=y)))
            energy = "Low" if avg_rms < 0.05 else ("Medium" if avg_rms < 0.15 else "High")
        except Exception:
            pass

        return bpm, key, camelot, energy
    except Exception as e:
        print(f"   -> [ERROR ANALISIS] {os.path.basename(ruta)}: {e}")
        return None, None, None, None


def convertir_a_mp3(ruta_orig):
    """Convierte a MP3 320k conservando metadatos; solo con --convert."""
    ruta_nueva = os.path.splitext(ruta_orig)[0] + '.mp3'
    if os.path.exists(ruta_nueva):
        print(f"   -> [SALTO CONV] ya existe {os.path.basename(ruta_nueva)}")
        return ruta_orig
    print(f"   -> [CONVIRTIENDO] {os.path.basename(ruta_orig)} -> MP3 320k")
    try:
        subprocess.run(['ffmpeg', '-y', '-i', ruta_orig, '-b:a', '320k',
                        '-map_metadata', '0', ruta_nueva],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(ruta_nueva):
            os.remove(ruta_orig)  # destructivo: solo tras conversión exitosa
            return ruta_nueva
    except Exception as e:
        print(f"   -> [ERROR CONVERSION] {e}")
    return ruta_orig


def escribir_tags(ruta, bpm, key, camelot, energy):
    if bpm == "SESSION" or not bpm:
        return
    try:
        if ruta.lower().endswith('.mp3'):
            try:
                audio = ID3(ruta)
            except Exception:
                audio = ID3()
            audio['TBPM'] = TBPM(encoding=3, text=str(bpm))
            audio['TKEY'] = TKEY(encoding=3, text=str(key))
            audio.delall('COMM')
            desc = f"Key: {key} | Camelot: {camelot}"
            if energy:
                desc += f" | Energy: {energy}"
            audio.add(COMM(encoding=3, lang='eng', desc='Comment', text=desc))
            audio.save(ruta, v2_version=3)
        elif ruta.lower().endswith('.flac'):
            audio = FLAC(ruta)
            audio['bpm'] = str(bpm)
            audio['initialkey'] = str(key)
            audio['camelotkey'] = str(camelot)
            if energy:
                audio['comment'] = f"Energy: {energy}"
            audio.save()
    except Exception as e:
        print(f"   -> [ERROR TAGS] {os.path.basename(ruta)}: {e}")


def escanear_carpeta(carpeta):
    archivos = []
    for root, _, files in os.walk(carpeta):
        for f in sorted(files):
            if f.lower().endswith(AUDIO_EXTS):
                archivos.append({'Nombre_Archivo': f,
                                 'Ruta_Completa': os.path.join(root, f),
                                 'Formato': os.path.splitext(f)[1].upper()})
    return archivos


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--folder', help='carpeta de música a analizar')
    ap.add_argument('--csv', help='CSV de entrada (sep ";", col Ruta_Completa) '
                                  'en lugar de escanear una carpeta')
    ap.add_argument('--out', default='UMA_ANALYSIS_RESULTS.csv', help='CSV de salida')
    ap.add_argument('--db', default=os.path.join(os.path.dirname(__file__), '..', 'data',
                                                 'uma_memory.db'), help='SQLite de resultados')
    ap.add_argument('--resume', action='store_true', help='saltar pistas ya en la DB')
    ap.add_argument('--limit', type=int, help='máximo de pistas a procesar')
    ap.add_argument('--rename', action='store_true', help='renombrar con nombre limpio '
                                                         '(destructivo: no pisa ficheros existentes)')
    ap.add_argument('--convert', action='store_true', help='convertir formatos no nativos a '
                                                           'MP3 320k y borrar el original (destructivo)')
    ap.add_argument('--tags', action='store_true', help='escribir BPM/clave/energía dentro '
                                                        'de los archivos (destructivo)')
    ap.add_argument('--dry-run', action='store_true', help='analiza pero no escribe nada')
    args = ap.parse_args()

    if args.dry_run:
        args.rename = args.convert = args.tags = False

    if args.folder:
        origen = args.folder
        if not os.path.isdir(origen):
            sys.exit(f"[SISTEMA] carpeta inexistente: {origen}")
        pistas = escanear_carpeta(origen)
    elif args.csv:
        import pandas as pd
        df = pd.read_csv(args.csv, sep=';')
        pistas = df.to_dict('records')
    else:
        ap.error('usa --folder o --csv')

    if args.limit:
        pistas = pistas[:args.limit]

    print(f"[SISTEMA] {len(pistas)} pistas; flags: rename={args.rename} convert={args.convert} "
          f"tags={args.tags} dry_run={args.dry_run} resume={args.resume}")

    db_path = os.path.abspath(args.db)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = init_db(db_path)
    done = load_done(conn) if args.resume else set()

    resultados = []
    t0 = time.time()
    for i, row in enumerate(pistas, 1):
        ruta = row.get('Ruta_Completa')
        nombre = row.get('Nombre_Archivo') or os.path.basename(ruta)
        if not ruta or not os.path.exists(ruta):
            continue
        if ruta in done:
            continue

        nombre_limpio = limpiar_nombre_logica(nombre)
        if args.rename and ruta != os.path.join(os.path.dirname(ruta), nombre_limpio):
            nueva = os.path.join(os.path.dirname(ruta), nombre_limpio)
            if not os.path.exists(nueva):
                try:
                    os.rename(ruta, nueva)
                    ruta = nueva
                    print(f"[LIMPIO] {nombre_limpio}")
                except OSError:
                    pass

        ext = os.path.splitext(ruta)[1].lower()
        if args.convert and ext not in NATIVE_EXTS:
            ruta = convertir_a_mp3(ruta)
            nombre_limpio = os.path.basename(ruta)

        bpm, key, camelot, energy = analizar_pista(ruta)

        # fallback de análisis por conversión (solo si se permite convertir)
        if bpm is None and args.convert and ext in ('.m4a', '.aac', '.wav', '.flac', '.aif', '.aiff'):
            ruta2 = convertir_a_mp3(ruta)
            if ruta2 != ruta:
                ruta = ruta2
                nombre_limpio = os.path.basename(ruta)
                bpm, key, camelot, energy = analizar_pista(ruta)

        if bpm:
            if args.tags:
                escribir_tags(ruta, bpm, key, camelot, energy)
            if not args.dry_run:
                save_to_db(conn, nombre_limpio, ruta, bpm, key, camelot, energy)
                if i % 50 == 0:
                    conn.commit()
            print(f"[{i}/{len(pistas)}] {bpm} BPM | {key} ({camelot}) | {energy} | {nombre_limpio}")

        resultados.append({'Nombre_Limpio': nombre_limpio, 'BPM': bpm, 'Key': key,
                           'Camelot': camelot, 'Energy': energy, 'Ruta': ruta})

    conn.commit()
    conn.close()

    import pandas as pd
    pd.DataFrame(resultados).to_csv(args.out, index=False, sep=';')
    mins = (time.time() - t0) / 60
    print(f"\n[SISTEMA COMPLETADO] {len(resultados)} analizadas en {mins:.1f} min")
    print(f"[REPORTE] CSV: {os.path.abspath(args.out)} | DB: {db_path}")


if __name__ == '__main__':
    main()
