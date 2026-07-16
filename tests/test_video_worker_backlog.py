"""video_worker のバックログ取得フェーズを検証するテストモジュールです。"""

from __future__ import annotations

import queue
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize(
    "backlog_counts, side_effect, verbose, expect_debug, expect_qsize",
    [
        (0, ([], None, 3000), True, False, 0),
        (-1, ([], None, 3000), True, False, 0),
        (10, ([], None, 3000), True, False, 0),
        (10, Exception("API error"), True, False, 0),
        (10, Exception("バックログ取得エラー"), False, True, 0),
        (10, "error_then_success", False, False, 0),
    ],
)
def test_video_worker_backlog_cases(
    app: Any,
    mock_video_client: MagicMock,
    backlog_counts: int,
    side_effect: Any,
    verbose: bool,
    expect_debug: bool,
    expect_qsize: int,
) -> None:
    """初期バックログ取得の各種ケースを検証します。"""
    call_count = 0

    def fetch_side_effect(
        video_id: str,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> tuple[list[Any], str | None, int]:
        nonlocal call_count
        call_count += 1
        if side_effect == "error_then_success":
            if call_count == 1:
                raise Exception("バックログ取得エラー")
            else:
                app.stop_event.set()
                return [], None, 3000
        elif isinstance(side_effect, Exception):
            if call_count == 1:
                raise side_effect
            else:
                app.stop_event.set()
                return [], None, 3000
        else:
            app.stop_event.set()
            return side_effect

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    with patch.object(app.logger, "debug") as mock_debug:
        app.video_worker(
            video_client=mock_video_client,
            video_id="video_123",
            chat_interval=0.01,
            verbose=verbose,
            backlog_counts=backlog_counts,
        )

    if expect_debug:
        mock_debug.assert_called()
    assert app.comment_queue.qsize() == expect_qsize


@pytest.mark.parametrize("verbose", [True, False])
def test_video_worker_backlog_ng_word(
    app: Any,
    mock_video_client: MagicMock,
    verbose: bool,
) -> None:
    """初期バックログ内の NG ワード
    スキップ処理を検証します。
    """
    mock_video_client.fetch_comment_threads.return_value = (
        [
            {
                "id": "c1",
                "authorDetails": {
                    "displayName": "User1",
                    "channelId": "ch1",
                },
                "snippet": {
                    "displayMessage": ("badword message"),
                    "publishedAt": ("2026-07-03T10:00:00Z"),
                },
            }
        ],
        None,
        3000,
    )
    app.config.ng_words = ["badword"]
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=verbose,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


@pytest.mark.parametrize("verbose", [True, False])
@patch("time.sleep")
def test_video_worker_backlog_ng_word_actual(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
    verbose: bool,
) -> None:
    """バックログ取得時に NG ワード分岐を
    実際に通過させて検証します。
    """
    app.config.ng_words = ["badword"]
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクトです。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "User1",
                        },
                        "snippet": {
                            "displayMessage": ("badword message"),
                        },
                    }
                ],
                None,
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=verbose,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


@pytest.mark.parametrize("pre_set_stop", [True, False])
def test_video_worker_backlog_queue_full(
    app: Any,
    mock_video_client: MagicMock,
    pre_set_stop: bool,
) -> None:
    """初期バックログ取得時にキューがいっぱいの場合
    スキップされるかを検証します。
    """
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクトです。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "User1",
                        },
                        "snippet": {
                            "displayMessage": ("Hello"),
                        },
                    }
                ],
                None,
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.comment_queue = queue.Queue(maxsize=1)
    app.comment_queue.put(("Existing", "Comment"))
    if pre_set_stop:
        app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 1


def test_video_worker_backlog_remaining_exhausted(
    app: Any, mock_video_client: MagicMock
) -> None:
    """バックログ取得の remaining_to_fetch が
    0 になって break するかを検証します。

    backlog_counts=1 のとき、1 件取得後に
    remaining_to_fetch が 0 になり、
    次のループ先頭で break が実行されることを
    検証します。
    """
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクトです。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # ページトークンを持たせてループ途中での
            # break を防ぎます。
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "U1",
                        },
                        "snippet": {
                            "displayMessage": ("Hello"),
                        },
                    }
                ],
                "next_token",
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        backlog_counts=1,
    )

    assert app.comment_queue.qsize() == 1


@patch("time.sleep")
def test_video_worker_backlog_unlimited_remaining(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
) -> None:
    """backlog_counts=-1 のとき、remaining_to_fetch
    が None になることを検証します。
    """
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクトです。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # ページトークンなし → break
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "U1",
                        },
                        "snippet": {
                            "displayMessage": ("Hello"),
                        },
                    }
                ],
                None,
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        backlog_counts=-1,
    )

    assert app.comment_queue.qsize() == 1
