from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Valores reales de despliegue en api/.env (no versionado). Defaults = placeholders.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    MPD_HOST: str = "localhost"
    MPD_PORT: int = 6600
    # Primary: local llama.cpp server
    LLAMA_SERVER_URL: str = "http://localhost:8080"
    # Fallback: remote model (real URL in .env)
    LLAMA_REMOTE_URL: str = "http://<llm-host>:8081"
    # Which LLM to use: "local" (always local), "remote" (always remote), "auto" (local first, fallback remote)
    LLAMA_MODE: str = "auto"
    DB_URL: str = "sqlite:///../data/uma.db"
    MUSIC_DIR: str = "/media/<usuario>/Seagate Expansion Drive"

settings = Settings()
