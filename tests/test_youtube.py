import pytest
from unittest.mock import MagicMock, patch
from googleapiclient.errors import HttpError
from httplib2 import Response
from youtube_tts import YouTubeChatClient

@pytest.fixture
def mock_creds():
    return MagicMock()

def test_extract_video_id(mock_creds):
    client = YouTubeChatClient(mock_creds)
    # 正常なケース
    assert client.extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert client.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert client.extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert client.extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # 例外が発生するケース
    with pytest.raises(RuntimeError) as excinfo:
        client.extract_video_id("https://www.youtube.com/invalid_path")
    assert "failed to extract video id" in str(excinfo.value)

@patch("youtube_tts.youtube.build")
def test_get_live_chat_id_success(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.videos().list().execute.return_value = {
        "items": [{
            "liveStreamingDetails": {
                "activeLiveChatId": "chat_id_123"
            }
        }]
    }

    client = YouTubeChatClient(mock_creds)
    assert client.get_live_chat_id("video_id_123") == "chat_id_123"

@patch("youtube_tts.youtube.build")
def test_get_live_chat_id_not_found(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.videos().list().execute.return_value = {"items": []}

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(RuntimeError) as excinfo:
        client.get_live_chat_id("invalid_id")
    assert "video not found" in str(excinfo.value)

@patch("youtube_tts.youtube.build")
def test_get_current_live_video_id_success(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.liveBroadcasts().list().execute.return_value = {
        "items": [
            {
                "status": {"lifeCycleStatus": "complete"},
                "id": "old_vid"
            },
            {
                "status": {"lifeCycleStatus": "live"},
                "id": "live_vid"
            }
        ]
    }

    client = YouTubeChatClient(mock_creds)
    vid, chat_url = client.get_current_live_video_id()
    assert vid == "live_vid"
    assert "v=live_vid" in chat_url

@patch("youtube_tts.youtube.build")
def test_get_current_live_video_id_no_broadcast(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.liveBroadcasts().list().execute.return_value = {"items": []}

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(RuntimeError) as excinfo:
        client.get_current_live_video_id()
    assert "No live broadcast found" in str(excinfo.value)

@patch("youtube_tts.youtube.build")
def test_fetch_chat_messages_success(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.liveChatMessages().list().execute.return_value = {
        "items": [{"id": "msg1", "snippet": {"displayMessage": "hello"}}],
        "nextPageToken": "next_token_456",
        "pollingIntervalMillis": 4000
    }

    client = YouTubeChatClient(mock_creds)
    items, token, interval = client.fetch_chat_messages("chat_id")
    assert items[0]["id"] == "msg1"
    assert token == "next_token_456"
    assert interval == 4000

@patch("youtube_tts.youtube.build")
def test_fetch_chat_messages_quota_exceeded(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"domain": "usageLimits", "reason": "quotaExceeded"}], "code": 403}}'
    mock_service.liveChatMessages().list().execute.side_effect = HttpError(resp, content)

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(HttpError):
        client.fetch_chat_messages("chat_id")

@patch("youtube_tts.youtube.build")
def test_get_live_chat_id_http_error(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    resp = Response({"status": 403, "reason": "Forbidden"})
    mock_service.videos().list().execute.side_effect = HttpError(resp, b"Forbidden")

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(HttpError):
        client.get_live_chat_id("vid")

@patch("youtube_tts.youtube.build")
def test_get_live_chat_id_missing_active_chat(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.videos().list().execute.return_value = {
        "items": [{
            "liveStreamingDetails": {}
        }]
    }

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(RuntimeError) as excinfo:
        client.get_live_chat_id("vid")
    assert "activeLiveChatId not found" in str(excinfo.value)

@patch("youtube_tts.youtube.build")
def test_get_current_live_video_id_http_error(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    resp = Response({"status": 403, "reason": "Forbidden"})
    mock_service.liveBroadcasts().list().execute.side_effect = HttpError(resp, b"Forbidden")

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(HttpError):
        client.get_current_live_video_id()

@patch("youtube_tts.youtube.build")
def test_check_stream_active_all_cases(mock_build, mock_creds, caplog):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    client = YouTubeChatClient(mock_creds)

    mock_service.videos().list().execute.return_value = {
        "items": [{
            "liveStreamingDetails": {"activeLiveChatId": "chat_id"}
        }]
    }
    assert client.check_stream_active("vid") is True

    mock_service.videos().list().execute.return_value = {"items": []}
    assert client.check_stream_active("vid") is False

    mock_service.videos().list().execute.return_value = {
        "items": [{
            "liveStreamingDetails": {}
        }]
    }
    assert client.check_stream_active("vid") is False

    resp = Response({"status": 500, "reason": "Internal Server Error"})
    mock_service.videos().list().execute.side_effect = HttpError(resp, b"Internal Error")
    with caplog.at_level("WARNING"):
        assert client.check_stream_active("vid") is True
    assert any("Error checking video status" in record.message for record in caplog.records)

@patch("youtube_tts.youtube.build")
def test_handle_quota_error(mock_build, mock_creds, caplog):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"domain": "usageLimits", "reason": "quotaExceeded"}], "code": 403, "message": "Quota exceeded"}}'
    
    client = YouTubeChatClient(mock_creds)
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)
    
    with pytest.raises(HttpError):
        with caplog.at_level("ERROR"):
            client.get_live_chat_id("vid")
        
    assert any("本日の無料枠上限（クォータ）を超過しました" in record.message for record in caplog.records)


