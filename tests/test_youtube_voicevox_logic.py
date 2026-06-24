import pytest
import sys
import time
import queue
import logging
import threading
from io import StringIO
from unittest.mock import MagicMock, patch

from youtube_voicevox import YouTubeTtsApp
from youtube_tts import (
    AppConfig,
    AudioPlayer,
    VoicevoxClient,
    YouTubeChatClient,
    setup_logger,
)

# Helper fixture to mock YouTubeTtsApp on each run
#
# 毎回テスト実行時に YouTubeTtsApp 用のモックなどを生成するヘルパー fixture
@pytest.fixture
def mock_app_dependencies():
    config = AppConfig(
        dictionary_path="dictionary.txt",
        ng_words_path="ng_words.txt",
        volume_path="volume.txt"
    )
    # Set values
    #
    # 値を設定
    config.volume_scale = 0.5
    
    voicevox_client = MagicMock(spec=VoicevoxClient)
    audio_player = MagicMock(spec=AudioPlayer)
    audio_player.target_sample_rate = 24000
    
    # Test-specific logger
    #
    # テスト専用の logger
    logger = setup_logger(verbose=True)
    
    return config, voicevox_client, audio_player, logger

@pytest.fixture
def app(mock_app_dependencies):
    config, voicevox_client, audio_player, logger = mock_app_dependencies
    return YouTubeTtsApp(
        config=config,
        voicevox_client=voicevox_client,
        audio_player=audio_player,
        logger=logger,
    )

# ==============================================================================
# 1. Test logger and setup_logger
#
# 1. logger および setup_logger のテスト
# ==============================================================================
def test_setup_logger():
    captured_output = StringIO()
    logger = setup_logger(verbose=True)
    
    # Temporarily add StreamHandler with StringIO to capture output from
    # existing handlers
    #
    # 既存のハンドラから出力を奪うために、StringIO を持つ StreamHandler を
    # 一時的に追加する
    handler = logging.StreamHandler(captured_output)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    try:
        logger.info("Hello Logger")
        logger.debug("Debug Info")
        
        output = captured_output.getvalue()
        lines = output.splitlines()
        
        assert len(lines) == 2
        assert "Hello Logger" in lines[0]
        assert "Debug Info" in lines[1]
        assert lines[0].startswith("[20")
    finally:
        # Remove handler to prevent affecting other tests
        #
        # 他のテストに影響しないようハンドラを削除する
        logger.removeHandler(handler)

def test_tagged_logger():
    from youtube_tts.logger import TaggedLogger, get_logger
    logger = get_logger()
    assert isinstance(logger, TaggedLogger)

    captured_output = StringIO()
    handler = logging.StreamHandler(captured_output)
    logger.addHandler(handler)
    
    try:
        logger.info("Normal message")
        logger.info("[CUSTOM] Custom prefix message")
        logger.critical("Critical message")
        try:
            raise ValueError("Test error")
        except ValueError:
            logger.exception("Exception message")
        logger.log(logging.WARNING, "Log message")
        logger.warn("Warn message")
        
        output = captured_output.getvalue()
        lines = output.splitlines()
        
        assert "[INFO] Normal message" in lines[0]
        assert "[CUSTOM] Custom prefix message" in lines[1]
        assert "[INFO] [CUSTOM]" not in lines[1]
        assert "[CRITICAL] Critical message" in lines[2]
        assert "[ERROR] Exception message" in lines[3]
        assert "[WARN] Log message" in lines[-2]
        assert "[WARN] Warn message" in lines[-1]
    finally:
        logger.removeHandler(handler)

# ==============================================================================
# 2. Test speak and playback_worker
#
# 2. speak および playback_worker のテスト
# ==============================================================================
def test_speak_success(app):
    app.voicevox_client.synthesize.return_value = b"mock_wav"
    app.speak("テストテキスト")
    
    app.voicevox_client.synthesize.assert_called_with(
        text="テストテキスト",
        volume_scale=0.5,
        speed_scale=1.0,
        target_sample_rate=app.audio_player.target_sample_rate
    )
    app.audio_player.play_wav.assert_called_with(b"mock_wav")


def test_speak_failure(app):
    app.voicevox_client.synthesize.side_effect = Exception("VOICEVOX Error")
    app.verbose = False
    
    # Verify it catches exception, doesn't crash, and logs are output
    #
    # 例外をキャッチし、クラッシュしないこと、ログが出力されることを確認
    with patch.object(app.logger, "error") as mock_error, \
         patch.object(app.logger, "debug") as mock_debug:
        app.speak("エラーテスト")
        app.audio_player.play_wav.assert_not_called()
        
        # Verify that error message is output 3 times
        #
        # エラーメッセージが3回出力されたことを確認
        assert mock_error.call_count == 3
        mock_error.assert_any_call("[ERROR] 音声の合成または再生に失敗しました。")
        mock_error.assert_any_call("        - VOICEVOX サーバーが起動しているか確認してください。")
        mock_error.assert_any_call("        - 出力オーディオデバイスの設定を確認してください。")
        
        # Verify debug log is not output since verbose is False
        #
        # verbose が False なのでデバッグログは出力されない
        mock_debug.assert_not_called()


def test_speak_failure_verbose(app):
    app.voicevox_client.synthesize.side_effect = Exception("VOICEVOX Error")
    app.verbose = True
    
    # Verify it catches exception, doesn't crash, and logs are output
    #
    # 例外をキャッチし、クラッシュしないこと、ログが出力されることを確認
    with patch.object(app.logger, "error") as mock_error, \
         patch.object(app.logger, "debug") as mock_debug:
        app.speak("エラーテスト")
        app.audio_player.play_wav.assert_not_called()
        
        # Verify that error message is output 3 times
        #
        # エラーメッセージが3回出力されたことを確認
        assert mock_error.call_count == 3
        
        # Verify debug log is output since verbose is True
        #
        # verbose が True なのでデバッグログが出力される
        mock_debug.assert_called_once_with("  (エラー詳細: VOICEVOX Error)")


def test_playback_worker(app):
    app.comment_queue.put(("User1", "こんにちは"))

    with patch.object(app, "speak") as mock_speak:
        # Set stop event to terminate thread after speak completes
        #
        # speak 実行後にスレッドを終了させるためにストップイベントをセット
        def side_effect(text, *args, **kwargs):
            app.stop_event.set()
        mock_speak.side_effect = side_effect

        app.playback_worker()

        mock_speak.assert_called_once_with("User1 こんにちは", speed_scale=1.0)


