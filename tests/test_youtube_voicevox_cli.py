import pytest
import os
from unittest.mock import patch, MagicMock

# Import the main function
from youtube_voicevox import main

@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.youtube_worker")
@patch("youtube_voicevox.cleanup")
@patch("youtube_voicevox.AudioPlayer")
@patch("sounddevice.query_devices")
def test_cli_device_option(mock_query, mock_audio_player_class, mock_cleanup, mock_worker, mock_chat_client, mock_auth):
    # Setup mocks
    mock_query.return_value = {"name": "test_device", "index": 6}
    
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    # Test with -d option
    with patch("sys.argv", ["youtube_voicevox.py", "-d", "6", "video123"]):
        main()
        
    # Verify AudioPlayer was initialized with default_device=6
    mock_audio_player_class.assert_called_with(default_device=6)
    mock_chat_client_instance.extract_video_id.assert_called_with("video123")

@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.youtube_worker")
@patch("youtube_voicevox.cleanup")
@patch("youtube_voicevox.AudioPlayer")
@patch("sounddevice.query_devices")
def test_cli_device_env_var(mock_query, mock_audio_player_class, mock_cleanup, mock_worker, mock_chat_client, mock_auth):
    # Setup mocks
    mock_query.return_value = {"name": "test_device", "index": 6}
    
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    # Test with VOICEVOX_DEVICE env var
    with patch.dict(os.environ, {"VOICEVOX_DEVICE": "6"}):
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
            
    # Verify AudioPlayer was initialized with default_device=6
    mock_audio_player_class.assert_called_with(default_device=6)


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.youtube_worker")
@patch("youtube_voicevox.cleanup")
@patch("youtube_voicevox.get_project_id")
def test_cli_quota_options(mock_get_project_id, mock_cleanup, mock_worker, mock_chat_client, mock_auth):
    mock_get_project_id.return_value = "test-project-123"
    
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_creds = MagicMock()
    mock_auth_instance.get_credentials.return_value = mock_creds
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    from youtube_voicevox import QUOTA_SCOPES
    
    # Test with --quota-talk and custom intervals
    with patch("sys.argv", ["youtube_voicevox.py", "--quota-talk", "--chat-interval", "10", "--quota-interval", "30", "video123"]):
        main()
        
    # Verify auth was called with QUOTA_SCOPES
    mock_auth.assert_called_with(
        client_secret_path="client_secret.json",
        token_path="token.json",
        scopes=QUOTA_SCOPES
    )
    
    # Verify get_project_id was called
    mock_get_project_id.assert_called_once()
    
    # Verify youtube_worker was called with correct parameters
    mock_worker.assert_called_with(
        mock_chat_client_instance,
        "video123",
        creds=mock_creds,
        quota_check=True,
        quota_talk=True,
        chat_interval=10.0,
        quota_interval=30.0,
        project_id="test-project-123"
    )

