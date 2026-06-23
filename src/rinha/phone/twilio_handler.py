from __future__ import annotations

import asyncio
import base64
import json
import time

from fastapi import WebSocket

from rinha.ai.stt import STT
from rinha.ai.tts import text_to_speech
from rinha.config import get_config
from rinha.orchestrator import Orchestrator
from rinha.phone.audio import (
    ulaw_to_pcm16, pcm16_to_ulaw,
    upsample_8_to_16, downsample_16_to_8
)


async def handle_call(ws: WebSocket):
    cfg = get_config()
    clinic = cfg.clinic_name
    stream_sid: str | None = None

    stt = STT(lang_hint="hi")
    await stt.start()

    orch = Orchestrator(clinic)
    send_queue: asyncio.Queue = asyncio.Queue()

    state: str = "INIT"
    utterance_text: str = ""
    utterance_final: bool = False
    send_active = True

    async def send_loop():
        nonlocal send_active
        seq = 0
        while send_active:
            chunk = None
            try:
                chunk = await asyncio.wait_for(send_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            if chunk is None:
                break
            if stream_sid is None:
                continue
            b64 = base64.b64encode(chunk).decode()
            msg = json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": b64},
                "sequenceNumber": str(seq),
            })
            seq += 1
            try:
                await ws.send_text(msg)
            except Exception:
                send_active = False
                break
            await asyncio.sleep(0.015)
        send_active = False

    async def speak_text(text: str, lang: str):
        nonlocal state
        state = "SPEAKING"
        pcm16_16k = await text_to_speech(text, lang)
        pcm16_8k = downsample_16_to_8(pcm16_16k)
        ulaw = pcm16_to_ulaw(pcm16_8k)
        chunk_size = 320
        for i in range(0, len(ulaw), chunk_size):
            send_queue.put_nowait(ulaw[i:i + chunk_size])
        await asyncio.sleep(0.4)
        state = "LISTENING"

    async def process_utterance():
        nonlocal utterance_text, utterance_final, state
        if not utterance_final or not utterance_text.strip():
            utterance_text = ""
            utterance_final = False
            return
        txt = utterance_text.strip()
        utterance_text = ""
        utterance_final = False
        print(f"[rinha] utterance: {txt[:120]}")
        orch.process_transcript(txt)

        resp = await orch.get_response()
        tool_loops = 0
        while resp.get("type") == "tool_call" and tool_loops < 5:
            tool_name = resp["tool_name"]
            args = resp["tool_args"]
            tc_id = resp["tool_call_id"]
            print(f"[rinha] tool: {tool_name}({json.dumps(args)})")
            await orch.execute_tool(tool_name, args, tc_id)
            resp = await orch.get_response()
            tool_loops += 1
            if tool_name == "nothing":
                state = "ENDED"
                return

        if resp.get("type") == "text" and resp.get("text"):
            reply = resp["text"]
            print(f"[rinha] reply ({orch._lang}): {reply[:120]}")
            await speak_text(reply, orch._lang)

    sender = asyncio.create_task(send_loop())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            evt = msg.get("event")

            if evt == "connected":
                stream_sid = msg.get("streamSid", "")
                print(f"[rinha] call connected: {stream_sid}")
                state = "GREETING"
                greeting = orch.get_greeting_text()
                print(f"[rinha] greeting ({orch._lang}): {greeting[:100]}")
                asyncio.create_task(speak_text(greeting, orch._lang))

            elif evt == "stop":
                print("[rinha] call ended")
                break

            elif evt == "media":
                if state == "SPEAKING":
                    continue

                payload = base64.b64decode(msg["media"]["payload"])
                pcm16 = ulaw_to_pcm16(payload)
                pcm16_16k = upsample_8_to_16(pcm16)
                await stt.send_audio(pcm16_16k)

                while not stt._queue.empty():
                    ev = stt._queue.get_nowait()
                    if "utterance_end" in ev:
                        if utterance_final and utterance_text.strip():
                            await process_utterance()
                    elif "transcript" in ev:
                        txt = ev["transcript"]
                        if ev["is_final"]:
                            utterance_text = txt
                            utterance_final = True
                        else:
                            utterance_text = txt

    except Exception as e:
        print(f"[rinha] error: {e}")
    finally:
        send_active = False
        send_queue.put_nowait(None)
        if summary := orch.booking_summary():
            print(f"[rinha] booking: {summary}")
        try:
            sender.cancel()
        except Exception:
            pass
        await stt.close()
