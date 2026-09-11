from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import requests


class OllamaError(Exception):
    pass


@dataclass
class OllamaHealth:
    ready: bool
    installed_models: Tuple[str, ...] = ()
    version: str = ""


class OllamaAdapter:
    def __init__(self, host: str = "http://localhost:11434") -> None:
        self.host = host.rstrip("/")

    def health(self) -> OllamaHealth:
        exe = shutil.which("ollama") or shutil.which("C:/Ollama/ollama.exe")
        try:
            v_res = requests.get(f"{self.host}/api/version", timeout=2)
            t_res = requests.get(f"{self.host}/api/tags", timeout=2)
            if v_res.status_code == 200 and t_res.status_code == 200:
                v_data = v_res.json()
                t_data = t_res.json()
                models = tuple(m.get("name", "") for m in t_data.get("models", []))
                return OllamaHealth(ready=True, installed_models=models, version=v_data.get("version", ""))
        except Exception:
            pass
        return OllamaHealth(ready=False)

    def model_available(self, model: str) -> bool:
        h = self.health()
        return model in h.installed_models or any(m.startswith(model) for m in h.installed_models)

    @staticmethod
    def _normalise_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        norm = []
        for msg in messages:
            content = msg.get("content")
            role = msg.get("role", "user")
            if isinstance(content, list):
                text_parts = []
                images = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif part.get("type") == "image_url":
                            img_obj = part.get("image_url", {})
                            url = img_obj.get("url", "") if isinstance(img_obj, dict) else str(img_obj)
                            if url.startswith("data:image/") and ";base64," in url:
                                b64 = url.split(";base64,", 1)[1]
                                images.append(b64)
                            else:
                                images.append(url)
                norm_msg: Dict[str, Any] = {"role": role, "content": " ".join(text_parts).strip()}
                if images:
                    norm_msg["images"] = images
                norm.append(norm_msg)
            else:
                norm.append(msg)
        return norm

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = "qwen3:4b",
        role: str = "general",
        timeout: float = 60.0,
    ) -> str:
        norm_messages = self._normalise_messages(messages)
        payload = {
            "model": model,
            "messages": norm_messages,
            "stream": False,
            "keep_alive": "5m",
        }
        try:
            res = requests.post(f"{self.host}/api/chat", json=payload, timeout=timeout)
            if res.status_code != 200:
                raise OllamaError(f"Ollama chat failed with status {res.status_code}: {res.text}")
            data = res.json()
            return data.get("message", {}).get("content", "")
        except Exception as exc:
            if isinstance(exc, OllamaError):
                raise
            raise OllamaError(f"Ollama connection error: {exc}") from exc
