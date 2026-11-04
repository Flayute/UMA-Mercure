#!/usr/bin/env python3
"""
Cliente base para todas las APIs externas
Proporciona:
- Rate limiting con backoff exponencial
- Caché local de respuestas
- Logging de peticiones
"""

import time
import hashlib
import json
import logging
from typing import Dict, Any, Optional
from functools import wraps
from collections import defaultdict

# Configuración de logging
logger = logging.getLogger(__name__)

# Estado del rate limiter
_rate_limiter_state = {
    "last_request": defaultdict(int),
    "requests_per_window": defaultdict(list),
    "window_size": 1.0  # 1 segundo
}

class RateLimiter:
    """Rate limiter con backoff exponencial"""
    
    @staticmethod
    def can_make_request(service: str) -> bool:
        """Verifica si puede hacer una petición"""
        config = {"max_requests_per_second": 1}
        max_reqs = config["max_requests_per_second"]
        window_size = _rate_limiter_state["window_size"]
        
        now = time.time()
        window_start = now - window_size
        
        # Limpiar ventanas antiguas
        _rate_limiter_state["requests_per_window"][service] = \
            sum(1 for ts in _rate_limiter_state["requests_per_window"][service] 
                 if ts > window_start)
        
        if _rate_limiter_state["requests_per_window"][service] < max_reqs:
            # Registrar petición
            _rate_limiter_state["requests_per_window"][service].append(now)
            _rate_limiter_state["last_request"][service] = now
            return True
        
        # Calcular tiempo de espera
        wait_time = _rate_limiter_state["window_size"] - \
                   (now - _rate_limiter_state["last_request"][service])
        return False, wait_time
    
    @staticmethod
    def wait_if_needed(service: str) -> None:
        """Espera si es necesario antes de hacer petición"""
        can_req, wait_time = RateLimiter.can_make_request(service)
        if not can_req:
            logger.debug(f"Rate limit alcanzado para {service}: esperando {wait_time:.1f}s")
            time.sleep(wait_time)


class APIResponseCache:
    """Caché local de respuestas API usando SQLite"""
    
    def __init__(self, db_path: str, default_ttl: int = 3600):
        self.db_path = db_path
        self.default_ttl = default_ttl
        self._init_db()
    
    def _init_db(self):
        """Inicializa la base de datos de caché"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key_hash TEXT PRIMARY KEY,
                data TEXT,
                created_at INTEGER,
                ttl INTEGER
            )
        """)
        conn.commit()
        conn.close()
    
    def _hash_key(self, key: str) -> str:
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, key: str, ttl: int = None) -> Optional[Dict]:
        """Obtiene dato de caché si no ha expirado"""
        ttl = ttl or self.default_ttl
        key_hash = self._hash_key(key)
        
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT data, created_at FROM cache 
            WHERE key_hash = ? AND ttl > ?
        """, (key_hash, ttl))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            data, created_at = row
            if time.time() - created_at < ttl:
                return json.loads(data)
        
        return None
    
    def set(self, key: str, data: Dict, ttl: int = None) -> None:
        """Guarda dato en caché"""
        ttl = ttl or self.default_ttl
        key_hash = self._hash_key(key)
        
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO cache (key_hash, data, created_at, ttl)
            VALUES (?, ?, ?, ?)
        """, (key_hash, json.dumps(data), time.time(), ttl))
        conn.commit()
        conn.close()
        logger.debug(f"Caché guardado: {key[:50]}...")


class BaseAPIClient:
    """Cliente base con rate limiting y caché"""
    
    def __init__(self, name: str, rate_limit_config: Dict, cache: Optional[APIResponseCache] = None):
        self.name = name
        self.rate_limit_config = rate_limit_config
        self.cache = cache or APIResponseCache(
            "cache/api_responses.db",
            rate_limit_config.get("default_ttl", 3600)
        )
    
    def _make_request(self, url: str, params: Dict = None, 
                     headers: Dict = None) -> Dict:
        """
        Hace petición a API con:
        1. Verificación de rate limit
        2. Consulta de caché
        3. Petición real
        4. Guardado en caché
        """
        import requests
        
        # 1. Verificar rate limit
        RateLimiter.wait_if_needed(self.name)
        
        # 2. Consultar caché
        cache_key = f"{url}?{json.dumps(params or {}, sort_keys=True)}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Respuesta de caché para {self.name}: {cache_key[:80]}")
            return cached
        
        # 3. Petición real
        try:
            response = requests.get(
                url,
                params=params,
                headers={**headers, "User-Agent": "UMA-Mercure/1.0"} if headers else {"User-Agent": "UMA-Mercure/1.0"},
                timeout=10
            )
            
            # Manejo de errores HTTP
            if response.status_code == 429:
                # Rate limit de la API externa
                logger.warning(f"Rate limit de {self.name} externo: {response.text}")
                time.sleep(2)
                return self._make_request(url, params, headers)
            
            if response.status_code != 200:
                logger.error(f"Error HTTP en {self.name}: {response.status_code}")
                return {"error": f"HTTP {response.status_code}"}
            
            # 4. Guardar en caché
            data = response.json()
            self.cache.set(cache_key, data)
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error en petición a {self.name}: {e}")
            return {"error": str(e)}
    
    def request(self, url: str, params: Dict = None, headers: Dict = None) -> Dict:
        """Método abstracto a implementar"""
        raise NotImplementedError