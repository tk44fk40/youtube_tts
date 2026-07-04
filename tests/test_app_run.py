"""YouTubeTtsApp の実行制御に関するテストです。"""

from __future__ import annotations

import signal
from typing import Any
from unittest.mock import MagicMock, patch


def test_run_live(app: Any) -> None:
    """run_live メソッドが正しく初期化とクリーンアップを行うかを検証します。"""
    mock_live_client = MagicMock()
    app.stop_event.set()  # 即座に待機ループを終了させます。

    with (
        patch("threading.Thread") as mock_thread,
        patch.object(app, "live_worker"),
    ):
        app.run_live(
            live_client=mock_live_client,
            video_id="video123",
            quota_check=True,
            quota_talk=True,
            tts_test=None,
            chat_interval=1.0,
            quota_interval=60.0,
            stream_check_interval=180.0,
            project_id="project123",
            verbose=False,
            backlog_seconds=10,
        )

        mock_thread.assert_called()


def test_run_live_signal_handling(app: Any) -> None:
    """シグナルハンドラの動作を検証します。"""
    mock_live_client = MagicMock()
    app.stop_event.set()

    with (
        patch("signal.signal") as mock_signal,
        patch("threading.Thread"),
        patch.object(app, "live_worker"),
    ):
        app.run_live(
            live_client=mock_live_client,
            video_id="video123",
            quota_check=True,
            quota_talk=True,
            tts_test=None,
            chat_interval=1.0,
            quota_interval=60.0,
            stream_check_interval=180.0,
            project_id="project123",
            verbose=False,
            backlog_seconds=10,
        )

        assert mock_signal.call_count >= 1
        args, _ = mock_signal.call_args_list[0]
        sig, handler = args

        app.stop_event.clear()
        handler(signal.SIGINT, None)
        assert app.stop_event.is_set() is True


def test_run_video(app: Any) -> None:
    """run_video メソッドが正しく初期化とクリーンアップを行うかを検証します。"""
    mock_video_client = MagicMock()
    app.stop_event.set()  # 即座に待機ループを終了させます。

    with (
        patch("threading.Thread") as mock_thread,
        patch.object(app, "video_worker"),
    ):
        app.run_video(
            video_client=mock_video_client,
            video_id="video123",
            chat_interval=1.0,
            verbose=False,
            backlog_counts=100,
        )

        mock_thread.assert_called()


def test_app_cleanup(app: Any) -> None:
    """cleanup メソッドがキュー内の残コメントを消化するかを検証します。"""
    app.comment_queue.put(("User", "Hello"))
    mock_thread = MagicMock()
    app.cleanup(playback_thread=mock_thread, wait_seconds=0.1)

    assert app.comment_queue.empty() is True
    app.audio_player.stop.assert_called_once()
    mock_thread.join.assert_called_once()


def test_is_and_mark_processed(app: Any) -> None:
    """重複メッセージ ID の判定処理を検証します。"""
    app.max_processed_message_ids = 2
    assert app.is_and_mark_processed("id1") is False
    assert app.is_and_mark_processed("id2") is False
    assert app.is_and_mark_processed("id2") is True

    # id3 を追加すると最大 2 件制限により最古の id1 が破棄されます。
    assert app.is_and_mark_processed("id3") is False
    assert app.is_and_mark_processed("id1") is False


def test_format_reset_time_for_speech(app: Any) -> None:
    """クォータリセット時刻の音声用フォーマット処理を検証します。"""
    from datetime import datetime, timedelta

    now = datetime.now().astimezone()

    # 今日が対象の場合のフォーマット結果を検証します。(delta_days=0)
    t0 = now.replace(hour=15, minute=30)
    res0 = app._format_reset_time_for_speech(t0)
    assert "今日" in res0
    assert "15時30分" in res0

    # 明日が対象の場合のフォーマット結果を検証します。(delta_days=1)
    t1 = (now + timedelta(days=1)).replace(hour=15, minute=0)
    res1 = app._format_reset_time_for_speech(t1)
    assert "明日" in res1
    assert "15時" in res1

    # 明後日以降が対象の場合のフォーマット結果を検証します。(delta_days=2)
    t2 = (now + timedelta(days=2)).replace(hour=15, minute=0)
    res2 = app._format_reset_time_for_speech(t2)
    assert f"{t2.month}月{t2.day}日" in res2


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


@patch("youtube_tts.workers.live.get_next_quota_reset_time")
def test_get_next_quota_reset_time(mock_get: MagicMock, app: Any) -> None:
    """次のクォータリセット時刻が正しく取得できるかを検証します。"""
    from datetime import datetime
    mock_get.return_value = datetime.now()
    res = app._get_next_quota_reset_time()
    assert res is not None


def test_app_cleanup_join_exception(app: Any) -> None:
    """cleanup 内の thread.join 失敗時の挙動を検証します。"""
    mock_thread = MagicMock()
    mock_thread.join.side_effect = RuntimeError("Join failed")
    app.cleanup(playback_thread=mock_thread, wait_seconds=0.1)


def test_run_live_signal_value_error(app: Any) -> None:
    """run_live 内のシグナル登録エラー時の挙動を検証します。"""
    mock_live_client = MagicMock()
    app.stop_event.set()
    with (
        patch("signal.signal", side_effect=ValueError("Not in main thread")),
        patch("threading.Thread"),
        patch.object(app, "live_worker"),
    ):
        app.run_live(live_client=mock_live_client, video_id="vid")


def test_run_live_worker_exception(app: Any) -> None:
    """live_worker 実行時の例外が正しくキャッチされるかを検証します。"""
    mock_live_client = MagicMock()
    with (
        patch("threading.Thread"),
        patch.object(
            app, "live_worker", side_effect=RuntimeError("Worker error")
        ),
        patch.object(app, "cleanup") as mock_cleanup,
    ):
        app.run_live(live_client=mock_live_client, video_id="vid")
        mock_cleanup.assert_called_once()


def test_run_video_signal_handling(app: Any) -> None:
    """run_video 内のシグナルハンドラの動作を検証します。"""
    mock_video_client = MagicMock()
    app.stop_event.set()
    with (
        patch("signal.signal") as mock_signal,
        patch("threading.Thread"),
        patch.object(app, "video_worker"),
    ):
        app.run_video(video_client=mock_video_client, video_id="video123")
        assert mock_signal.call_count >= 1
        args, _ = mock_signal.call_args_list[0]
        sig, handler = args
        app.stop_event.clear()
        handler(signal.SIGINT, None)
        assert app.stop_event.is_set() is True


def test_run_video_signal_value_error(app: Any) -> None:
    """run_video 内のシグナル登録エラー時の挙動を検証します。"""
    mock_video_client = MagicMock()
    app.stop_event.set()
    with (
        patch("signal.signal", side_effect=ValueError("Not in main thread")),
        patch("threading.Thread"),
        patch.object(app, "video_worker"),
    ):
        app.run_video(video_client=mock_video_client, video_id="vid")


def test_run_video_worker_exception(app: Any) -> None:
    """video_worker 実行時の例外が正しくキャッチされるかを検証します。"""
    mock_video_client = MagicMock()
    with (
        patch("threading.Thread"),
        patch.object(
            app, "video_worker", side_effect=RuntimeError("Worker error")
        ),
        patch.object(app, "cleanup") as mock_cleanup,
    ):
        app.run_video(video_client=mock_video_client, video_id="vid")
        mock_cleanup.assert_called_once()
