import requests
import json
import logging
from core.config import settings

logger = logging.getLogger(__name__)

class LLMAgent:
    def __init__(self, server_url=None):
        self.server_url = server_url or settings.LLAMA_SERVER_URL
        self.remote_url = settings.LLAMA_REMOTE_URL
        self.mode = settings.LLAMA_MODE  # "auto", "local", "remote"
        self._last_used_local = True  # track fallback state

    def _get_base_url(self) -> tuple:
        """Return (url, label) for the LLM to use."""
        if self.mode == "local":
            return (self.server_url, "local (Qwen2.5-2B)")
        elif self.mode == "remote":
            return (self.remote_url, "remote (9B)")
        else:  # auto
            # Prefer local; use remote if local was unreachable
            if self._last_used_local:
                return (self.server_url, "local (Qwen2.5-2B)")
            else:
                return (self.remote_url, "remote (9B)")

    def _call_llm(self, url: str, messages: list) -> dict:
        """Call an OpenAI-compatible chat API and return parsed intent."""
        payload = {
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1000
        }
        res = requests.post(f"{url}/v1/chat/completions", json=payload, timeout=30)
        res.raise_for_status()
        data = res.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        # If no content but has reasoning, use reasoning
        if not content.strip() and message.get("reasoning_content"):
            content = message["reasoning_content"]
        return content

    def parse_intent(self, user_query: str) -> dict:
        """
        Sends user text to LLM and returns structured intent dict.
        Falls back from local 2B to remote 9B on failure.
        """
        system_prompt = (
            "Eres el DJ Inteligente de UMA Mercure. Tu misión es traducir el lenguaje natural del usuario "
            "en comandos estructurados JSON para el reproductor MPD.\n\n"
            "ACCIONES SOPORTADAS:\n"
            "- {\"action\": \"play\"} -> Reanudar.\n"
            "- {\"action\": \"pause\"} -> Pausar.\n"
            "- {\"action\": \"stop\"} -> Detener.\n"
            "- {\"action\": \"next\"} -> Siguiente.\n"
            "- {\"action\": \"previous\"} -> Anterior.\n"
            "- {\"action\": \"volume\", \"value\": 0-100} -> Ajustar volumen.\n"
            "- {\"action\": \"play_target\", \"target\": \"nombre\"} -> Reproducir artista/canción.\n"
            "- {\"action\": \"smart_playlist\", \"params\": {\"genre\": \"...\", \"bpm\": 120, \"mood\": \"...\"}} -> Crear lista por criterios.\n"
            "- {\"action\": \"propose_playlist\", \"params\": {\"genre\": \"...\", \"mood\": \"...\"}} -> Sugerir una lista.\n"
            "- {\"action\": \"shuffle_all\"} -> Mezclar toda la biblioteca.\n\n"
            "REGLAS:\n"
            "1. Responde SIEMPRE y ÚNICAMENTE con el objeto JSON.\n"
            "2. Si pide música por género, mood o BPM, usa 'smart_playlist'.\n"
            "3. Si pide recomendaciones sin reproducir de inmediato, usa 'propose_playlist'.\n"
            "4. Si pide un artista concreto, usa 'play_target'.\n\n"
            "EJEMPLOS:\n"
            "User: 'Pon algo de techno a 125 bpm'\n"
            "Assistant: {\"action\": \"smart_playlist\", \"params\": {\"genre\": \"techno\", \"bpm\": 125}}\n\n"
            "User: '¿Qué me recomiendas para una tarde chill?'\n"
            "Assistant: {\"action\": \"propose_playlist\", \"params\": {\"mood\": \"chill\"}}\n\n"
            "User: 'Pon toda mi música en aleatorio'\n"
            "Assistant: {\"action\": \"shuffle_all\"}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]

        base_url, label = self._get_base_url()
        logger.info(f"LLM intent: querying {label} ({base_url})")

        try:
            content = self._call_llm(base_url, messages)
            intent = self._parse_json(content)
            if intent and isinstance(intent, dict) and "action" in intent:
                self._last_used_local = True  # success, prefer local
                logger.info(f"✅ LLM response from {label}: {intent.get('action')}")
                return intent
        except Exception as e:
            logger.warning(f"❌ LLM error ({label}): {e}")

        # Fallback to the other LLM
        if base_url == self.server_url:
            fallback_url = self.remote_url
            fallback_label = "remote (9B)"
        else:
            fallback_url = self.server_url
            fallback_label = "local (Qwen2.5-2B)"

        logger.info(f"🔄 Falling back to {fallback_label} ({fallback_url})")
        try:
            content = self._call_llm(fallback_url, messages)
            intent = self._parse_json(content)
            if intent and isinstance(intent, dict) and "action" in intent:
                self._last_used_local = (fallback_url == self.server_url)
                logger.info(f"✅ LLM response from {fallback_label}: {intent.get('action')}")
                return intent
        except Exception as e:
            logger.error(f"❌ Fallback LLM error ({fallback_label}): {e}")

        return {"action": "error", "message": "No pude procesar tu comando con ninguno de los modelos disponibles."}

    def _parse_json(self, content: str) -> dict:
        """Extract JSON from LLM response text."""
        import re
        content = content.replace('```json', '').replace('```', '').strip()
        match = re.search(r'(\{.*\})', content, re.DOTALL)
        if match:
            content = match.group(1)
        brace_count = 0
        json_str = ""
        for char in content:
            json_str += char
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            if brace_count == 0 and json_str.strip():
                break
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}
