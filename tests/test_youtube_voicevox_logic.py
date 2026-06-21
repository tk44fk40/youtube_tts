import pytest
import sys
import time
import queue
import logging
import threading
from io import StringIO
from unittest.mock import MagicMock, patch

from youtube_voicevox import YouTubeTtsApp
from youtube_tts import AppConfig, AudioPlayer, VoicevoxClient, YouTubeChatClient, setup_logger

# 毎回テスト実行時に YouTubeTtsApp 用のモックなどを生成するヘルパー fixture
@pytest.fixture
def mock_app_dependencies():
    config = AppConfig(
        dictionary_path="dictionary.txt",
        ng_words_path="ng_words.txt",
        volume_path="volume.txt"
    )
    # 値を設定
    config.volume_scale = 0.5
    
    voicevox_client = MagicMock(spec=VoicevoxClient)
    audio_player = MagicMock(spec=AudioPlayer)
    audio_player.target_sample_rate = 24000
    
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
# 1. logger および setup_logger のテスト
# ==============================================================================
def test_setup_logger():
    captured_output = StringIO()
    logger = setup_logger(verbose=True)
    
    # 既存のハンドラから出力を奪うために、StringIO を持つ StreamHandler を一時的に追加する
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
        # 他のテストに影響しないようハンドラを削除する
        logger.removeHandler(handler)

# ==============================================================================
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
    
    # 例外をキャッチし、クラッシュしないこと、ログが出力されることを確認
    with patch.object(app.logger, "error") as mock_error:
        app.speak("エラーテスト")
        app.audio_player.play_wav.assert_not_called()
        mock_error.assert_called_once()


def test_playback_worker(app):
    app.comment_queue.put(("User1", "こんにちは"))

    with patch.object(app, "speak") as mock_speak:
        # speak 実行後にスレッドを終了させるためにストップイベントをセット
        def side_effect(text, *args, **kwargs):
            app.stop_event.set()
        mock_speak.side_effect = side_effect

        app.playback_worker()

        mock_speak.assert_called_once_with("User1 こんにちは", speed_scale=1.0)


# ==============================================================================
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
    """playback_thread.join() が例外を投げてもクラッシュしないことを確認。"""
    mock_thread = MagicMock(spec=threading.Thread)
    mock_thread.join.side_effect = RuntimeError("Join error")

    app.cleanup(playback_thread=mock_thread, wait_seconds=0.1)
    assert app.stop_event.is_set()


