"""get_quota_info スクリプトの main 関数テストモジュールです。"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts.models import QuotaInfo


@pytest.fixture
def mock_deps() -> Generator[dict[str, MagicMock], None, None]:
    """main 関数のテストに必要なモックをセットアップします。"""
    with (
        patch("get_quota_info.get_logger") as mock_logger_class,
        patch("get_quota_info.get_project_id") as mock_project_id,
        patch("get_quota_info.YouTubeAuthenticator") as mock_auth_class,
        patch("get_quota_info.get_quota_info") as mock_quota_info,
    ):
        mock_logger = MagicMock()
        mock_logger_class.return_value = mock_logger
        mock_project_id.return_value = "test-project"

        mock_auth = MagicMock()
        mock_auth_class.return_value = mock_auth
        mock_auth.get_credentials.return_value = MagicMock()

        yield {
            "logger": mock_logger,
            "project_id": mock_project_id,
            "auth": mock_auth,
            "quota_info": mock_quota_info,
        }


def test_main_success(
    mock_deps: dict[str, MagicMock],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """正常系: クォータ情報を取得してコンソール出力できることを検証します。"""
    mock_deps["quota_info"].return_value = QuotaInfo(used=3000, limit=10000)

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "test-project" in captured.out
    assert "10,000" in captured.out
    assert "3,000" in captured.out
    assert "7,000" in captured.out
    assert "30.00%" in captured.out


def test_main_limit_zero(
    mock_deps: dict[str, MagicMock],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """上限値が0の場合に使用率が0%となることを検証します。"""
    mock_deps["quota_info"].return_value = QuotaInfo(used=0, limit=0)

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "0.00%" in captured.out


def test_main_remaining_clamped_to_zero(
    mock_deps: dict[str, MagicMock],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """使用量が上限超過の場合に残量が0になることを検証します。"""
    # 使用量が上限を超えている場合です。
    mock_deps["quota_info"].return_value = QuotaInfo(used=12000, limit=10000)

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "残量 (Remaining) : 0 units" in captured.out


def test_main_billing_error(
    mock_deps: dict[str, MagicMock],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """課金未設定エラー時に対策メッセージが出力されることを検証します。"""
    mock_deps["project_id"].side_effect = Exception(
        "billing to be enabled for this project"
    )

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "原因と対策" in captured.out
    assert "課金" in captured.out


def test_main_billing_error_with_project_id(
    mock_deps: dict[str, MagicMock],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """project_id 取得後に課金エラーが発生した際の URL 出力を検証します。"""
    mock_deps["project_id"].return_value = "my-project"
    mock_deps["quota_info"].side_effect = Exception(
        "billing to be enabled for this project"
    )

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "my-project" in captured.out
    assert "billing/enable" in captured.out
    assert "youtube.googleapis.com/quotas" in captured.out


def test_main_generic_error(
    mock_deps: dict[str, MagicMock],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """汎用エラー時に Cloud Monitoring API 確認メッセージの出力を検証します。"""
    mock_deps["project_id"].side_effect = Exception("some generic error")

    import get_quota_info as gqi

    gqi.main()

    captured = capsys.readouterr()
    assert "Cloud Monitoring API" in captured.out
