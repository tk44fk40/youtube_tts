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


@pytest.mark.parametrize(
    "backlog_counts, comments_list, next_tokens, ng_words, maxsize, fill_queue, pre_set_stop, verbose, expected_qsize",
    [
        # NGワード (verbose=True, False) (事前に stop_event.set() されるケース)
        (10, [[{"id": "c1", "authorDetails": {"displayName": "User1", "channelId": "ch1"}, "snippet": {"displayMessage": "badword message", "publishedAt": "2026-07-03T10:00:00Z"}}]], [None], ["badword"], None, False, True, True, 0),
        (10, [[{"id": "c1", "authorDetails": {"displayName": "User1", "channelId": "ch1"}, "snippet": {"displayMessage": "badword message", "publishedAt": "2026-07-03T10:00:00Z"}}]], [None], ["badword"], None, False, True, False, 0),
        # NGワード (verbose=True, False) (2回目のフェッチが発生し、その中で stop_event.set() されるケース)
        (10, [[{"id": "c1", "authorDetails": {"displayName": "User1"}, "snippet": {"displayMessage": "badword message"}}], []], [None, None], ["badword"], None, False, False, True, 0),
        (10, [[{"id": "c1", "authorDetails": {"displayName": "User1"}, "snippet": {"displayMessage": "badword message"}}], []], [None, None], ["badword"], None, False, False, False, 0),
        # キュー満杯ケース
        (10, [[{"id": "c1", "authorDetails": {"displayName": "User1"}, "snippet": {"displayMessage": "Hello"}}], []], [None, None], [], 1, True, True, False, 1),
        (10, [[{"id": "c1", "authorDetails": {"displayName": "User1"}, "snippet": {"displayMessage": "Hello"}}], []], [None, None], [], 1, True, False, False, 1),
        # 件数制限によるブレイク (backlog_counts=1)
        (1, [[{"id": "c1", "authorDetails": {"displayName": "U1"}, "snippet": {"displayMessage": "Hello"}}], []], ["next_token", None], [], None, False, False, False, 1),
        # 無制限バックログ (backlog_counts=-1)
        (-1, [[{"id": "c1", "authorDetails": {"displayName": "U1"}, "snippet": {"displayMessage": "Hello"}}], []], [None, None], [], None, False, False, False, 1),
    ]
)
@patch("time.sleep")
def test_video_worker_backlog_various_cases(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
    backlog_counts: int,
    comments_list: list[list[Any]],
    next_tokens: list[str | None],
    ng_words: list[str],
    maxsize: int | None,
    fill_queue: bool,
    pre_set_stop: bool,
    verbose: bool,
    expected_qsize: int,
) -> None:
    """NGワード、キュー満杯、件数制限などによるバックログ処理の終了・スキップ挙動をまとめて検証します。"""
    call_count = 0
    app.config.ng_words = ng_words

    if maxsize is not None:
        app.comment_queue = queue.Queue(maxsize=maxsize)
    if fill_queue:
        app.comment_queue.put(("Existing", "Comment"))
    if pre_set_stop:
        app.stop_event.set()

    def fetch_side_effect(
        video_id: str,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> tuple[list[Any], str | None, int]:
        nonlocal call_count
        idx = call_count
        call_count += 1
        if idx >= len(comments_list):
            app.stop_event.set()
            return [], None, 3000

        # 最後のフェッチまたは次のトークンがない場合、stop_eventをセットして無限ループを防ぐ
        # (ただし事前にstop_eventがセットされていれば呼ばれない)
        if idx == len(comments_list) - 1:
            app.stop_event.set()

        return comments_list[idx], next_tokens[idx], 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=verbose,
        backlog_counts=backlog_counts,
    )

    assert app.comment_queue.qsize() == expected_qsize
