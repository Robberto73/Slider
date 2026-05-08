from abc import ABC, abstractmethod
from pathlib import Path

from openai import OpenAI
from typing import Dict, Any, Optional, List

class BaseLLM:
    """Универсальный клиент к OpenAI-совместимым API."""
    def __init__(self, base_url: str, api_key: str):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = self._detect_model()

    def _detect_model(self) -> str:
        try:
            models = self.client.models.list()
            if models.data:
                return models.data[0].id
        except Exception:
            pass
        return "default"

    def chat(self, messages: List[Dict], temperature=0.3, max_tokens=2000) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return resp.choices[0].message.content

class PresentationAgent(ABC):
    @abstractmethod
    def generate(self, topic: str, slides_count: int, style: str,
                 language: str, include_charts: bool, include_icons: bool,
                 output_dir: Path) -> Dict[str, Any]:
        pass