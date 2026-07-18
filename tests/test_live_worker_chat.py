"""live_worker のチャット取得正常系を検証するテストモジュールです。"""

from __future__ import annotations

import queue
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts.workers.live import live_worker


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
        live_worker(
            app=app,
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
    assert app.speech_queue.qsize() == 3
    assert app.speech_queue.queued_char_count == 42
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

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
        backlog_seconds=-1,
    )

    assert app.speech_queue.qsize() == 0


@pytest.mark.parametrize(
    "display_message, published_at, ng_words, queue_maxsize, "
    "backlog_seconds, expect_qsize",
    [
        ("Hello", "2026-07-03T00:00:00Z", [], None, 10, 0),
        ("World", "invalid_date", [], None, 10, 1),
        ("This badword message", None, ["badword"], None, 10, 0),
        ("New message", None, [], 1, 10, 0),
        ("Hello", "2026-07-03T00:00:00Z", [], None, -1, 1),
    ],
)
def test_live_worker_filters(
    app: Any,
    mock_live_client: MagicMock,
    display_message: str,
    published_at: str | None,
    ng_words: list[str],
    queue_maxsize: int | None,
    backlog_seconds: int,
    expect_qsize: int,
) -> None:
    """チャット取得時の各種フィルタリング処理を検証します。"""
    app.config.ng_words = ng_words
    if queue_maxsize is not None:
        from youtube_tts.queue import SpeechQueue
        app.speech_queue = SpeechQueue(maxsize=queue_maxsize)
        if queue_maxsize == 1:
            from youtube_tts.models import SpeechItem
            app.speech_queue.put(SpeechItem("Existing", "Comment", 15))

    def fetch_side_effect(
        *args: Any, **kwargs: Any
    ) -> tuple[list[dict[str, Any]], str, int]:
        app.stop_event.set()
        snippet: dict[str, Any] = {"displayMessage": display_message}
        if published_at is not None:
            snippet["publishedAt"] = published_at
        return (
            [
                {
                    "id": "msg1",
                    "authorDetails": {"displayName": "User1"},
                    "snippet": snippet,
                }
            ],
            "next_token_123",
            1000,
        )

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
        backlog_seconds=backlog_seconds,
    )

    actual_qsize = app.speech_queue.qsize()
    if queue_maxsize == 1:
        assert actual_qsize == 1
    else:
        assert actual_qsize == expect_qsize


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
        live_worker(
            app=app,
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
        live_worker(
            app=app,
            live_client=mock_live_client,
            video_id="video_other_live",
            tts_test="テスト音声です",
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )
        mock_speak.assert_not_called()
