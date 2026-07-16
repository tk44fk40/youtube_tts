"""YouTubeLiveChatClient の動作を検証するテストモジュールです。

本モジュールでは、ライブ配信のチャットID取得、配信ステータスチェック、
メッセージフェッチ、およびクォータ上限超過時の例外ハンドリングなどの
正常系・異常系を網羅して検証します。
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_tts.live import YouTubeLiveChatClient


@pytest.fixture
def mock_client() -> Generator[
    tuple[YouTubeLiveChatClient, MagicMock], None, None
]:
    """認証モックとサービスモックを内包したクライアントを生成します。

    Yields:
        tuple[YouTubeLiveChatClient, MagicMock]: 生成されたクライアントと
            モック化されたサービスのタプルです。
    """
    creds = MagicMock()
    with patch("youtube_tts.client.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        client = YouTubeLiveChatClient(creds)
        yield client, mock_service


def test_get_my_channel_id_success(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """チャンネルIDが正常に取得され、キャッシュされることを検証します。"""
    client, mock_service = mock_client
    # チャンネルID取得 API の正常なレスポンスをモックします。
    mock_list = mock_service.channels().list
    mock_list.return_value.execute.return_value = {
        "items": [{"id": "my_channel_id_123"}]
    }

    assert client.get_my_channel_id() == "my_channel_id_123"
    # チャンネルIDがキャッシュされることを検証します。
    assert client.get_my_channel_id() == "my_channel_id_123"
    mock_list.assert_called_once_with(part="id", mine=True)


def test_get_my_channel_id_failure(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """APIエラー発生時に警告ログを出力し、Noneを返すか検証します。"""
    client, mock_service = mock_client
    # API エラー発生時の挙動をモックするために例外を設定します。
    mock_list = mock_service.channels().list
    mock_list.return_value.execute.side_effect = Exception("API error")

    with caplog.at_level("WARNING"):
        assert client.get_my_channel_id() is None
    assert any(
        "自分のチャンネル ID の取得に失敗しました" in r.message
        for r in caplog.records
    )


def test_get_my_channel_id_empty_items(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """APIレスポンスが空の場合に None が返ることを検証します。"""
    client, mock_service = mock_client
    # レスポンス内のアイテムが空となる状況をモックします。
    mock_service.channels().list().execute.return_value = {"items": []}
    # チャンネルIDの取得結果が None となることを確認します。
    assert client.get_my_channel_id() is None


def test_get_live_chat_id_success(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """動画IDからライブチャットIDを正常に取得できることを検証します。"""
    client, mock_service = mock_client
    # 動画詳細レスポンスから activeLiveChatId が返るようモックします。
    mock_service.videos().list().execute.return_value = {
        "items": [{"liveStreamingDetails": {"activeLiveChatId": "chat_id_123"}}]
    }
    # チャットIDが正常に抽出できることを確認します。
    assert client.get_live_chat_id("vid") == "chat_id_123"


def test_get_live_chat_id_not_found(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """動画が存在しない場合に RuntimeError が発生するか検証します。"""
    client, mock_service = mock_client
    # 動画自体が見つからない空のレスポンスを設定します。
    mock_service.videos().list().execute.return_value = {"items": []}

    # 動画が存在しない場合に例外が発生することを確認します。
    with pytest.raises(RuntimeError, match="video not found"):
        client.get_live_chat_id("vid")


def test_get_live_chat_id_missing_active_chat(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """チャットIDが無い場合に RuntimeError が発生するか検証します。"""
    client, mock_service = mock_client
    # activeLiveChatId のキーが無いレスポンスをモックします。
    mock_service.videos().list().execute.return_value = {"items": [{}]}

    # チャットIDが見つからない場合に例外が発生することを確認します。
    with pytest.raises(RuntimeError, match="activeLiveChatId not found"):
        client.get_live_chat_id("vid")


def test_get_live_chat_id_http_error(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """APIエラー時に例外がそのまま再スローされることを検証します。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    mock_service.videos().list().execute.side_effect = HttpError(resp, b"Err")

    with pytest.raises(HttpError):
        client.get_live_chat_id("vid")


