"""video_worker のリアルタイム監視ポーリングフェーズを
検証するテストモジュールです。
"""

from __future__ import annotations

import queue
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts.models import YouTubeMessage


def test_video_worker_success(app: Any, mock_video_client: MagicMock) -> None:
    """正常に動画コメントを取得し、コメントキューが更新されるかを検証します。"""
    call_count = 0

    # API呼び出しのモック動作を定義します。
    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # 1回目は初期バックログ用コメントを返します。
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "User1",
                            "channelId": "ch1",
                        },
                        "snippet": {
                            "displayMessage": "Backlog1",
                            "publishedAt": "2026-07-03T10:00:00Z",
                        },
                    }
                ],
                "token_next",
                3000,
            )
        elif call_count == 2:
            # 2回目はバックログ取得のループ終了条件を満たすために空を返します。
            return [], None, 3000
        else:
            # 3回目はメインループ内での動作として、
            # 重複と新規コメントを返します。
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",  # バックログとの重複のためスキップされます
                        "authorDetails": {
                            "displayName": "User1",
                            "channelId": "ch1",
                        },
                        "snippet": {
                            "displayMessage": "Backlog1",
                            "publishedAt": "2026-07-03T10:00:00Z",
                        },
                    },
                    {
                        "id": "c2",  # 新規コメントとしてキューに格納されます
                        "authorDetails": {
                            "displayName": "User2",
                            "channelId": "ch2",
                        },
                        "snippet": {
                            "displayMessage": "NewComment",
                            "publishedAt": "2026-07-03T10:05:00Z",
                        },
                    },
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    # 対象のワーカー関数を実行します。
    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    # 取得したコメント数および文字数が想定通りか検証します。
    assert app.comment_queue.qsize() == 2
    assert app.queued_char_count == 32


@pytest.mark.parametrize("verbose", [True, False])
def test_video_worker_polling_error(
    app: Any, mock_video_client: MagicMock, verbose: bool
) -> None:
    """メインポーリング中エラー発生時のループ終了を検証します。"""
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            raise Exception("API error")

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=verbose,
        backlog_counts=10,
    )

    assert app.stop_event.is_set() is True


@pytest.mark.parametrize("verbose", [True, False])
def test_video_worker_polling_ng_word(
    app: Any, mock_video_client: MagicMock, verbose: bool
) -> None:
    """メインポーリング時のNGワードスキップ処理を検証します。"""
    app.config.ng_words = ["badword"]

    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "User1",
                            "channelId": "ch1",
                        },
                        "snippet": {
                            "displayMessage": "badword message",
                            "publishedAt": "2026-07-03T10:05:00Z",
                        },
                    }
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=verbose,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_polling_queue_full(
    app: Any, mock_video_client: MagicMock
) -> None:
    """メインポーリング時のキュー満杯によるスキップを検証します。"""
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "User1",
                            "channelId": "ch1",
                        },
                        "snippet": {
                            "displayMessage": "NewComment",
                            "publishedAt": "2026-07-03T10:05:00Z",
                        },
                    }
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.comment_queue = queue.Queue(maxsize=1)
    app.comment_queue.put(("Existing", "Comment"))

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 1


@patch("time.sleep")
def test_video_worker_polling_verbose_false(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
) -> None:
    """ポーリングループで、verbose=False のときの分岐を検証します。"""
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {"displayName": "User1"},
                        "snippet": {"displayMessage": "Hello"},
                    }
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=False,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 1


def test_video_worker_success_with_dataclasses(
    app: Any, mock_video_client: MagicMock
) -> None:
    """本番用のデータクラスオブジェクトをモックとして返し、キャストがバイパスされることを検証します。"""
    call_count = 0
    now = datetime.now(timezone.utc)

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # バックログコメント
            return (
                [
                    YouTubeMessage(
                        id="c1",
                        author_name="User1",
                        author_id="ch1",
                        message="Hello",
                        published_at=now,
                    )
                ],
                None,
                3000,
            )
        else:
            # ポーリングコメント
            app.stop_event.set()
            return (
                [
                    YouTubeMessage(
                        id="c2",
                        author_name="User2",
                        author_id="ch2",
                        message="World",
                        published_at=now,
                    )
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 2
