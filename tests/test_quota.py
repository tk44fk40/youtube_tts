import json
import pytest
from unittest.mock import patch, MagicMock
from youtube_tts.quota import get_project_id, get_quota_info


def test_get_project_id_missing_file(tmp_path):
    missing_file = tmp_path / "non_existent.json"
    with pytest.raises(RuntimeError, match="non_existent.json が見つかりません。"):
        get_project_id(missing_file)


def test_get_project_id_success_installed(tmp_path):
    secret_file = tmp_path / "client_secret.json"
    data = {"installed": {"project_id": "installed-project-id"}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    assert get_project_id(secret_file) == "installed-project-id"


def test_get_project_id_success_web(tmp_path):
    secret_file = tmp_path / "client_secret.json"
    data = {"web": {"project_id": "web-project-id"}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    assert get_project_id(secret_file) == "web-project-id"


def test_get_project_id_missing_id(tmp_path):
    secret_file = tmp_path / "client_secret.json"
    data = {"installed": {}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="client_secret.json から project_id を取得できませんでした。",
    ):
        get_project_id(secret_file)


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_success(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # Mock usage results
    mock_point_1 = MagicMock()
    mock_point_1.value.int64_value = 500
    mock_point_2 = MagicMock()
    mock_point_2.value.int64_value = 463

    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_1, mock_point_2]

    # Mock limit results
    mock_point_limit = MagicMock()
    mock_point_limit.value.int64_value = 15000
    mock_result_limit = MagicMock()
    mock_result_limit.points = [mock_point_limit]

    # Configure client to return these values
    # The first call is for usage, second is for limit
    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        [mock_result_limit],
    ]

    creds = MagicMock()
    used, limit = get_quota_info(creds, "my-project")

    assert used == 963
    assert limit == 15000
    mock_client_class.assert_called_with(credentials=creds)


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_fallback(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # usage results return normally (used = 200)
    mock_point_usage = MagicMock()
    mock_point_usage.value.int64_value = 200
    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_usage]

    # limit results call raises an exception to trigger default limit 10000
    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        Exception("API Error"),
    ]

    creds = MagicMock()
    used, limit = get_quota_info(creds, "my-project")

    assert used == 200
    assert limit == 10000  # fallback to 10000 on exception


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
@patch("youtube_tts.quota.ZoneInfo")
def test_get_quota_info_tz_error_fallback(mock_zoneinfo, mock_client_class):
    # Simulate ZoneInfo raising exception to force fallback to UTC past 24 hours
    mock_zoneinfo.side_effect = Exception("ZoneInfo error")

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_point_usage = MagicMock()
    mock_point_usage.value.int64_value = 120
    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_usage]

    mock_point_limit = MagicMock()
    mock_point_limit.value.int64_value = 5000
    mock_result_limit = MagicMock()
    mock_result_limit.points = [mock_point_limit]

    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        [mock_result_limit],
    ]

    creds = MagicMock()
    used, limit = get_quota_info(creds, "my-project")

    assert used == 120
    assert limit == 5000
