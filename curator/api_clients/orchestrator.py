#!/usr/bin/env python3
"""
Orquestador de APIs de análisis musical
Coordina múltiples fuentes de datos (Last.fm, MusicBrainz, AcousticBrainz, Spotify)
para obtener los metadatos más completos posibles.
"""

import json
import logging
from typing import Dict, Optional, List, Union
from curator.api_clients.lastfm import LastFMClient
from curator.api_clients.musicbrainz import MusicBrainzClient
from curator.api_clients.acousticbrainz import AcousticBrainzClient

logger = logging.getLogger(__name__)


class MusicMetadataOrchestrator:
    """
    Orquestador que combina múltiples APIs para obtener análisis musical completo.
    
    Flujo de trabajo:
    1. Buscar pista en MusicBrainz/Last.fm para obtener MBID
    2. Consultar todas las APIs con el MBID
    3. Fusionar resultados de todas las fuentes
    4. Devolver metadatos completos
    """
    
    def __init__(self, 
                 lastfm_api_key: str = None,
                 musicbrainz_api_key: str = None,
                 acousticbrainz_api_key: str = None,
                 spotify_api_key: str = None):
        """
        Inicializa el orquestador
        
        Args:
            lastfm_api_key: API key de Last.fm (opcional)
            musicbrainz_api_key: API key de MusicBrainz (opcional)
            acousticbrainz_api_key: API key de AcousticBrainz (opcional)
            spotify_api_key: API key de Spotify (opcional)
        """
        self.lastfm = LastFMClient(api_key=lastfm_api_key)
        self.musicbrainz = MusicBrainzClient(api_key=musicbrainz_api_key)
        self.acousticbrainz = AcousticBrainzClient(api_key=acousticbrainz_api_key)
        self.spotify = None  # Spotify requiere autenticación OAuth2
        
        # Configurar logging
        self.api_usage_log = []
    
    def analyze_track(self, title: str, artist: str = None) -> Dict:
        """
        Analiza una pista usando todas las APIs disponibles
        
        Args:
            title: Título de la pista
            artist: Nombre del artista (opcional)
            
        Returns:
            Dict con todos los metadatos disponibles
        """
        logger.info(f"Starting analysis for: {title} by {artist or 'Unknown'}")
        
        # Paso 1: Buscar la pista para obtener identificador único
        track_id = self._find_track(title, artist)
        
        if not track_id or "error" in track_id:
            logger.error(f"Could not find track: {title}")
            return track_id
        
        # Paso 2: Consultar todas las APIs con el identificador
        metadata_sources = {
            "musicbrainz": self.musicbrainz.get_recording_info(track_id.get("recording_mbid", "")),
            "acousticbrainz": self.acousticbrainz.get_metadata(track_id.get("recording_mbid", "")),
            "lastfm": self.lastfm.get_track_info(track_id.get("recording_mbid", "")),
        }
        
        # Paso 3: Fusionar todos los resultados
        combined_metadata = self._merge_metadata(metadata_sources, track_id)
        
        # Paso 4: Agregar log de uso
        self._log_api_usage(title, track_id)
        
        logger.info(f"Analysis complete for: {title[:30]}...")
        return combined_metadata
    
    def analyze_from_mbid(self, recording_mbid: str) -> Dict:
        """
        Analiza una pista directamente con MBID conocido
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con todos los metadatos disponibles
        """
        logger.info(f"Analyzing track with MBID: {recording_mbid[:8]}...")
        
        metadata_sources = {
            "musicbrainz": self.musicbrainz.get_recording_info(recording_mbid),
            "acousticbrainz": self.acousticbrainz.get_metadata(recording_mbid),
        }
        
        return self._merge_metadata(metadata_sources, {"recording_mbid": recording_mbid})
    
    def analyze_from_file(self, file_path: str) -> Dict:
        """
        Analiza una pista desde un archivo de audio
        
        Args:
            file_path: Ruta al archivo de audio
            
        Returns:
            Dict con todos los metadatos disponibles
        """
        # Nota: Para leer metadados del archivo, necesitaríamos id3v2 o similar
        # Esta función se reserva para futuras implementaciones
        
        logger.warning("File analysis requires additional dependencies (id3v2)")
        return {"error": "File analysis not yet implemented"}
    
    def _find_track(self, title: str, artist: str = None) -> Dict:
        """
        Busca una pista en múltiples fuentes para obtener identificador único
        
        Args:
            title: Título de la pista
            artist: Nombre del artista (opcional)
            
        Returns:
            Dict con identificador único de la pista
        """
        # Intentar buscar en MusicBrainz
        search_result = self.musicbrainz.get_recording_by_title(title, artist)
        
        if search_result and not "error" in search_result:
            return search_result
        
        # Intentar buscar en Last.fm
        search_result = self.lastfm.search_track(title, artist)
        
        if search_result and not "error" in search_result:
            return {
                "recording_mbid": search_result.get("recording_mbid", ""),
                "title": search_result.get("title", title),
                "artist": search_result.get("artist", artist or "")
            }
        
        # Si no se encuentra, retornar el título original
        return {
            "recording_mbid": title,  # Usar título como MBID fallback
            "title": title,
            "artist": artist or "",
            "disambiguation": "Not found in databases"
        }
    
    def _merge_metadata(self, sources: Dict, track_id: Dict) -> Dict:
        """
        Fusiona metadatos de múltiples fuentes
        
        Args:
            sources: Dict con resultados de cada API
            track_id: Identificador único de la pista
            
        Returns:
            Dict con metadatos fusionados
        """
        # Inicializar estructura de metadatos
        metadata = {
            "track_id": track_id.get("recording_mbid", ""),
            "title": track_id.get("title", ""),
            "artist": track_id.get("artist", ""),
            "sources": {},
        }
        
        # Procesar cada fuente
        for source_name, result in sources.items():
            if "error" in result:
                metadata["sources"][source_name] = {"error": result["error"]}
                continue
            
            metadata["sources"][source_name] = result
            
            # Extraer campos relevantes
            if "bpm" in result:
                metadata["bpm"] = result.get("bpm")
            
            if "key" in result:
                metadata["key"] = result.get("key")
            
            if "features" in result:
                metadata["features"] = result.get("features", {})
            
            if "genres" in result:
                metadata["genres"] = result.get("genres", [])
            
            if "duration" in result:
                metadata["duration"] = result.get("duration")
        
        # Asegurar que todos los campos están presentes
        metadata.setdefault("bpm", None)
        metadata.setdefault("key", None)
        metadata.setdefault("features", {})
        metadata.setdefault("genres", [])
        
        return metadata
    
    def _log_api_usage(self, title: str, track_id: Dict):
        """
        Registra el uso de APIs para análisis y optimización
        
        Args:
            title: Título de la pista analizada
            track_id: Identificador de la pista
        """
        log_entry = {
            "track_id": track_id.get("recording_mbid", ""),
            "title": title[:100],  # Limitar longitud
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "apis_used": list(self.lastfm.api_info.get("name", "") if self.lastfm else []),
        }
        self.api_usage_log.append(log_entry)
        
        # Mantener solo los últimos 10000 registros
        if len(self.api_usage_log) > 10000:
            self.api_usage_log = self.api_usage_log[-10000:]
    
    def get_usage_statistics(self) -> Dict:
        """
        Obtiene estadísticas de uso de APIs
        
        Returns:
            Dict con estadísticas de uso
        """
        if not self.api_usage_log:
            return {"total_requests": 0}
        
        stats = {
            "total_requests": len(self.api_usage_log),
            "unique_tracks": len(set(entry["track_id"] for entry in self.api_usage_log)),
            "apis_used": {},
        }
        
        # Contar uso por API
        for entry in self.api_usage_log:
            for api in entry.get("apis_used", []):
                stats["apis_used"][api] = stats["apis_used"].get(api, 0) + 1
        
        return stats
    
    def clear_cache(self):
        """
        Limpia el caché de uso de APIs
        
        Returns:
            Número de entradas eliminadas
        """
        count = len(self.api_usage_log)
        self.api_usage_log.clear()
        return count


