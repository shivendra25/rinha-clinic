from __future__ import annotations

import json
import re
from pathlib import Path

from groq import AsyncGroq
from rinha.config import get_config

_PROMPT_FILE = Path(__file__).resolve().parent.parent.parent.parent \
    / "prompts" / "receptionist.md"

_FALLBACK = """\
You are a warm medical receptionist for {clinic_name}.

CLINIC: {clinic_name}, general physician.
Speak in the patient's language: Hindi, English, or Kannada.

RULES:
- If booking: IMMEDIATELY call book_appointment. Never describe what you will do.
- For FAQ: answer directly.
- For emergency: call escalate_to_human.
- Keep responses under 25 words. No emojis. No markdown.
"""


def _load_prompt() -> str:
    try:
        return _PROMPT_FILE.read_text(encoding="utf-8")
    except Exception:
        return _FALLBACK


SYSTEM_PROMPT_TEMPLATE = _load_prompt()


class LLM:
    def __init__(self, clinic_name: str = "Dr. Sharma"):
        cfg = get_config()
        self._client = AsyncGroq(api_key=cfg.groq_api_key)
        self._model = "llama-3.3-70b-versatile"
        doctor = clinic_name.removeprefix("Dr. ").strip()
        self._system = SYSTEM_PROMPT_TEMPLATE.format(
            clinic_name=clinic_name, doctor_name=doctor)

    async def chat(self, user_text: str) -> str:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.7,
                max_tokens=200,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            print(f"[llm] error: {e}")
            return "Maaf kijiye, kuch samasya ho gayi."
