"""video_worker のバックログ取得フェーズを検証するテストモジュールです。"""

from __future__ import annotations

import queue
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def test_video_worker_backlog_counts_zero(
    app: Any, mock_video_client: MagicMock
) -> None:
    """backlog_countsが0の場合に初期コメントロードが
    スキップされるかを検証します。
    """
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=0,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_counts_negative(
    app: Any, mock_video_client: MagicMock
) -> None:
    """backlog_countsが負数の場合に
    制限なしでロードできるかを検証します。
    """
    mock_video_client.fetch_comment_threads.return_value = (
        [],
        None,
        3000,
    )
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=-1,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_empty(
    app: Any, mock_video_client: MagicMock
) -> None:
    """初期バックログが空の場合に
    正しく動作するかを検証します。
    """
    mock_video_client.fetch_comment_threads.return_value = (
        [],
        None,
        3000,
    )
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_error(
    app: Any, mock_video_client: MagicMock
) -> None:
    """初期バックログ取得中にエラーが発生しても
    処理が継続するかを検証します。
    """
    mock_video_client.fetch_comment_threads.side_effect = Exception("API error")
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_error_emits_debug_log(
    app: Any, mock_video_client: MagicMock
) -> None:
    """バックログ取得エラー時に DEBUG ログが
    出ることを検証します。
    """
    mock_video_client.fetch_comment_threads.side_effect = Exception(
        "バックログ取得エラー"
    )

    with patch.object(app.logger, "debug") as mock_debug:
        app.video_worker(
            video_client=mock_video_client,
            video_id="video_123",
            chat_interval=0.01,
            verbose=False,
            backlog_counts=10,
        )

    mock_debug.assert_called()
    assert app.comment_queue.qsize() == 0


@patch("time.sleep")
def test_video_worker_backlog_error_verbose_false(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
) -> None:
    """バックログ取得エラー時に verbose=False の
    分岐を検証します。
    """
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクトです。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("バックログ取得エラー")
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=False,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


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
