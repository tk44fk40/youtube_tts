import pytest
from unittest.mock import patch, MagicMock
from youtube_tts import ObsClient

def test_obs_update_missing_password():
    client = ObsClient(password=None)
    assert client.update_chat_url("source", "http://chat_url") is False

def test_obs_update_success():
    """Verifies that it returns True on successful connection
    and connect / disconnect are called.
    
    接続成功時に True を返し、
    connect / disconnect が呼ばれることを確認。
    """
    client = ObsClient(host="127.0.0.1", port=4455, password="secret_password")

    # Simulate the presence of the obswebsocket library and inject
    # a mock directly.
    # Replace _obsws or _obs_requests cached in ObsClient.__init__
    # at the instance level.
    #
    # obswebsocket ライブラリが存在することをシミュレートし、
    # モックを直接注入する。
    # ObsClient の __init__ でキャッシュした _obsws や _obs_requests を
    # インスタンスレベルで差し替える。
    mock_ws = MagicMock()
    client._available = True
    client._obsws = MagicMock(return_value=mock_ws)
    client._obs_requests = MagicMock()

    result = client.update_chat_url("BrowserSource", "http://chat_url")

    assert result is True
    mock_ws.connect.assert_called_once()
    mock_ws.disconnect.assert_called_once()

def test_obs_update_not_available(caplog):
    """Returns False if obs-websocket-py is not installed.
    
    obs-websocket-py が未インストールの場合に False を返す。
    """
    client = ObsClient(host="127.0.0.1", port=4455, password="secret_password")
    # Simulate not-installed state
    #
    # インストールされていない状態をシミュレート
    client._available = False

    with caplog.at_level("WARNING"):
        result = client.update_chat_url("BrowserSource", "http://chat_url")

    assert result is False
    assert any(
        "obs-websocket library is not installed" in record.message
        for record in caplog.records
    )

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


def test_obs_client_import_error():
    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "obswebsocket":
            raise ImportError("Mocked import error")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        client = ObsClient(password="secret_password")
        assert client._available is False
        assert client._obsws is None
        assert client._obs_requests is None
