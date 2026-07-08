"""Transcribe Telegram voice notes with OpenAI Whisper.

Telegram sends voice notes as OGG/Opus, which Whisper accepts directly — no
ffmpeg needed. Audio is kept in memory and never written to disk (plan §8:
transcripts are stored, audio is not).
"""

from __future__ import annotations

# Whisper is priced at $0.006 per minute of audio, billed per second.
WHISPER_USD_PER_MINUTE = 0.006

# Whisper's hard input cap is 25 MB; Telegram voice notes are ~1 MB/min, so this
# duration ceiling keeps us well under it and bounds cost/latency.
MAX_VOICE_SECONDS = 600


def transcription_cost(duration_seconds: float) -> float:
    """USD cost of transcribing a clip of the given length."""
    return max(0.0, duration_seconds) / 60.0 * WHISPER_USD_PER_MINUTE


async def transcribe(
    client, model: str, audio: bytes, filename: str = "voice.ogg"
) -> str:
    """Return the transcript of OGG/Opus `audio`. Language is auto-detected.

    Passing a ``(filename, bytes)`` tuple lets Whisper infer the format from the
    extension without us touching the filesystem.
    """
    response = await client.audio.transcriptions.create(
        model=model,
        file=(filename, audio),
    )
    return (response.text or "").strip()