# ==============================================================================
# 3. Test cleanup
#
# 3. cleanup のテスト
# ==============================================================================
def test_cleanup_flow(app):
    app.comment_queue.put(("UserA", "MessageB"))
    mock_thread = MagicMock(spec=threading.Thread)

    app.cleanup(playback_thread=mock_thread, wait_seconds=0.1)

    assert app.stop_event.is_set()
    app.audio_player.stop.assert_called_once()
    mock_thread.join.assert_called_once_with(timeout=0.1)
    assert app.comment_queue.empty()


def test_cleanup_join_exception(app):
    """Verifies that the application does not crash even if
    playback_thread.join() throws an exception.
    
    playback_thread.join() が例外を投げてもクラッシュしないことを確認。
    """
    mock_thread = MagicMock(spec=threading.Thread)
    mock_thread.join.side_effect = RuntimeError("Join error")

    app.cleanup(playback_thread=mock_thread, wait_seconds=0.1)
    assert app.stop_event.is_set()


# ==============================================================================
# 4. Test youtube_worker
#
# 4. youtube_worker のテスト
# ==============================================================================
def test_youtube_worker_normal_flow(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # Return comment on first call and terminate loop on second call
    #
    # 初回呼び出しでコメントを返し、2回目でループを終了させる
    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            items = [{
                "id": "msg_001",
                "authorDetails": {"displayName": "視聴者A"},
                "snippet": {"displayMessage": "こんにちは！"}
            }]
            return items, "next_token_123", 1000
        else:
            app.stop_event.set()
            return [], "next_token_456", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    # Verify comment is normalized and put into queue correctly
    #
    # コメントが正しく正規化されてキューに格納されていることを確認
    assert not app.comment_queue.empty()
    author, msg = app.comment_queue.get()
    assert author == "視聴者Aさん"
    assert msg == "こんにちは!"


def test_youtube_worker_backlog_seconds_filter(app):
    from datetime import datetime, timezone, timedelta
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    now = datetime.now(timezone.utc)
    # Old message (20 seconds ago)
    #
    # 古いメッセージ（20秒前）
    old_time_str = (
        (now - timedelta(seconds=20)).isoformat().replace("+00:00", "Z")
    )
    # New message (5 seconds ago)
    #
    # 新しいメッセージ（5秒前）
    new_time_str = (
        (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    )

    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            items = [
                {
                    "id": "msg_old",
                    "authorDetails": {"displayName": "視聴者A"},
                    "snippet": {
                        "displayMessage": "古いメッセージ",
                        "publishedAt": old_time_str
                    }
                },
                {
                    "id": "msg_new",
                    "authorDetails": {"displayName": "視聴者B"},
                    "snippet": {
                        "displayMessage": "新しいメッセージ",
                        "publishedAt": new_time_str
                    }
                }
            ]
            return items, "next_token_123", 1000
        else:
            app.stop_event.set()
            return [], "next_token_456", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_side_effect

    # Configuration to backtrack up to 10 seconds
    #
    # 10秒前までを遡る設定
    with patch.object(app.logger, "debug") as mock_debug:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
            backlog_seconds=10,
            verbose=True,
        )

    # Verify that SKIP(PAST) log is output
    #
    # SKIP(PAST) ログが出力されたことを確認
    assert any(
        "[SKIP(PAST)]" in call[0][0] for call in mock_debug.call_args_list
    )

    # Verify that only the new message is in the queue
    #
    # 新しいメッセージのみがキューに入っていることを確認
    assert app.comment_queue.qsize() == 1
    author, msg = app.comment_queue.get()
    assert author == "視聴者Bさん"
    assert msg == "新しいメッセージ"

    # Verify that both IDs are added to deduplication list
    #
    # 重複防止IDには両方追加されていることを確認
    assert "msg_old" in app.processed_message_ids
    assert "msg_new" in app.processed_message_ids


def test_youtube_worker_backlog_seconds_all(app):
    from datetime import datetime, timezone, timedelta
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    now = datetime.now(timezone.utc)
    old_time_str = (
        (now - timedelta(seconds=20)).isoformat().replace("+00:00", "Z")
    )

    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            items = [
                {
                    "id": "msg_old",
                    "authorDetails": {"displayName": "視聴者A"},
                    "snippet": {
                        "displayMessage": "古いメッセージ",
                        "publishedAt": old_time_str
                    }
                }
            ]
            return items, "next_token_123", 1000
        else:
            app.stop_event.set()
            return [], "next_token_456", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_side_effect

    # Configuration for no limit (-1)
    #
    # 制限なし（-1）の設定
    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
        backlog_seconds=-1,
    )

    # Verify that old messages are also in the queue
    #
    # 古いメッセージもキューに入っていることを確認
    assert app.comment_queue.qsize() == 1
    author, msg = app.comment_queue.get()
    assert author == "視聴者Aさん"
    assert msg == "古いメッセージ"



def test_youtube_worker_ng_word(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # Return comments containing NG words
    #
    # NGワードを含むコメントを返す
    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            items = [{
                "id": "msg_ng",
                "authorDetails": {"displayName": "悪質ユーザー"},
                "snippet": {"displayMessage": "これはNGワードを含むコメントです"}
            }]
            return items, "token_next", 1000
        else:
            app.stop_event.set()
            return [], "token_next", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_side_effect

    # Patch to force NG word check to True
    #
    # NGワード判定をTrueにするパッチ
    with patch.object(
        app.text_processor, "contains_ng_word", return_value=True
    ) as mock_ng_check:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )
        mock_ng_check.assert_called_with("これはNGワードを含むコメントです")

    # Verify comment queue is empty (skipped)
    #
    # コメントキューが空であることを確認（スキップされた）
    assert app.comment_queue.empty()


def test_youtube_worker_stream_inactive(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    
    # First fetch is empty, then active check returns False
    #
    # 最初のチャット取得は空、そのまま直後のアクティブチェックでFalseを返す
    mock_chat_client.fetch_chat_messages.return_value = ([], "token_1", 1000)
    mock_chat_client.check_stream_active.return_value = False

    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        chat_interval=0.01,
        stream_check_interval=-1.0,  # 常に時間チェックをトリガーする
        quota_interval=100.0,
    )

    # Loop terminates via stop_event when stream end is detected
    #
    # 配信終了検知により、stop_eventがセットされてループを抜けること
    assert app.stop_event.is_set()
    mock_chat_client.check_stream_active.assert_called_once_with("video_abc")


