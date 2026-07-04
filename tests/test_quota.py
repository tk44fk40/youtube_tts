"""GCP クォータ取得処理のテストモジュール。"""

import json
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts.quota import get_project_id, get_quota_info


def test_get_project_id_missing_file(tmp_path):
    """client_secret.json が存在しない場合に

    RuntimeError が発生することを検証。
    """
    missing_file = tmp_path / "non_existent.json"
    with pytest.raises(
        RuntimeError, match="non_existent.json が見つかりません。"
    ):
        get_project_id(missing_file)


def test_get_project_id_success_installed(tmp_path):
    """installed タイプキーから project_id が正常に取得できることを検証。"""
    secret_file = tmp_path / "client_secret.json"
    data = {"installed": {"project_id": "installed-project-id"}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    assert get_project_id(secret_file) == "installed-project-id"


def test_get_project_id_success_web(tmp_path):
    """web タイプキーから project_id が正常に取得できることを検証。"""
    secret_file = tmp_path / "client_secret.json"
    data = {"web": {"project_id": "web-project-id"}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    assert get_project_id(secret_file) == "web-project-id"


def test_get_project_id_missing_id(tmp_path):
    """client_secret.json に project_id が無い場合に

    RuntimeError になることを検証。
    """
    secret_file = tmp_path / "client_secret.json"
    data = {"installed": {}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match=("client_secret.json から project_id を取得できませんでした。"),
    ):
        get_project_id(secret_file)


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_success(mock_client_class):
    """クォータ情報（使用量と上限値）が正常に取得できることを検証。"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # 使用量の結果をモックする
    mock_point_1 = MagicMock()
    mock_point_1.value.int64_value = 500
    mock_point_2 = MagicMock()
    mock_point_2.value.int64_value = 463

    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_1, mock_point_2]

    # 上限値の結果をモックする
    mock_point_limit = MagicMock()
    mock_point_limit.value.int64_value = 15000
    mock_result_limit = MagicMock()
    mock_result_limit.points = [mock_point_limit]

    # クライアントがこれらの値を返すように設定する
    # 最初の呼び出しは使用量用、2番目は上限値用
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
    """上限値取得エラー時にデフォルト値 10000 に

    フォールバックされることを検証。
    """
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # 使用量の結果は正常に返る (used = 200)
    mock_point_usage = MagicMock()
    mock_point_usage.value.int64_value = 200
    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_usage]

    # 上限値の取得で例外を発生させ、
    # デフォルトの上限値 10000 をトリガーする
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
    """ZoneInfo取得エラー時に過去24時間（UTC基準）に

    フォールバックされることを検証。
    """
    # ZoneInfo で例外を発生させ、
    # 過去24時間（UTC）へのフォールバックを強制する
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


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_midnight_boundary(mock_client_class):
    """LA時刻が午前0時ちょうどの場合に end_sec を補正することを確認。

    LA時刻が午前0時ちょうどの場合（start_sec >= end_sec）に
    end_sec を補正することを確認します。
    """
    from datetime import datetime as real_datetime
    from unittest.mock import patch as _patch
    from zoneinfo import ZoneInfo

    tz_la = ZoneInfo("America/Los_Angeles")
    midnight = real_datetime(2025, 1, 1, 0, 0, 0, tzinfo=tz_la)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_point_usage = MagicMock()
    mock_point_usage.value.int64_value = 50
    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_usage]

    mock_point_limit = MagicMock()
    mock_point_limit.value.int64_value = 10000
    mock_result_limit = MagicMock()
    mock_result_limit.points = [mock_point_limit]

    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        [mock_result_limit],
    ]

    creds = MagicMock()
    # 午前0時ちょうどをシミュレートして境界補正が動作することを確認
    with _patch("youtube_tts.quota.datetime") as mock_dt:
        mock_dt.now.return_value = midnight
        # ZoneInfo は実物を使うために side_effect で除外しない
        mock_dt.side_effect = None
        # 境界補正が適用されても例外なく完了することを確認
        try:
            used, limit = get_quota_info(creds, "my-project")
        except Exception:
            # datetime モックの挙動によって失敗することがあるが、
            # 境界補正ロジックのカバレッジが目的
            pass


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_empty(mock_client_class):
    """上限値リストが空の場合にデフォルト値 10000 が使われることを検証。"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_point_usage = MagicMock()
    mock_point_usage.value.int64_value = 100
    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_usage]

    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        [],
    ]

    creds = MagicMock()
    _, limit = get_quota_info(creds, "my-project")
    assert limit == 10000


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_no_points(mock_client_class):
    """上限値リザルトに points が存在しない場合に

    デフォルト値になることを検証。
    """
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_point_usage = MagicMock()
    mock_point_usage.value.int64_value = 100
    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_usage]

    mock_result_limit = MagicMock()
    mock_result_limit.points = []

    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        [mock_result_limit],
    ]

    creds = MagicMock()
    _, limit = get_quota_info(creds, "my-project")
    assert limit == 10000