def test_get_current_live_video_id_success(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """配信中のアクティブなブロードキャストIDを検出できることを検証します。"""
    client, mock_service = mock_client
    # 終了済みの配信と、ライブ中（live）の配信レスポンスをモックします。
    mock_service.liveBroadcasts().list().execute.return_value = {
        "items": [
            {"status": {"lifeCycleStatus": "complete"}, "id": "old_vid"},
            {"status": {"lifeCycleStatus": "live"}, "id": "live_vid"},
        ]
    }
    # 現在ライブ中の動画IDとチャットURLが正しく抽出されるか検証します。
    vid, chat_url = client.get_current_live_video_id()
    assert vid == "live_vid"
    assert "v=live_vid" in chat_url


def test_get_current_live_video_id_no_broadcast(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """配信がない場合に RuntimeError が発生するか検証します。"""
    client, mock_service = mock_client
    # ブロードキャストが見つからない空のレスポンスをモックします。
    mock_service.liveBroadcasts().list().execute.return_value = {"items": []}

    # 配信が見つからない場合に例外が発生することを確認します。
    with pytest.raises(RuntimeError, match="No live broadcast found"):
        client.get_current_live_video_id()


def test_get_current_live_video_id_http_error(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """配信一覧取得時の API エラー例外が再スローされることを検証します。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    mock_service.liveBroadcasts().list().execute.side_effect = HttpError(
        resp, b"Err"
    )

    with pytest.raises(HttpError):
        client.get_current_live_video_id()


def test_fetch_chat_messages_success(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """チャットメッセージおよびポーリング情報の取得を検証します。"""
    client, mock_service = mock_client
    # チャットメッセージ一覧取得 API の正常なレスポンスをモックします。
    mock_service.liveChatMessages().list().execute.return_value = {
        "items": [{"id": "msg1", "snippet": {"displayMessage": "hello"}}],
        "nextPageToken": "next_token",
        "pollingIntervalMillis": 4000,
    }
    # 取得されたメッセージとトークン、ポーリング間隔を検証します。
    items, token, interval = client.fetch_chat_messages("chat_id")
    assert items[0].id == "msg1"
    assert token == "next_token"
    assert interval == 4000


def test_fetch_chat_messages_quota_exceeded(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
) -> None:
    """メッセージ取得時のクォータ超過エラー（HTTP 403）を検証します。"""
    client, mock_service = mock_client
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    mock_service.liveChatMessages().list().execute.side_effect = HttpError(
        resp, content
    )

    with pytest.raises(HttpError):
        client.fetch_chat_messages("chat_id")


def test_check_stream_active_all_cases(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """配信アクティブチェックの各ステータス（真偽値）の返却を検証します。"""
    client, mock_service = mock_client

    # 1. 配信がアクティブな場合に True が返ることを検証します。
    mock_service.videos().list().execute.return_value = {
        "items": [{"liveStreamingDetails": {"activeLiveChatId": "chat_id"}}]
    }
    assert client.check_stream_active("vid") is True

    # 2. 動画が見つからない場合に False が返ることを検証します。
    mock_service.videos().list().execute.return_value = {"items": []}
    assert client.check_stream_active("vid") is False

    # 3. チャットIDが無い場合に False が返ることを検証します。
    mock_service.videos().list().execute.return_value = {"items": [{}]}
    assert client.check_stream_active("vid") is False

    # 4. APIエラー時に True を返し警告を出力することを確認します。
    resp = Response({"status": 500, "reason": "Error"})
    mock_service.videos().list().execute.side_effect = HttpError(resp, b"Err")
    with caplog.at_level("WARNING"):
        assert client.check_stream_active("vid") is True
    assert any(
        "動画ステータスの確認中にエラーが発生しました" in r.message
        for r in caplog.records
    )


def test_handle_quota_error(
    mock_client: tuple[YouTubeLiveChatClient, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """共通ハンドラ経由でクォータ超過の日本語エラーログが出るか検証します。"""
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

