# tests/conftest.py
# Defines common fixtures and helpers across tests.
#
# テスト全体で共通のフィクスチャやヘルパーを定義します。
import io
import wave
import pytest


@pytest.fixture
def dummy_wav_bytes():
    """Generates a 0.1-second silent WAV data (24000Hz, mono, 16bit).
    
    0.1秒の無音WAVデータ（24000Hz, モノラル, 16bit）を
    生成する共通フィクスチャ。
    """
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\x00" * 4800)
    return wav_io.getvalue()


@pytest.fixture
def dummy_stereo_wav_bytes():
    """Generates a 0.1-second silent WAV data (24000Hz, stereo, 16bit).
    
    0.1秒の無音WAVデータ（24000Hz, ステレオ, 16bit）を
    生成する共通フィクスチャ。
    """
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\x00" * 9600)
    return wav_io.getvalue()
