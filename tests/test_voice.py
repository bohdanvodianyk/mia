"""Offline units for the voice layer (cost math; no network)."""

from __future__ import annotations

from mia.voice import transcribe as vt


def test_transcription_cost_one_minute():
    assert vt.transcription_cost(60) == 0.006


def test_transcription_cost_prorated():
    # 30 seconds is half a minute.
    assert vt.transcription_cost(30) == 0.003


def test_transcription_cost_zero_and_negative_are_free():
    assert vt.transcription_cost(0) == 0.0
    assert vt.transcription_cost(-5) == 0.0


def test_max_voice_seconds_is_generous_but_bounded():
    assert vt.MAX_VOICE_SECONDS == 600