@patch("youtube_voicevox.get_quota_info")
def test_youtube_worker_quota_talk(mock_get_quota_info, app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()  # 初回呼び出しでループを終了させる
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    mock_get_quota_info.return_value = (3500, 10000)

    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        creds="mock_creds",
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        quota_interval=-1.0,  # 常にクォータチェックをトリガーする
        stream_check_interval=100.0,
        project_id="project_123",
    )

    # Verify quota announcement text is in the queue
    #
    # クォータの読み上げテキストがキューに入っていること
    assert not app.comment_queue.empty()
    author, msg = app.comment_queue.get()
    assert author == ""
    assert msg == "ぴんぽーん！クォータ使用量は 3500 ユニットです。"


def test_youtube_worker_verbose_logs(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    
    # Terminate on the first loop
    #
    # 1ループ目で終了させる
    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()  # 1ループ目でループを終了させる
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    with patch.object(app.logger, "debug") as mock_debug:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
            verbose=True,
        )

    # Verify verbose output is included
    #
    # verbose 出力が含まれていることを確認
    mock_debug.assert_any_call(
        "Fetching chat messages (is_live: True, pageToken: None)"
    )


# ==============================================================================
# 5. Test edge cases and exception handling
#
# 5. エッジケース・例外ハンドリングのテスト
# ==============================================================================
def test_youtube_worker_deduplication(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # Return the same message twice
    #
    # 同一のメッセージを2回返す
    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            items = [
                {
                    "id": "msg_dup",
                    "authorDetails": {"displayName": "UserA"},
                    "snippet": {"displayMessage": "Hello"}
                },
                {
                    "id": "msg_dup",
                    "authorDetails": {"displayName": "UserA"},
                    "snippet": {"displayMessage": "Hello"}
                }
            ]
            return items, "token_1", 1000
        else:
            app.stop_event.set()
            return [], "token_2", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    # Verify only 1 item is queued due to deduplication
    #
    # 重複判定により、キューに格納されるのは1件のみであることを確認
    assert app.comment_queue.qsize() == 1


def test_youtube_worker_history_overflow(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    app.max_processed_message_ids = 2

    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            # Fetch 3 messages
            #
            # 3件のメッセージを取得
            items = [
                {
                    "id": "msg_1",
                    "authorDetails": {"displayName": "User"},
                    "snippet": {"displayMessage": "Msg 1"}
                },
                {
                    "id": "msg_2",
                    "authorDetails": {"displayName": "User"},
                    "snippet": {"displayMessage": "Msg 2"}
                },
                {
                    "id": "msg_3",
                    "authorDetails": {"displayName": "User"},
                    "snippet": {"displayMessage": "Msg 3"}
                },
            ]
            return items, "token_1", 1000
        else:
            app.stop_event.set()
            return [], "token_2", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.comment_queue.qsize() == 3


def test_youtube_worker_queue_full_skip(app):
    # Fill comment queue to maximum size (50)
    #
    # コメントキューを最大件数（50件）で満たす
    for i in range(50):
        app.comment_queue.put(("User", f"Message {i}"))

    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            items = [
                {
                    "id": "msg_extra",
                    "authorDetails": {"displayName": "User"},
                    "snippet": {"displayMessage": "Extra"}
                }
            ]
            return items, "token_1", 1000
        else:
            app.stop_event.set()
            return [], "token_2", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_side_effect

    with patch.object(app.logger, "info") as mock_info:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    # Verify skip log due to full queue
    #
    # キュー満杯によるスキップログを確認
    mock_info.assert_any_call("[SKIP(QUEUE)] Userさん: Extra")
    assert app.comment_queue.qsize() == 50


def test_youtube_worker_fetch_exception(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    mock_chat_client.fetch_chat_messages.side_effect = Exception(
        "YouTube API Error"
    )

    with patch.object(app.logger, "error") as mock_error:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    mock_error.assert_called_with("[ERROR] チャットまたはコメントの取得に失敗しました。")
    assert app.stop_event.is_set()


def test_youtube_worker_my_live_stream(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"activeLiveChatId": "chat_my_live"}
    }
    mock_chat_client.get_live_chat_id.return_value = "chat_my_live"
    
    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    with patch.object(app.logger, "info") as mock_info:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_my_live",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )
    
    mock_info.assert_any_call("[INFO] 動画判定: 自分のライブ配信（チャットを取得します）")
    mock_chat_client.get_live_chat_id.assert_called_once_with("video_my_live")
    mock_chat_client.fetch_chat_messages.assert_called_once_with(
        "chat_my_live", page_token=None
    )


def test_youtube_worker_others_live_stream(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "other_channel_456"},
        "liveStreamingDetails": {"activeLiveChatId": "chat_other_live"}
    }
    mock_chat_client.get_live_chat_id.return_value = "chat_other_live"
    
    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    with patch.object(app.logger, "info") as mock_info:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_other_live",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )
    
    mock_info.assert_any_call("[INFO] 動画判定: 他者のライブ配信（チャットを取得します）")
    mock_chat_client.get_live_chat_id.assert_called_once_with(
        "video_other_live"
    )
    mock_chat_client.fetch_chat_messages.assert_called_once_with(
        "chat_other_live", page_token=None
    )


def test_youtube_worker_archive_mode(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {
            "activeLiveChatId": "chat_old",
            "actualEndTime": "2026-06-21T12:00:00Z"
        }
    }
    
    mock_chat_client.fetch_comment_threads.side_effect = [
        (
            [
                {
                    "id": "c1",
                    "authorDetails": {"displayName": "Alice"},
                    "snippet": {"displayMessage": "Hello!"}
                }
            ],
            None,
            3000
        ),
        (
            [
                {
                    "id": "c2",
                    "authorDetails": {"displayName": "Bob"},
                    "snippet": {"displayMessage": "New Comment"}
                }
            ],
            None,
            3000
        ),
    ]

    with patch.object(app, "speak") as mock_speak:
        def side_effect(text, *args, **kwargs):
            if "Bob" in text:
                app.stop_event.set()
        mock_speak.side_effect = side_effect

        with patch.object(app.logger, "info") as mock_info:
            app.youtube_worker(
                chat_client=mock_chat_client,
                video_id="video_archive",
                chat_interval=0.01,
                stream_check_interval=100.0,
                quota_interval=100.0,
                backlog_counts=10,
            )
    
    mock_info.assert_any_call("[INFO] 動画判定: 過去の配信アーカイブ（コメントを取得します）")
    mock_chat_client.get_live_chat_id.assert_not_called()
    mock_chat_client.check_stream_active.assert_not_called()
    
    assert not app.comment_queue.empty()
    item1 = app.comment_queue.get()
    assert item1[0] == "Aliceさん"


@patch("youtube_voicevox.get_quota_info")
def test_youtube_worker_quota_exception(mock_get_quota_info, app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()  # 初回呼び出しでループを終了させる
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    mock_get_quota_info.side_effect = Exception(
        "Monitoring API Error"
    )

    with patch.object(app.logger, "warning") as mock_warning, \
         patch.object(app.logger, "debug") as mock_debug:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            creds="mock_creds",
            quota_check=True,
            chat_interval=0.01,
            quota_interval=-1.0,
            stream_check_interval=100.0,
            project_id="project_123",
            verbose=True,
        )

    mock_warning.assert_any_call("[WARNING] クォータ情報の取得に失敗しました。")
    mock_debug.assert_any_call("  (エラー詳細: Monitoring API Error)")


def test_youtube_worker_stream_active_verbose(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    
    # Terminate on first loop. Trigger active check on first loop.
    #
    # 1ループ目で終了させる。1ループ目でアクティブチェックをトリガーする。
    def fetch_and_stop(live_chat_id, page_token=None):
        app.stop_event.set()  # 1ループ目でループを終了させる
        return [], "token_2", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop
    mock_chat_client.check_stream_active.return_value = True

    with patch.object(app.logger, "debug") as mock_debug:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            chat_interval=0.01,
            stream_check_interval=-1.0,  # 常にチェックを実行
            quota_interval=100.0,
            verbose=True,
        )

    mock_debug.assert_any_call("Checking stream active status...")
    mock_debug.assert_any_call("Stream active status: True")


@patch("youtube_voicevox.get_quota_info")
def test_youtube_worker_quota_verbose(mock_get_quota_info, app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()  # 初回呼び出しでループを終了させる
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    mock_get_quota_info.return_value = (3500, 10000)

    with patch.object(app.logger, "debug") as mock_debug:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            creds="mock_creds",
            quota_check=True,
            chat_interval=0.01,
            quota_interval=-1.0,
            stream_check_interval=100.0,
            project_id="project_123",
            verbose=True,
        )

    mock_debug.assert_any_call("Fetching quota info...")


def test_playback_worker_dynamic_speed_boost(app):
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    # Set comments in the queue and character counter
    # Comment 1: "User1 Hello"
    # Comment 2: "User2 AAAAA..." (180 chars)
    # Total chars = 11 + 180 = 191
    #
    # キューと文字数カウンタにコメントをセット
    # コメント 1: "User1 Hello"
    # コメント 2: "User2 AAAAA..." (180文字)
    # 合計文字数 = 11 + 180 = 191
    from youtube_voicevox import CommentItem
    app.comment_queue.put(CommentItem("User1", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 175, 180))
    app.queued_char_count = 191

    with patch.object(app, "speak") as mock_speak:
        # Set stop event to terminate the thread after speak completes
        #
        # speak 完了後にスレッドを終了させるためにストップイベントをセット
        def side_effect(text, speed_scale=None):
            app.stop_event.set()
        mock_speak.side_effect = side_effect

        app.playback_worker()

        # Verify remaining chars is 180 after subtracting 11 consumed chars
        # from 191
        #
        # 191文字から今回消費した11文字を引いて、残りは180文字になること
        assert app.queued_char_count == 180
        mock_speak.assert_called_once_with("User1 Hello", speed_scale=1.8)


def test_playback_worker_backward_compatibility(app):
    # Put 2-element tuple into queue (simulating legacy test cases)
    #
    # 2要素タプルをキューに投入 (旧仕様テストケースのシミュレーション)
    app.comment_queue.put(("UserOld", "HelloOld"))
    app.queued_char_count = 15  # "UserOld" (7) + "HelloOld" (8) = 15文字

    with patch.object(app, "speak") as mock_speak:
        def side_effect(text, speed_scale=None):
            app.stop_event.set()
        mock_speak.side_effect = side_effect

        app.playback_worker()

        # Verify it is unpacked successfully and characters are subtracted
        #
        # 無事にアンパックされ、文字数が引かれていること
        assert app.queued_char_count == 0
        mock_speak.assert_called_once_with("UserOld HelloOld", speed_scale=1.0)


def test_youtube_worker_video_details_failure(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_video_details.side_effect = Exception(
        "Details API Error"
    )

    with patch.object(app.logger, "error") as mock_error, \
         patch.object(app.logger, "debug") as mock_debug:
        app.youtube_worker(mock_chat_client, "vid", verbose=True)
    
    mock_error.assert_called_with("[ERROR] 動画情報の取得に失敗しました。")
    mock_debug.assert_called_with("  (エラー詳細: Details API Error)")
    assert app.stop_event.is_set()


def test_youtube_worker_get_live_chat_id_failure(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {}
    }
    mock_chat_client.get_live_chat_id.side_effect = Exception(
        "Chat ID API Error"
    )

    with patch.object(app.logger, "error") as mock_error, \
         patch.object(app.logger, "debug") as mock_debug:
        app.youtube_worker(mock_chat_client, "vid", verbose=True)

    mock_error.assert_called_with("[ERROR] liveChatId の取得に失敗しました。")
    mock_debug.assert_called_with("  (エラー詳細: Chat ID API Error)")
    assert app.stop_event.is_set()


def test_youtube_worker_posted_video_mode(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"}
    }
    
    # side_effect to complete normally
    #
    # 正常終了させるための side_effect
    def side_effect(*args, **kwargs):
        app.stop_event.set()
        return [], None, 3000
    mock_chat_client.fetch_comment_threads.side_effect = side_effect
    app.youtube_worker(mock_chat_client, "vid", chat_interval=0.01)


def test_youtube_worker_initial_fetch_comments_failure(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"actualEndTime": "2026-06-21T12:00:00Z"}
    }
    mock_chat_client.fetch_comment_threads.side_effect = Exception(
        "Fetch API Error"
    )

    with patch.object(app.logger, "error") as mock_error, \
         patch.object(app.logger, "debug") as mock_debug:
        app.youtube_worker(
            mock_chat_client, "vid", chat_interval=0.01, verbose=True
        )
    
    mock_error.assert_any_call("[ERROR] 初期コメントスレッドの取得に失敗しました。")
    mock_debug.assert_any_call("  (エラー詳細: Fetch API Error)")


def test_youtube_worker_initial_fetch_comments_no_items(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"actualEndTime": "2026-06-21T12:00:00Z"}
    }
    
    def side_effect(*args, **kwargs):
        app.stop_event.set()
        return [], None, 3000
    mock_chat_client.fetch_comment_threads.side_effect = [
        ([], None, 3000),
        side_effect
    ]
    app.youtube_worker(mock_chat_client, "vid", chat_interval=0.01)


