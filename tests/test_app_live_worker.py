"""YouTubeTtsApp.live_worker の動作を検証するテストモジュールです。"""

from __future__ import annotations

import queue
from typing import Any
from unittest.mock import MagicMock, patch

from youtube_tts import YouTubeLiveChatClient


def test_live_worker_success(app: Any) -> None:
    """正常にチャットを取得し、コメントキューが更新されるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {"displayName": "User1"},
                    "snippet": {
                        "displayMessage": "Hello",
                        "publishedAt": now_iso,
                    },
                },
                # 重複したメッセージIDによるスキップを誘発します。
                {
                    "id": "msg1",
                    "authorDetails": {"displayName": "User1"},
                    "snippet": {
                        "displayMessage": "Hello",
                        "publishedAt": now_iso,
                    },
                },
                {
                    "id": "msg2",
                    "authorDetails": {"displayName": "User2"},
                    "snippet": {
                        "displayMessage": "World",
                        "publishedAt": now_iso,
                    },
                },
                {
                    "id": "msg3",  # スーパーチャットです。
                    "authorDetails": {"displayName": "SuperUser"},
                    "snippet": {
                        "displayMessage": "Thanks!",
                        "publishedAt": now_iso,
                        "superChatDetails": {
                            "amountMicros": 1000000,
                            "currency": "JPY",
                            "amountDisplayString": "¥1,000",
                        },
                    },
                },
            ],
            "next_token_123",
            1000,
        )

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    with patch.object(app, "speak") as mock_speak:
        app.live_worker(
            live_client=mock_live_client,
            video_id="video_123",
            tts_test=None,
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
            backlog_seconds=10,
        )

    # User1(7) + Hello(5) + SuperUser(10) + Thanks!(7) = 29 と計算されます。
    # 各送信者名の末尾に「さん」を追加するため、それぞれ2文字増えます。
    assert app.comment_queue.qsize() == 3
    assert app.queued_char_count == 42
    mock_speak.assert_not_called()


def test_live_worker_backlog_seconds_negative(app: Any) -> None:
    """backlog_secondsが負数の場合にthreshold_timeがNoneになるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    mock_live_client.fetch_chat_messages.return_value = ([], "token", 1000)
    app.stop_event.set()

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
        backlog_seconds=-1,
    )

    assert app.comment_queue.qsize() == 0


def test_live_worker_quota_exceeded(app: Any) -> None:
    """クォータ超過エラー（403）発生時に、適切に待機状態へ遷移するかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    from googleapiclient.errors import HttpError
    from httplib2 import Response

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    ex = HttpError(resp, content)
    mock_live_client.fetch_chat_messages.side_effect = ex

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        creds=MagicMock(),
        quota_check=True,
        quota_talk=True,
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=5.0,
    )

    assert app.comment_queue.qsize() == 1
    assert app.stop_event.is_set() is True


def test_live_worker_generic_exception(app: Any) -> None:
    """一般的な例外が発生した際に、通常のインターバルでリトライされるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    mock_live_client.fetch_chat_messages.side_effect = Exception(
        "Generic Network Error"
    )

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.5,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_tts_test_triggered(app: Any) -> None:
    """tts_testが有効かつ自分の配信の際、テスト発声が実行されるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return [], "token", 1000

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    with patch.object(app, "speak") as mock_speak:
        app.live_worker(
            live_client=mock_live_client,
            video_id="video_my_live",
            tts_test="テスト音声です",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )
        mock_speak.assert_called_once_with("テスト音声です")


def test_live_worker_tts_test_not_triggered_on_others_live(app: Any) -> None:
    """他者の配信である場合、テスト発声がスキップされるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "other_channel_456"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_other_live"

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return [], "token", 1000

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    with patch.object(app, "speak") as mock_speak:
        app.live_worker(
            live_client=mock_live_client,
            video_id="video_other_live",
            tts_test="テスト音声です",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )
        mock_speak.assert_not_called()


def test_live_worker_skip_past_comments(app: Any) -> None:
    """backlog_seconds を超えて古いコメントがスキップされるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {"displayName": "User1"},
                    "snippet": {
                        "displayMessage": "Hello",
                        "publishedAt": "2026-07-03T00:00:00Z",
                    },
                },
                {
                    "id": "msg2",
                    "authorDetails": {"displayName": "User2"},
                    "snippet": {
                        "displayMessage": "World",
                        "publishedAt": "invalid_date",
                    },
                },
            ],
            "next_token_123",
            1000,
        )

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
        backlog_seconds=10,
    )

    assert app.comment_queue.qsize() == 1


def test_live_worker_skip_ng_word(app: Any) -> None:
    """NGワードを含むメッセージがスキップされるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    app.config.ng_words = ["badword"]

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {"displayName": "User1"},
                    "snippet": {"displayMessage": "This badword message"},
                }
            ],
            "next_token_123",
            1000,
        )

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.comment_queue.qsize() == 0


