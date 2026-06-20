import pytest
from unittest.mock import patch, MagicMock
from youtube_tts import ObsClient

def test_obs_update_missing_password():
    client = ObsClient(password=None)
    assert client.update_chat_url("source", "http://chat_url") is False

@patch("obswebsocket.obsws", create=True)
@patch("obswebsocket.requests", create=True)
def test_obs_update_success(mock_obs_requests, mock_obsws_class):
    mock_ws = MagicMock()
    mock_obsws_class.return_value = mock_ws
    
    mock_set_settings = MagicMock()
    mock_obs_requests.SetInputSettings = mock_set_settings

    client = ObsClient(host="127.0.0.1", port=4455, password="secret_password")
    
    result = client.update_chat_url("BrowserSource", "http://chat_url")
    
    assert result is True
    mock_ws.connect.assert_called_once()
    mock_set_settings.assert_called_once_with(
        inputName="BrowserSource",
        inputSettings={"url": "http://chat_url"}
    )
    mock_ws.call.assert_called_once()
    mock_ws.disconnect.assert_called_once()

@patch("obswebsocket.obsws", create=True)
def test_obs_update_connection_failure(mock_obsws_class):
    mock_ws = MagicMock()
    mock_ws.connect.side_effect = Exception("Connection timed out")
    mock_obsws_class.return_value = mock_ws

    client = ObsClient(host="127.0.0.1", port=4455, password="secret_password")
    
    # Ensure it doesn't crash on connection error and returns False
    result = client.update_chat_url("BrowserSource", "http://chat_url")
    assert result is False

def test_obs_update_missing_source_name():
    client = ObsClient(password="secret_password")
    assert client.update_chat_url("", "http://chat_url") is False