def test_youtube_worker_initial_comments_ng_skip(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"actualEndTime": "2026-06-21T12:00:00Z"}
    }
    
    def side_effect(*args, **kwargs):
        app.stop_event.set()
        return [], None, 3000

    mock_chat_client.fetch_comment_threads.side_effect = [
        (
            [
                {
                    "id": "ng_c",
                    "authorDetails": {"displayName": "Spammer"},
                    "snippet": {"displayMessage": "badword"}
                }
            ],
            None,
            3000
        ),
        side_effect
    ]

    with patch.object(
        app.text_processor, "contains_ng_word", return_value=True
    ):
        with patch.object(app.logger, "info") as mock_info:
            app.youtube_worker(
                mock_chat_client, "vid", chat_interval=0.01, verbose=True
            )
    
    mock_info.assert_any_call("[SKIP(NG)] Spammer: badword")
    assert app.comment_queue.empty()


def test_youtube_worker_initial_comments_queue_full_skip(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"actualEndTime": "2026-06-21T12:00:00Z"}
    }

    for i in range(50):
        app.comment_queue.put(("User", f"Msg {i}"))
    
    def side_effect(*args, **kwargs):
        app.stop_event.set()
        return [], None, 3000

    mock_chat_client.fetch_comment_threads.side_effect = [
        (
            [
                {
                    "id": "overflow_c",
                    "authorDetails": {"displayName": "User"},
                    "snippet": {"displayMessage": "Hello"}
                }
            ],
            None,
            3000
        ),
        side_effect
    ]

    with patch.object(app.logger, "info") as mock_info:
        app.youtube_worker(mock_chat_client, "vid", chat_interval=0.01)
    
    mock_info.assert_any_call("[SKIP(QUEUE)] Userさん: Hello")


