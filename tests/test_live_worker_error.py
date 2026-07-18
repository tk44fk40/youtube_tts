"""live_worker のエラーハンドリングを検証するテストモジュールです。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_tts import YouTubeLiveChatClient
from youtube_tts.workers.live import live_worker


def _create_http_403_error(
    content: bytes = b"",
) -> HttpError:
    """テスト用の HTTP 403 エラーを生成します。

    Args:
        content: レスポンスボディです。

    Returns:
        HttpError: 403 エラーオブジェクトです。
    """
    resp = Response({"status": 403, "reason": "Forbidden"})
    return HttpError(resp, content)


def test_live_worker_generic_exception(
    app: Any, mock_live_client: MagicMock
) -> None:
    """一般的な例外が発生した際に、通常の
    インターバルでリトライされるかを検証します。
    """
    mock_live_client.fetch_chat_messages.side_effect = Exception(
        "Generic Network Error"
    )

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        tts_test=None,
        chat_interval=0.5,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


@pytest.mark.parametrize("verbose", [True, False])
def test_live_worker_get_video_details_failure(
    app: Any,
    verbose: bool,
) -> None:
    """動画情報取得に失敗した際に
    早期リターンするかを検証します。
    """
    mock_live_client = MagicMock(spec=YouTubeLiveChatClient)
    mock_live_client.get_video_details.side_effect = Exception("API error")

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        verbose=verbose,
    )

    assert app.stop_event.is_set() is True


@pytest.mark.parametrize("verbose", [True, False])
def test_live_worker_get_live_chat_id_failure(
    app: Any,
    mock_live_client: MagicMock,
    verbose: bool,
) -> None:
    """liveChatId 取得に失敗した際に
    早期リターンするかを検証します。
    """
    mock_live_client.get_live_chat_id.side_effect = Exception("API error")

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        verbose=verbose,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_no_content(
    app: Any, mock_live_client: MagicMock
) -> None:
    """HttpError 発生時に content が None の場合の
    クォータ判定を検証します。
    """
    ex = _create_http_403_error(b"")
    ex.content = None
    mock_live_client.fetch_chat_messages.side_effect = ex

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_decode_error(
    app: Any, mock_live_client: MagicMock
) -> None:
    """HttpError の content デコードが
    失敗した場合の処理を検証します。
    """
    ex = _create_http_403_error(b"not_quota")
    mock_content = MagicMock()
    mock_content.decode.side_effect = UnicodeDecodeError(
        "utf-8", b"", 0, 1, "reason"
    )
    ex.content = mock_content
    mock_live_client.fetch_chat_messages.side_effect = ex

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_quota_check_exception(
    app: Any, mock_live_client: MagicMock
) -> None:
    """クォータ判定中に予期しない例外が発生した場合の
    処理を検証します。

    HttpError の resp を空スペック MagicMock に
    差し替えることで、`e.resp.status` アクセス時に
    AttributeError を発生させることを検証します。
    """
    ex = _create_http_403_error(b"")
    # spec=[] を指定し、属性アクセス時に
    # AttributeError を発生させます。
    ex.resp = MagicMock(spec=[])
    mock_live_client.fetch_chat_messages.side_effect = ex

    live_worker(
        app=app,
        live_client=mock_live_client,
        video_id="video_123",
        chat_interval=0.01,
        stream_check_interval=100.0,
        quota_interval=100.0,
    )

    assert app.stop_event.is_set() is True


def test_live_worker_fetch_error_emits_debug_log(
    app: Any, mock_live_client: MagicMock
) -> None:
    """チャット取得失敗時に DEBUG ログが出ることを
    検証します。
    """
    mock_live_client.fetch_chat_messages.side_effect = Exception("error")

    with patch.object(app.logger, "debug") as mock_debug:
        live_worker(
            app=app,
            live_client=mock_live_client,
            video_id="video_123",
            verbose=False,
            chat_interval=0.01,
            stream_check_interval=100.0,
            quota_interval=100.0,
        )

    mock_debug.assert_called()
    assert app.stop_event.is_set() is True
