"""音声合成および再生制御の動作を検証します。"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from youtube_tts import CommentItem


def test_speak_success(app: Any) -> None:
    """指定パラメータによる音声合成と再生の正常系連動を検証します。"""
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


def test_speak_failure(app: Any) -> None:
    """音声合成の例外発生時にクラッシュしないかを検証します。"""
    app.voicevox_client.synthesize.side_effect = Exception("VOICEVOX Error")
    app.verbose = False

    with (
        patch.object(app.logger, "error") as mock_error,
        patch.object(app.logger, "debug") as mock_debug,
    ):
        app.speak("エラーテスト")
        app.audio_player.play_wav.assert_not_called()

        assert mock_error.call_count == 3
        mock_error.assert_any_call(
            "[ERROR] 音声の合成または再生に失敗しました。"
        )
        mock_debug.assert_not_called()


def test_speak_failure_verbose(app: Any) -> None:
    """音声合成の失敗時に詳細ログが出力されるかを検証します。"""
    app.voicevox_client.synthesize.side_effect = Exception("VOICEVOX Error")
    app.verbose = True

    with (
        patch.object(app.logger, "error") as mock_error,
        patch.object(app.logger, "debug") as mock_debug,
    ):
        app.speak("エラーテスト")
        app.audio_player.play_wav.assert_not_called()

        assert mock_error.call_count == 3
        mock_debug.assert_called_once_with("  (エラー詳細: VOICEVOX Error)")


def test_playback_worker(app: Any) -> None:
    """再生用のコメントが正しく整形されて音声再生されるかを検証します。"""
    app.comment_queue.put(("User1", "こんにちは"))

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text: str, *args: Any, **kwargs: Any) -> None:
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()

        mock_speak.assert_called_once_with("User1 こんにちは", speed_scale=1.0)


def test_playback_worker_dynamic_speed_boost(app: Any) -> None:
    """滞留文字数に応じて再生速度が自動でブーストされるかを検証します。"""
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    app.comment_queue.put(CommentItem("User1", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 175, 180))
    app.queued_char_count = 191

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text: str, speed_scale: float | None = None) -> None:
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()

        assert app.queued_char_count == 180
        mock_speak.assert_called_once_with("User1 Hello", speed_scale=1.8)


def test_playback_worker_backward_compatibility(app: Any) -> None:
    """再生キューにおける旧仕様（タプル形式）データとの互換性を検証します。"""
    app.comment_queue.put(("UserOld", "HelloOld"))
    app.queued_char_count = 15

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text: str, speed_scale: float | None = None) -> None:
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()

        assert app.queued_char_count == 0
        mock_speak.assert_called_once_with("UserOld HelloOld", speed_scale=1.0)


def test_playback_worker_speed_boost_lower_limit(app: Any) -> None:
    """自動ブーストの閾値未満において通常速度が維持されるかを検証します。"""
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    app.comment_queue.put(CommentItem("User", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 25, 30))
    app.queued_char_count = 41

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text: str, speed_scale: float | None = None) -> None:
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()
        mock_speak.assert_called_once_with("User Hello", speed_scale=1.0)


def test_playback_worker_speed_boost_upper_limit(app: Any) -> None:
    """自動ブースト時に最大速度を超えないかを検証します。"""
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.0

    app.comment_queue.put(CommentItem("User", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 295, 300))
    app.queued_char_count = 311

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text: str, speed_scale: float | None = None) -> None:
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()
        mock_speak.assert_called_once_with("User Hello", speed_scale=2.0)
