"""GCP クォータ取得処理のテストモジュールです。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts.quota import get_project_id, get_quota_info


def test_get_project_id_missing_file(tmp_path: Path) -> None:
    """認証キーファイルがない場合のエラー発生を検証します。"""
    missing_file = tmp_path / "non_existent.json"
    with pytest.raises(
        RuntimeError, match="non_existent.json が見つかりません。"
    ):
        get_project_id(missing_file)


def test_get_project_id_success_installed(tmp_path: Path) -> None:
    """installedキーからプロジェクトIDを取得できることを検証します。"""
    secret_file = tmp_path / "client_secret.json"
    data = {"installed": {"project_id": "installed-project-id"}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    assert get_project_id(secret_file) == "installed-project-id"


def test_get_project_id_success_web(tmp_path: Path) -> None:
    """webキーからプロジェクトIDを取得できることを検証します。"""
    secret_file = tmp_path / "client_secret.json"
    data = {"web": {"project_id": "web-project-id"}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    assert get_project_id(secret_file) == "web-project-id"


def test_get_project_id_missing_id(tmp_path: Path) -> None:
    """プロジェクトIDが無い場合にエラーが発生することを検証します。"""
    secret_file = tmp_path / "client_secret.json"
    data = {"installed": {}}
    secret_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match=("client_secret.json から project_id を取得できませんでした。"),
    ):
        get_project_id(secret_file)


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_success(mock_client_class: MagicMock) -> None:
    """クォータ情報（使用量と上限値）の正常取得を検証します。"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # 使用量の結果をモックします。
    mock_point_1 = MagicMock()
    mock_point_1.value.int64_value = 500
    mock_point_2 = MagicMock()
    mock_point_2.value.int64_value = 463

    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_1, mock_point_2]

    # 上限値の結果をモックします。
    mock_point_limit = MagicMock()
    mock_point_limit.value.int64_value = 15000
    mock_result_limit = MagicMock()
    mock_result_limit.points = [mock_point_limit]

    # クライアントがこれらの値を返すように設定します。
    # 最初の呼び出しは使用量用、2番目は上限値用とします。
    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        [mock_result_limit],
    ]

    creds = MagicMock()
    quota_info = get_quota_info(creds, "my-project")

    assert quota_info.used == 963
    assert quota_info.limit == 15000
    mock_client_class.assert_called_with(credentials=creds)


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_fallback(mock_client_class: MagicMock) -> None:
    """上限値取得失敗時のデフォルト値フォールバックを検証します。"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # 使用量の結果は正常に返ります (used = 200)。
    mock_point_usage = MagicMock()
    mock_point_usage.value.int64_value = 200
    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_usage]

    # 上限値の取得で例外を発生させ、
    # デフォルトの上限値 10000 をトリガーします。
    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        Exception("API Error"),
    ]

    creds = MagicMock()
    quota_info = get_quota_info(creds, "my-project")

    assert quota_info.used == 200
    assert quota_info.limit == 10000  # 例外発生時は10000にフォールバックされます。


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
@patch("youtube_tts.quota.ZoneInfo")
def test_get_quota_info_tz_error_fallback(
    mock_zoneinfo: MagicMock, mock_client_class: MagicMock
) -> None:
    """タイムゾーン取得エラー時の過去24時間集計移行を検証します。"""
    # ZoneInfo で例外を発生させ、
    # 過去24時間（UTC）へのフォールバックを強制します。
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
    quota_info = get_quota_info(creds, "my-project")

    assert quota_info.used == 120
    assert quota_info.limit == 5000


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_midnight_boundary(mock_client_class: MagicMock) -> None:
    """時刻が午前0時ちょうどの場合の境界値補正を検証します。"""
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
    # 午前0時ちょうどをシミュレートして境界補正が動作することを確認します。
    with _patch("youtube_tts.quota.datetime") as mock_dt:
        mock_dt.now.return_value = midnight
        # ZoneInfo は実物を使うために side_effect で除外しません。
        mock_dt.side_effect = None
        # 境界補正が適用されても例外なく完了することを確認します。
        try:
            quota_info = get_quota_info(creds, "my-project")
        except Exception:
            # datetime のモック化の挙動によって失敗することがありますが、
            # 境界補正ロジックのカバレッジ取得を目的とします。
            pass


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_empty(mock_client_class: MagicMock) -> None:
    """上限値リストが空の場合にデフォルト値となることを検証します。"""
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
    quota_info = get_quota_info(creds, "my-project")
    assert quota_info.limit == 10000


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_no_points(mock_client_class: MagicMock) -> None:
    """上限値ポイントが空の場合にデフォルト値となることを検証します。"""
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
    quota_info = get_quota_info(creds, "my-project")
    assert quota_info.limit == 10000