@patch("youtube_tts.youtube.build")
def test_handle_comments_disabled_error(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"domain": "youtube.commentThread", "reason": "commentsDisabled"}], "code": 403, "message": "Comments are disabled"}}'
    
    # test verbose = False
    client = YouTubeChatClient(mock_creds, verbose=False)
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)
    
    with patch("youtube_tts.youtube.logger") as mock_logger:
        with pytest.raises(HttpError):
            client.get_live_chat_id("vid")
            
        mock_logger.error.assert_any_call("[ERROR] この動画・アーカイブはコメント機能がオフ（無効）に設定されています。")
        mock_logger.error.assert_any_call("        - コメント（チャット）機能が有効な動画・配信のURLを指定してください。")
        mock_logger.debug.assert_not_called()

    # test verbose = True
    client_verbose = YouTubeChatClient(mock_creds, verbose=True)
    with patch("youtube_tts.youtube.logger") as mock_logger:
        with pytest.raises(HttpError):
            client_verbose.get_live_chat_id("vid")
            
        mock_logger.error.assert_any_call("[ERROR] この動画・アーカイブはコメント機能がオフ（無効）に設定されています。")
        mock_logger.error.assert_any_call("        - コメント（チャット）機能が有効な動画・配信のURLを指定してください。")
        mock_logger.debug.assert_called_once()
        args, _ = mock_logger.debug.call_args
        assert "(エラー詳細:" in args[0]


