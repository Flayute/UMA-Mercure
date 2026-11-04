#!/usr/bin/env python3
"""
Cliente MusicBrainz API
MusicBrainz es una base de datos libre de música que proporciona:
- Información detallada de pistas, álbumes y artistas
- BPM preciso (derivado de análisis de grabación)
- Tonalidad exacta
- Información de grabación (recording)
- Enlaces a grabaciones específicas

Ventajas:
- Completamente gratuito
- Open source
- Alta precisión en BPM y tonalidad
- No requiere API key para uso básico
"""

import json
import logging
from typing import Dict, Optional, List
from curator.api_clients.base import BaseAPIClient, RateLimiter

logger = logging.getLogger(__name__)


class MusicBrainzClient(BaseAPIClient):
    """Cliente para la API de MusicBrainz"""
    
    API_BASE_URL = "https://musicbrainz.org/ws/2/"
    RECORDINGS_URL = "https://musicbrainz.org/ws/2/recording/"
    
    def __init__(self, api_key: str = None, **kwargs):
        """
        Inicializa el cliente MusicBrainz
        
        Args:
            api_key: API key de MusicBrainz (opcional, no requerida para uso básico)
        """
        super().__init__("musicbrainz", kwargs)
        
        # Configuración de rate limiting
        self.rate_limit_config = {
            "max_requests_per_second": 1,  # MusicBrainz es MUY estricto: 1 req/seg
            "default_ttl": 300,  # 5 minutos de caché
        }
        
        # Información adicional de la API
        self.api_info = {
            "name": "MusicBrainz",
            "description": "Base de datos libre de música con BPM y tonalidad precisos",
            "documentation": "https://musicbrainz.org/doc/Development",
            "rate_limits": "5 requests per second (generoso)",
            "auth_required": False
        }
    
    def get_recording_info(self, recording_mbid: str) -> Dict:
        """
        Obtiene información de una grabación específica usando MBID
        
        Args:
            recording_mbid: MusicBrainz Recording ID (MBID)
            
        Returns:
            Dict con información de la grabación
        """
        url = f"{self.RECORDINGS_URL}{recording_mbid}/"
        params = {
            "inc": "artists,artists-relations,track,release,track-relation,urls,genres,recordings",
            "fmt": "json",
            "lsort": "artists,artists-relations,genres,recordings,urls",
        }
        
        response = self._make_request(url, params)
        
        if "error" in response:
            logger.error(f"Error MusicBrainz get_recording_info: {response}")
            return response
        
        try:
            data = response.get("recording", {})
            
            info = {
                "recording_mbid": data.get("id", recording_mbid),
                "title": data.get("title", ""),
                "disambiguation": data.get("disambiguation", ""),
                "tracklist": data.get("tracklist", []),
            }
            
            # BPM y tonalidad si están disponibles
            bpm = data.get("bpm", None)
            key = data.get("firstKey", None)
            
            if bpm is not None:
                info["bpm"] = bpm
                logger.debug(f"MusicBrainz BPM: {bpm}")
            
            if key is not None:
                info["key"] = key
                logger.debug(f"MusicBrainz Key: {key}")
            
            # Información del artista
            artists = data.get("artist", [])
            if artists:
                artist_name = artists[0].get("name", "")
                info["artist"] = artist_name
            
            # Información del álbum
            releases = data.get("release", [])
            if releases:
                album_title = releases[0].get("title", "")
                album_mbid = releases[0].get("id", "")
                info["album"] = album_title
                info["album_mbid"] = album_mbid
            
            # Género
            genres = data.get("genres", [])
            if genres:
                info["genres"] = genres[0].get("name", "")
            
            # Duración
            length = data.get("length", None)
            if length:
                info["duration"] = length / 1000  # Convertir a segundos
            
            logger.debug(f"MusicBrainz recording info: {recording_mbid[:8]}...")
            return info
            
        except Exception as e:
            logger.error(f"Error procesando grabación: {e}")
            return {"error": str(e)}
    
    def get_recording_by_title(self, title: str, artist: str = None) -> Optional[Dict]:
        """
        Busca una grabación por título (y artista opcional)
        
        Args:
            title: Título de la pista
            artist: Nombre del artista (opcional, para filtrar)
            
        Returns:
            Dict con información de la grabación encontrada o None
        """
        # Usar el endpoint de búsqueda
        search_url = f"{self.API_BASE_URL}search/"
        params = {
            "q": f"track:{title} artist:{artist}",
            "type": "recording",
            "limit": 1,  # Solo queremos el primer resultado
            "fmt": "json"
        }
        
        response = self._make_request(search_url, params)
        
        if "error" in response:
            logger.warning(f"Error MusicBrainz search: {response.get('error', {}).get('message', 'Unknown')}")
            return None
        
        try:
            results = response.get("recording", [])
            
            if not results:
                logger.warning(f"No found recording for: {title}")
                return None
            
            # Retornar la primera grabación encontrada
            mbid = results[0].get("id", "")
            return self.get_recording_info(mbid)
            
        except Exception as e:
            logger.error(f"Error buscando grabación: {e}")
            return None
    
    def get_track_releases(self, recording_mbid: str) -> Dict:
        """
        Obtiene todos los releases (álbumes) de una grabación
        
        Args:
            recording_mbid: MBID de la grabación
            
        Returns:
            Dict con lista de releases
        """
        url = f"{self.RECORDINGS_URL}{recording_mbid}/releases/"
        params = {
            "fmt": "json"
        }
        
        response = self._make_request(url, params)
        
        if "error" in response:
            logger.warning(f"Error MusicBrainz track releases: {response}")
            return {"releases": []}
        
        try:
            releases = response.get("releases", [])
            
            result = {
                "recording_mbid": recording_mbid,
                "releases": []
            }
            
            for release in releases:
                release_info = {
                    "title": release.get("title", ""),
                    "mbid": release.get("id", ""),
                    "status": release.get("status", "official"),
                    "date": release.get("date", ""),
                    "media": release.get("media", []),
                    "recording": release.get("recording", {}),
                }
                result["releases"].append(release_info)
            
            logger.debug(f"MusicBrainz releases: {len(result['releases'])}")
            return result
            
        except Exception as e:
            logger.error(f"Error obteniendo releases: {e}")
            return {"error": str(e)}
    
    def search_artists(self, artist_name: str) -> List[Dict]:
        """
        Busca artistas por nombre
        
        Args:
            artist_name: Nombre del artista
            
        Returns:
            Lista de artistas encontrados
        """
        search_url = f"{self.API_BASE_URL}search/"
        params = {
            "q": f"artist:{artist_name}",
            "type": "artist",
            "limit": 5,  # Máximo 5 resultados
            "fmt": "json"
        }
        
        response = self._make_request(search_url, params)
        
        if "error" in response:
            logger.warning(f"Error MusicBrainz artist search: {response}")
            return []
        
        try:
            results = response.get("artist", [])
            
            artists = []
            for artist in results:
                artist_info = {
                    "name": artist.get("name", ""),
                    "mbid": artist.get("id", ""),
                    "disambiguation": artist.get("disambiguation", ""),
                    "image": artist.get("image", {}).get("#0", {}).get("ext", ""),
                    "type": artist.get("type", "recording"),
                }
                artists.append(artist_info)
            
            logger.debug(f"MusicBrainz found {len(artists)} artists")
            return artists
            
        except Exception as e:
            logger.error(f"Error buscando artistas: {e}")
            return []
    
    def get_artist_releases(self, artist_mbid: str) -> Dict:
        """
        Obtiene todos los releases de un artista
        
        Args:
            artist_mbid: MBID del artista
            
        Returns:
            Dict con lista de releases
        """
        url = f"{self.API_BASE_URL}artist/{artist_mbid}/release/"
        params = {
            "fmt": "json"
        }
        
        response = self._make_request(url, params)
        
        if "error" in response:
            logger.warning(f"Error MusicBrainz artist releases: {response}")
            return {"releases": []}
        
        try:
            releases = response.get("releases", [])
            
            result = {
                "artist_mbid": artist_mbid,
                "releases": []
            }
            
            for release in releases:
                release_info = {
                    "title": release.get("title", ""),
                    "mbid": release.get("id", ""),
                    "status": release.get("status", "official"),
                    "date": release.get("date", ""),
                    "media": release.get("media", []),
                    "recording": release.get("recording", {}),
                }
                result["releases"].append(release_info)
            
            logger.debug(f"MusicBrainz artist releases: {len(result['releases'])}")
            return result
            
        except Exception as e:
            logger.error(f"Error obteniendo artist releases: {e}")
            return {"error": str(e)}
    
    def get_spectral_data(self, recording_mbid: str) -> Optional[Dict]:
        """
        Obtiene datos espectrales usando AcousticBrainz endpoint
        
        Args:
            recording_mbid: MBID de la grabación
            
        Returns:
            Dict con datos espectrales o None
        """
        # Usar el endpoint de AcousticBrainz
        spectral_url = "https://api.acousticbrainz.org/v1/metadata"
        params = {
            "mbid": recording_mbid,
            "json": True
        }
        
        response = self._make_request(spectral_url, params)
        
        if "error" in response:
            logger.warning(f"AcousticBrainz error: {response.get('error', {}).get('message', 'Unknown')}")
            return None
        
        try:
            data = response.get("metadata", {})
            
            if not data:
                return None
            
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
            
            # Clave
            key = data.get("key", {})
            if key:
                features["key"] = key.get("root", None)
                features["mode"] = key.get("mode", None)
            
            # Género
            genres = data.get("genre", {})
            if genres:
                features["genres"] = genres.get("genres", [])
            
            # Grabación
            recording_info = data.get("recording", {})
            if recording_info:
                features["recording_mbid"] = recording_info.get("mbid", None)
                features["title"] = recording_info.get("title", None)
                features["bpm"] = recording_info.get("bpm", None)
            
            logger.debug(f"AcousticBrainz features: {list(features.keys())}")
            return features
            
        except Exception as e:
            logger.error(f"Error obteniendo datos espectrales: {e}")
            return None
    
    def get_complete_track_metadata(self, title: str, artist: str = None) -> Dict:
        """
        Obtiene todos los metadatos posibles para una pista
        
        Args:
            title: Título de la pista
            artist: Nombre del artista (opcional)
            
        Returns:
            Dict con todos los metadatos disponibles
        """
        # Buscar grabación
        recording = self.get_recording_by_title(title, artist)
        
        if not recording or "error" in recording:
            return recording
        
        metadata = {
            "source": "musicbrainz",
            "recording_mbid": recording.get("recording_mbid", ""),
            "title": recording.get("title", ""),
            "disambiguation": recording.get("disambiguation", ""),
            "artist": recording.get("artist", ""),
            "album": recording.get("album", ""),
            "album_mbid": recording.get("album_mbid", ""),
            "bpm": recording.get("bpm"),
            "key": recording.get("key"),
            "genres": recording.get("genres", []),
            "duration": recording.get("duration"),
        }
        
        # Obtener datos espectrales
        spectral = self.get_spectral_data(recording.get("recording_mbid", ""))
        if spectral:
            metadata["features"] = spectral
        
        return metadata


# Factory function for creating MusicBrainzClient instances
def create_musicbrainz_client(api_key: str = None, **kwargs) -> MusicBrainzClient:
    """
    Crea una instancia de MusicBrainzClient
    
    Args:
        api_key: API key de MusicBrainz (opcional, no requerida)
        **kwargs: Parámetros adicionales para el cliente base
        
    Returns:
        Instancia de MusicBrainzClient
    """
    return MusicBrainzClient(api_key=api_key, **kwargs)