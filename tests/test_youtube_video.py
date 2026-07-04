"""YouTubeVideoClient の動作を検証するテストモジュールです。

動画情報の取得、コメントスレッドのパース、
およびコメント機能無効化時のエラーハンドリングなどの
正常系・異常系を網羅して検証します。
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from callee import Contains
from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_tts.video import YouTubeVideoClient


@pytest.fixture
def mock_client() -> Generator[
    tuple[YouTubeVideoClient, MagicMock], None, None
]:
    """認証モックとサービスモックを内包したクライアントを生成します。

    Yields:
        tuple[YouTubeVideoClient, MagicMock]: 生成されたクライアントと
            モック化されたサービスのタプルです。
    """
    creds = MagicMock()
    with patch("youtube_tts.client.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        client = YouTubeVideoClient(creds)
        yield client, mock_service


def test_get_video_details_success(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
) -> None:
    """動画の詳細情報が正常に取得できることを検証します。"""
    client, mock_service = mock_client
    # 動画詳細取得 API の正常なレスポンスをモックします。
    mock_service.videos().list().execute.return_value = {
        "items": [{"id": "vid123", "snippet": {"title": "My Video"}}]
    }

    # 取得された詳細情報が期待通りであることを検証します。
    details = client.get_video_details("vid123")
    assert details["id"] == "vid123"
    assert details["snippet"]["title"] == "My Video"


def test_get_video_details_not_found(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
) -> None:
    """動画IDが存在しない場合に RuntimeError が発生することを検証します。"""
    client, mock_service = mock_client
    # 動画が存在しない空のレスポンスをモックします。
    mock_service.videos().list().execute.return_value = {"items": []}

    # 動画が見つからない場合に例外が発生することを確認します。
    with pytest.raises(RuntimeError, match="video not found"):
        client.get_video_details("vid123")


def test_get_video_details_http_error(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """APIエラー時に例外が再スローされるか検証します。"""
    client, mock_service = mock_client
    # クォータ超過のエラー（HTTP 403）をシミュレートします。
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)

    # APIエラーが適切に再スローされ、エラーログが出力されることを検証します。
    with pytest.raises(HttpError), caplog.at_level("ERROR"):
        client.get_video_details("vid")
    assert any("本日の無料枠上限" in r.message for r in caplog.records)


def test_fetch_comment_threads_success(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
) -> None:
    """コメントが正常に取得されパースされるか検証します。"""
    client, mock_service = mock_client
    # コメントスレッド取得 API の正常なレスポンスをモックします。
    mock_service.commentThreads().list().execute.return_value = {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "id": "c1",
                        "snippet": {
                            "authorDisplayName": "Alice",
                            "textOriginal": "Nice!",
                            "publishedAt": "2026-06-21T12:00:00Z",
                            "authorChannelId": {"value": "UC_a123"},
                        },
                    }
                }
            }
        ],
        "nextPageToken": "next_token",
    }

    # コメントスレッドを取得し、期待通りにパースされるか検証します。
    items, next_token, interval = client.fetch_comment_threads("vid123")
    assert len(items) == 1
    assert items[0]["id"] == "c1"
    assert items[0]["authorDetails"]["displayName"] == "Alice"
    assert items[0]["authorDetails"]["channelId"] == "UC_a123"
    assert items[0]["snippet"]["displayMessage"] == "Nice!"
    assert next_token == "next_token"
    assert interval == 3000


def test_fetch_comment_threads_http_error(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """コメント取得時の API エラー例外が再スローされるか検証します。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    mock_service.commentThreads().list().execute.side_effect = HttpError(
        resp, content
    )

    with pytest.raises(HttpError), caplog.at_level("ERROR"):
        client.fetch_comment_threads("vid")
    assert any("本日の無料枠上限" in r.message for r in caplog.records)


def test_fetch_comment_threads_parse_error(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """不正な形式のコメントがスキップされることを検証します。"""
    client, mock_service = mock_client
    # 正常なコメントと、不正な形式のコメントをモックします。
    mock_service.commentThreads().list().execute.return_value = {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "id": "c_ok",
                        "snippet": {
                            "authorDisplayName": "OK",
                            "textOriginal": "Msg",
                        },
                    }
                }
            },
            {
                "snippet": {
                    "topLevelComment": {
                        "id": None,
                        "snippet": {
                            "authorDisplayName": "No ID",
                            "textOriginal": "Msg",
                        },
                    }
                }
            },
            "invalid_item_not_a_dict",
        ]
    }

    # パースに失敗した不正コメントが無視されることを検証します。
    with caplog.at_level("WARNING"):
        items, _, _ = client.fetch_comment_threads("vid")

    assert len(items) == 1
    assert items[0]["id"] == "c_ok"
    assert any(
        "コメントのパースに失敗しました" in r.message for r in caplog.records
    )


@pytest.mark.parametrize("verbose", [False, True])
def test_get_video_details_comment_disabled(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
    verbose: bool,
) -> None:
    """コメント無効動画へのアクセスログの出力を検証します。"""
    client, mock_service = mock_client
    client.verbose = verbose

    # コメント機能が無効（commentsDisabled）な HTTP 403 エラーをモックします。
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "commentsDisabled"}]}}'
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)

    # ロガーの出力が適切に行われていることを検証します。
    with (
        patch("youtube_tts.client.logger") as mock_logger,
        pytest.raises(HttpError),
    ):
        client.get_video_details("vid")

    mock_logger.error.assert_any_call(Contains("コメント機能がオフ"))
    mock_logger.debug.assert_called_once_with(Contains("(エラー詳細:"))


def test_handle_api_error_decode_failure(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
) -> None:
    """APIエラー時にデコード失敗しても例外なく処理されるか検証します。"""
    client, mock_service = mock_client
    # レスポンスのデコードが失敗するよう、不正な UTF-8 バイトをモックします。
    resp = Response({"status": 500, "reason": "Internal Server Error"})
    content = b"\xff\xff\xff"  # 不正なUTF-8バイト
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)

    # 例外なく APIエラーが処理されて再スローされることを検証します。
    with pytest.raises(HttpError):
        client.get_video_details("vid")


def test_handle_api_error_no_content(
    mock_client: tuple[YouTubeVideoClient, MagicMock],
) -> None:
    """エラーの content が無くても安全に処理されるか検証します。"""
    client, mock_service = mock_client

    # エラーレスポンスに content 属性が存在しない状況をモックします。
    resp = Response({"status": 500, "reason": "Internal Server Error"})
    mock_e = HttpError(resp, b"")
    if hasattr(mock_e, "content"):
        del mock_e.content

    mock_service.videos().list().execute.side_effect = mock_e

    # content が存在しない場合でも安全に APIエラーが処理されることを確認します。
    with pytest.raises(HttpError):
        client.get_video_details("vid")
