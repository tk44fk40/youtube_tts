"""音声合成および再生制御の動作を検証します。"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from youtube_tts import SpeechItem

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp


def test_speak_success(app: YouTubeTtsApp) -> None:
    """指定パラメータによる音声合成と再生の正常系連動を検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
    """
    app.voicevox_client.synthesize.return_value = b"mock_wav"
    app.speak("テストテキスト")

    app.voicevox_client.synthesize.assert_called_with(
        text="テストテキスト",
        volume_scale=0.5,
        speed_scale=1.0,
        target_sample_rate=app.audio_player.target_sample_rate,
    )
    app.audio_player.play_wav.assert_called_with(b"mock_wav")

    # 速度を指定した場合の音声合成と再生の連動を検証します。
    app.speak("テストテキスト2", speed_scale=1.5)
    app.voicevox_client.synthesize.assert_called_with(
        text="テストテキスト2",
        volume_scale=0.5,
        speed_scale=1.5,
        target_sample_rate=app.audio_player.target_sample_rate,
    )


@pytest.mark.parametrize("verbose", [False, True])
def test_speak_failure(app: YouTubeTtsApp, verbose: bool) -> None:
    """音声合成の例外発生時にクラッシュしないかを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
        verbose: 詳細ログを出力するかどうかの設定値です。
    """
    app.voicevox_client.synthesize.side_effect = Exception("VOICEVOX Error")
    app.verbose = verbose

    with (
        patch.object(app.logger, "error") as mock_error,
        patch.object(app.logger, "debug") as mock_debug,
    ):
        app.speak("エラーテスト")
        app.audio_player.play_wav.assert_not_called()

        assert mock_error.call_count == 3
        mock_error.assert_any_call("音声の合成または再生に失敗しました。")
        mock_debug.assert_called_once_with("  (エラー詳細: VOICEVOX Error)")


def test_playback_worker(app: YouTubeTtsApp) -> None:
    """再生用のコメントが正しく整形されて音声再生されるかを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
    """
    app.speech_queue.put(SpeechItem("User1", "こんにちは", 11))

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text: str, *args: Any, **kwargs: Any) -> None:
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        from youtube_tts.workers.playback import playback_worker
        playback_worker(app)

        mock_speak.assert_called_once_with("User1 こんにちは", speed_scale=1.0)


def test_playback_worker_dynamic_speed_boost(
    app: YouTubeTtsApp,
    stop_on_speak: Callable[..., None],
) -> None:
    """滞留文字数に応じて再生速度が自動でブーストされるかを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
        stop_on_speak: speak 時に停止するコールバックです。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    app.speech_queue.put(SpeechItem("User1", "Hello", 11))
    app.speech_queue.put(SpeechItem("User2", "A" * 175, 180))
    # SpeechQueue.put internally updates queued_char_count, so no need to manually set it.
    # The count should be 191 naturally.

    with patch.object(app, "speak") as mock_speak:
        mock_speak.side_effect = stop_on_speak
        from youtube_tts.workers.playback import playback_worker
        playback_worker(app)

        assert app.speech_queue.queued_char_count == 180
        mock_speak.assert_called_once_with("User1 Hello", speed_scale=1.8)


def test_playback_worker_speed_boost_lower_limit(
    app: YouTubeTtsApp,
    stop_on_speak: Callable[..., None],
) -> None:
    """自動ブーストの閾値未満において通常速度が維持されるかを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
        stop_on_speak: speak 時に停止するコールバックです。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    app.speech_queue.put(SpeechItem("User", "Hello", 11))
    app.speech_queue.put(SpeechItem("User2", "A" * 25, 30))

    with patch.object(app, "speak") as mock_speak:
        mock_speak.side_effect = stop_on_speak
        from youtube_tts.workers.playback import playback_worker
        playback_worker(app)
        mock_speak.assert_called_once_with("User Hello", speed_scale=1.0)


def test_playback_worker_speed_boost_upper_limit(
    app: YouTubeTtsApp,
    stop_on_speak: Callable[..., None],
) -> None:
    """自動ブースト時に最大速度を超えないかを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
        stop_on_speak: speak 時に停止するコールバックです。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.0

    app.speech_queue.put(SpeechItem("User", "Hello", 11))
    app.speech_queue.put(SpeechItem("User2", "A" * 295, 300))

    with patch.object(app, "speak") as mock_speak:
        mock_speak.side_effect = stop_on_speak
        from youtube_tts.workers.playback import playback_worker
        playback_worker(app)
        mock_speak.assert_called_once_with("User Hello", speed_scale=2.0)


