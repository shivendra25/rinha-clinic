#!/usr/bin/env python3
"""Rinha pipeline smoke test — no Twilio needed.

Tests: STT (Deepgram), LLM (Groq), TTS (Sarvam).
Pass a WAV file (16kHz mono) on the command line or record one via mic.

  python test_pipeline.py recording.wav
  python test_pipeline.py --record          # record 5s from mic

Requires: .env with DEEPGRAM_API_KEY, GROQ_API_KEY, SARVAM_API_KEY.
"""
from __future__ import annotations

import asyncio
import argparse
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rinha.config import get_config
from rinha.ai.stt import STT
from rinha.ai.llm import LLM
from rinha.ai.tts import text_to_speech
from rinha.orchestrator import Orchestrator, detect_language

CHUNK = 3200  # 200ms @ 16kHz mono 16-bit


async def transcribe_file(wav_path: str) -> str:
    stt = STT(lang_hint="hi")
    await stt.start()

    with wave.open(wav_path, "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1 or wf.getframerate() != 16000:
            print("[test] WAV must be 16kHz mono 16-bit PCM")
            return ""

        frames: list[str] = []
        utt_done = asyncio.Event()

        async def collect():
            while not utt_done.is_set():
                ev = await stt._queue.get()
                if "utterance_end" in ev:
                    utt_done.set()
                    break
                if "transcript" in ev and ev["is_final"]:
                    frames.append(ev["transcript"])

        collector = asyncio.create_task(collect())

        data = wf.readframes(CHUNK)
        pcm16 = bytes(2 * CHUNK) if len(data) != CHUNK * 2 else data
        while data:
            await stt.send_audio(data)
            data = wf.readframes(CHUNK)
            await asyncio.sleep(0.005)

        await asyncio.sleep(2.0)
        await stt._queue.put({"utterance_end": True})
        await asyncio.wait_for(utt_done.wait(), timeout=5.0)
        collector.cancel()
        try:
            await collector
        except asyncio.CancelledError:
            pass

    await stt.close()
    return " ".join(frames)


async def run_pipeline(wav_path: str):
    cfg = get_config()
    print(f"[test] Clinic: {cfg.clinic_name}")
    print(f"[test] Languages: {cfg.clinic_languages}")
    print()

    print("[1/3] STT — transcribing...")
    transcript = await transcribe_file(wav_path)
    if not transcript:
        transcript = "Namaste, mujhe kal subah ka appointment chahiye"
        print(f"[1/3] STT empty — using fallback: {transcript}")
    else:
        print(f"[1/3] STT result: {transcript}")

    lang = detect_language(transcript)
    print(f"[1/3] Detected language: {lang}")
    print()

    print("[2/3] LLM — generating response...")
    orch = Orchestrator(cfg.clinic_name)
    orch._lang = lang
    orch.process_transcript(transcript)

    resp = await orch.get_response()
    tool_loops = 0
    while resp.get("type") == "tool_call" and tool_loops < 5:
        print(f"[2/3] Tool call: {resp['tool_name']}({resp['tool_args']})")
        await orch.execute_tool(resp["tool_name"], resp["tool_args"],
                                resp["tool_call_id"])
        resp = await orch.get_response()
        tool_loops += 1
        if resp.get("tool_name") == "nothing":
            break

    reply = resp.get("text", "")
    print(f"[2/3] LLM reply: {reply}")
    print()

    if reply:
        print("[3/3] TTS — generating audio...")
        t0 = time.time()
        audio = await text_to_speech(reply, lang)
        elapsed = time.time() - t0
        out_file = "/tmp/rinha_response.wav"
        with wave.open(out_file, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio)
        print(f"[3/3] TTS done: {len(audio)} bytes, {elapsed:.2f}s")
        print(f"[3/3] Saved to {out_file}")
        print(f"[3/3] Play: afplay {out_file}  # macOS")

    if summary := orch.booking_summary():
        print(f"\n[test] Booking: {summary}")


def record_wav(seconds: int = 5) -> str:
    path = "/tmp/rinha_test.wav"
    cmd = ["rec" if sys.platform != "darwin" else "sox",
           "-d", "-r", "16000", "-c", "1", "-b", "16",
           path, "trim", "0", str(seconds)]
    print(f"[test] Recording {seconds}s... speak now")
    subprocess.run(["sox", "-d", "-r", "16000", "-c", "1", "-b", "16",
                    path, "trim", "0", str(seconds)],
                   capture_output=True, check=False)
    return path


def main():
    parser = argparse.ArgumentParser(description="Rinha pipeline smoke test")
    parser.add_argument("wav", nargs="?", help="16kHz mono WAV file")
    parser.add_argument("--record", action="store_true",
                        help="Record 5s from microphone")
    args = parser.parse_args()

    wav = args.wav
    if args.record:
        wav = record_wav()
    if not wav:
        parser.print_help()
        sys.exit(1)

    asyncio.run(run_pipeline(wav))


if __name__ == "__main__":
    main()
