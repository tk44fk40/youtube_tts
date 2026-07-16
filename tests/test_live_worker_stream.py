"""live_worker のストリーム状態チェック・データクラステストモジュールです。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from youtube_tts.models import (
    QuotaInfo,
    VideoDetails,
    YouTubeMessage,
)


def test_live_worker_stream_inactive(
    app: Any, mock_live_client: MagicMock
) -> None:
    """配信がアクティブではない（終了した）場合に
    ループが終了するかを検証します。
    """
    mock_live_client.fetch_chat_messages.return_value = (
        [],
        "next_token",
        1000,
    )
    mock_live_client.check_stream_active.return_value = False

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.01,
        stream_check_interval=0.01,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


@patch("time.sleep")
def test_live_worker_stream_active_then_stop(
    mock_sleep: Any,
    app: Any,
    mock_live_client: MagicMock,
) -> None:
    """ストリームがアクティブな場合に
    last_stream_check_time が
    更新されるかを検証します。
    """
    mock_live_client.check_stream_active.return_value = True

    fetch_call_count = 0

    def fetch_side_effect(*args, **kwargs):
        """フェッチのサイドエフェクトです。"""
        nonlocal fetch_call_count
        fetch_call_count += 1
        if fetch_call_count >= 2:
            app.stop_event.set()
        return [], "token", 100

    mock_live_client.fetch_chat_messages.side_effect = fetch_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        verbose=True,
        chat_interval=0.0,
        stream_check_interval=0.0,
        quota_interval=100.0,
    )

    assert mock_live_client.check_stream_active.called


@patch("youtube_tts.workers.live.get_quota_info")
def test_live_worker_success_with_dataclasses(
    mock_quota_info: Any,
    app: Any,
    mock_live_client: MagicMock,
) -> None:
    """本番用のデータクラスオブジェクトをモックとして
    返し、キャストがバイパスされることを検証します。
    """
    mock_live_client.get_video_details.return_value = VideoDetails(
        video_id="video_123",
        channel_id="my_channel_123",
        title="My Title",
    )

    now = datetime.now(timezone.utc)
    mock_live_client.fetch_chat_messages.return_value = (
        [
            YouTubeMessage(
                id="msg1",
                author_name="User1",
                author_id="ch-user1",
                message="Hello",
                published_at=now,
            )
        ],
        "next_token",
        1000,
    )

    def quota_side_effect(*args):
        app.stop_event.set()
        return QuotaInfo(used=1000, limit=10000)

    mock_quota_info.side_effect = quota_side_effect

    app.live_worker(
        live_client=mock_live_client,
        video_id="video_123",
        creds=MagicMock(),
        quota_check=True,
        quota_talk=True,
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=0.01,
        project_id="proj123",
        verbose=True,
    )

    assert mock_quota_info.call_count >= 1