@patch("youtube_tts.youtube.build")
def test_get_my_channel_id_success(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.channels().list().execute.return_value = {
        "items": [{"id": "my_channel_id_123"}]
    }

    client = YouTubeChatClient(mock_creds)
    assert client.get_my_channel_id() == "my_channel_id_123"
    # test caching
    assert client.get_my_channel_id() == "my_channel_id_123"
    # check that it was only called once (due to caching)
    # mock_service.channels().list is called once, but the mock might record multiple sub-calls
    # since we patch at the build level, mock_service.channels().list() will be called twice for the return value
    # but the .list() call itself is cached. Let's verify channels().list was called once.
    # The actual call is client.youtube.channels().list(...)
    # Let's count mock calls. We reset the mock list to be sure.
    mock_list = mock_service.channels().list
    mock_list.reset_mock()
    if hasattr(client, "_my_channel_id"):
        del client._my_channel_id
    assert client.get_my_channel_id() == "my_channel_id_123"
    assert client.get_my_channel_id() == "my_channel_id_123"
    mock_list.assert_called_once_with(part="id", mine=True)

@patch("youtube_tts.youtube.build")
def test_get_my_channel_id_failure(mock_build, mock_creds, caplog):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.channels().list().execute.side_effect = Exception("API error")

    client = YouTubeChatClient(mock_creds)
    with caplog.at_level("WARNING"):
        assert client.get_my_channel_id() is None
    assert any("Failed to get my channel ID" in record.message for record in caplog.records)

@patch("youtube_tts.youtube.build")
def test_get_video_details_success(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.videos().list().execute.return_value = {
        "items": [{"id": "vid123", "snippet": {"title": "My Video"}}]
    }

    client = YouTubeChatClient(mock_creds)
    details = client.get_video_details("vid123")
    assert details["id"] == "vid123"
    assert details["snippet"]["title"] == "My Video"

@patch("youtube_tts.youtube.build")
def test_get_video_details_not_found(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.videos().list().execute.return_value = {"items": []}

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(RuntimeError) as excinfo:
        client.get_video_details("vid123")
    assert "video not found" in str(excinfo.value)

@patch("youtube_tts.youtube.build")
def test_fetch_comment_threads_success(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.commentThreads().list().execute.return_value = {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "id": "comment_1",
                        "snippet": {
                            "authorDisplayName": "Alice",
                            "textOriginal": "Nice video!",
                            "publishedAt": "2026-06-21T12:00:00Z"
                        }
                    }
                }
            }
        ],
        "nextPageToken": "comment_next_token"
    }

    client = YouTubeChatClient(mock_creds)
    items, next_token, interval = client.fetch_comment_threads("vid123", max_results=50)
    assert len(items) == 1
    assert items[0]["id"] == "comment_1"
    assert items[0]["authorDetails"]["displayName"] == "Alice"
    assert items[0]["snippet"]["displayMessage"] == "Nice video!"
    assert items[0]["snippet"]["publishedAt"] == "2026-06-21T12:00:00Z"
    assert next_token == "comment_next_token"


@patch("youtube_tts.youtube.build")
def test_get_my_channel_id_empty_items(mock_build, mock_creds):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.channels().list().execute.return_value = {"items": []}

    client = YouTubeChatClient(mock_creds)
    assert client.get_my_channel_id() is None


@patch("youtube_tts.youtube.build")
def test_get_video_details_http_error(mock_build, mock_creds, caplog):
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"domain": "usageLimits", "reason": "quotaExceeded"}], "code": 403, "message": "Quota exceeded"}}'
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(HttpError):
        with caplog.at_level("ERROR"):
            client.get_video_details("vid")
    assert any("本日の無料枠上限（クォータ）を超過しました" in record.message for record in caplog.records)


@patch("youtube_tts.youtube.build")
def test_fetch_comment_threads_http_error(mock_build, mock_creds, caplog):
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"domain": "usageLimits", "reason": "quotaExceeded"}], "code": 403, "message": "Quota exceeded"}}'
    mock_service.commentThreads().list().execute.side_effect = HttpError(resp, content)

    client = YouTubeChatClient(mock_creds)
    with pytest.raises(HttpError):
        with caplog.at_level("ERROR"):
            client.fetch_comment_threads("vid")
    assert any("本日の無料枠上限（クォータ）を超過しました" in record.message for record in caplog.records)


@patch("youtube_tts.youtube.build")
def test_fetch_comment_threads_parse_error(mock_build, mock_creds, caplog):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.commentThreads().list().execute.return_value = {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "id": "c_ok",
                        "snippet": {
                            "authorDisplayName": "UserOK",
                            "textOriginal": "OkMsg",
                            "publishedAt": "2026-06-21T12:00:00Z"
                        }
                    }
                }
            },
            # 辞書ではない値を渡すことで AttributeError を発生させる
            "invalid_item_not_a_dict"
        ]
    }

    client = YouTubeChatClient(mock_creds)
    with caplog.at_level("WARNING"):
        items, _, _ = client.fetch_comment_threads("vid")
    
    assert len(items) == 1
    assert items[0]["id"] == "c_ok"
    assert any("Failed to parse comment" in record.message for record in caplog.records)


