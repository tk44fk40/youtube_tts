"""live_worker のチャット取得正常系を検証するテストモジュールです。"""

from __future__ import annotations

import queue
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch


def test_live_worker_success(app: Any, mock_live_client: MagicMock) -> None:
    """正常にチャットを取得し、コメントキューが更新されるかを検証します。"""
    now_iso = datetime.now(timezone.utc).isoformat()

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {
                        "displayName": "User1",
                    },
                    "snippet": {
                        "displayMessage": "Hello",
                        "publishedAt": now_iso,
                    },
                },
                # 重複したメッセージIDによるスキップを
                # 誘発します。
                {
                    "id": "msg1",
                    "authorDetails": {
                        "displayName": "User1",
                    },
                    "snippet": {
                        "displayMessage": "Hello",
                        "publishedAt": now_iso,
                    },
                },
                {
                    "id": "msg2",
                    "authorDetails": {
                        "displayName": "User2",
                    },
                    "snippet": {
                        "displayMessage": "World",
                        "publishedAt": now_iso,
                    },
                },
                {
                    "id": "msg3",
                    "authorDetails": {
                        "displayName": "SuperUser",
                    },
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

    # User1(7) + Hello(5) + SuperUser(10) + Thanks!(7)
    # = 29 と計算されます。
    # 各送信者名の末尾に「さん」を追加するため、
    # それぞれ2文字増えます。
    assert app.comment_queue.qsize() == 3
    assert app.queued_char_count == 42
    mock_speak.assert_not_called()


def test_live_worker_backlog_seconds_negative(
    app: Any, mock_live_client: MagicMock
) -> None:
    """backlog_secondsが負数の場合に
    threshold_timeがNoneになるかを検証します。
    """
    mock_live_client.fetch_chat_messages.return_value = (
        [],
        "token",
        1000,
    )
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


def test_live_worker_skip_past_comments(
    app: Any, mock_live_client: MagicMock
) -> None:
    """backlog_seconds を超えて古いコメントが
    スキップされるかを検証します。
    """

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {
                        "displayName": "User1",
                    },
                    "snippet": {
                        "displayMessage": "Hello",
                        "publishedAt": ("2026-07-03T00:00:00Z"),
                    },
                },
                {
                    "id": "msg2",
                    "authorDetails": {
                        "displayName": "User2",
                    },
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


def test_live_worker_skip_ng_word(
    app: Any, mock_live_client: MagicMock
) -> None:
    """NGワードを含むメッセージが
    スキップされるかを検証します。
    """
    app.config.ng_words = ["badword"]

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {
                        "displayName": "User1",
                    },
                    "snippet": {
                        "displayMessage": ("This badword message"),
                    },
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


def test_live_worker_queue_full(app: Any, mock_live_client: MagicMock) -> None:
    """コメントキューがいっぱいのときに新規コメントが
    スキップされるかを検証します。
    """
    app.comment_queue = queue.Queue(maxsize=1)
    app.comment_queue.put(("Existing", "Comment"))

    def fetch_side_effect(*args, **kwargs):
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {
                        "displayName": "User1",
                    },
                    "snippet": {
                        "displayMessage": "New message",
                    },
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


def test_live_worker_threshold_time_none(
    app: Any, mock_live_client: MagicMock
) -> None:
    """backlog_seconds=-1（threshold_time=None）の場合に
    全コメントを処理するかを検証します。
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    def fetch_side_effect(*args, **kwargs):
        """フェッチのサイドエフェクトです。"""
        app.stop_event.set()
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {
                        "displayName": "User1",
                    },
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


def test_live_worker_tts_test_triggered(
    app: Any, mock_live_client: MagicMock
) -> None:
    """tts_testが有効かつ自分の配信の際、
    テスト発声が実行されるかを検証します。
    """

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


def test_live_worker_tts_test_not_triggered_on_others_live(
    app: Any, mock_live_client: MagicMock
) -> None:
    """他者の配信である場合、テスト発声が
    スキップされるかを検証します。
    """
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
