"""YouTubeVideoClient の動画詳細および
コメント取得機能を検証するテストモジュール。

動画情報の取得、コメントスレッドのパース、
およびコメント機能無効化時のエラーハンドリングなどの
正常系・異常系を網羅しています。
"""

from unittest.mock import MagicMock, patch

import pytest
from callee import Contains
from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_tts.video import YouTubeVideoClient


@pytest.fixture
def mock_client():
    """認証モックとサービスモックを内包したクライアントを生成します。"""
    creds = MagicMock()
    with patch("youtube_tts.client.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        client = YouTubeVideoClient(creds)
        yield client, mock_service


def test_get_video_details_success(mock_client):
    """動画の詳細情報が正常に取得できることを検証。"""
    client, mock_service = mock_client
    mock_service.videos().list().execute.return_value = {
        "items": [{"id": "vid123", "snippet": {"title": "My Video"}}]
    }

    details = client.get_video_details("vid123")
    assert details["id"] == "vid123"
    assert details["snippet"]["title"] == "My Video"


def test_get_video_details_not_found(mock_client):
    """動画IDが存在しない場合に RuntimeError が発生することを検証。"""
    client, mock_service = mock_client
    mock_service.videos().list().execute.return_value = {"items": []}

    with pytest.raises(RuntimeError, match="video not found"):
        client.get_video_details("vid123")


def test_get_video_details_http_error(mock_client, caplog):
    """APIエラー発生時にクォータ超過ログが出力され例外が再スローされるか。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)

    with pytest.raises(HttpError), caplog.at_level("ERROR"):
        client.get_video_details("vid")
    assert any("本日の無料枠上限" in r.message for r in caplog.records)


def test_fetch_comment_threads_success(mock_client):
    """コメントが正常に取得されライブチャット形式にパースされるか。"""
    client, mock_service = mock_client
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

    items, next_token, interval = client.fetch_comment_threads("vid123")
    assert len(items) == 1
    assert items[0]["id"] == "c1"
    assert items[0]["authorDetails"]["displayName"] == "Alice"
    assert items[0]["authorDetails"]["channelId"] == "UC_a123"
    assert items[0]["snippet"]["displayMessage"] == "Nice!"
    assert next_token == "next_token"
    assert interval == 3000


def test_fetch_comment_threads_http_error(mock_client, caplog):
    """コメント取得時にAPIエラーが発生した場合に再スローされるか。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    mock_service.commentThreads().list().execute.side_effect = HttpError(resp, content)

    with pytest.raises(HttpError), caplog.at_level("ERROR"):
        client.fetch_comment_threads("vid")
    assert any("本日の無料枠上限" in r.message for r in caplog.records)


def test_fetch_comment_threads_parse_error(mock_client, caplog):
    """不正な構造のコメントが含まれる場合にスキップされることを検証。"""
    client, mock_service = mock_client
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

    with caplog.at_level("WARNING"):
        items, _, _ = client.fetch_comment_threads("vid")

    assert len(items) == 1
    assert items[0]["id"] == "c_ok"
    assert any("Failed to parse comment" in r.message for r in caplog.records)


@pytest.mark.parametrize("verbose, expect_debug", [(False, False), (True, True)])
def test_get_video_details_comment_disabled(mock_client, verbose, expect_debug):
    """コメント無効動画アクセス時、設定に応じたログが出るかを検証。"""
    client, mock_service = mock_client
    client.verbose = verbose

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "commentsDisabled"}]}}'
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)

    with (
        patch("youtube_tts.client.logger") as mock_logger,
        pytest.raises(HttpError),
    ):
        client.get_video_details("vid")

    mock_logger.error.assert_any_call(Contains("コメント機能がオフ"))
    if expect_debug:
        mock_logger.debug.assert_called_once_with(Contains("(エラー詳細:"))
    else:
        mock_logger.debug.assert_not_called()


def test_handle_api_error_decode_failure(mock_client):
    """APIエラー発生時に e.content のデコードに失敗しても安全に処理されるか。"""
    client, mock_service = mock_client
    resp = Response({"status": 500, "reason": "Internal Server Error"})
    content = b"\xff\xff\xff"  # 不正なUTF-8バイト
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)

    with pytest.raises(HttpError):
        client.get_video_details("vid")


def test_handle_api_error_no_content(mock_client):
    """APIエラーの e.content が存在しない場合でも安全に処理されるか。"""
    client, mock_service = mock_client

    resp = Response({"status": 500, "reason": "Internal Server Error"})
    mock_e = HttpError(resp, b"")
    if hasattr(mock_e, "content"):
        del mock_e.content

    mock_service.videos().list().execute.side_effect = mock_e

    with pytest.raises(HttpError):
        client.get_video_details("vid")
