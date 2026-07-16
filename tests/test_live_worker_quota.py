"""live_worker のクォータ関連処理を検証するテストモジュールです。"""

from __future__ import annotations

import queue as queue_module
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

_QUOTA_EXCEEDED_CONTENT = (
    b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
)


def _create_quota_exceeded_error() -> HttpError:
    """テスト用のクォータ超過エラーを生成します。

    Returns:
        HttpError: クォータ超過の 403 エラーです。
    """
    resp = Response({"status": 403, "reason": "Forbidden"})
    return HttpError(resp, _QUOTA_EXCEEDED_CONTENT)


def test_live_worker_quota_exceeded(
    app: Any, mock_live_client: MagicMock
) -> None:
    """クォータ超過エラー（403）発生時に、
    適切に待機状態へ遷移するかを検証します。
    """
    ex = _create_quota_exceeded_error()
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


def test_live_worker_quota_exceeded_no_quota_talk(
    app: Any, mock_live_client: MagicMock
) -> None:
    """クォータ超過でも quota_talk=False の場合に
    即終了するかを検証します。
    """
    ex = _create_quota_exceeded_error()
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


def test_live_worker_quota_exceeded_drain_empty(
    app: Any, mock_live_client: MagicMock
) -> None:
    """キュードレイン中に queue.Empty が
    発生した場合の処理を検証します。
    """
    ex = _create_quota_exceeded_error()
    mock_live_client.fetch_chat_messages.side_effect = ex

    # empty() が最初に False を返してループに入り、
    # get_nowait が queue.Empty を発生させることで
    # except 節を通過させます。
    empty_call_count = 0

    def mock_empty():
        """empty() のモックです。"""
        nonlocal empty_call_count
        empty_call_count += 1
        return empty_call_count != 1

    with (
        patch.object(
            app.comment_queue,
            "empty",
            side_effect=mock_empty,
        ),
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


def test_live_worker_quota_exceeded_drain_actual(
    app: Any, mock_live_client: MagicMock
) -> None:
    """キュードレイン時の正常な処理を検証します。

    get_nowait が成功して task_done が
    呼ばれること、またキューに実際のアイテムを積んで
    正常なドレインパスを通過することを確認します。
    """
    ex = _create_quota_exceeded_error()
    mock_live_client.fetch_chat_messages.side_effect = ex

    # キューに実際のアイテムを積んで
    # drain ループを通過させます。
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


@patch(
    "youtube_tts.workers.live.get_next_quota_reset_time",
    side_effect=Exception("tz error"),
)
def test_live_worker_quota_exceeded_reset_time_failure(
    mock_reset_time: Any,
    app: Any,
    mock_live_client: MagicMock,
) -> None:
    """リセット時刻取得に失敗した場合の
    フォールバックメッセージを検証します。
    """
    ex = _create_quota_exceeded_error()
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


def test_live_worker_quota_exceeded_content_str(
    app: Any, mock_live_client: MagicMock
) -> None:
    """HttpError の content が str の場合でも
    正しく判定されることを検証します。
    """
    resp = Response({"status": 403, "reason": "Forbidden"})
    ex = HttpError(resp, b"")
    # 例外生成後に content 属性を
    # 文字列に差し替えます。
    ex.content = '{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
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


@pytest.mark.parametrize(
    "quota_info_side_effect, last_spoken_used, verbose, expected_qsize",
    [
        ((1000, 10000), None, True, 1),
        (Exception("Quota check failure"), None, True, 0),
        ((1000, 10000), None, False, 1),
        ((1000, 10000), 1000, None, 0),
        (Exception("quota error"), None, False, 0),
    ],
)
@patch("youtube_tts.workers.live.get_quota_info")
@patch("time.sleep")
def test_live_worker_quota_info_cases(
    mock_sleep: Any,
    mock_quota_info: Any,
    app: Any,
    mock_live_client: MagicMock,
    quota_info_side_effect: Any,
    last_spoken_used: int | None,
    verbose: bool | None,
    expected_qsize: int,
) -> None:
    """クォータ情報取得時の各種処理を検証します。"""
    mock_live_client.fetch_chat_messages.return_value = (
        [],
        "next_token",
        1000,
    )

    if isinstance(quota_info_side_effect, Exception):
        mock_quota_info.side_effect = quota_info_side_effect
    else:
        mock_quota_info.return_value = quota_info_side_effect

    if last_spoken_used is not None:
        app.last_spoken_used = last_spoken_used

    sleep_call_count = 0

    def sleep_side_effect(*args: Any) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            app.stop_event.set()

    mock_sleep.side_effect = sleep_side_effect

    kwargs: dict[str, Any] = {
        "live_client": mock_live_client,
        "video_id": "video_123",
        "creds": MagicMock(),
        "quota_check": True,
        "quota_talk": True,
        "chat_interval": 0.01,
        "stream_check_interval": 100.0,
        "quota_interval": 0.01,
        "project_id": "proj123",
    }
    if verbose is not None:
        kwargs["verbose"] = verbose

    app.live_worker(**kwargs)

    assert mock_quota_info.call_count >= 1
    assert app.comment_queue.qsize() == expected_qsize


def test_format_reset_time_for_speech_direct(
    app: Any,
) -> None:
    """app._format_reset_time_for_speech の
    直接呼び出しをテストします。
    """
    now_local = datetime.now().astimezone()

    # 今日の場合のテストです。
    reset_today = now_local.replace(hour=23, minute=30)
    res = app._format_reset_time_for_speech(reset_today)
    assert "今日" in res
    assert "23時30分" in res

    # 明日の場合のテストです。
    reset_tomorrow = (now_local + timedelta(days=1)).replace(hour=5, minute=0)
    res = app._format_reset_time_for_speech(reset_tomorrow)
    assert "明日" in res
    assert "5時" in res

    # それ以外の日の場合のテストです。
    reset_other = (now_local + timedelta(days=3)).replace(hour=12, minute=0)
    res = app._format_reset_time_for_speech(reset_other)
    assert f"{reset_other.month}月{reset_other.day}日" in res
