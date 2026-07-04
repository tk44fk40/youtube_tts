"""get_quota_info スクリプトの main 関数テストモジュールです。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@patch("get_quota_info.get_quota_info")
@patch("get_quota_info.get_project_id")
@patch("get_quota_info.YouTubeAuthenticator")
@patch("get_quota_info.get_logger")
def test_main_success(
    mock_get_logger: MagicMock,
    mock_authenticator_class: MagicMock,
    mock_get_project_id: MagicMock,
    mock_get_quota_info: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """正常系: クォータ情報を取得してコンソール出力できることを検証します。"""
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    mock_get_project_id.return_value = "test-project"
    mock_authenticator = MagicMock()
    mock_authenticator_class.return_value = mock_authenticator
    mock_authenticator.get_credentials.return_value = MagicMock()
    mock_get_quota_info.return_value = (3000, 10000)

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "test-project" in captured.out
    assert "10,000" in captured.out
    assert "3,000" in captured.out
    assert "7,000" in captured.out
    assert "30.00%" in captured.out


@patch("get_quota_info.get_quota_info")
@patch("get_quota_info.get_project_id")
@patch("get_quota_info.YouTubeAuthenticator")
@patch("get_quota_info.get_logger")
def test_main_limit_zero(
    mock_get_logger: MagicMock,
    mock_authenticator_class: MagicMock,
    mock_get_project_id: MagicMock,
    mock_get_quota_info: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """上限値が0の場合に使用率が0%となることを検証します。"""
    mock_get_logger.return_value = MagicMock()
    mock_get_project_id.return_value = "test-project"
    mock_authenticator = MagicMock()
    mock_authenticator_class.return_value = mock_authenticator
    mock_authenticator.get_credentials.return_value = MagicMock()
    mock_get_quota_info.return_value = (0, 0)

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "0.00%" in captured.out


@patch("get_quota_info.get_quota_info")
@patch("get_quota_info.get_project_id")
@patch("get_quota_info.YouTubeAuthenticator")
@patch("get_quota_info.get_logger")
def test_main_remaining_clamped_to_zero(
    mock_get_logger: MagicMock,
    mock_authenticator_class: MagicMock,
    mock_get_project_id: MagicMock,
    mock_get_quota_info: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """使用量が上限超過の場合に残量が0になることを検証します。"""
    mock_get_logger.return_value = MagicMock()
    mock_get_project_id.return_value = "test-project"
    mock_authenticator = MagicMock()
    mock_authenticator_class.return_value = mock_authenticator
    mock_authenticator.get_credentials.return_value = MagicMock()
    # 使用量が上限を超えている場合です。
    mock_get_quota_info.return_value = (12000, 10000)

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "残量 (Remaining) : 0 units" in captured.out


@patch("get_quota_info.get_project_id")
@patch("get_quota_info.get_logger")
def test_main_billing_error(
    mock_get_logger: MagicMock,
    mock_get_project_id: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """課金未設定エラー時に対策メッセージが出力されることを検証します。"""
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    mock_get_project_id.side_effect = Exception(
        "billing to be enabled for this project"
    )

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "原因と対策" in captured.out
    assert "課金" in captured.out


@patch("get_quota_info.get_quota_info")
@patch("get_quota_info.get_project_id")
@patch("get_quota_info.YouTubeAuthenticator")
@patch("get_quota_info.get_logger")
def test_main_billing_error_with_project_id(
    mock_get_logger: MagicMock,
    mock_authenticator_class: MagicMock,
    mock_get_project_id: MagicMock,
    mock_get_quota_info: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """project_id 取得後に課金エラーが発生した際の URL 出力を検証します。"""
    mock_get_logger.return_value = MagicMock()
    mock_get_project_id.return_value = "my-project"
    mock_authenticator = MagicMock()
    mock_authenticator_class.return_value = mock_authenticator
    mock_authenticator.get_credentials.return_value = MagicMock()
    mock_get_quota_info.side_effect = Exception(
        "billing to be enabled for this project"
    )

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "my-project" in captured.out
    assert "billing/enable" in captured.out
    assert "youtube.googleapis.com/quotas" in captured.out


@patch("get_quota_info.get_project_id")
@patch("get_quota_info.get_logger")
def test_main_generic_error(
    mock_get_logger: MagicMock,
    mock_get_project_id: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """汎用エラー時に Cloud Monitoring API 確認メッセージの出力を検証します。"""
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    mock_get_project_id.side_effect = Exception("some generic error")

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "Cloud Monitoring API" in captured.out
