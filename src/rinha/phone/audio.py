from __future__ import annotations

import audioop
import numpy as np

# Twilio Media Streams sends/receives mu-law 8kHz.
# Deepgram wants linear16 16kHz.
# Sarvam TTS returns linear16 16kHz.

# Mu-Law to linear16 (16-bit PCM, signed)
def ulaw_to_pcm16(payload: bytes) -> bytes:
    return audioop.ulaw2lin(payload, 2)


def pcm16_to_ulaw(samples: bytes) -> bytes:
    return audioop.lin2ulaw(samples, 2)


# Simple 8→16 kHz upsampling (duplicate samples)
def upsample_8_to_16(pcm16_8khz: bytes) -> bytes:
    arr = np.frombuffer(pcm16_8khz, dtype=np.int16)
    up = np.repeat(arr, 2)
    return up.tobytes()


# Simple 16→8 kHz downsampling (average pairs)
def downsample_16_to_8(pcm16_16khz: bytes) -> bytes:
    arr = np.frombuffer(pcm16_16khz, dtype=np.int16)
    if len(arr) % 2 != 0:
        arr = arr[:-1]
    pairs = arr.reshape(-1, 2).astype(np.int32)
    down = (pairs.sum(axis=1) / 2).astype(np.int16)
    return down.tobytes()