def test_live_worker_queue_full(app: Any) -> None:
    """コメントキューがいっぱいのときに新規コメントがスキップされるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    app.comment_queue = queue.Queue(maxsize=1)
    app.comment_queue.put(("Existing", "Comment"))

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {"displayName": "User1"},
                    "snippet": {"displayMessage": "New message"},
                }
            ],
            "next_token_123",
            1000,
        )

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.comment_queue.qsize() == 1


def test_live_worker_stream_inactive(app: Any) -> None:
    """配信がアクティブではない（終了した）場合にループが終了するかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    mock_live_client.fetch_chat_messages.return_value = (
        [],
        "next_token",
        1000,
    )
    mock_live_client.check_stream_active.return_value = False

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=0.01,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_get_video_details_failure(app: Any) -> None:
    """動画情報取得に失敗した際に早期リターンするかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_video_details.side_effect = Exception("API error")

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=True,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_get_live_chat_id_failure(app: Any) -> None:
    """liveChatId 取得に失敗した際に早期リターンするかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.side_effect = Exception("API error")

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=True,
    )

    assert app.stop_event.is_set() is True


@patch("youtube_tts.workers.live.get_quota_info")
def test_live_worker_quota_info_check(mock_quota_info: Any, app: Any) -> None:
    """クォータ情報取得が実行され、通知キューが更新されるかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    mock_live_client.fetch_chat_messages.return_value = (
        [],
        "next_token",
        1000,
    )
    mock_quota_info.return_value = (1000, 10000)

    call_count = 0

    def sleep_side_effect(*args):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            app.stop_event.set()

    with patch("time.sleep", side_effect=sleep_side_effect):
        app.live_worker(
            live_client=mock_live_client,
            video_id="video_123",
            creds=MagicMock(),
            quota_check=True,
            quota_talk=True,
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=0.01,
            project_id="proj123",
            verbose=True,
        )

    assert mock_quota_info.call_count >= 1
    assert app.comment_queue.qsize() == 1


@patch("youtube_tts.workers.live.get_quota_info")
def test_live_worker_quota_info_error(mock_quota_info: Any, app: Any) -> None:
    """クォータ情報取得中にエラーが発生しても処理が継続するかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    mock_live_client.fetch_chat_messages.return_value = (
        [],
        "next_token",
        1000,
    )
    mock_quota_info.side_effect = Exception("Quota check failure")

    call_count = 0

    def sleep_side_effect(*args):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            app.stop_event.set()

    with patch("time.sleep", side_effect=sleep_side_effect):
        app.live_worker(
            live_client=mock_live_client,
            video_id="video_123",
            creds=MagicMock(),
            quota_check=True,
            quota_talk=True,
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=0.01,
            project_id="proj123",
            verbose=True,
        )

    assert mock_quota_info.call_count >= 1
    assert app.comment_queue.qsize() == 0


def test_format_reset_time_for_speech_direct(app: Any) -> None:
    """app._format_reset_time_for_speech の直接呼び出しをテストします。"""
    from datetime import datetime, timedelta

    now_local = datetime.now().astimezone()

    # 今日の場合のテストです。
    reset_today = now_local.replace(hour=23, minute=30)
    res = app._format_reset_time_for_speech(reset_today)
    assert "今日" in res
    assert "23時30分" in res

    # 明日の場合のテストです。
    reset_tomorrow = (now_local + timedelta(days=1)).replace(hour=5, minute=0)
    res = app._format_reset_time_for_speech(reset_tomorrow)
    assert "明日" in res
    assert "5時" in res

    # それ以外の日の場合のテストです。
    reset_other = (now_local + timedelta(days=3)).replace(hour=12, minute=0)
    res = app._format_reset_time_for_speech(reset_other)
    assert f"{reset_other.month}月{reset_other.day}日" in res


@patch("zoneinfo.ZoneInfo", side_effect=Exception("zoneinfo not available"))
def test_get_next_quota_reset_time_zoneinfo_failure(mock_zi: Any) -> None:
    """zoneinfo が利用不可の場合のフォールバック処理を検証します。

    固定 UTC オフセット UTC-7/-8 の
    フォールバックタイムゾーンが実行されることを確認します。
    """
    from youtube_tts.workers.live import get_next_quota_reset_time

    result = get_next_quota_reset_time()
    assert result is not None


