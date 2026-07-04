# Copyright 2026 tk44fk40
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Tests for YouTubeTtsApp.live_worker.

YouTubeTtsApp.live_worker のテストモジュール。
"""

import queue
from unittest.mock import MagicMock, patch

import youtube_tts.workers.live  # noqa: F401
from youtube_tts import YouTubeLiveChatClient


def test_live_worker_success(app):
    """正常にチャットを取得し、コメントキューが更新されるか検証。"""
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
                {
                    "id": "msg1",  # Duplicate message ID to trigger skip
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
                    "id": "msg3",  # Super Chat
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

    # User1(7) + Hello(5) + SuperUser(10) + Thanks!(7) = 29
    # Suffix 'さん' adds 2 chars for each author
    assert app.comment_queue.qsize() == 3
    assert app.queued_char_count == 42
    mock_speak.assert_not_called()


def test_live_worker_backlog_seconds_negative(app):
    """backlog_secondsが負数の場合にthreshold_timeがNoneになるか検証。"""
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


def test_live_worker_quota_exceeded(app):
    """クォータ超過エラー（403）発生時に、適切に待機状態へ遷移するか検証。"""
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


def test_live_worker_generic_exception(app):
    """一般的な例外が発生した際に、通常のインターバルでリトライされるか検証。"""
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


def test_live_worker_tts_test_triggered(app):
    """tts_testが有効かつ自分の配信の際、テスト発声が実行されるか検証。"""
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


def test_live_worker_tts_test_not_triggered_on_others_live(app):
    """他者の配信である場合、テスト発声がスキップされるか検証。"""
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


def test_live_worker_skip_past_comments(app):
    """backlog_seconds を超えて古いコメントがスキップされるか検証。"""
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


def test_live_worker_skip_ng_word(app):
    """NGワードを含むメッセージがスキップされるか検証。"""
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


def test_live_worker_queue_full(app):
    """コメントキューがいっぱいのときに新規コメントがスキップされるか検証。"""
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


def test_live_worker_stream_inactive(app):
    """配信がアクティブではない（終了した）場合にループが終了するか検証。"""
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


def test_live_worker_get_video_details_failure(app):
    """動画情報取得に失敗した際に早期リターンするか検証。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_video_details.side_effect = Exception("API error")

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=True,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_get_live_chat_id_failure(app):
    """liveChatId 取得に失敗した際に早期リターンするか検証。"""
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
def test_live_worker_quota_info_check(mock_quota_info, app):
    """クォータ情報取得が実行され、通知キューが更新されるか検証。"""
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
def test_live_worker_quota_info_error(mock_quota_info, app):
    """クォータ情報取得中にエラーが発生しても処理が継続するか検証。"""
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


def test_format_reset_time_for_speech_direct(app):
    """app._format_reset_time_for_speech の直接呼び出しテスト。"""
    from datetime import datetime, timedelta

    now_local = datetime.now().astimezone()

    # 今日
    reset_today = now_local.replace(hour=23, minute=30)
    res = app._format_reset_time_for_speech(reset_today)
    assert "今日" in res
    assert "23時30分" in res

    # 明日
    reset_tomorrow = (now_local + timedelta(days=1)).replace(hour=5, minute=0)
    res = app._format_reset_time_for_speech(reset_tomorrow)
    assert "明日" in res
    assert "5時" in res

    # それ以外の日
    reset_other = (now_local + timedelta(days=3)).replace(hour=12, minute=0)
    res = app._format_reset_time_for_speech(reset_other)
    assert f"{reset_other.month}月{reset_other.day}日" in res


@patch("zoneinfo.ZoneInfo", side_effect=Exception("zoneinfo not available"))
def test_get_next_quota_reset_time_zoneinfo_failure(mock_zi):
    """zoneinfo が利用不可の場合のフォールバック処理を検証する。

    固定 UTC オフセット UTC-7/-8 の
    フォールバックタイムゾーン）が実行されることを確認する。
    """
    from youtube_tts.workers.live import get_next_quota_reset_time

    result = get_next_quota_reset_time()
    assert result is not None