# ==============================================================================
# 4. youtube_worker のテスト
# ==============================================================================
def test_youtube_worker_normal_flow(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

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
    # 古いメッセージ（20秒前）
    old_time_str = (now - timedelta(seconds=20)).isoformat().replace("+00:00", "Z")
    # 新しいメッセージ（5秒前）
    new_time_str = (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")

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

    # SKIP(PAST) ログが出力されたことを確認
    assert any("[SKIP(PAST)]" in call[0][0] for call in mock_debug.call_args_list)

    # 新しいメッセージのみがキューに入っていることを確認
    assert app.comment_queue.qsize() == 1
    author, msg = app.comment_queue.get()
    assert author == "視聴者Bさん"
    assert msg == "新しいメッセージ"

    # 重複防止IDには両方追加されていることを確認
    assert "msg_old" in app.processed_message_ids
    assert "msg_new" in app.processed_message_ids


def test_youtube_worker_backlog_seconds_all(app):
    from datetime import datetime, timezone, timedelta
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    now = datetime.now(timezone.utc)
    old_time_str = (now - timedelta(seconds=20)).isoformat().replace("+00:00", "Z")

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

    # 制限なし（-1）の設定
    app.youtube_worker(
        chat_client=mock_chat_client,
        video_id="video_abc",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
        backlog_seconds=-1,
    )

    # 古いメッセージもキューに入っていることを確認
    assert app.comment_queue.qsize() == 1
    author, msg = app.comment_queue.get()
    assert author == "視聴者Aさん"
    assert msg == "古いメッセージ"



def test_youtube_worker_ng_word(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

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

    # NGワード判定をTrueにするパッチ
    with patch.object(app.text_processor, "contains_ng_word", return_value=True) as mock_ng_check:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )
        mock_ng_check.assert_called_with("これはNGワードを含むコメントです")

    # コメントキューが空であることを確認（スキップされた）
    assert app.comment_queue.empty()


def test_youtube_worker_stream_inactive(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    
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

    # クォータの読み上げテキストがキューに入っていること
    assert not app.comment_queue.empty()
    author, msg = app.comment_queue.get()
    assert author == ""
    assert msg == "ぴんぽーん！クォータ使用量は 3500 ユニットです。"


def test_youtube_worker_verbose_logs(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    
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

    # verbose 出力が含まれていることを確認
    mock_debug.assert_any_call("Fetching chat messages (is_live: True, pageToken: None)")


# ==============================================================================
# 5. エッジケース・例外ハンドリングのテスト
# ==============================================================================
def test_youtube_worker_deduplication(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    # 同一のメッセージを2回返す
    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            items = [
                {"id": "msg_dup", "authorDetails": {"displayName": "UserA"}, "snippet": {"displayMessage": "Hello"}},
                {"id": "msg_dup", "authorDetails": {"displayName": "UserA"}, "snippet": {"displayMessage": "Hello"}}
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

    # 重複判定により、キューに格納されるのは1件のみであることを確認
    assert app.comment_queue.qsize() == 1


def test_youtube_worker_history_overflow(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    app.max_processed_message_ids = 2

    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            # 3件のメッセージを取得
            items = [
                {"id": "msg_1", "authorDetails": {"displayName": "User"}, "snippet": {"displayMessage": "Msg 1"}},
                {"id": "msg_2", "authorDetails": {"displayName": "User"}, "snippet": {"displayMessage": "Msg 2"}},
                {"id": "msg_3", "authorDetails": {"displayName": "User"}, "snippet": {"displayMessage": "Msg 3"}},
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
    # コメントキューを最大件数（50件）で満たす
    for i in range(50):
        app.comment_queue.put(("User", f"Message {i}"))

    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"

    def fetch_side_effect(live_chat_id, page_token=None):
        if page_token is None:
            items = [{"id": "msg_extra", "authorDetails": {"displayName": "User"}, "snippet": {"displayMessage": "Extra"}}]
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

    # キュー満杯によるスキップログを確認
    mock_info.assert_any_call("[SKIP(QUEUE)] Userさん: Extra")
    assert app.comment_queue.qsize() == 50


def test_youtube_worker_fetch_exception(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    mock_chat_client.fetch_chat_messages.side_effect = Exception("YouTube API Error")

    with patch.object(app.logger, "error") as mock_error:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    mock_error.assert_called_with("Failed to fetch chat/comments: YouTube API Error")
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
    mock_chat_client.fetch_chat_messages.assert_called_once_with("chat_my_live", page_token=None)


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
    mock_chat_client.get_live_chat_id.assert_called_once_with("video_other_live")
    mock_chat_client.fetch_chat_messages.assert_called_once_with("chat_other_live", page_token=None)


def test_youtube_worker_archive_mode(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {"activeLiveChatId": "chat_old", "actualEndTime": "2026-06-21T12:00:00Z"}
    }
    
    mock_chat_client.fetch_comment_threads.side_effect = [
        ([{"id": "c1", "authorDetails": {"displayName": "Alice"}, "snippet": {"displayMessage": "Hello!"}}], None, 3000),
        ([{"id": "c2", "authorDetails": {"displayName": "Bob"}, "snippet": {"displayMessage": "New Comment"}}], None, 3000),
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

    mock_get_quota_info.side_effect = Exception("Monitoring API Error")

    with patch.object(app.logger, "warning") as mock_warning:
        app.youtube_worker(
            chat_client=mock_chat_client,
            video_id="video_abc",
            creds="mock_creds",
            quota_check=True,
            chat_interval=0.01,
            quota_interval=-1.0,
            stream_check_interval=100.0,
            project_id="project_123",
        )

    mock_warning.assert_called_with("Failed to fetch quota info: Monitoring API Error")


def test_youtube_worker_stream_active_verbose(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_live_chat_id.return_value = "chat_id_123"
    
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

    # キューと文字数カウンタにコメントをセット
    # Comment 1: "User1 Hello"
    # Comment 2: "User2 AAAAA..." (180 chars)
    # Total chars = 11 + 180 = 191
    from youtube_voicevox import CommentItem
    app.comment_queue.put(CommentItem("User1", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 175, 180))
    app.queued_char_count = 191

    with patch.object(app, "speak") as mock_speak:
        # speak 完了後にスレッドを終了させるためにストップイベントをセット
        def side_effect(text, speed_scale=None):
            app.stop_event.set()
        mock_speak.side_effect = side_effect

        app.playback_worker()

        # 191文字から今回消費した11文字を引いて、残りは180文字になること
        assert app.queued_char_count == 180
        mock_speak.assert_called_once_with("User1 Hello", speed_scale=1.8)


def test_playback_worker_backward_compatibility(app):
    # 2要素タプルをキューに投入 (旧仕様テストケースのシミュレーション)
    app.comment_queue.put(("UserOld", "HelloOld"))
    app.queued_char_count = 15  # "UserOld" (7) + "HelloOld" (8) = 15文字

    with patch.object(app, "speak") as mock_speak:
        def side_effect(text, speed_scale=None):
            app.stop_event.set()
        mock_speak.side_effect = side_effect

        app.playback_worker()

        # 無事にアンパックされ、文字数が引かれていること
        assert app.queued_char_count == 0
        mock_speak.assert_called_once_with("UserOld HelloOld", speed_scale=1.0)


def test_youtube_worker_video_details_failure(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_video_details.side_effect = Exception("Details API Error")

    with patch.object(app.logger, "error") as mock_error:
        app.youtube_worker(mock_chat_client, "vid")
    
    mock_error.assert_called_with("Failed to get video details: Details API Error")
    assert app.stop_event.is_set()


def test_youtube_worker_get_live_chat_id_failure(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
        "liveStreamingDetails": {}
    }
    mock_chat_client.get_live_chat_id.side_effect = Exception("Chat ID API Error")

    with patch.object(app.logger, "error") as mock_error:
        app.youtube_worker(mock_chat_client, "vid")

    mock_error.assert_called_with("Failed to get liveChatId: Chat ID API Error")
    assert app.stop_event.is_set()


def test_youtube_worker_posted_video_mode(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    mock_chat_client.get_my_channel_id.return_value = "my_channel_123"
    mock_chat_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"}
    }
    
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
    mock_chat_client.fetch_comment_threads.side_effect = Exception("Fetch API Error")

    with patch.object(app.logger, "error") as mock_error:
        app.youtube_worker(mock_chat_client, "vid", chat_interval=0.01)
    
    mock_error.assert_any_call("Failed to fetch initial comment threads: Fetch API Error")


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
        ([{"id": "ng_c", "authorDetails": {"displayName": "Spammer"}, "snippet": {"displayMessage": "badword"}}], None, 3000),
        side_effect
    ]

    with patch.object(app.text_processor, "contains_ng_word", return_value=True):
        with patch.object(app.logger, "info") as mock_info:
            app.youtube_worker(mock_chat_client, "vid", chat_interval=0.01, verbose=True)
    
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
        ([{"id": "overflow_c", "authorDetails": {"displayName": "User"}, "snippet": {"displayMessage": "Hello"}}], None, 3000),
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
        app.youtube_worker(mock_chat_client, "vid", chat_interval=0.01, backlog_seconds=10)
    
    mock_warning.assert_any_call("Failed to parse publishedAt: invalid-date-format, error: Invalid isoformat string: 'invalid-date-format'")


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
        ([{"id": f"c_{i}", "authorDetails": {"displayName": "U"}, "snippet": {"displayMessage": "M"}} for i in range(10)], "next_token_1", 3000),
        polling_stop
    ]

    app.youtube_worker(mock_chat_client, "vid", chat_interval=0.01, backlog_counts=5)
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
                {"id": "c1", "authorDetails": {"displayName": "U"}, "snippet": {"displayMessage": "M1"}},
                {"id": "c2", "authorDetails": {"displayName": "U"}, "snippet": {"displayMessage": "M2"}},
                {"id": "c3", "authorDetails": {"displayName": "U"}, "snippet": {"displayMessage": "M3"}},
            ], None, 3000
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_chat_client.fetch_comment_threads.side_effect = fetch_threads_side_effect
    
    app.youtube_worker(mock_chat_client, "vid", chat_interval=0.01, backlog_counts=10)
    # c3 (oldest) should be discarded when history size is capped at 2 (c1, c2 are newer)
    assert "c3" not in app.processed_message_ids
    assert "c2" in app.processed_message_ids
    assert "c1" in app.processed_message_ids


def test_youtube_app_run_unexpected_error(app):
    mock_chat_client = MagicMock(spec=YouTubeChatClient)
    with patch.object(app, "youtube_worker", side_effect=Exception("Unexpected crash!")):
        with patch.object(app.logger, "error") as mock_error:
            app.run(mock_chat_client, "vid")
    
    mock_error.assert_called_with("Unexpected error: Unexpected crash!")