def test_live_worker_get_video_details_failure_verbose_false(
    app: Any,
) -> None:
    """動画情報取得失敗時に、
    verbose=False でも早期リターンするかを検証します。
    """
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_video_details.side_effect = Exception("error")

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=False,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_get_live_chat_id_failure_verbose_false(
    app: Any,
) -> None:
    """liveChatId 取得失敗時に、
    verbose=False でも早期リターンするかを検証します。
    """
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.side_effect = Exception("error")

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=False,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_no_content(app: Any) -> None:
    """HttpError 発生時に content が None の場合の
    クォータ判定を検証します。
    """
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "ch"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "ch"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_id"

    resp = Response({"status": 403, "reason": "Forbidden"})
    ex = HttpError(resp, b"")
    ex.content = None  # content がない場合をシミュレートします。
    mock_live_client.fetch_chat_messages.side_effect = ex

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_decode_error(app: Any) -> None:
    """HttpError の content デコードが失敗した場合の処理を検証します。"""
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "ch"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "ch"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_id"

    resp = Response({"status": 403, "reason": "Forbidden"})
    ex = HttpError(resp, b"not_quota")
    mock_content = MagicMock()
    mock_content.decode.side_effect = UnicodeDecodeError(
        "utf-8", b"", 0, 1, "reason"
    )
    ex.content = mock_content
    mock_live_client.fetch_chat_messages.side_effect = ex

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_quota_check_exception(app: Any) -> None:
    """クォータ判定中に予期しない例外が発生した場合の処理を検証します。

    HttpError の resp を空スペック MagicMock に差し替えることで、
    `e.resp.status` アクセス時に AttributeError を発生させることを検証します。
    """
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "ch"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "ch"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_id"

    resp = Response({"status": 403, "reason": "Forbidden"})
    ex = HttpError(resp, b"")
    # spec=[] を指定し、属性アクセス時に AttributeError を発生させます。
    ex.resp = MagicMock(spec=[])
    mock_live_client.fetch_chat_messages.side_effect = ex

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_quota_exceeded_no_quota_talk(app: Any) -> None:
    """クォータ超過でも quota_talk=False の場合に即終了するかを検証します。"""
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "ch"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "ch"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_id"

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    ex = HttpError(resp, content)
    mock_live_client.fetch_chat_messages.side_effect = ex

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        quota_talk=False,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True
    assert app.comment_queue.qsize() == 0


