#!/usr/bin/env python3
"""
Cliente Last.fm API
Proporciona:
- Información del artista
- Información del tema (track)
- Información de álbum
- Información de género (Tags)
"""

import json
import logging
from typing import Dict, Optional, List
from curator.api_clients.base import BaseAPIClient

logger = logging.getLogger(__name__)


class LastFMClient(BaseAPIClient):
    """Cliente para la API de Last.fm"""
    
    API_BASE_URL = "https://ws.audioscrobbler.com/2.0/"
    
    def __init__(self, api_key: str = None, **kwargs):
        """
        Inicializa el cliente Last.fm
        """
        super().__init__("lastfm", kwargs)
        self.api_key = api_key
        
        # Configuración de rate limiting específica para Last.fm
        self.rate_limit_config = {
            "max_requests_per_second": 2,
            "default_ttl": 86400  # 24 horas de caché para tags
        }
    
    def get_track_info(self, artist: str, track: str, album: str = None) -> Dict:
        """
        Obtiene información de una pista específica
        """
        url = self.API_BASE_URL
        params = {
            "method": "track.getInfo",
            "artist": artist,
            "track": track,
            "api_key": self.api_key,
            "format": "json"
        }
        
        if album:
            params["album"] = album
        
        response = self._make_request(url, params)
        
        if "error" in response:
            return response
        
        try:
            data = response.get("track", {})
            
            # Extraer tags (géneros)
            tags = [t.get("name") for t in data.get("toptags", {}).get("tag", [])]
            
            info = {
                "artist": data.get("artist", {}).get("name", artist),
                "track": data.get("name", track),
                "album": data.get("album", {}).get("title", album or "Unknown"),
                "duration": data.get("duration", None),
                "url": data.get("url", ""),
                "tags": tags
            }
            
            return info
            
        except Exception as e:
            logger.error(f"Error procesando respuesta Last.fm: {e}")
            return {"error": str(e)}

    def get_artist_info(self, artist: str) -> Dict:
        """
        Obtiene información detallada de un artista
        """
        url = self.API_BASE_URL
        params = {
            "method": "artist.getinfo",
            "artist": artist,
            "api_key": self.api_key,
            "format": "json"
        }
        
        response = self._make_request(url, params)
        
        if "error" in response:
            return response
        
        try:
            artist_data = response.get("artist", {})
            tags = [t.get("name") for t in artist_data.get("tags", {}).get("tag", [])]
            
            info = {
                "name": artist_data.get("name", artist),
                "mbid": artist_data.get("mbid", ""),
                "url": artist_data.get("url", ""),
                "listeners": artist_data.get("stats", {}).get("listeners", 0),
                "playcount": artist_data.get("stats", {}).get("playcount", 0),
                "tags": tags
            }
            
            return info
            
        except Exception as e:
            logger.error(f"Error procesando artista: {e}")
            return {"error": str(e)}

    def search_track(self, title: str, artist: str = None) -> Dict:
        """
        Busca una pista para obtener su MBID o información básica
        """
        url = self.API_BASE_URL
        params = {
            "method": "track.search",
            "track": title,
            "api_key": self.api_key,
            "format": "json"
        }
        if artist:
            params["artist"] = artist
            
        response = self._make_request(url, params)
        if "error" in response:
            return response
            
        try:
            results = response.get("results", {}).get("trackmatches", {}).get("track", [])
            if not results:
                return {"error": "No tracks found"}
                
            best_match = results[0]
            return {
                "title": best_match.get("name"),
                "artist": best_match.get("artist"),
                "recording_mbid": best_match.get("mbid"),
                "url": best_match.get("url")
            }
        except Exception as e:
            return {"error": str(e)}

def create_lastfm_client(api_key: str = None, **kwargs) -> LastFMClient:
    return LastFMClient(api_key=api_key, **kwargs)