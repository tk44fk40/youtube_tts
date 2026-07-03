"""YouTube TTS アプリケーションテスト用の共通フィクスチャ定義。

重複するモックのセットアップをここに集約します。
"""

import io
import sys
import wave
from unittest.mock import MagicMock

import pytest

# Mock sounddevice to avoid PortAudio dependency in test environments
# テスト環境における PortAudio 依存を回避するために sounddevice をモックする
sys.modules["sounddevice"] = MagicMock()

from youtube_tts import (
    AppConfig,
    AudioPlayer,
    VoicevoxClient,
    YouTubeTtsApp,
    setup_logger,
)


@pytest.fixture
def mock_sd():
    """sounddevice のモックをクリーンな状態で提供するフィクスチャ。

    Yields:
        MagicMock: テストごとに新しく生成された sounddevice のモック。
    """
    original_sd = sys.modules.get("sounddevice")
    new_sd = MagicMock()
    # stream.active ループが無限ループになるのを防ぐため、初期状態で False に設定する
    new_sd.get_stream.return_value.active = False
    sys.modules["sounddevice"] = new_sd
    yield new_sd
    if original_sd is not None:
        sys.modules["sounddevice"] = original_sd


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


@pytest.fixture
def mock_app_dependencies():
    """アプリケーションが依存するコンポーネントのモックを生成します。"""
    config = AppConfig(
        dictionary_path="dictionary.txt",
        ng_words_path="ng_words.txt",
        volume_path="volume.txt",
    )
    config.volume_scale = 0.5

    voicevox_client = MagicMock(spec=VoicevoxClient)
    audio_player = MagicMock(spec=AudioPlayer)
    audio_player.target_sample_rate = 24000

    logger = setup_logger(verbose=True)

    return config, voicevox_client, audio_player, logger


@pytest.fixture
def app(mock_app_dependencies):
    """テスト対象となる YouTubeTtsApp インスタンスを生成します。"""
    config, voicevox_client, audio_player, logger = mock_app_dependencies
    return YouTubeTtsApp(
        config=config,
        voicevox_client=voicevox_client,
        audio_player=audio_player,
        logger=logger,
    )
