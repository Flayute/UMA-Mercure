#!/usr/bin/env python3
"""
Cliente AcousticBrainz API
AcousticBrainz proporciona análisis acústico detallado de audio:
- BPM exacto
- Tonalidad/clave
- Features acústicas (energía, valencia, danzabilidad, etc.)
- Información de grabación y artista

Ventajas:
- Especializado en análisis acústico
- Datos muy precisos
- Gratuito
- Open source
"""

import json
import logging
from typing import Dict, Optional, List
from curator.api_clients.base import BaseAPIClient, RateLimiter

logger = logging.getLogger(__name__)


class AcousticBrainzClient(BaseAPIClient):
    """Cliente para la API de AcousticBrainz"""
    
    API_BASE_URL = "https://api.acousticbrainz.org/v1/"
    METADATA_URL = "https://api.acousticbrainz.org/v1/metadata"
    
    def __init__(self, api_key: str = None, **kwargs):
        """
        Inicializa el cliente AcousticBrainz
        
        Args:
            api_key: API key de AcousticBrainz (opcional)
        """
        super().__init__("acousticbrainz", kwargs)
        
        # Configuración de rate limiting
        self.rate_limit_config = {
            "max_requests_per_second": 3,
            "default_ttl": 300,  # 5 minutos de caché
        }
        
        # Información adicional de la API
        self.api_info = {
            "name": "AcousticBrainz",
            "description": "Análisis acústico de audio con BPM y tonalidad precisos",
            "documentation": "https://acousticbrainz.org/",
            "rate_limits": "3 requests per second",
            "auth_required": False
        }
    
    def get_metadata(self, recording_mbid: str) -> Dict:
        """
        Obtiene metadatos completos para una grabación
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con todos los metadatos disponibles
        """
        url = f"{self.METADATA_URL}?mbid={recording_mbid}"
        params = {
            "json": True
        }
        
        response = self._make_request(url, params)
        
        if "error" in response:
            logger.error(f"Error AcousticBrainz get_metadata: {response}")
            return response
        
        try:
            data = response.get("metadata", {})
            
            if not data:
                return {"error": "No metadata found"}
            
            metadata = {
                "source": "acousticbrainz",
                "recording_mbid": data.get("recording", {}).get("mbid", recording_mbid),
                "title": data.get("recording", {}).get("title", ""),
                "artist": data.get("recording", {}).get("artist", ""),
            }
            
            # BPM exacto
            bpm = data.get("features", {}).get("bpm", None)
            if bpm is not None:
                metadata["bpm"] = bpm
                logger.debug(f"AcousticBrainz BPM: {bpm}")
            
            # Tonalidad
            key = data.get("key", {})
            if key:
                metadata["key"] = {
                    "root": key.get("root", None),
                    "mode": key.get("mode", None),
                }
            
            # Features acústicas
            features = {
                "energy": data.get("features", {}).get("energy", None),
                "danceability": data.get("features", {}).get("danceability", None),
                "happyness": data.get("features", {}).get("happyness", None),
                "sadness": data.get("features", {}).get("sadness", None),
                "acousticness": data.get("features", {}).get("acousticness", None),
                "liveness": data.get("features", {}).get("liveness", None),
                "tempo": data.get("features", {}).get("tempo", None),
            }
            metadata["features"] = features
            
            # Género
            genres = data.get("genre", {}).get("genres", [])
            metadata["genres"] = genres
            
            # Duración
            length = data.get("length", None)
            if length:
                metadata["duration"] = length / 1000  # Convertir a segundos
            
            # Grabación
            recording = data.get("recording", {})
            if recording:
                metadata["recording"] = {
                    "mbid": recording.get("mbid", None),
                    "title": recording.get("title", None),
                    "bpm": recording.get("bpm", None),
                }
            
            logger.debug(f"AcousticBrainz metadata: {list(metadata.keys())}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error procesando metadatos: {e}")
            return {"error": str(e)}
    
    def search_by_title(self, title: str, artist: str = None) -> Optional[Dict]:
        """
        Busca grabación por título
        
        Args:
            title: Título de la pista
            artist: Nombre del artista (opcional)
            
        Returns:
            Dict con metadatos de la grabación encontrada o None
        """
        # Usar búsqueda por texto (no hay endpoint directo de búsqueda)
        # Necesitamos usar MusicBrainz para encontrar el MBID primero, luego AcousticBrainz
        
        # Para mantener simplicidad, usamos el endpoint de búsqueda de MusicBrainz
        # y luego consultamos AcousticBrainz con el MBID
        return None
    
    def search_by_url(self, url: str) -> Optional[Dict]:
        """
        Busca grabación por URL de audio (si está disponible)
        
        Args:
            url: URL de la pista de audio
            
        Returns:
            Dict con metadatos de la grabación o None
        """
        # AcousticBrainz no tiene búsqueda directa por URL
        # Esta función se reserva para futuras implementaciones
        logger.warning("Search by URL not implemented")
        return None
    
    def get_artist_metadata(self, artist_mbid: str) -> Dict:
        """
        Obtiene metadatos de un artista
        
        Args:
            artist_mbid: MusicBrainz Artist ID (MBID)
            
        Returns:
            Dict con información del artista
        """
        url = f"{self.API_BASE_URL}artist/{artist_mbid}"
        params = {
            "json": True
        }
        
        response = self._make_request(url, params)
        
        if "error" in response:
            logger.warning(f"Error AcousticBrainz artist: {response}")
            return {}
        
        try:
            artist_data = response.get("artist", {})
            
            metadata = {
                "mbid": artist_data.get("mbid", artist_mbid),
                "name": artist_data.get("name", ""),
                "disambiguation": artist_data.get("disambiguation", ""),
            }
            
            # Grabaciones del artista
            recordings = artist_data.get("recording", [])
            metadata["recordings"] = recordings[:10]  # Máximo 10
            
            logger.debug(f"AcousticBrainz artist: {artist_mbid[:8]}...")
            return metadata
            
        except Exception as e:
            logger.error(f"Error obteniendo artist metadata: {e}")
            return {}
    
    def get_spectrum_data(self, recording_mbid: str) -> Optional[Dict]:
        """
        Obtiene datos espectrales detallados
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con datos espectrales o None
        """
        # Los datos espectrales vienen en el endpoint de metadatos
        # Esta función es una abstracción para futuras necesidades
        metadata = self.get_metadata(recording_mbid)
        
        if "error" in metadata:
            return None
        
        # Los datos espectrales están incluidos en metadatos
        return metadata.get("features", None)
    
    def get_genre_statistics(self) -> Dict:
        """
        Obtiene estadísticas por género
        
        Returns:
            Dict con estadísticas por género
        """
        # Esta información no está disponible directamente en la API
        # Necesitaría una implementación más compleja
        return {}
    
    def get_track_recommendations(self, recording_mbid: str) -> Optional[Dict]:
        """
        Obtiene recomendaciones de pistas similares
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con recomendaciones o None
        """
        # Esta función requiere una implementación más compleja
        # con cálculo de similitudes acústicas
        logger.warning("Track recommendations not implemented")
        return None
    
    def get_tempo_analysis(self, recording_mbid: str) -> Optional[Dict]:
        """
        Obtiene análisis de tempo detallado
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con análisis de tempo o None
        """
        metadata = self.get_metadata(recording_mbid)
        
        if "error" in metadata:
            return None
        
        bpm = metadata.get("features", {}).get("bpm", None)
        tempo = metadata.get("features", {}).get("tempo", None)
        
        return {
            "bpm": bpm,
            "tempo": tempo,
            "source": "acousticbrainz"
        }
    
    def get_key_analysis(self, recording_mbid: str) -> Optional[Dict]:
        """
        Obtiene análisis de tonalidad detallado
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con análisis de tonalidad o None
        """
        metadata = self.get_metadata(recording_mbid)
        
        if "error" in metadata:
            return None
        
        key = metadata.get("key", {})
        
        return {
            "root": key.get("root", None),
            "mode": key.get("mode", None),
            "source": "acousticbrainz"
        }
    
    def get_acoustic_features(self, recording_mbid: str) -> Optional[Dict]:
        """
        Obtiene todas las features acústicas disponibles
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con features acústicas o None
        """
        metadata = self.get_metadata(recording_mbid)
        
        if "error" in metadata:
            return None
        
        features = metadata.get("features", {})
        
        return {
            "energy": features.get("energy"),
            "danceability": features.get("danceability"),
            "happyness": features.get("happyness"),
            "sadness": features.get("sadness"),
            "acousticness": features.get("acousticness"),
            "liveness": features.get("liveness"),
            "bpm": features.get("bpm"),
            "source": "acousticbrainz"
        }
    
    def get_complete_analysis(self, recording_mbid: str) -> Dict:
        """
        Obtiene todo el análisis posible para una grabación
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con todo el análisis disponible
        """
        metadata = self.get_metadata(recording_mbid)
        
        if "error" in metadata:
            return metadata
        
        analysis = {
            "recording_mbid": metadata.get("recording_mbid", ""),
            "title": metadata.get("title", ""),
            "artist": metadata.get("artist", ""),
            "bpm": metadata.get("bpm"),
            "key": metadata.get("key"),
            "features": metadata.get("features", {}),
            "genres": metadata.get("genres", []),
            "duration": metadata.get("duration"),
        }
        
        return analysis


# Factory function for creating AcousticBrainzClient instances
def create_acousticbrainz_client(api_key: str = None, **kwargs) -> AcousticBrainzClient:
    """
    Crea una instancia de AcousticBrainzClient
    
    Args:
        api_key: API key de AcousticBrainz (opcional)
        **kwargs: Parámetros adicionales para el cliente base
        
    Returns:
        Instancia de AcousticBrainzClient
    """
    return AcousticBrainzClient(api_key=api_key, **kwargs)