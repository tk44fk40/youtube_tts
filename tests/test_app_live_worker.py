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

import pytest

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


@patch("youtube_tts.app.get_quota_info")
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


@patch("youtube_tts.app.get_quota_info")
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
