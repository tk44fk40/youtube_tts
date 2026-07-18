"""video_worker のリアルタイム監視ポーリングフェーズを
検証するテストモジュールです。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from youtube_tts.models import YouTubeMessage
from youtube_tts.workers.video import video_worker


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

    video_worker(
        app=app,
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    # 取得したコメント数および文字数が想定通りか検証します。
    assert app.speech_queue.qsize() == 2
    assert app.speech_queue.queued_char_count == 32


@pytest.mark.parametrize(
    "ng_words, queue_maxsize, verbose, raise_error, expect_stop, expect_qsize",
    [
        ([], None, True, True, True, 0),
        ([], None, False, True, True, 0),
        (["badword"], None, True, False, False, 0),
        (["badword"], None, False, False, False, 0),
        ([], 1, True, False, False, 1),
        ([], None, False, False, False, 1),
    ],
)
def test_video_worker_polling_cases(
    app: Any,
    mock_video_client: MagicMock,
    ng_words: list[str],
    queue_maxsize: int | None,
    verbose: bool,
    raise_error: bool,
    expect_stop: bool,
    expect_qsize: int,
) -> None:
    """メインポーリング時の各種ケースを検証します。"""
    app.config.ng_words = ng_words
    if queue_maxsize is not None:
        from youtube_tts.models import SpeechItem
        from youtube_tts.queue import SpeechQueue

        app.speech_queue = SpeechQueue(maxsize=queue_maxsize)
        if queue_maxsize == 1:
            app.speech_queue.put(SpeechItem("Existing", "Comment", 15))

    call_count = 0

    def fetch_side_effect(
        video_id: str,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> tuple[list[dict[str, Any]], str | None, int]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            if raise_error:
                raise Exception("API error")
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
                            "displayMessage": (
                                "badword message" if ng_words else "NewComment"
                            ),
                            "publishedAt": "2026-07-03T10:05:00Z",
                        },
                    }
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    video_worker(
        app=app,
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=verbose,
        backlog_counts=10,
    )

    if expect_stop:
        assert app.stop_event.is_set() is True
    assert app.speech_queue.qsize() == expect_qsize


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

    video_worker(
        app=app,
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.speech_queue.qsize() == 2
