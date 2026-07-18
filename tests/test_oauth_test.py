"""oauth_test.py のテストを行うモジュールです。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from oauth_test import main


def test_oauth_test_success() -> None:
    """OAuth 認証が正常に成功するケースを検証します。"""
    with (
        patch("oauth_test.YouTubeAuthenticator") as mock_auth_class,
        patch("oauth_test.get_logger") as mock_get_logger,
    ):
        mock_auth = MagicMock()
        mock_auth_class.return_value = mock_auth
        mock_creds = MagicMock()
        mock_creds.token = "mock_token_1234567890123456789012345678901234567890"
        mock_auth.get_credentials.return_value = mock_creds

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        main()

        mock_logger.info.assert_called_once()
        mock_auth.get_credentials.assert_called_once()


def test_oauth_test_failure() -> None:
    """OAuth 認証に失敗して終了するケースを検証します。"""
    with (
        patch("oauth_test.YouTubeAuthenticator") as mock_auth_class,
        patch("oauth_test.get_logger") as mock_get_logger,
    ):
        mock_auth = MagicMock()
        mock_auth_class.return_value = mock_auth
        err_msg = "Auth connection error"
        mock_auth.get_credentials.side_effect = Exception(err_msg)

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_logger.error.assert_called_once()