def test_youtube_worker_published_at_parse_failure(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_123"
    
    def fetch_side_effect(*args, **kwargs):
        if app.stop_event.is_set():
            return [], None, 3000
        items = [{
            "id": "msg_invalid_date",
            "authorDetails": {"displayName": "User"},
            "snippet": {
                "displayMessage": "Msg",
                "publishedAt": "invalid-date-format"
            }
        }]
        app.stop_event.set()
        return items, "token_1", 1000

    mock_chat_client.fetch_chat_messages.side_effect = fetch_side_effect

    with patch.object(app.logger, "warning") as mock_warning:
        app.youtube_worker(
            mock_chat_client, "vid", chat_interval=0.01, backlog_seconds=10
        )
    
    mock_warning.assert_any_call(
        f"Failed to parse publishedAt: invalid-date-format, "
        f"error: Invalid isoformat string: 'invalid-date-format'"
    )


def test_youtube_app_run_success(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    
    def dummy_worker(*args, **kwargs):
        app.stop_event.set()
    
    with patch.object(app, "youtube_worker", side_effect=dummy_worker):
        app.run(mock_chat_client, "vid")
        
    assert app.stop_event.is_set()


def test_youtube_app_init_logger_none():
    config = AppConfig(
        dictionary_path="dictionary.txt",
        ng_words_path="ng_words.txt",
        volume_path="volume.txt"
    )
    voicevox_client = MagicMock(spec=VoicevoxClient)
    audio_player = MagicMock(spec=AudioPlayer)
    
    app_logger_none = YouTubeTtsApp(
        config=config,
        voicevox_client=voicevox_client,
        audio_player=audio_player,
        logger=None,
    )
    assert app_logger_none.logger is not None


def test_playback_worker_speed_boost_lower_limit(app):
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2
    from youtube_voicevox import CommentItem
    app.comment_queue.put(CommentItem("User", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 25, 30))
    app.queued_char_count = 41
    
    with patch.object(app, "speak") as mock_speak:
        def side_effect(text, speed_scale=None):
            app.stop_event.set()
        mock_speak.side_effect = side_effect
        app.playback_worker()
        mock_speak.assert_called_once_with("User Hello", speed_scale=1.0)


def test_playback_worker_speed_boost_upper_limit(app):
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.0
    from youtube_voicevox import CommentItem
    app.comment_queue.put(CommentItem("User", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 295, 300))
    app.queued_char_count = 311
    
    with patch.object(app, "speak") as mock_speak:
        def side_effect(text, speed_scale=None):
            app.stop_event.set()
        mock_speak.side_effect = side_effect
        app.playback_worker()
        mock_speak.assert_called_once_with("User Hello", speed_scale=2.0)


def test_youtube_worker_initial_fetch_comments_counts_limit(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"actualEndTime": "2026-06-21T12:00:00Z"}
    }
    
    def polling_stop(*args, **kwargs):
        app.stop_event.set()
        return [], None, 3000
        
    mock_chat_client.fetch_comment_threads.side_effect = [
        (
            [
                {
                    "id": f"c_{i}",
                    "authorDetails": {"displayName": "U"},
                    "snippet": {"displayMessage": "M"}
                }
                for i in range(10)
            ],
            "next_token_1",
            3000
        ),
        polling_stop
    ]

    app.youtube_worker(
        mock_chat_client, "vid", chat_interval=0.01, backlog_counts=5
    )
    assert mock_chat_client.fetch_comment_threads.call_count == 2


def test_youtube_worker_initial_comments_history_overflow(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"actualEndTime": "2026-06-21T12:00:00Z"}
    }
    
    app.max_processed_message_ids = 2
    
    calls = []
    def fetch_threads_side_effect(*args, **kwargs):
        if not calls:
            calls.append(1)
            return [
                {
                    "id": "c1",
                    "authorDetails": {"displayName": "U"},
                    "snippet": {"displayMessage": "M1"}
                },
                {
                    "id": "c2",
                    "authorDetails": {"displayName": "U"},
                    "snippet": {"displayMessage": "M2"}
                },
                {
                    "id": "c3",
                    "authorDetails": {"displayName": "U"},
                    "snippet": {"displayMessage": "M3"}
                }
            ], None, 3000
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_chat_client.fetch_comment_threads.side_effect = (
        fetch_threads_side_effect
    )
    
    app.youtube_worker(
        mock_chat_client, "vid", chat_interval=0.01, backlog_counts=10
    )
    # c3 (oldest) should be discarded when history size is capped at 2
    # (c1, c2 are newer)
    #
    # 履歴サイズ上限が 2 の場合、最も古い c3 は破棄される
    # （c1, c2 がより新しい）
    assert "c3" not in app.processed_message_ids
    assert "c2" in app.processed_message_ids
    assert "c1" in app.processed_message_ids


