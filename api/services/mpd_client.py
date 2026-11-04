import mpd
import time

class MPDService:
    def __init__(self, host="localhost", port=6600):
        self.host = host
        self.port = port
        self.client = mpd.MPDClient()
        self.client.timeout = 10
        self.client.idletimeout = None 
        self._connected = False

    def _ensure_connected(self):
        if not self._connected:
            self.connect()
        else:
            try:
                self.client.ping()
            except Exception:
                self.connect()

    def connect(self):
        try:
            self.client.disconnect()
        except:
            pass
        self.client.connect(self.host, self.port)
        self._connected = True

    def disconnect(self):
        try:
            self.client.close()
            self.client.disconnect()
        except:
            pass
        self._connected = False

    def status(self):
        try:
            self._ensure_connected()
            return self.client.status()
        except Exception as e:
            return {"error": str(e)}

    def current_song(self):
        try:
            self._ensure_connected()
            return self.client.currentsong()
        except Exception as e:
            return {"error": str(e)}

    def play(self):
        self._ensure_connected()
        self.client.play()

    def pause(self):
        self._ensure_connected()
        self.client.pause()

    def next(self):
        self._ensure_connected()
        self.client.next()

    def previous(self):
        self._ensure_connected()
        self.client.previous()

    def stop(self):
        self._ensure_connected()
        self.client.stop()

    def set_volume(self, vol: int):
        self._ensure_connected()
        vol = max(0, min(100, vol))
        self.client.setvol(vol)

    def list_all_tracks(self):
        """Devuelve todos los archivos indexados por MPD."""
        self._ensure_connected()
        return self.client.listallinfo()

    def search(self, tag: str, query: str):
        """Búsqueda flexible en la base de datos de MPD."""
        self._ensure_connected()
        return self.client.search(tag, query)

    def load_and_play(self, tag: str, query: str):
        """Limpia cola, busca, añade resultados y reproduce."""
        self._ensure_connected()
        results = self.client.search(tag, query)
        if not results:
            return None
        self.client.clear()
        for track in results:
            if "file" in track:
                self.client.add(track["file"])
        self.client.play()
        return results

    def get_playlist(self):
        """Devuelve la cola de reproducción actual."""
        self._ensure_connected()
        return self.client.playlistinfo()

    def get_stats(self):
        """Estadísticas de la base de datos musical."""
        self._ensure_connected()
        return self.client.stats()

    def play_file(self, file_path: str):
        """Limpia cola, añade el archivo específico y lo reproduce.
        repeat OFF: si no, una cola de 1 pista queda en bucle infinito."""
        self._ensure_connected()
        self.client.clear()
        self.client.repeat(0)
        self.client.add(file_path)
        self.client.play()
        return True

    def add_files(self, file_paths: list):
        """Añade varias pistas a la cola sin limpiarla."""
        self._ensure_connected()
        for f in file_paths:
            self.client.add(f)
        return True

    def add_file(self, file_path: str):
        """Añade un archivo a la cola sin limpiarla."""
        self._ensure_connected()
        self.client.add(file_path)
        return True

    def shuffle_all(self):
        """Modo radio: cola completa de la biblioteca, aleatorio y repetición ON."""
        self._ensure_connected()
        self.client.clear()
        self.client.random(1)
        self.client.repeat(1)
        self.client.add("/")
        self.client.play()
        return True

    def ensure_stream_output(self):
        """Fuerza la salida httpd habilitada y la alsa/HDMI deshabilitada
        (el Pi va sin monitor y alsa hw:0,0 falla: 'Failed to open audio output')."""
        self._ensure_connected()
        for i, out in enumerate(self.client.outputs()):
            name = out.get("outputname", "")
            if "Stream" in name:
                self.client.enableoutput(i)
            elif "HDMI" in name:
                self.client.disableoutput(i)
        return True

    def toggle_output(self, output_id: int, state: bool):
        """Activa o desactiva una salida de audio (0-indexed)."""
        self._ensure_connected()
        if state:
            self.client.enableoutput(output_id)
        else:
            self.client.disableoutput(output_id)
        return True

    def list_playlists(self):
        """Lista todas las listas de reproducción guardadas en disco."""
        self._ensure_connected()
        return self.client.listplaylists()

    def save_playlist(self, name: str):
        """Guarda la cola de reproducción actual como una lista nueva."""
        self._ensure_connected()
        # Eliminar si ya existe para sobrescribir
        try:
            self.client.rm(name)
        except:
            pass
        self.client.save(name)
        return True

    def load_playlist(self, name: str):
        """Carga una lista guardada en la cola actual y la reproduce."""
        self._ensure_connected()
        self.client.clear()
        self.client.load(name)
        self.client.play()
        return True
