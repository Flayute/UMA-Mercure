import sys
import os
import json
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Añadir el path de la API para importar modelos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../api')))

from models.database import TrackMetadata, init_db
from services.mpd_client import MPDService
from core.config import settings

def tag_library():
    print("🚀 Iniciando Escaneo y Etiquetado Soberano de UMA...")
    engine = init_db()
    Session = sessionmaker(bind=engine)
    session = Session()
    
    mpd = MPDService(host=settings.MPD_HOST, port=settings.MPD_PORT)
    tracks = mpd.list_all_tracks()
    
    print(f"📦 Encontrados {len(tracks)} tracks en MPD.")
    
    for t in tracks:
        if 'file' not in t: continue
        
        file_path = t['file']
        # Saltar si ya existe en la DB
        if session.query(TrackMetadata).filter_by(file=file_path).first():
            continue
            
        artist = t.get('artist', 'Desconocido')
        title = t.get('title', os.path.basename(file_path))
        
        print(f"🧠 Analizando: {artist} - {title}...")
        
        # Consultar al LLM local para metadatos sugeridos
        prompt = (
            f"Analiza esta canción y devuelve un JSON con: genre, mood, energy (0.0-1.0), bpm (int).\n"
            f"Canción: {artist} - {title}\n"
            f"Responde ÚNICAMENTE el JSON."
        )
        
        try:
            res = requests.post(
                f"{settings.LLAMA_SERVER_URL}/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                },
                timeout=10
            )
            content = res.json()["choices"][0]["message"]["content"]
            # Limpiar por si el modelo añade texto
            import re
            match = re.search(r'(\{.*\})', content, re.DOTALL)
            if match:
                meta = json.loads(match.group(1))
                
                track_meta = TrackMetadata(
                    file=file_path,
                    artist=artist,
                    title=title,
                    album=t.get('album'),
                    genre=meta.get('genre', 'General'),
                    bpm=float(meta.get('bpm', 120)),
                    energy=float(meta.get('energy', 0.5)),
                    mood=meta.get('mood', 'Normal')
                )
                session.add(track_meta)
                session.commit()
                print(f"✅ Etiquetado: {meta.get('genre')} | {meta.get('bpm')} BPM")
            else:
                print(f"⚠️ El modelo no devolvió JSON válido para {title}")
        except Exception as e:
            print(f"❌ Error analizando {title}: {e}")
            session.rollback()

    print("🏁 Proceso de etiquetado finalizado.")

if __name__ == "__main__":
    tag_library()
