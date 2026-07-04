"""YouTubeTtsApp のライフサイクルと実行メソッドのテスト。"""

import signal
from unittest.mock import MagicMock, patch


def test_run_live(app):
    """run_live メソッドが正しく初期化とクリーンアップを行うか検証。"""
    mock_live_client = MagicMock()
    app.stop_event.set()  # 即座に待機ループを終了させる

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


def test_run_live_signal_handling(app):
    """run_live 内で登録されるシグナルハンドラが正しく動作するか検証。"""
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


def test_run_video(app):
    """run_video メソッドが正しく初期化とクリーンアップを行うか検証。"""
    mock_video_client = MagicMock()
    app.stop_event.set()  # 即座に待機ループを終了させる

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


def test_app_cleanup(app):
    """cleanup メソッドがキュー内の残コメントを消化するか検証。"""
    app.comment_queue.put(("User", "Hello"))
    mock_thread = MagicMock()
    app.cleanup(playback_thread=mock_thread, wait_seconds=0.1)

    assert app.comment_queue.empty() is True
    app.audio_player.stop.assert_called_once()
    mock_thread.join.assert_called_once()


def test_is_and_mark_processed(app):
    """重複メッセージIDの判定および最大件数制限時のローテーションを検証。"""
    app.max_processed_message_ids = 2
    assert app.is_and_mark_processed("id1") is False
    assert app.is_and_mark_processed("id2") is False
    assert app.is_and_mark_processed("id2") is True

    # id3を追加すると最大2件制限により最古の id1 が破棄されるはず
    # Adding id3 discards the oldest id1 due to the limit of 2
    assert app.is_and_mark_processed("id3") is False
    assert app.is_and_mark_processed("id1") is False


def test_format_reset_time_for_speech(app):
    """クォータリセット時刻の音声用フォーマット処理を検証。"""
    from datetime import datetime, timedelta

    now = datetime.now().astimezone()

    # 今日 (delta_days = 0, minutes > 0)
    # Today
    t0 = now.replace(hour=15, minute=30)
    res0 = app._format_reset_time_for_speech(t0)
    assert "今日" in res0
    assert "15時30分" in res0

    # 明日 (delta_days = 1, minutes = 0)
    # Tomorrow
    t1 = (now + timedelta(days=1)).replace(hour=15, minute=0)
    res1 = app._format_reset_time_for_speech(t1)
    assert "明日" in res1
    assert "15時" in res1

    # 明後日以降 (delta_days = 2)
    # Beyond tomorrow
    t2 = (now + timedelta(days=2)).replace(hour=15, minute=0)
    res2 = app._format_reset_time_for_speech(t2)
    assert f"{t2.month}月{t2.day}日" in res2


def test_app_init_default_logger():
    """引数 logger が None の場合にデフォルトロガーが設定されるか検証。"""
    from youtube_tts import YouTubeTtsApp

    test_app = YouTubeTtsApp(
        config=MagicMock(),
        voicevox_client=MagicMock(),
        audio_player=MagicMock(),
        obs_client=MagicMock(),
    )
    assert test_app.logger is not None
