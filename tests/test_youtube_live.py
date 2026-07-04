"""YouTubeLiveChatClient の各メソッドおよび
共通 API エラー処理を検証するテストモジュール。

本モジュールでは、ライブ配信のチャットID取得、
配信ステータスチェック、メッセージフェッチ、
およびクォータ上限超過時の例外ハンドリングなどの
正常系・異常系を網羅しています。
"""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_tts.live import YouTubeLiveChatClient


@pytest.fixture
def mock_client():
    """認証モックとサービスモックを内包したクライアントを生成します。"""
    creds = MagicMock()
    with patch("youtube_tts.client.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        client = YouTubeLiveChatClient(creds)
        yield client, mock_service


def test_get_my_channel_id_success(mock_client):
    """チャンネルIDが正常に取得され、キャッシュされることを検証。"""
    client, mock_service = mock_client
    mock_list = mock_service.channels().list
    mock_list.return_value.execute.return_value = {
        "items": [{"id": "my_channel_id_123"}]
    }

    assert client.get_my_channel_id() == "my_channel_id_123"
    assert client.get_my_channel_id() == "my_channel_id_123"  # キャッシュ
    mock_list.assert_called_once_with(part="id", mine=True)


def test_get_my_channel_id_failure(mock_client, caplog):
    """APIエラー発生時に警告ログが出力され None が返ることを検証。"""
    client, mock_service = mock_client
    mock_list = mock_service.channels().list
    mock_list.return_value.execute.side_effect = Exception("API error")

    with caplog.at_level("WARNING"):
        assert client.get_my_channel_id() is None
    assert any(
        "自分のチャンネル ID の取得に失敗しました" in r.message
        for r in caplog.records
    )


def test_get_my_channel_id_empty_items(mock_client):
    """APIレスポンスが空の場合に None が返ることを検証。"""
    client, mock_service = mock_client
    mock_service.channels().list().execute.return_value = {"items": []}
    assert client.get_my_channel_id() is None


def test_get_live_chat_id_success(mock_client):
    """動画IDからライブチャットIDを正常に取得できることを検証。"""
    client, mock_service = mock_client
    mock_service.videos().list().execute.return_value = {
        "items": [{"liveStreamingDetails": {"activeLiveChatId": "chat_id_123"}}]
    }
    assert client.get_live_chat_id("vid") == "chat_id_123"


def test_get_live_chat_id_not_found(mock_client):
    """動画自体が存在しない場合に RuntimeError が発生することを検証。"""
    client, mock_service = mock_client
    mock_service.videos().list().execute.return_value = {"items": []}

    with pytest.raises(RuntimeError, match="video not found"):
        client.get_live_chat_id("vid")


def test_get_live_chat_id_missing_active_chat(mock_client):
    """activeLiveChatId が無い場合にRuntimeError が発生することを検証。"""
    client, mock_service = mock_client
    mock_service.videos().list().execute.return_value = {"items": [{}]}

    with pytest.raises(RuntimeError, match="activeLiveChatId not found"):
        client.get_live_chat_id("vid")


def test_get_live_chat_id_http_error(mock_client):
    """APIエラー時に例外がそのまま再スローされることを検証。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    mock_service.videos().list().execute.side_effect = HttpError(resp, b"Err")

    with pytest.raises(HttpError):
        client.get_live_chat_id("vid")


def test_get_current_live_video_id_success(mock_client):
    """配信中のアクティブなブロードキャストIDを検出できることを検証。"""
    client, mock_service = mock_client
    mock_service.liveBroadcasts().list().execute.return_value = {
        "items": [
            {"status": {"lifeCycleStatus": "complete"}, "id": "old_vid"},
            {"status": {"lifeCycleStatus": "live"}, "id": "live_vid"},
        ]
    }
    vid, chat_url = client.get_current_live_video_id()
    assert vid == "live_vid"
    assert "v=live_vid" in chat_url


def test_get_current_live_video_id_no_broadcast(mock_client):
    """アクティブな配信がない場合に RuntimeError が発生することを検証。"""
    client, mock_service = mock_client
    mock_service.liveBroadcasts().list().execute.return_value = {"items": []}

    with pytest.raises(RuntimeError, match="No live broadcast found"):
        client.get_current_live_video_id()


def test_get_current_live_video_id_http_error(mock_client):
    """配信一覧取得時の API エラー例外が再スローされることを検証。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    mock_service.liveBroadcasts().list().execute.side_effect = HttpError(
        resp, b"Err"
    )

    with pytest.raises(HttpError):
        client.get_current_live_video_id()


def test_fetch_chat_messages_success(mock_client):
    """チャットメッセージおよびポーリング情報の取得を検証。"""
    client, mock_service = mock_client
    mock_service.liveChatMessages().list().execute.return_value = {
        "items": [{"id": "msg1", "snippet": {"displayMessage": "hello"}}],
        "nextPageToken": "next_token",
        "pollingIntervalMillis": 4000,
    }
    items, token, interval = client.fetch_chat_messages("chat_id")
    assert items[0]["id"] == "msg1"
    assert token == "next_token"
    assert interval == 4000


def test_fetch_chat_messages_quota_exceeded(mock_client):
    """メッセージ取得時のクォータ超過エラー（HTTP 403）を検証。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    mock_service.liveChatMessages().list().execute.side_effect = HttpError(
        resp, content
    )

    with pytest.raises(HttpError):
        client.fetch_chat_messages("chat_id")


def test_check_stream_active_all_cases(mock_client, caplog):
    """配信アクティブチェックの各ステータス（真偽値）の返却を検証。"""
    client, mock_service = mock_client

    # 1. アクティブ
    mock_service.videos().list().execute.return_value = {
        "items": [{"liveStreamingDetails": {"activeLiveChatId": "chat_id"}}]
    }
    assert client.check_stream_active("vid") is True

    # 2. 動画なし
    mock_service.videos().list().execute.return_value = {"items": []}
    assert client.check_stream_active("vid") is False

    # 3. チャットIDなし
    mock_service.videos().list().execute.return_value = {"items": [{}]}
    assert client.check_stream_active("vid") is False

    # 4. APIエラー時（継続優先で True）
    resp = Response({"status": 500, "reason": "Error"})
    mock_service.videos().list().execute.side_effect = HttpError(resp, b"Err")
    with caplog.at_level("WARNING"):
        assert client.check_stream_active("vid") is True
    assert any(
        "Error checking video status" in r.message for r in caplog.records
    )


def test_handle_quota_error(mock_client, caplog):
    """共通ハンドラ経由でクォータ超過の日本語エラーログが出るか検証。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)

    with pytest.raises(HttpError), caplog.at_level("ERROR"):
        client.get_live_chat_id("vid")

    assert any(
        "本日の無料枠上限（クォータ）を超過しました" in r.message
        for r in caplog.records
    )
