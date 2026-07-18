"""YouTube TTS アプリケーションテスト用の共通フィクスチャ定義。

重複するモックのセットアップをここに集約します。
"""

from __future__ import annotations

import io
import wave
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from youtube_tts import (
    AppConfig,
    AudioPlayer,
    VoicevoxClient,
    YouTubeLiveChatClient,
    YouTubeTtsApp,
    YouTubeVideoClient,
    setup_logger,
)

if TYPE_CHECKING:
    import logging


@pytest.fixture
def mock_live_client() -> MagicMock:
    """標準的な YouTubeLiveChatClient モックを生成します。

    Returns:
        MagicMock: 自チャンネル所有の配信として
            セットアップ済みの live_client モックです。
    """
    client = MagicMock(spec=YouTubeLiveChatClient)
    client.get_my_channel_id.return_value = "my_channel_123"
    client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    client.get_live_chat_id.return_value = "chat_live_123"
    return client


@pytest.fixture
def mock_video_client() -> MagicMock:
    """標準的な YouTubeVideoClient モックを生成します。

    Returns:
        MagicMock: YouTubeVideoClient のモックです。
    """
    return MagicMock(spec=YouTubeVideoClient)


@pytest.fixture
def dummy_wav_bytes() -> bytes:
    """0.1秒の無音WAVデータ（24000Hz, モノラル, 16bit）を生成します。

    Returns:
        WAVフォーマットのバイト列。
    """
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\x00" * 4800)
    return wav_io.getvalue()


@pytest.fixture
def dummy_stereo_wav_bytes() -> bytes:
    """0.1秒の無音WAVデータ（24000Hz, ステレオ, 16bit）を生成します。

    Returns:
        WAVフォーマットのバイト列。
    """
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\x00" * 9600)
    return wav_io.getvalue()


@pytest.fixture
def mock_app_dependencies() -> tuple[
    AppConfig, MagicMock, MagicMock, logging.Logger
]:
    """アプリケーションが依存するコンポーネントのモックを生成します。

    Returns:
        config, voicevox_client, audio_player, logger のタプル。
    """
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
def app(
    mock_app_dependencies: tuple[
        AppConfig, MagicMock, MagicMock, logging.Logger
    ],
) -> YouTubeTtsApp:
    """テスト対象となる YouTubeTtsApp インスタンスを生成します。

    Args:
        mock_app_dependencies: 依存コンポーネントのモックタプル。

    Returns:
        YouTubeTtsApp インスタンス。
    """
    config, voicevox_client, audio_player, logger = mock_app_dependencies
    return YouTubeTtsApp(
        config=config,
        voicevox_client=voicevox_client,
        audio_player=audio_player,
        logger=logger,
    )


@pytest.fixture
def stop_on_speak(
    app: YouTubeTtsApp,
) -> Callable[..., None]:
    """speak 呼び出し時に stop_event をセットするコールバックです。

    playback_worker テスト用に、1回の speak 呼び出しで
    ループを終了させるために使用します。

    Args:
        app: YouTubeTtsApp インスタンスです。

    Returns:
        speak の side_effect 用コールバック関数です。
    """

    def _side_effect(*args: Any, **kwargs: Any) -> None:
        app.stop_event.set()

    return _side_effect
