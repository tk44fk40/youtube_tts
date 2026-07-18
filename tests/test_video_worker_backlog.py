"""video_worker のバックログ取得処理に関するテストモジュールです。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts.workers.video import video_worker


@pytest.mark.parametrize(
    "backlog_counts, side_effect, verbose, expect_debug, expect_qsize",
    [
        pytest.param(
            0,
            ([], None, 3000),
            True,
            False,
            0,
            id="zero_counts",
        ),
        pytest.param(
            -1,
            ([], None, 3000),
            True,
            False,
            0,
            id="negative_counts",
        ),
        pytest.param(
            10,
            ([], None, 3000),
            True,
            False,
            0,
            id="empty_response",
        ),
        pytest.param(
            10,
            Exception("API error"),
            True,
            False,
            0,
            id="api_error_verbose",
        ),
        pytest.param(
            10,
            Exception("バックログ取得エラー"),
            False,
            True,
            0,
            id="api_error_non_verbose",
        ),
        pytest.param(
            10,
            "error_then_success",
            False,
            False,
            0,
            id="error_then_success",
        ),
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
        video_worker(
            app=app,
            video_client=mock_video_client,
            video_id="video_123",
            chat_interval=0.01,
            verbose=verbose,
            backlog_counts=backlog_counts,
        )

    if expect_debug:
        mock_debug.assert_called()
    assert app.speech_queue.qsize() == expect_qsize


@pytest.mark.parametrize(
    "verbose, pre_set_stop",
    [
        (True, True),
        (False, True),
        (True, False),
        (False, False),
    ],
)
@patch("time.sleep")
def test_video_worker_backlog_ng_words(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
    verbose: bool,
    pre_set_stop: bool,
) -> None:
    """NGワードが含まれるコメントがスキップされることを検証します。"""
    app.config.ng_words = ["badword"]
    if pre_set_stop:
        app.stop_event.set()

    comments_list = [
        [
            {
                "id": "c1",
                "authorDetails": {"displayName": "User1"},
                "snippet": {"displayMessage": "badword message"},
            }
        ],
        [],
    ]

    call_count = 0

    def fetch_side_effect(
        *args: Any, **kwargs: Any
    ) -> tuple[list[Any], str | None, int]:
        nonlocal call_count
        idx = call_count
        call_count += 1
        if idx >= len(comments_list):
            app.stop_event.set()
            return [], None, 3000
        if idx == len(comments_list) - 1:
            app.stop_event.set()
        return comments_list[idx], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    video_worker(
        app=app,
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=verbose,
        backlog_counts=10,
    )

    assert app.speech_queue.qsize() == 0


@pytest.mark.parametrize("pre_set_stop", [True, False])
@patch("time.sleep")
def test_video_worker_backlog_queue_full(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
    pre_set_stop: bool,
) -> None:
    """キューが満杯の際にコメント追加がスキップされることを検証します。"""
    from youtube_tts.models import SpeechItem
    from youtube_tts.queue import SpeechQueue

    app.speech_queue = SpeechQueue(maxsize=1)
    app.speech_queue.put(SpeechItem("Existing", "Comment", 15))

    if pre_set_stop:
        app.stop_event.set()

    comments_list = [
        [
            {
                "id": "c1",
                "authorDetails": {"displayName": "User1"},
                "snippet": {"displayMessage": "Hello"},
            }
        ],
        [],
    ]

    call_count = 0

    def fetch_side_effect(
        *args: Any, **kwargs: Any
    ) -> tuple[list[Any], str | None, int]:
        nonlocal call_count
        idx = call_count
        call_count += 1
        if idx >= len(comments_list):
            app.stop_event.set()
            return [], None, 3000
        if idx == len(comments_list) - 1:
            app.stop_event.set()
        return comments_list[idx], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    video_worker(
        app=app,
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=False,
        backlog_counts=10,
    )

    assert app.speech_queue.qsize() == 1


@patch("time.sleep")
def test_video_worker_backlog_item_limit(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
) -> None:
    """指定した backlog_counts 件数で取得が停止することを検証します。"""
    comments_list = [
        [
            {
                "id": "c1",
                "authorDetails": {"displayName": "U1"},
                "snippet": {"displayMessage": "Hello"},
            }
        ],
        [],
    ]

    call_count = 0

    def fetch_side_effect(
        *args: Any, **kwargs: Any
    ) -> tuple[list[Any], str | None, int]:
        nonlocal call_count
        idx = call_count
        call_count += 1
        if idx >= len(comments_list):
            app.stop_event.set()
            return [], None, 3000
        return comments_list[idx], "next_token" if idx == 0 else None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    video_worker(
        app=app,
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=False,
        backlog_counts=1,
    )

    assert app.speech_queue.qsize() == 1


@patch("time.sleep")
def test_video_worker_backlog_unlimited(
    mock_sleep: Any,
    app: Any,
    mock_video_client: MagicMock,
) -> None:
    """backlog_counts=-1 の場合に無制限に取得し、
    トークンがなくなるまで動作することを検証します。"""
    comments_list = [
        [
            {
                "id": "c1",
                "authorDetails": {"displayName": "U1"},
                "snippet": {"displayMessage": "Hello"},
            }
        ],
        [],
    ]

    call_count = 0

    def fetch_side_effect(
        *args: Any, **kwargs: Any
    ) -> tuple[list[Any], str | None, int]:
        nonlocal call_count
        idx = call_count
        call_count += 1
        if idx >= len(comments_list):
            app.stop_event.set()
            return [], None, 3000
        if idx == len(comments_list) - 1:
            app.stop_event.set()
        return comments_list[idx], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    video_worker(
        app=app,
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=False,
        backlog_counts=-1,
    )

    assert app.speech_queue.qsize() == 1