def test_youtube_app_run_unexpected_error(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    with patch.object(
        app, "youtube_worker", side_effect=Exception("Unexpected crash!")
    ):
        with patch.object(app.logger, "exception") as mock_exception:
            app.run(mock_chat_client, "vid")
    
    mock_exception.assert_called_with("Unexpected error")


def test_youtube_app_run_signal_handling(app):
    import signal
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    
    handlers = {}
    def mock_signal(sig, handler):
        handlers[sig] = handler
        return None
    
    def dummy_worker(*args, **kwargs):
        # Execute signal handler
        #
        # シグナルハンドラを実行する
        if signal.SIGINT in handlers:
            handlers[signal.SIGINT](signal.SIGINT, None)
    
    with patch("signal.signal", side_effect=mock_signal), \
         patch.object(app, "youtube_worker", side_effect=dummy_worker), \
         patch.object(app.logger, "info") as mock_info:
        app.run(mock_chat_client, "vid")
        
    assert app.stop_event.is_set()
    mock_info.assert_any_call("Signal received, shutting down...")


def test_youtube_app_run_signal_value_error(app):
    import signal
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    
    def mock_signal(sig, handler):
        raise ValueError("signal only works in main thread")
        
    def dummy_worker(*args, **kwargs):
        app.stop_event.set()
        
    with patch("signal.signal", side_effect=mock_signal), \
         patch.object(app, "youtube_worker", side_effect=dummy_worker):
        # Confirm ValueError is ignored and exits normally
        #
        # ValueError が発生しても無視されて正常に終了することを確認
        app.run(mock_chat_client, "vid")
        
    assert app.stop_event.is_set()


def test_write_chat_log_normal(app, tmp_path):
    log_file = tmp_path / "test_chat.jsonl"
    app.config.chat_log_path = str(log_file)
    
    item = {
        "id": "msg_123",
        "authorDetails": {
            "channelId": "UC_abc",
            "displayName": "User",
            "isChatSponsor": True,
            "isChatModerator": False,
            "isChatOwner": False
        },
        "snippet": {
            "type": "textMessageEvent",
            "displayMessage": "Hello, World!",
            "publishedAt": "2026-06-22T02:00:00Z"
        }
    }
    
    app.write_chat_log(item, "vid_123")
    
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8").strip()
    import json
    data = json.loads(content)
    
    assert data["timestamp"] == "2026-06-22T02:00:00Z"
    assert data["video_id"] == "vid_123"
    assert data["author_id"] == "UC_abc"
    assert data["author_name"] == "User"
    assert data["message"] == "Hello, World!"
    assert data["message_type"] == "textMessageEvent"
    assert data["is_member"] is True
    assert data["is_moderator"] is False
    assert data["is_owner"] is False
    assert data["super_chat"] is None


def test_write_chat_log_no_published_at(app, tmp_path):
    log_file = tmp_path / "test_chat.jsonl"
    app.config.chat_log_path = str(log_file)
    
    item = {
        "id": "msg_123",
        "authorDetails": {
            "channelId": "UC_abc",
            "displayName": "User"
        },
        "snippet": {
            "displayMessage": "Hello"
        }
    }
    
    app.write_chat_log(item, "vid_123")
    
    content = log_file.read_text(encoding="utf-8").strip()
    import json
    data = json.loads(content)
    assert data["timestamp"] is not None


def test_write_chat_log_super_chat(app, tmp_path):
    log_file = tmp_path / "test_chat.jsonl"
    app.config.chat_log_path = str(log_file)
    
    item = {
        "id": "msg_123",
        "authorDetails": {
            "channelId": "UC_abc",
            "displayName": "User"
        },
        "snippet": {
            "type": "superChatEvent",
            "displayMessage": "Super Chat Message",
            "superChatDetails": {
                "amountMicros": 1000000000,
                "currency": "JPY",
                "amountDisplayString": "￥1,000"
            }
        }
    }
    
    app.write_chat_log(item, "vid_123")
    
    content = log_file.read_text(encoding="utf-8").strip()
    import json
    data = json.loads(content)
    assert data["super_chat"] == {
        "amount_micros": 1000000000,
        "currency": "JPY",
        "display_string": "￥1,000"
    }


def test_write_chat_log_error(app):
    app.config.chat_log_path = "/nonexistent_directory_12345/chat.jsonl"
    
    item = {
        "id": "msg_123",
        "authorDetails": {},
        "snippet": {}
    }
    
    with patch.object(app.logger, "error") as mock_error:
        app.write_chat_log(item, "vid")
        mock_error.assert_called_once()
        assert (
            "[ERROR] チャットログの保存に失敗しました"
            in mock_error.call_args[0][0]
        )


# ==============================================================================
# 6. Test read-aloud functionality on quota limit exceeded
#
# 6. クォータ超過時の読み上げ機能のテスト
# ==============================================================================
@patch("youtube_voicevox.get_quota_info")
def test_youtube_worker_quota_exceeded_speech(mock_get_quota_info, app):
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    from youtube_voicevox import CommentItem

    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # Simulate quota limit exceeded error
    #
    # クォータ超過エラーをシミュレート
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = (
        b'{"error": {"errors": [{"domain": "usageLimits", '
        b'"reason": "quotaExceeded"}], "code": 403, '
        b'"message": "Quota exceeded"}}'
    )
    mock_chat_client.fetch_chat_messages.side_effect = HttpError(resp, content)

    # Simulate a state where existing comments remain in the queue
    #
    # 既存のコメントがキューに残っている状態をシミュレート
    app.comment_queue.put(CommentItem("User", "Old Comment", 11))

    # Test with quota_talk=True
    #
    # quota_talk=True のテスト
    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        creds="mock_creds",
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        quota_interval=100.0,
        stream_check_interval=100.0,
    )

    # Verify stop event is set
    #
    # スレッド停止イベントがセットされていること
    assert app.stop_event.is_set()
    # Verify queue contains only quota warning (old comments cleared)
    #
    # キューには「クォータ超過しました」の警告コメントのみがあること（古いコメン
    # トはクリアされている）
    assert app.comment_queue.qsize() == 1
    author, msg = app.comment_queue.get()
    assert author == ""
    assert "クォータを超過しました" in msg
    assert "お待ち下さい" in msg

    # Call task_done on queue to empty it
    #
    # queueの task_done を呼んで空にする
    app.comment_queue.task_done()
    assert app.comment_queue.empty()

    # Test with quota_talk=False
    #
    # quota_talk=False のテスト
    app.stop_event.clear()
    app.comment_queue.put(CommentItem("User", "Old Comment", 11))
    
    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        creds="mock_creds",
        quota_check=True,
        quota_talk=False,  # 読み上げ無効
        chat_interval=0.01,
        quota_interval=100.0,
        stream_check_interval=100.0,
    )
    
    # Warning message is not queued and old comments are not cleared
    #
    # 警告メッセージは投入されず、古いコメントもクリアされない
    assert app.comment_queue.qsize() == 1
    author, msg = app.comment_queue.get()
    assert author == "User"
    assert msg == "Old Comment"
    app.comment_queue.task_done()