def test_playback_worker_empty_queue(app: YouTubeTtsApp) -> None:
    """キューが空のときにループが継続し、stop_eventで終了することを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
    """
    import queue

    # 最初は空で、タイムアウト後に stop_event がセットされるようにします。
    # playback_worker は stop_event がセットされるまでループするため、
    # スレッドやモック側で制御するか、一定回数で stop_event をセットします。
    # ここでは queue.get をパッチして、1回目に queue.Empty を発生させ、
    # 2回目に stop_event をセットして終了させます。
    original_get = app.speech_queue.get

    call_count = 0

    def mock_get(timeout: float | None = None, block: bool = True) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise queue.Empty()
        app.stop_event.set()
        return original_get(timeout=timeout, block=block)

    with patch.object(app.speech_queue, "get", side_effect=mock_get):
        from youtube_tts.workers.playback import playback_worker
        playback_worker(app)
        assert call_count == 2


def test_playback_worker_auto_speed_boost_info_log(app: YouTubeTtsApp) -> None:
    """自動ブースト有効時と無効時で異なるTALKログが出力されるかを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2
    app.speech_queue.put(SpeechItem("User", "Hello", 11))
    app.speech_queue.put(SpeechItem("User2", "A" * 175, 180))

    with (
        patch.object(app, "speak") as mock_speak,
        patch.object(app.logger, "info") as mock_info,
    ):

        def side_effect(text: str, speed_scale: float | None = None) -> None:
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        from youtube_tts.workers.playback import playback_worker
        playback_worker(app)

        # [TALK] ログに (Speed: 1.80x) が含まれることを確認します。
        mock_info.assert_any_call("[TALK] User Hello (Speed: 1.80x)")


def test_playback_worker_speed_boost_no_boost_needed(
    app: YouTubeTtsApp,
    stop_on_speak: Callable[..., None],
) -> None:
    """基本速度が最大速度以上の場合にブーストが行われないことを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
        stop_on_speak: speak 時に停止するコールバックです。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 2.5
    app.config.max_speed = 2.2
    app.speech_queue.put(SpeechItem("User", "Hello", 11))
    app.speech_queue.put(SpeechItem("User2", "A" * 175, 180))

    with patch.object(app, "speak") as mock_speak:
        mock_speak.side_effect = stop_on_speak
        from youtube_tts.workers.playback import playback_worker
        playback_worker(app)
        mock_speak.assert_called_once_with("User Hello", speed_scale=2.5)


def test_playback_worker_rate_at_base_zero(
    app: YouTubeTtsApp,
    stop_on_speak: Callable[..., None],
) -> None:
    """基本速度が0の場合に、推定所要時間が0となり、
    ブースト速度が基本速度のままとなることを検証します。

    Args:
        app: YouTubeTtsApp インスタンス。
        stop_on_speak: speak 時に停止するコールバックです。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 0.0
    app.config.max_speed = 2.2
    app.speech_queue.put(SpeechItem("User", "Hello", 11))

    with patch.object(app, "speak") as mock_speak:
        mock_speak.side_effect = stop_on_speak
        from youtube_tts.workers.playback import playback_worker
        playback_worker(app)
        mock_speak.assert_called_once_with("User Hello", speed_scale=0.0)
