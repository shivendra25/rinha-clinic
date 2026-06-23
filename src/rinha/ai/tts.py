from __future__ import annotations

import base64
import httpx
from rinha.config import get_config

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

_LANG_MAP = {
    "en": "en-IN",
    "hi": "hi-IN",
    "kn": "kn-IN",
}

_SPEAKER = {
    "hi": "anushka",
    "en": "anushka",
    "kn": "anushka",
}


async def text_to_speech(text: str, lang: str = "en") -> bytes:
    cfg = get_config()
    speaker = _SPEAKER.get(lang, "anushka")
    target_lang = _LANG_MAP.get(lang, "en-IN")

    payload = {
        "inputs": [text],
        "target_language_code": target_lang,
        "speaker": speaker,
        "pitch": 0.0,
        "pace": 1.0,
        "loudness": 1.0,
        "speech_sample_rate": 16000,
        "enable_preprocessing": True,
        "model": "bulbul:v2",
    }

    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": cfg.sarvam_api_key,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(SARVAM_TTS_URL, json=payload,
                                 headers=headers)
        resp.raise_for_status()
        data = resp.json()
        audios = data.get("audios", [])
        if not audios:
            raise RuntimeError(f"Sarvam TTS returned no audio: {data}")
        return base64.b64decode(audios[0])
