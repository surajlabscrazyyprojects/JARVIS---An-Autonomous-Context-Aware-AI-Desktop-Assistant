"""Integration test: drive the REAL WebSocket backend with natural-language commands.

Requires a working LLM key (GROQ_API_KEY/GEMINI_API_KEY in .env). Skips otherwise.
Opens real apps/URLs and performs real file create/delete, granting destructive
permission automatically for the test. Verifies on-disk side effects.
"""
import sys
import asyncio
import json
import importlib.util
import os
import websockets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("jarvis_launcher", str(ROOT / "jarvis.py"))
jl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jl)
PORT = 8795


async def main():
    if not (os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        print("SKIP: no LLM key configured")
        return
    backend = jl.Backend()
    server = await websockets.serve(backend.handler, "127.0.0.1", PORT)
    async with websockets.connect(f"ws://127.0.0.1:{PORT}") as ws:
        await ws.recv()

        async def send_cmd(text, grant=True):
            await ws.send(json.dumps({"type": "command", "text": text}))
            replies = []
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 90))
                replies.append(msg)
                if msg.get("type") == "permission_request":
                    await ws.send(json.dumps({"type": "permission", "granted": grant}))
                    continue
                if msg.get("type") in ("done", "error"):
                    break
            return replies

        p = ROOT / "test_find.txt"
        await send_cmd("create a file called test_find.txt in the project containing hello world")
        assert p.exists(), "file was not created"
        assert "hello world" in p.read_text(errors="replace")
        await send_cmd("delete the file test_find.txt", grant=True)
        assert not p.exists(), "file was not deleted"
        print("INTEGRATION TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
