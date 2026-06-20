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
def test_check_stream_active_all_cases(mock_build, mock_creds, capsys):
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
    assert client.check_stream_active("vid") is True
    captured = capsys.readouterr()
    assert "Error checking video status" in captured.out or "Error checking video status" in captured.err

@patch("youtube_tts.youtube.build")
def test_handle_quota_error(mock_build, mock_creds, capsys):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    
    resp = Response({"status": 403, "reason": "Forbidden"})
    content = b'{"error": {"errors": [{"domain": "usageLimits", "reason": "quotaExceeded"}], "code": 403, "message": "Quota exceeded"}}'
    
    client = YouTubeChatClient(mock_creds)
    mock_service.videos().list().execute.side_effect = HttpError(resp, content)
    
    with pytest.raises(HttpError):
        client.get_live_chat_id("vid")
        
    captured = capsys.readouterr()
    assert "YouTube API quota exceeded" in captured.out or "YouTube API quota exceeded" in captured.err

