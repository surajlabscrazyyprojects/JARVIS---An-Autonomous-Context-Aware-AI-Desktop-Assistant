from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from jarvis.ai.ollama import OllamaAdapter, OllamaError


class OllamaAdapterTests(unittest.TestCase):
    def test_health_requires_executable_service_and_discovery(self) -> None:
        version = Mock(status_code=200)
        version.json.return_value = {"version": "0.32.11"}
        tags = Mock(status_code=200)
        tags.json.return_value = {"models": [{"name": "qwen3:1.7b"}]}
        with patch("jarvis.ai.ollama.shutil.which", return_value="C:/Ollama/ollama.exe"), patch(
            "jarvis.ai.ollama.requests.get", side_effect=[version, tags]
        ):
            health = OllamaAdapter().health()
        self.assertTrue(health.ready)
        self.assertEqual(("qwen3:1.7b",), health.installed_models)

    def test_normalises_data_url_images_for_native_ollama(self) -> None:
        messages = OllamaAdapter._normalise_messages([
            {"role": "user", "content": [
                {"type": "text", "text": "Describe this image"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,aGVsbG8="}},
            ]}
        ])
        self.assertEqual("Describe this image", messages[0]["content"])
        self.assertEqual(["aGVsbG8="], messages[0]["images"])

    def test_chat_sends_keep_alive_and_returns_content(self) -> None:
        adapter = OllamaAdapter()
        response = Mock(status_code=200)
        response.json.return_value = {"message": {"content": "Vision result"}}
        with patch.object(adapter, "model_available", return_value=True), patch(
            "jarvis.ai.ollama.requests.post", return_value=response
        ) as post:
            text = adapter.chat([{"role": "user", "content": "test"}], model="gemma3:4b", role="vision")
        self.assertEqual(text, "Vision result")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "gemma3:4b")
        self.assertEqual(payload["keep_alive"], "5m")


if __name__ == "__main__":
    unittest.main()