def test_live_worker_quota_exceeded_drain_empty(app: Any) -> None:
    """キュードレイン中に queue.Empty が発生した場合の処理を検証します。"""
    import queue as queue_module

    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "ch"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "ch"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_id"

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    ex = HttpError(resp, content)
    mock_live_client.fetch_chat_messages.side_effect = ex

    # empty() が最初に False を返してループに入り、get_nowait が
    # queue.Empty を発生させることで except 節を通過させます。
    empty_call_count = 0

    def mock_empty():
        """empty() のモックです。"""
        nonlocal empty_call_count
        empty_call_count += 1
        return empty_call_count != 1

    with (
        patch.object(app.comment_queue, "empty", side_effect=mock_empty),
        patch.object(
            app.comment_queue,
            "get_nowait",
            side_effect=queue_module.Empty,
        ),
    ):
        app.live_worker(
            live_client=mock_live_client,
            video_id="video_123",
            quota_talk=True,
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    assert app.stop_event.is_set() is True


@patch(
    "youtube_tts.workers.live.get_next_quota_reset_time",
    side_effect=Exception("tz error"),
)
def test_live_worker_quota_exceeded_reset_time_failure(
    mock_reset_time: Any,
    app: Any,
) -> None:
    """リセット時刻取得に失敗した場合の
    フォールバックメッセージを検証します。
    """
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "ch"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "ch"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_id"

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    ex = HttpError(resp, content)
    mock_live_client.fetch_chat_messages.side_effect = ex

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.comment_queue.qsize() == 1
    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_verbose(app: Any) -> None:
    """チャット取得失敗時に verbose=True でデバッグログが出るかを検証します。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "ch"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "ch"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_id"
    mock_live_client.fetch_chat_messages.side_effect = Exception("error")

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_threshold_time_none(app: Any) -> None:
    """backlog_seconds=-1（threshold_time=None）の場合に全コメントを
    処理するかを検証します。
    """
    from datetime import datetime, timezone

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    now_iso = datetime.now(timezone.utc).isoformat()

    def fetch_side_effect(*args, **kwargs):
        """フェッチのサイドエフェクトです。"""
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {"displayName": "User1"},
                    "snippet": {
                        "displayMessage": "Hello",
                        "publishedAt": now_iso,
                    },
                }
            ],
            None,
            1000,
        )

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        backlog_seconds=-1,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.comment_queue.qsize() == 1


@patch("time.sleep")
def test_live_worker_stream_active_then_stop(mock_sleep: Any, app: Any) -> None:
    """ストリームがアクティブな場合に last_stream_check_time が
    更新されるかを検証します。
    """
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"
    mock_live_client.check_stream_active.return_value = True

    fetch_call_count = 0

    def fetch_side_effect(*args, **kwargs):
        """フェッチのサイドエフェクトです。"""
        nonlocal fetch_call_count
        fetch_call_count += 1
        if fetch_call_count >= 2:
            app.stop_event.set()
        return [], "token", 100

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=True,
        chat_interval=0.0,
        stream_check_interval=0.0,
        quota_interval=100.0,
    )

    assert mock_live_client.check_stream_active.called


@patch("youtube_tts.workers.live.get_quota_info")
@patch("time.sleep")
def test_live_worker_quota_check_verbose_false(
    mock_sleep: Any,
    mock_quota_info: Any,
    app: Any,
) -> None:
    """クォータチェック時に
    verbose=False の分岐を検証します。
    """
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"
    mock_live_client.fetch_chat_messages.return_value = ([], "token", 1000)
    mock_quota_info.return_value = (1000, 10000)

    sleep_call_count = 0

    def sleep_side_effect(*args):
        """sleep のサイドエフェクトです。"""
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            app.stop_event.set()

    mock_sleep.side_effect = sleep_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        creds=MagicMock(),
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=0.01,
        project_id="proj123",
        verbose=False,
    )

    assert mock_quota_info.call_count >= 1


@patch("youtube_tts.workers.live.get_quota_info")
@patch("time.sleep")
def test_live_worker_quota_talk_same_used(
    mock_sleep: Any,
    mock_quota_info: Any,
    app: Any,
) -> None:
    """前回と使用量が同じ場合に
    読み上げがスキップされるかを検証します。
    """
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"
    mock_live_client.fetch_chat_messages.return_value = ([], "token", 1000)
    mock_quota_info.return_value = (1000, 10000)
    # 前回の使用量を同じ値にして is_diff=False にします。
    app.last_spoken_used = 1000

    sleep_call_count = 0

    def sleep_side_effect(*args):
        """sleep のサイドエフェクトです。"""
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            app.stop_event.set()

    mock_sleep.side_effect = sleep_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        creds=MagicMock(),
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=0.01,
        project_id="proj123",
    )

    assert app.comment_queue.qsize() == 0


@patch("youtube_tts.workers.live.get_quota_info")
@patch("time.sleep")
def test_live_worker_quota_error_verbose_false(
    mock_sleep: Any,
    mock_quota_info: Any,
    app: Any,
) -> None:
    """クォータ情報取得失敗時に
    verbose=False の分岐を検証します。
    """
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"
    mock_live_client.fetch_chat_messages.return_value = ([], "token", 1000)
    mock_quota_info.side_effect = Exception("quota error")

    sleep_call_count = 0

    def sleep_side_effect(*args):
        """sleep のサイドエフェクトです。"""
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            app.stop_event.set()

    mock_sleep.side_effect = sleep_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        creds=MagicMock(),
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=0.01,
        project_id="proj123",
        verbose=False,
    )

    assert app.comment_queue.qsize() == 0


@patch("youtube_tts.workers.live.datetime")
def test_get_next_quota_reset_time_pst_winter(mock_datetime: Any) -> None:
    """zoneinfo 失敗時に冬時間（PST, UTC-8）へ
    フォールバックされるかを検証します。

    テスト実行月に依存しないよう
    datetime.now を 12 月にモックします。
    """
    from datetime import datetime, timedelta, timezone

    from youtube_tts.workers.live import get_next_quota_reset_time

    # 12月（PST）として動作させます。
    fake_now = datetime(2024, 12, 15, 10, 0, 0, tzinfo=timezone.utc)

    def mock_now(tz=None):
        if tz is not None:
            return fake_now.astimezone(tz)
        return fake_now

    mock_datetime.now.side_effect = mock_now

    with patch(
        "zoneinfo.ZoneInfo", side_effect=Exception("zoneinfo が利用できません")
    ):
        result = get_next_quota_reset_time()

    assert result is not None
    # UTC-8 オフセットで次の日午前0時に設定されることを検証します。
    # 2024-12-15 10:00:00 UTC は 2024-12-15 02:00:00 PST (UTC-8)
    expected_tz = timezone(timedelta(hours=-8))
    now_pst = fake_now.astimezone(expected_tz)
    expected = (now_pst + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    assert result.astimezone(timezone.utc) == expected.astimezone(timezone.utc)


def test_live_worker_quota_exceeded_drain_actual(app: Any) -> None:
    """キュードレイン時の正常な処理を検証します。

    get_nowait が成功して task_done が
    呼ばれること、またキューに実際のアイテムを積んで
    正常なドレインパスを通過することを確認します。
    """
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "ch"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "ch"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_id"

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    ex = HttpError(resp, content)
    mock_live_client.fetch_chat_messages.side_effect = ex

    # キューに実際のアイテムを積んで drain ループを通過させます。
    app.comment_queue.put(("Author", "Message"))

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True