@patch("youtube_voicevox.get_quota_info")
def test_youtube_worker_quota_exceeded_speech_time_failure(
    mock_get_quota_info, app
):
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    from youtube_voicevox import CommentItem

    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # Simulate quota limit exceeded error
    #
    # クォータ超過エラーをシミュレート
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = (
        b'{"error": {"errors": [{"domain": "usageLimits", '
        b'"reason": "quotaExceeded"}], "code": 403, '
        b'"message": "Quota exceeded"}}'
    )
    mock_chat_client.fetch_chat_messages.side_effect = HttpError(resp, content)

    # Mock _get_next_quota_reset_time to raise exception
    #
    # _get_next_quota_reset_time が例外を投げるようにモック
    with patch.object(
        app, "_get_next_quota_reset_time",
        side_effect=RuntimeError("Time Error")
    ):
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            creds="mock_creds",
            quota_check=True,
            quota_talk=True,
            chat_interval=0.01,
            quota_interval=100.0,
            stream_check_interval=100.0,
        )

    # Verify that announcement is queued with default text
    #
    # アナウンスがデフォルトの文言で投入されていること
    assert app.comment_queue.qsize() == 1
    author, msg = app.comment_queue.get()
    assert author == ""
    assert msg == "ぴんぽーん！残念！クォータを超過しました。"
    app.comment_queue.task_done()


def test_quota_reset_time_calculation_and_speech_formatting(app):
    from datetime import datetime, timezone, timedelta

    # Test _get_next_quota_reset_time (normal case)
    # Test assuming ZoneInfo is available
    #
    # _get_next_quota_reset_time のテスト (正常系)
    # ZoneInfo が使える前提でテストする
    reset_time = app._get_next_quota_reset_time()
    assert isinstance(reset_time, datetime)
    assert reset_time.tzinfo is not None

    # Mock ZoneInfo to raise exception on import to verify fallback
    # behaviour when ZoneInfo loading fails
    #
    # ZoneInfo 読み込み失敗時のフォールバック動作を検証するため、
    # ZoneInfo の import 時に例外を投げるようにモックする
    with patch("zoneinfo.ZoneInfo", side_effect=Exception("mock import error")):
        # When current time is daylight saving time (e.g. June)
        #
        # 現在が夏時間 (6月など) の場合
        reset_time_fallback = app._get_next_quota_reset_time()
        assert isinstance(reset_time_fallback, datetime)

        # Mock current time to winter (e.g. January) to cover PST fallback
        #
        # 現在を冬時間 (1月など) にモックして、PST へのフォールバック (L211) を
        # カバーする
        with patch("youtube_voicevox.datetime") as mock_datetime:
            from datetime import datetime as real_datetime
            mock_datetime.now.side_effect = (
                lambda tz=None: real_datetime(2026, 1, 15, 10, 0, 0, tzinfo=tz)
            )
            
            # Execute _get_next_quota_reset_time to verify tz_la is PST
            #
            # _get_next_quota_reset_time を実行して、tz_la が PST (UTC-8) になる
            # ことを検証
            reset_time_winter = app._get_next_quota_reset_time()
            assert isinstance(reset_time_winter, real_datetime)

    # Test _format_reset_time_for_speech
    # Adjust test dates relative to current time
    #
    # _format_reset_time_for_speech のテスト
    # テスト対象の日付を現在時刻に対して調整
    now_local = datetime.now().astimezone()
    
    # 1. Reset today (same day)
    #
    # 1. 今日のリセット (同日)
    reset_today = now_local.replace(hour=16, minute=0, second=0, microsecond=0)
    formatted = app._format_reset_time_for_speech(reset_today)
    assert "今日の16時" in formatted

    # 1.1 With minutes specified
    #
    # 1.1 分数がある場合
    reset_today_min = now_local.replace(
        hour=16, minute=30, second=0, microsecond=0
    )
    formatted = app._format_reset_time_for_speech(reset_today_min)
    assert "今日の16時30分" in formatted

    # 2. Reset tomorrow
    #
    # 2. 明日のリセット
    reset_tomorrow = (now_local + timedelta(days=1)).replace(
        hour=17, minute=0, second=0, microsecond=0
    )
    formatted = app._format_reset_time_for_speech(reset_tomorrow)
    assert "明日の17時" in formatted

    # 3. Other date reset
    #
    # 3. それ以降の日付
    reset_future = (now_local + timedelta(days=3)).replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    formatted = app._format_reset_time_for_speech(reset_future)
    expected_day = f"{reset_future.month}月{reset_future.day}日"
    assert f"{expected_day}の16時" in formatted


