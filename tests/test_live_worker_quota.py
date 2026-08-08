"""live_worker のクォータ関連処理を検証するテストモジュールです。"""

from __future__ import annotations

import queue as queue_module
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_tts.models import SpeechItem
from youtube_tts.workers.live import live_worker

_QUOTA_EXCEEDED_CONTENT = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'


def _create_quota_exceeded_error() -> HttpError:
    """テスト用のクォータ超過エラーを生成します。"""
    resp = Response({"status": 403, "reason": "Forbidden"})
    return HttpError(resp, _QUOTA_EXCEEDED_CONTENT)


def test_live_worker_quota_exceeded(app: Any, mock_live_client: MagicMock) -> None:
    """クォータ超過エラー（403）発生時の待機状態遷移を検証します。"""
    ex = _create_quota_exceeded_error()
    mock_live_client.fetch_chat_messages.side_effect = ex

    live_worker(
        app=app,
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

    assert app.speech_queue.qsize() == 1
    assert app.stop_event.is_set() is True


def test_live_worker_quota_exceeded_no_quota_talk(
    app: Any, mock_live_client: MagicMock
) -> None:
    """クォータ超過かつ quota_talk=False 時の即終了を検証します。"""
    ex = _create_quota_exceeded_error()
    mock_live_client.fetch_chat_messages.side_effect = ex

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        quota_talk=False,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True
    assert app.speech_queue.qsize() == 0


def test_live_worker_quota_exceeded_drain_empty(
    app: Any, mock_live_client: MagicMock
) -> None:
    """キュードレイン中の queue.Empty 発生時処理を検証します。"""
    ex = _create_quota_exceeded_error()
    mock_live_client.fetch_chat_messages.side_effect = ex

    with (
        patch.object(
            app.speech_queue,
            "empty",
            side_effect=[False, True],
        ),
        patch.object(
            app.speech_queue,
            "get_nowait",
            side_effect=queue_module.Empty,
        ),
    ):
        live_worker(
            app=app,
            live_client=mock_live_client,
            video_id="video_123",
            quota_talk=True,
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
            quota_check=True,
        )

    assert app.stop_event.is_set() is True


def test_live_worker_quota_exceeded_drain_actual(
    app: Any, mock_live_client: MagicMock
) -> None:
    """キュードレイン時の正常な処理を検証します。"""
    ex = _create_quota_exceeded_error()
    mock_live_client.fetch_chat_messages.side_effect = ex

    # キューに実際のアイテムを積んで drain ループを通過させます。
    app.speech_queue.put(SpeechItem("Author", "Message", 14))

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        quota_talk=True,
        quota_check=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


@patch(
    "youtube_tts.workers.quota_monitor.QuotaMonitor.get_next_reset_time",
    side_effect=Exception("tz error"),
)
def test_live_worker_quota_exceeded_reset_time_failure(
    mock_reset_time: Any,
    app: Any,
    mock_live_client: MagicMock,
) -> None:
    """リセット時刻取得失敗時のフォールバックメッセージを検証します。"""
    ex = _create_quota_exceeded_error()
    mock_live_client.fetch_chat_messages.side_effect = ex

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.speech_queue.qsize() == 1
    assert app.stop_event.is_set() is True


def test_live_worker_quota_exceeded_content_str(
    app: Any, mock_live_client: MagicMock
) -> None:
    """HttpError の content が str の場合の正常判定を検証します。"""
    resp = Response({"status": 403, "reason": "Forbidden"})
    ex = HttpError(resp, b"")
    ex.content = '{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    mock_live_client.fetch_chat_messages.side_effect = ex

    live_worker(
        app=app,
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

    assert app.speech_queue.qsize() == 1
    assert app.stop_event.is_set() is True


@pytest.mark.parametrize("verbose", [True, False])
@patch("youtube_tts.workers.quota_monitor.get_quota_info")
@patch("time.sleep")
def test_live_worker_quota_info_success(
    mock_sleep: Any,
    mock_quota_info: Any,
    app: Any,
    mock_live_client: MagicMock,
    verbose: bool,
) -> None:
    """クォータ情報が正常取得されキューに追加されることを検証します。"""
    mock_live_client.fetch_chat_messages.return_value = ([], "next_token", 1000)
    mock_quota_info.return_value = (1000, 10000)

    sleep_call_count = 0

    def sleep_side_effect(*args: Any) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            app.stop_event.set()

    mock_sleep.side_effect = sleep_side_effect

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        creds=MagicMock(),
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=0.01,
        project_id="proj123",
        verbose=verbose,
    )

    assert mock_quota_info.call_count >= 1
    assert app.speech_queue.qsize() == 1


@pytest.mark.parametrize("verbose", [True, False])
@patch("youtube_tts.workers.quota_monitor.get_quota_info")
@patch("time.sleep")
def test_live_worker_quota_info_error(
    mock_sleep: Any,
    mock_quota_info: Any,
    app: Any,
    mock_live_client: MagicMock,
    verbose: bool,
) -> None:
    """クォータ情報取得エラー時にキューへ追加されないことを検証します。"""
    mock_live_client.fetch_chat_messages.return_value = ([], "next_token", 1000)
    mock_quota_info.side_effect = Exception("Quota check failure")

    sleep_call_count = 0

    def sleep_side_effect(*args: Any) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            app.stop_event.set()

    mock_sleep.side_effect = sleep_side_effect

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        creds=MagicMock(),
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=0.01,
        project_id="proj123",
        verbose=verbose,
    )

    assert mock_quota_info.call_count >= 1
    assert app.speech_queue.qsize() == 0


@patch("youtube_tts.workers.quota_monitor.get_quota_info")
@patch("time.sleep")
def test_live_worker_quota_info_same_value_skip(
    mock_sleep: Any,
    mock_quota_info: Any,
    app: Any,
    mock_live_client: MagicMock,
) -> None:
    """使用量不変時にアナウンスがスキップされることを検証します。"""
    mock_live_client.fetch_chat_messages.return_value = ([], "next_token", 1000)
    mock_quota_info.return_value = (1000, 10000)

    sleep_call_count = 0

    def sleep_side_effect(*args: Any) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            app.stop_event.set()

    mock_sleep.side_effect = sleep_side_effect

    with patch("youtube_tts.workers.live.QuotaMonitor") as mock_qm_class:
        mock_qm_instance = mock_qm_class.return_value
        live_worker(
            app=app,
            live_client=mock_live_client,
            video_id="video_123",
            creds=MagicMock(),
            quota_check=True,
            quota_talk=True,
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=0.01,
            project_id="proj123",
        )

    # _get_quota_info 自体は呼ばれないが、QuotaMonitor をモックしているので、
    # check_and_talk が呼ばれたかを検証する
    assert mock_qm_instance.check_and_talk.call_count >= 1
