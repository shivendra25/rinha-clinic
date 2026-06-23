from __future__ import annotations

import asyncio
import json
from urllib.parse import urlencode

import websockets.asyncio.client as ws_client

from rinha.config import get_config


class STT:
    def __init__(self, lang_hint: str = "en"):
        cfg = get_config()
        self._api_key = cfg.sarvam_api_key
        self._lang = lang_hint
        self._queue: asyncio.Queue = asyncio.Queue()
        self._ws = None
        self._recv_task = None

    async def start(self):
        lang_map = {"hi": "hi-IN", "en": "en-IN", "kn": "kn-IN"}
        lang_code = lang_map.get(self._lang, "hi-IN")

        params = {
            "language_code": lang_code,
        }
        url = f"wss://api.sarvam.ai/speech-to-text-stream?{urlencode(params)}"
        headers = {"api-subscription-key": self._api_key}
        self._ws = await ws_client.connect(url, extra_headers=headers)
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def _recv_loop(self):
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                if msg_type == "transcript":
                    text = msg.get("text", "").strip()
                    if text:
                        await self._queue.put({
                            "transcript": text,
                            "is_final": msg.get("is_final", True),
                            "confidence": msg.get("confidence", 0.0),
                        })
                elif msg_type == "utterance_end":
                    await self._queue.put({"utterance_end": True})
                elif msg_type == "error":
                    print(f"[stt] Sarvam error: {msg}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[stt] recv error: {e}")

    async def send_audio(self, pcm16_16khz: bytes):
        if self._ws:
            await self._ws.send(pcm16_16khz)

    async def close(self):
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
