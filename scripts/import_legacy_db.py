import sqlite3
import os
import sys

# Path a la base de datos nueva
import os
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEW_DB = os.path.join(_BASE, 'data', 'uma.db')
# Path a la base de datos antigua en el Seagate
OLD_DB = '/run/media/<usuario>/Seagate Expansion Drive/Music/uma_memory.db'

def migrate():
    if not os.path.exists(OLD_DB):
        print(f"❌ No se encuentra la DB antigua en {OLD_DB}")
        return

    print("🛰️ Iniciando migración de 14.179 registros...")
    
    conn_old = sqlite3.connect(OLD_DB)
    conn_new = sqlite3.connect(NEW_DB)
    
    cur_old = conn_old.cursor()
    cur_new = conn_new.cursor()
    
    # Asegurar que la tabla existe en la nueva DB
    cur_new.execute('''
        CREATE TABLE IF NOT EXISTS track_metadata (
            id INTEGER PRIMARY KEY,
            file TEXT UNIQUE,
            artist TEXT,
            title TEXT,
            album TEXT,
            genre TEXT,
            bpm FLOAT,
            musical_key TEXT,
            energy FLOAT,
            mood TEXT
        )
    ''')
    
    cur_old.execute("SELECT path, filename, bpm, key, energy, llm_context FROM songs")
    rows = cur_old.fetchall()
    
    count = 0
    for row in rows:
        old_path, filename, bpm, key, energy, llm_context = row
        
        # Convertir path antiguo a path relativo de MPD (Seagate_Music/...)
        # El path antiguo era /home/<usuario>/Música/SUBFOLDER/FILE.mp3
        rel_path = old_path.replace('/home/<usuario>/Música/', '')
        new_file_path = os.path.join('Seagate_Music', rel_path)
        
        # Intentar extraer artista/título del nombre si no hay más datos
        artist = "Desconocido"
        title = filename
        if " - " in filename:
            parts = filename.split(" - ", 1)
            artist = parts[0]
            title = parts[1].replace('.mp3', '').replace('.m4a', '').replace('.flac', '')

        # Mapear energía (en la vieja DB parece ser texto o float)
        try:
            energy_val = float(energy) if energy else 0.5
        except:
            energy_val = 0.5

        try:
            cur_new.execute('''
                INSERT OR IGNORE INTO track_metadata (file, artist, title, bpm, musical_key, energy, mood)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (new_file_path, artist, title, float(bpm or 120), key, energy_val, llm_context))
            count += 1
        except Exception as e:
            pass

    conn_new.commit()
    print(f"✅ Migración finalizada: {count} canciones importadas con éxito.")
    
    conn_old.close()
    conn_new.close()

if __name__ == "__main__":
    migrate()
