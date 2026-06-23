from __future__ import annotations

import uvicorn
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import PlainTextResponse, HTMLResponse

from rinha.ai.llm import LLM
from rinha.orchestrator import detect_language, parse_booking_intent, book

app = FastAPI(title="Rinha Clinic")

# ── Twilio ───────────────────────────────────────────────────────────────────

TWILIO_GREETING = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/process-speech" method="POST"
            speechTimeout="auto" language="hi-IN" speechModel="phone_call">
        <Say voice="Polly.Aditi" language="hi-IN">
            Namaste. Dr. Sharma clinic mein aapka swagat hai. Main aapki kaise madad kar sakta hoon?
        </Say>
    </Gather>
    <Say voice="Polly.Aditi" language="hi-IN">Koi jawab nahi mila. Dhanyavaad.</Say>
</Response>"""


@app.post("/twilio-call")
async def twilio_call():
    return PlainTextResponse(TWILIO_GREETING, media_type="text/xml")


# ── Exotel ───────────────────────────────────────────────────────────────────

EXOTEL_GREETING = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Namaste. Dr. Sharma clinic mein aapka swagat hai. Appointment book karne ke liye, kripya beep ke baad apna naam, phone number aur pasand ka samay bataayein.</Say>
    <Record maxSilence="4s" action="/exotel-recording" method="POST" />
</Response>"""

EXOTEL_RESPONSE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{reply}</Say>
    <Record maxSilence="4s" action="/exotel-recording" method="POST" />
</Response>"""


@app.post("/exotel-call")
async def exotel_call():
    print("[exotel] incoming call")
    return PlainTextResponse(EXOTEL_GREETING, media_type="text/xml")


@app.post("/exotel-recording")
async def exotel_recording(RecordingUrl: str = Form(""),
                           CallSid: str = Form("")):
    print(f"[exotel] recording: {RecordingUrl[:80]}...")
    if not RecordingUrl:
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            '<Say>Maaf kijiye, recording nahi mili.</Say></Response>',
            media_type="text/xml")

    # Download recording and transcribe via Sarvam
    try:
        from rinha.config import get_config
        cfg = get_config()
        async with httpx.AsyncClient(timeout=30) as client:
            rec_resp = await client.get(RecordingUrl)
            audio_bytes = rec_resp.content

        # Sarvam STT
        stt_resp = httpx.post(
            "https://api.sarvam.ai/speech-to-text-translate",
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            data={
                "language_code": "hi-IN",
                "model": "saaras:v2",
                "with_timestamps": "false",
            },
            headers={"api-subscription-key": cfg.sarvam_api_key},
            timeout=30,
        )
        stt_data = stt_resp.json()
        text = stt_data.get("transcript", "").strip()
        print(f"[exotel] STT: \"{text}\"")
    except Exception as e:
        print(f"[exotel] STT error: {e}")
        text = ""

    # Process
    if text:
        lang = detect_language(text)
        booking = parse_booking_intent(text)
        if booking:
            book(booking)
            name = booking["name"]
            tm = booking["time"]
            reply = f"{name} ji, aapka appointment {tm} ke liye book ho gaya hai. Dhanyavaad."
        else:
            llm = LLM("Dr. Sharma Clinic")
            reply = await llm.chat(text)
    else:
        reply = "Maaf kijiye, aapki aawaaz clear nahi suni. Kripya dobara boliye."

    reply = reply.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return PlainTextResponse(
        EXOTEL_RESPONSE_TEMPLATE.replace("{reply}", reply),
        media_type="text/xml")


# ── Shared ───────────────────────────────────────────────────────────────────

@app.post("/process-speech")
async def process_speech(CallSid: str = Form(...),
                         SpeechResult: str = Form(""),
                         Confidence: str = Form("0")):
    text = SpeechResult.strip()
    print(f"[rinha] call={CallSid[-8:]}: \"{text}\"")

    if not text:
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            '<Say voice="Polly.Aditi" language="hi-IN">Maaf kijiye, mujhe sunai nahi diya.</Say></Response>',
            media_type="text/xml")

    lang = detect_language(text)

    booking = parse_booking_intent(text)
    if booking:
        book(booking)
        name = booking["name"]
        tm = booking["time"]
        reply = f"{name} ji, aapka appointment {tm} ke liye book ho gaya hai. Dhanyavaad."
    else:
        llm = LLM("Dr. Sharma Clinic")
        reply = await llm.chat(text)

    reply = reply.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    voice = "Polly.Aditi"
    lang_code = "hi-IN" if lang == "hi" else ("kn-IN" if lang == "kn" else "en-IN")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{voice}" language="{lang_code}">{reply}</Say>
    <Gather input="speech" action="/process-speech" method="POST"
            speechTimeout="auto" language="{lang_code}" speechModel="phone_call">
        <Say voice="{voice}" language="{lang_code}">Kuch aur madad chahiye?</Say>
    </Gather>
</Response>"""
    return PlainTextResponse(twiml, media_type="text/xml")


@app.get("/", response_class=HTMLResponse)
async def index():
    return "<h1>Rinha Clinic</h1><p>AI receptionist running.</p>"


@app.get("/health")
async def health():
    return {"status": "ok"}


def cli():
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"[rinha] on port {port}")
    uvicorn.run("rinha.main:app", host="0.0.0.0", port=port,
                log_level="warning", reload=False)


if __name__ == "__main__":
    cli()
