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
