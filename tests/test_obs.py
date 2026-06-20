import pytest
from unittest.mock import patch, MagicMock
from youtube_tts import ObsClient

def test_obs_update_missing_password():
    client = ObsClient(password=None)
    assert client.update_chat_url("source", "http://chat_url") is False

def test_obs_update_success():
    """接続成功時に True を返し、connect / disconnect が呼ばれることを確認。"""
    client = ObsClient(host="127.0.0.1", port=4455, password="secret_password")

    # obswebsocket ライブラリが存在することをシミュレートし、モックを直接注入する。
    # ObsClient の __init__ でキャッシュした _obsws / _obs_requests をインスタンスレベルで差し替える。
    mock_ws = MagicMock()
    client._available = True
    client._obsws = MagicMock(return_value=mock_ws)
    client._obs_requests = MagicMock()

    result = client.update_chat_url("BrowserSource", "http://chat_url")

    assert result is True
    mock_ws.connect.assert_called_once()
    mock_ws.disconnect.assert_called_once()

def test_obs_update_not_available(capsys):
    """obs-websocket-py が未インストールの場合に False を返す。"""
    client = ObsClient(host="127.0.0.1", port=4455, password="secret_password")
    client._available = False  # インストールされていない状態をシミュレート

    result = client.update_chat_url("BrowserSource", "http://chat_url")

    assert result is False
    captured = capsys.readouterr()
    assert "obs-websocket library is not installed" in captured.out

def test_obs_update_connection_failure():
    client = ObsClient(host="127.0.0.1", port=4455, password="secret_password")
    client._available = True
    mock_ws = MagicMock()
    mock_ws.connect.side_effect = Exception("Connection timed out")
    client._obsws = MagicMock(return_value=mock_ws)
    client._obs_requests = MagicMock()

    result = client.update_chat_url("BrowserSource", "http://chat_url")
    assert result is False

def test_obs_update_missing_source_name():
    client = ObsClient(password="secret_password")
    assert client.update_chat_url("", "http://chat_url") is False