# Factory function for creating orchestrator instances
def create_orchestrator(lastfm_api_key: str = None,
                        musicbrainz_api_key: str = None,
                        acousticbrainz_api_key: str = None,
                        spotify_api_key: str = None) -> MusicMetadataOrchestrator:
    """
    Crea una instancia de MusicMetadataOrchestrator
    
    Args:
        lastfm_api_key: API key de Last.fm (opcional)
        musicbrainz_api_key: API key de MusicBrainz (opcional)
        acousticbrainz_api_key: API key de AcousticBrainz (opcional)
        spotify_api_key: API key de Spotify (opcional)
        
    Returns:
        Instancia de MusicMetadataOrchestrator
    """
    return MusicMetadataOrchestrator(
        lastfm_api_key=lastfm_api_key,
        musicbrainz_api_key=musicbrainz_api_key,
        acousticbrainz_api_key=acousticbrainz_api_key,
        spotify_api_key=spotify_api_key
    )


# Función de ejemplo para demostrar el uso
if __name__ == "__main__":
    # Crear orquestador sin API keys (usará versiones públicas de las APIs)
    orchestrator = create_orchestrator()
    
    # Analizar una pista
    result = orchestrator.analyze_track(
        title="Bohemian Rhapsody",
        artist="Queen"
    )
    
    print("=== Metadatos Completos ===")
    print(f"Título: {result.get('title', 'N/A')}")
    print(f"Artista: {result.get('artist', 'N/A')}")
    print(f"BPM: {result.get('bpm')}")
    print(f"Clave: {result.get('key')}")
    print(f"Duración: {result.get('duration')} segundos")
    print(f"Géneros: {result.get('genres')}")
    print(f"Features: {result.get('features')}")
    print(f"Fuente: {result.get('sources')}")