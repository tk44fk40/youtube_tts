import pytest
import io
import wave
import numpy as np
from unittest.mock import patch, MagicMock
from youtube_tts import AudioPlayer

@pytest.fixture
def dummy_wav_bytes():
    # Generate 0.1s silence WAV (24000Hz, 1ch, 16bit)
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\x00" * 4800)
    return wav_io.getvalue()

@patch("youtube_tts.audio.sd")
def test_audio_initialization_success(mock_sd):
    mock_sd.query_devices.return_value = {"name": "default", "default_samplerate": 48000}
    player = AudioPlayer(default_device="custom_device")
    assert player.target_sample_rate == 48000
    assert mock_sd.default.device == "custom_device"
    mock_sd.query_devices.assert_called_once_with(None, 'output')

@patch("youtube_tts.audio.sd")
def test_audio_initialization_default_none(mock_sd):
    mock_sd.query_devices.return_value = {"name": "default", "default_samplerate": 48000}
    # Create a mock property to verify it was not set
    mock_sd.default = MagicMock()
    player = AudioPlayer()
    assert player.target_sample_rate == 48000
    # Verify that sd.default.device was not assigned
    assert not mock_sd.default.mock_calls

@patch("youtube_tts.audio.sd")
def test_audio_initialization_no_device(mock_sd):
    mock_sd.query_devices.side_effect = Exception("No output device found")
    player = AudioPlayer()
    # Fallback sampling rate in headless or CI environments
    assert player.target_sample_rate == 24000

def test_resample_audio():
    player = AudioPlayer()
    audio = np.array([100, 200, 300, 400], dtype=np.int16)
    
    assert np.array_equal(player.resample_audio(audio, 24000, 24000), audio)
    
    resampled = player.resample_audio(audio, 24000, 12000)
    assert len(resampled) == 2
    assert resampled[0] == 100
    assert resampled[1] == 400

@patch("youtube_tts.audio.sd")
def test_play_wav_success(mock_sd, dummy_wav_bytes):
    mock_sd.query_devices.return_value = {"name": "default", "default_samplerate": 24000}
    player = AudioPlayer()
    
    player.play_wav(dummy_wav_bytes)
    
    mock_sd.play.assert_called_once()
    args, kwargs = mock_sd.play.call_args
    assert kwargs["samplerate"] == 24000
    mock_sd.wait.assert_called_once()

@patch("youtube_tts.audio.sd")
def test_play_wav_with_device_switch(mock_sd, dummy_wav_bytes):
    mock_sd.query_devices.return_value = {"name": "default", "default_samplerate": 24000}
    player = AudioPlayer()
    
    player.play_wav(dummy_wav_bytes, device="3")
    assert mock_sd.default.device == 3

@pytest.fixture
def dummy_stereo_wav_bytes():
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\x00" * 9600)
    return wav_io.getvalue()

@patch("youtube_tts.audio.sd")
def test_play_wav_stereo(mock_sd, dummy_stereo_wav_bytes):
    mock_sd.query_devices.return_value = {"name": "default", "default_samplerate": 24000}
    player = AudioPlayer()
    
    player.play_wav(dummy_stereo_wav_bytes)
    
    mock_sd.play.assert_called_once()
    args, kwargs = mock_sd.play.call_args
    audio_data = args[0]
    assert audio_data.ndim == 2
    assert audio_data.shape[1] == 2

@patch("youtube_tts.audio.sd")
def test_play_wav_invalid_device_name(mock_sd, dummy_wav_bytes):
    mock_sd.query_devices.return_value = {"name": "default", "default_samplerate": 24000}
    player = AudioPlayer()
    
    player.play_wav(dummy_wav_bytes, device="default")
    assert mock_sd.default.device == "default"

@patch("youtube_tts.audio.sd")
def test_query_devices(mock_sd):
    mock_sd.query_devices.return_value = {"name": "dummy"}
    player = AudioPlayer()
    res = player.query_devices(device=1, kind="output")
    assert res == {"name": "dummy"}
    mock_sd.query_devices.assert_called_with(1, "output")

@patch("youtube_tts.audio.sd")
def test_audio_stop_exception(mock_sd, capsys):
    mock_sd.stop.side_effect = Exception("sounddevice error")
    player = AudioPlayer()
    
    player.stop()
    captured = capsys.readouterr()
    assert "sounddevice stop failed" in captured.out or "sounddevice stop failed" in captured.err

