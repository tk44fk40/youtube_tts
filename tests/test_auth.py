"""YouTube 認証ハンドラーの単体テストを行うモジュール。"""

import json
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts import YouTubeAuthenticator


@patch("youtube_tts.auth.Credentials")
def test_auth_valid_cache(mock_creds_class, tmp_path):
    """有効なキャッシュトークンが存在する場合の認証情報取得テスト。"""
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "valid_token"}', encoding="utf-8")

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds_class.from_authorized_user_file.return_value = mock_creds

    authenticator = YouTubeAuthenticator(
        client_secret_path=tmp_path / "client_secret.json",
        token_path=token_file,
    )

    creds = authenticator.get_credentials()
    assert creds == mock_creds
    mock_creds_class.from_authorized_user_file.assert_called_once_with(
        str(token_file), authenticator.scopes
    )


@patch("youtube_tts.auth.Request")
@patch("youtube_tts.auth.Credentials")
def test_auth_expired_refresh_success(
    mock_creds_class, mock_request_class, tmp_path
):
    """期限切れトークンのリフレッシュ処理が成功するかのテスト。"""
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "expired_token"}', encoding="utf-8")

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "some_refresh_token"
    mock_creds.to_json.return_value = '{"token": "new_refreshed_token"}'
    mock_creds_class.from_authorized_user_file.return_value = mock_creds

    authenticator = YouTubeAuthenticator(
        client_secret_path=tmp_path / "client_secret.json",
        token_path=token_file,
    )

    creds = authenticator.get_credentials()
    assert creds == mock_creds
    mock_creds.refresh.assert_called_once()

    saved_data = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved_data["token"] == "new_refreshed_token"


@patch("youtube_tts.auth.InstalledAppFlow")
def test_auth_no_cache_oauth_success(mock_flow_class, tmp_path):
    """キャッシュがない場合に新規OAuthフローが走るかのテスト。"""
    client_secret = tmp_path / "client_secret.json"
    client_secret.touch()
    token_file = tmp_path / "token.json"

    mock_flow = MagicMock()
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "new_oauth_token"}'
    mock_flow.run_local_server.return_value = mock_creds
    mock_flow_class.from_client_secrets_file.return_value = mock_flow

    authenticator = YouTubeAuthenticator(
        client_secret_path=client_secret, token_path=token_file
    )

    creds = authenticator.get_credentials()
    assert creds == mock_creds
    mock_flow_class.from_client_secrets_file.assert_called_once_with(
        str(client_secret), authenticator.scopes
    )
    mock_flow.run_local_server.assert_called_once_with(port=0)

    assert token_file.exists()
    saved_data = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved_data["token"] == "new_oauth_token"


@patch("youtube_tts.auth.InstalledAppFlow")
@patch("youtube_tts.auth.Credentials")
def test_auth_corrupted_json(mock_creds_class, mock_flow_class, tmp_path):
    """キャッシュファイルが破損している場合のフォールバックテスト。"""
    client_secret = tmp_path / "client_secret.json"
    client_secret.touch()
    token_file = tmp_path / "token.json"
    token_file.write_text("{corrupted_json", encoding="utf-8")

    mock_creds_class.from_authorized_user_file.side_effect = Exception(
        "JSONDecodeError"
    )

    mock_flow = MagicMock()
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "new_oauth_token"}'
    mock_flow.run_local_server.return_value = mock_creds
    mock_flow_class.from_client_secrets_file.return_value = mock_flow

    authenticator = YouTubeAuthenticator(
        client_secret_path=client_secret, token_path=token_file
    )

    creds = authenticator.get_credentials()
    assert creds == mock_creds
    assert token_file.exists()
    saved_data = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved_data["token"] == "new_oauth_token"


def test_auth_missing_client_secret(tmp_path):
    """クライアントシークレットファイルが無い場合に例外が出るかのテスト。"""
    authenticator = YouTubeAuthenticator(
        client_secret_path=tmp_path / "non_existent_client_secret.json",
        token_path=tmp_path / "token.json",
    )
    with pytest.raises(RuntimeError) as excinfo:
        authenticator.get_credentials()
    assert "was not found" in str(excinfo.value)


@patch("youtube_tts.auth.InstalledAppFlow")
@patch("youtube_tts.auth.Credentials")
@patch("youtube_tts.auth.Path.unlink")
def test_auth_corrupted_json_unlink_oserror(
    mock_unlink, mock_creds_class, mock_flow_class, tmp_path
):
    """破損キャッシュの削除でOSエラーが出ても処理が継続するかのテスト。"""
    client_secret = tmp_path / "client_secret.json"
    client_secret.touch()
    token_file = tmp_path / "token.json"
    token_file.write_text("{corrupted_json", encoding="utf-8")

    mock_creds_class.from_authorized_user_file.side_effect = Exception(
        "JSONDecodeError"
    )
    mock_unlink.side_effect = OSError("Permission denied")

    mock_flow = MagicMock()
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "new_oauth_token"}'
    mock_flow.run_local_server.return_value = mock_creds
    mock_flow_class.from_client_secrets_file.return_value = mock_flow

    authenticator = YouTubeAuthenticator(
        client_secret_path=client_secret, token_path=token_file
    )

    creds = authenticator.get_credentials()
    assert creds == mock_creds


@patch("youtube_tts.auth.InstalledAppFlow")
@patch("youtube_tts.auth.Credentials")
@patch("youtube_tts.auth.Request")
def test_auth_refresh_exception(
    mock_request_class, mock_creds_class, mock_flow_class, tmp_path
):
    """トークンリフレッシュで例外時にOAuthへ遷移するかのテスト。"""
    client_secret = tmp_path / "client_secret.json"
    client_secret.touch()
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "expired_token"}', encoding="utf-8")

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "some_refresh_token"
    mock_creds.refresh.side_effect = Exception("Network error")
    mock_creds_class.from_authorized_user_file.return_value = mock_creds

    mock_flow = MagicMock()
    mock_oauth_creds = MagicMock()
    mock_oauth_creds.to_json.return_value = '{"token": "new_oauth_token"}'
    mock_flow.run_local_server.return_value = mock_oauth_creds
    mock_flow_class.from_client_secrets_file.return_value = mock_flow

    authenticator = YouTubeAuthenticator(
        client_secret_path=client_secret, token_path=token_file
    )

    creds = authenticator.get_credentials()
    assert creds == mock_oauth_creds
