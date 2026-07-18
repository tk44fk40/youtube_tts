"""YouTubeTtsApp の実行制御に関するテストです。"""

from __future__ import annotations

import signal
from typing import Any
from unittest.mock import MagicMock, patch

from youtube_tts.runners.live import LiveRunner
from youtube_tts.runners.video import VideoRunner


def test_run_live(app: Any) -> None:
    """LiveRunner.run が正しく初期化とクリーンアップを行うかを検証します。"""
    mock_live_client = MagicMock()
    app.stop_event.set()

    runner = LiveRunner(
        app=app,
        live_client=mock_live_client,
        video_id="video123",
    )

    with (
        patch("threading.Thread") as mock_thread,
        patch("youtube_tts.workers.live.live_worker"),
    ):
        runner.run()
        mock_thread.assert_called()


def test_run_live_signal_handling(app: Any) -> None:
    """シグナルハンドラの動作を検証します。"""
    mock_live_client = MagicMock()
    app.stop_event.set()

    runner = LiveRunner(
        app=app,
        live_client=mock_live_client,
        video_id="video123",
    )

    with (
        patch("signal.signal") as mock_signal,
        patch("threading.Thread"),
        patch("youtube_tts.workers.live.live_worker"),
    ):
        runner.run()
        assert mock_signal.call_count >= 1
        args, _ = mock_signal.call_args_list[0]
        sig, handler = args

        app.stop_event.clear()
        handler(signal.SIGINT, None)
        assert app.stop_event.is_set() is True


def test_run_video(app: Any) -> None:
    """VideoRunner.run が正しく初期化とクリーンアップを行うかを検証します。"""
    mock_video_client = MagicMock()
    app.stop_event.set()

    runner = VideoRunner(
        app=app,
        video_client=mock_video_client,
        video_id="video123",
    )

    with (
        patch("threading.Thread") as mock_thread,
        patch("youtube_tts.workers.video.video_worker"),
    ):
        runner.run()
        mock_thread.assert_called()


def test_app_cleanup(app: Any) -> None:
    """cleanup メソッドがキュー内の残コメントを消化するかを検証します。"""
    from youtube_tts.models import SpeechItem

    app.speech_queue.put(SpeechItem("User", "Hello", 5))
    mock_thread = MagicMock()
    app.cleanup(playback_thread=mock_thread, wait_seconds=0.1)

    assert app.speech_queue.empty() is True
    app.audio_player.stop.assert_called_once()
    mock_thread.join.assert_called_once()


def test_app_cleanup_no_thread(app: Any) -> None:
    """cleanup 内で playback_thread が None の場合の挙動を検証します。"""
    from youtube_tts.models import SpeechItem

    app.speech_queue.put(SpeechItem("User", "Hello", 5))
    app.cleanup(playback_thread=None, wait_seconds=0.1)

    assert app.speech_queue.empty() is True
    app.audio_player.stop.assert_called_once()


def test_is_and_mark_processed(app: Any) -> None:
    """重複メッセージ ID の判定処理を検証します。"""
    app.max_processed_message_ids = 2
    assert app.is_and_mark_processed("id1") is False
    assert app.is_and_mark_processed("id2") is False
    assert app.is_and_mark_processed("id2") is True

    assert app.is_and_mark_processed("id3") is False
    assert app.is_and_mark_processed("id1") is False


def test_app_init_default_logger() -> None:
    """ロガー未指定時のデフォルト設定を検証します。"""
    from youtube_tts import YouTubeTtsApp

    test_app = YouTubeTtsApp(
        config=MagicMock(),
        voicevox_client=MagicMock(),
        audio_player=MagicMock(),
        obs_client=MagicMock(),
    )
    assert test_app.logger is not None


def test_write_chat_log_exception(app: Any) -> None:
    """チャットログの保存失敗時の例外ハンドリングを検証します。"""
    with patch("builtins.open", side_effect=OSError("Permission denied")):
        app.write_chat_log({"snippet": {"displayMessage": "test"}}, "vid123")


def test_app_cleanup_join_exception(app: Any) -> None:
    """cleanup 内の thread.join 失敗時の挙動を検証します。"""
    mock_thread = MagicMock()
    mock_thread.join.side_effect = RuntimeError("Join failed")
    app.cleanup(playback_thread=mock_thread, wait_seconds=0.1)


def test_run_live_signal_value_error(app: Any) -> None:
    """run 内のシグナル登録エラー時の挙動を検証します。"""
    mock_live_client = MagicMock()
    app.stop_event.set()
    runner = LiveRunner(app=app, live_client=mock_live_client, video_id="vid")
    with (
        patch("signal.signal", side_effect=ValueError("Not in main thread")),
        patch("threading.Thread"),
        patch("youtube_tts.workers.live.live_worker"),
    ):
        runner.run()


def test_run_live_worker_exception(app: Any) -> None:
    """live_worker 実行時の例外が正しくキャッチされるかを検証します。"""
    mock_live_client = MagicMock()
    runner = LiveRunner(app=app, live_client=mock_live_client, video_id="vid")
    with (
        patch("threading.Thread"),
        patch(
            "youtube_tts.workers.live.live_worker",
            side_effect=RuntimeError("Worker error"),
        ),
        patch.object(app, "cleanup") as mock_cleanup,
    ):
        runner.run()
        mock_cleanup.assert_called_once()


def test_run_video_signal_handling(app: Any) -> None:
    """run 内のシグナルハンドラの動作を検証します。"""
    mock_video_client = MagicMock()
    app.stop_event.set()
    runner = VideoRunner(
        app=app, video_client=mock_video_client, video_id="video123"
    )
    with (
        patch("signal.signal") as mock_signal,
        patch("threading.Thread"),
        patch("youtube_tts.workers.video.video_worker"),
    ):
        runner.run()
        assert mock_signal.call_count >= 1
        args, _ = mock_signal.call_args_list[0]
        sig, handler = args
        app.stop_event.clear()
        handler(signal.SIGINT, None)
        assert app.stop_event.is_set() is True


def test_run_video_signal_value_error(app: Any) -> None:
    """run 内のシグナル登録エラー時の挙動を検証します。"""
    mock_video_client = MagicMock()
    app.stop_event.set()
    runner = VideoRunner(
        app=app, video_client=mock_video_client, video_id="vid"
    )
    with (
        patch("signal.signal", side_effect=ValueError("Not in main thread")),
        patch("threading.Thread"),
        patch("youtube_tts.workers.video.video_worker"),
    ):
        runner.run()


def test_run_video_worker_exception(app: Any) -> None:
    """video_worker 実行時の例外が正しくキャッチされるかを検証します。"""
    mock_video_client = MagicMock()
    runner = VideoRunner(
        app=app, video_client=mock_video_client, video_id="vid"
    )
    with (
        patch("threading.Thread"),
        patch(
            "youtube_tts.workers.video.video_worker",
            side_effect=RuntimeError("Worker error"),
        ),
        patch.object(app, "cleanup") as mock_cleanup,
    ):
        runner.run()
        mock_cleanup.assert_called_once()