@patch("youtube_voicevox.get_quota_info")
def test_youtube_worker_quota_exceeded_speech_decode_failure(
    mock_get_quota_info, app
):
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # Simulate quota exceeded error (with invalid byte sequence causing decode
    # error)
    #
    # クォータ超過エラーをシミュレート 
    # (デコードエラーになる不正なバイト列を設定)
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'\xff\xff\xff'
    # Verify exception is raised in decode() even if str(e) doesn't have
    # quotaExceeded
    #
    # str(e) に quotaExceeded が含まれないが、e.content.decode("utf-8") で
    # 例外が発生することを確認する
    mock_chat_client.fetch_chat_messages.side_effect = HttpError(resp, content)

    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        creds="mock_creds",
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        quota_interval=100.0,
        stream_check_interval=100.0,
    )

    # Confirm normal error exit occurs due to decode error (no speech)
    #
    # デコードエラーで例外が発生して pass され、通常のエラー終了になる
    # （読み上げは入らない）
    assert app.stop_event.is_set()
    assert app.comment_queue.empty()


@patch("youtube_voicevox.get_quota_info")
def test_youtube_worker_quota_exceeded_speech_import_error(
    mock_get_quota_info, app
):
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # Simulate quota limit exceeded error
    #
    # クォータ超過エラーをシミュレート
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = (
        b'{"error": {"errors": [{"domain": "usageLimits", '
        b'"reason": "quotaExceeded"}], "code": 403, '
        b'"message": "Quota exceeded"}}'
    )
    mock_chat_client.fetch_chat_messages.side_effect = HttpError(resp, content)

    # Patch builtins.__import__ to throw ImportError
    #
    # builtins.__import__ をフックして ImportError を投げるようにパッチする
    import builtins
    real_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if "googleapiclient" in name:
            raise ImportError("mock import error")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            creds="mock_creds",
            quota_check=True,
            quota_talk=True,
            chat_interval=0.01,
            quota_interval=100.0,
            stream_check_interval=100.0,
        )

    # Confirm normal error exit occurs due to import error (no speech)
    #
    # インポートエラーで pass され、通常のエラー終了になる
    # （読み上げは入らない）
    assert app.stop_event.is_set()
    assert app.comment_queue.empty()


@patch("youtube_voicevox.get_quota_info")
def test_youtube_worker_quota_exceeded_speech_queue_empty(
    mock_get_quota_info, app
):
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    import queue

    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # Simulate quota limit exceeded error
    #
    # クォータ超過エラーをシミュレート
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = (
        b'{"error": {"errors": [{"domain": "usageLimits", '
        b'"reason": "quotaExceeded"}], "code": 403, '
        b'"message": "Quota exceeded"}}'
    )
    mock_chat_client.fetch_chat_messages.side_effect = HttpError(resp, content)

    # Mock queue.Empty on get_nowait while making queue appear non-empty
    # initially by patching empty() to return False once
    #
    # キューの中身が入っていると見せかけて、get_nowait() で
    # queue.Empty を発生させる
    # comment_queue.empty() が一瞬 False になるようにパッチしつつ、
    # get_nowait は Empty を投げる
    with patch.object(
        app.comment_queue, "empty", side_effect=[False, True]
    ), patch.object(
        app.comment_queue, "get_nowait", side_effect=queue.Empty
    ):
        
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            creds="mock_creds",
            quota_check=True,
            quota_talk=True,
            chat_interval=0.01,
            quota_interval=100.0,
            stream_check_interval=100.0,
        )

    # Warning message is queued but clearing old messages safely breaks via
    # queue.Empty
    #
    # 警告メッセージは投入されるが、古いメッセージのクリア処理が
    # queue.Empty で安全に break される
    assert app.stop_event.is_set()
    assert app.comment_queue.qsize() == 1
    app.comment_queue.get()
    app.comment_queue.task_done()


# ==============================================================================
# Tests for TTS read-aloud functionality
#
# TTS テスト読み上げ機能のテスト
# ==============================================================================
def test_youtube_worker_tts_test_default_text(app):
    """If default text is specified in tts_test:
    speak() is called with that text.
    
    tts_test にデフォルト文を指定した場合: speak() がそのテキストで呼ばれる
    """
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"activeLiveChatId": "chat_my_live"}
    }
    mock_chat_client.get_live_chat_id.return_value = "chat_my_live"

    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    with patch.object(app, "speak") as mock_speak:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_my_live",
            tts_test="ぴんぽーん！チャット読上げのテストです",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    mock_speak.assert_called_once_with("ぴんぽーん！チャット読上げのテストです")


def test_youtube_worker_tts_test_custom_text(app):
    """If custom text is specified in tts_test:
    speak() is called with that text.
    
    tts_test にカスタムテキストを指定した場合: speak() がそのテキストで呼ばれる
    """
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"activeLiveChatId": "chat_my_live"}
    }
    mock_chat_client.get_live_chat_id.return_value = "chat_my_live"

    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    with patch.object(app, "speak") as mock_speak:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_my_live",
            tts_test="カスタムテキスト",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    mock_speak.assert_called_once_with("カスタムテキスト")


def test_youtube_worker_tts_test_disabled(app):
    """If tts_test=None: speak() is not called even on own live stream.
    
    tts_test=None の場合: 自分のライブでも speak() が呼ばれない
    """
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"activeLiveChatId": "chat_my_live"}
    }
    mock_chat_client.get_live_chat_id.return_value = "chat_my_live"

    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    with patch.object(app, "speak") as mock_speak:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_my_live",
            tts_test=None,
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    mock_speak.assert_not_called()


def test_youtube_worker_tts_test_not_triggered_on_others_live(app):
    """Even if tts_test is enabled,
    speak() is not called on others' live streams.
    
    tts_test 有効でも他者のライブ配信では speak() が呼ばれない
    """
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "other_channel_456"},
        "liveStreamingDetails": {"activeLiveChatId": "chat_other_live"}
    }
    mock_chat_client.get_live_chat_id.return_value = "chat_other_live"

    def fetch_and_stop(*args, **kwargs):
        app.stop_event.set()
        return [], "token", 1000
    mock_chat_client.fetch_chat_messages.side_effect = fetch_and_stop

    with patch.object(app, "speak") as mock_speak:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_other_live",
            tts_test="ぴんぽーん！チャット読上げのテストです",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    mock_speak.assert_not_called()