def test_live_worker_get_video_details_failure_verbose_false(app):
    """動画情報取得失敗時に verbose=False でも早期リターンするか検証。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_video_details.side_effect = Exception("error")

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=False,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_get_live_chat_id_failure_verbose_false(app):
    """liveChatId 取得失敗時に verbose=False でも早期リターンするか検証。"""
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


def test_live_worker_fetch_error_no_content(app):
    """HttpError 発生時に content が None の場合のクォータ判定を検証。"""
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
    ex.content = None  # content なし
    mock_live_client.fetch_chat_messages.side_effect = ex

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_decode_error(app):
    """HttpError の content デコードが失敗した場合の処理を検証する。"""
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


def test_live_worker_fetch_error_quota_check_exception(app):
    """クォータ判定中に予期しない例外が発生した場合の処理を検証する。

    HttpError の resp を空スペック MagicMock に差し替えることで、
    `e.resp.status` アクセス時に AttributeError を発生させる。
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
    # spec=[] → 属性アクセス時に AttributeError を発生させる
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


def test_live_worker_quota_exceeded_no_quota_talk(app):
    """クォータ超過でも quota_talk=False の場合に即終了するか検証。"""
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


def test_live_worker_quota_exceeded_drain_empty(app):
    """キュードレイン中に queue.Empty が発生した場合の処理を検証する。"""
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

    # empty() が最初 False を返してループに入り、get_nowait が
    # queue.Empty を発生させることで except 節を通過させる
    empty_call_count = 0

    def mock_empty():
        """empty() のモック。"""
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
def test_live_worker_quota_exceeded_reset_time_failure(mock_reset_time, app):
    """リセット時刻取得に失敗した場合のフォールバックメッセージを検証。"""
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


def test_live_worker_fetch_error_verbose(app):
    """チャット取得失敗時に verbose=True でデバッグログが出るか検証。"""
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


def test_live_worker_threshold_time_none(app):
    """backlog_seconds=-1（threshold_time=None）の場合に全コメントを
    処理するか検証する"""
    from datetime import datetime, timezone

    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"

    now_iso = datetime.now(timezone.utc).isoformat()

    def fetch_side_effect(*args, **kwargs):
        """フェッチのサイドエフェクト。"""
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
def test_live_worker_stream_active_then_stop(mock_sleep, app):
    """ストリームがアクティブな場合に last_stream_check_time が
    更新されるか検証。
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
        """フェッチのサイドエフェクト。"""
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
    mock_sleep, mock_quota_info, app
):
    """クォータチェック時に verbose=False の分岐を検証する。"""
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
        """sleep のサイドエフェクト。"""
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
def test_live_worker_quota_talk_same_used(mock_sleep, mock_quota_info, app):
    """前回と使用量が同じ場合に読み上げがスキップされるか検証する。"""
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_my_channel_id.return_value = "my_channel_123"
    mock_live_client.get_video_details.return_value = {
        "snippet": {"channelId": "my_channel_123"},
    }
    mock_live_client.get_live_chat_id.return_value = "chat_live_123"
    mock_live_client.fetch_chat_messages.return_value = ([], "token", 1000)
    mock_quota_info.return_value = (1000, 10000)
    # 前回の使用量を同じ値にして is_diff=False にする
    app.last_spoken_used = 1000

    sleep_call_count = 0

    def sleep_side_effect(*args):
        """sleep のサイドエフェクト。"""
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
    mock_sleep, mock_quota_info, app
):
    """クォータ情報取得失敗時に verbose=False の分岐を検証する。"""
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
        """sleep のサイドエフェクト。"""
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
def test_get_next_quota_reset_time_pst_winter(mock_datetime):
    """zoneinfo 失敗時に冬時間（PST, UTC-8）フォールバックを検証する。

    テスト実行月に依存しないよう datetime.now を 12 月にモックする。
    """
    from datetime import datetime, timedelta, timezone

    from youtube_tts.workers.live import get_next_quota_reset_time

    # 12月（PST）に見せかける
    fake_now = datetime(2024, 12, 15, 10, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = fake_now

    with patch(
        "zoneinfo.ZoneInfo", side_effect=Exception("zoneinfo not available")
    ):
        result = get_next_quota_reset_time()

    assert result is not None
    # UTC-8 オフセットで次の日午前0時に設定されること
    expected_tz = timezone(timedelta(hours=-8))
    now_pst = fake_now.astimezone(expected_tz)
    expected = (now_pst + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    assert result.utcoffset() == expected.utcoffset()


def test_live_worker_quota_exceeded_drain_actual(app):
    """キュードレイン時に get_nowait が成功して task_done が呼ばれるか検証。

    キューに実際のアイテムを積んで正常な drain パスを通過させる。
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

    # キューに実際のアイテムを積んで drain ループを通過させる
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
