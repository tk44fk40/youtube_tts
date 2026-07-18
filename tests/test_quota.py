"""GCP クォータ取得処理のテストモジュールです。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts.quota import get_project_id, get_quota_info


def _build_quota_mocks(
    mock_client_class: MagicMock,
    usage_values: list[int],
    limit_result: list[int] | Exception | None = None,
) -> MagicMock:
    """クォータ取得テスト用のモッククライアントを構築します。

    Args:
        mock_client_class: MetricServiceClient のモック
            クラスです。
        usage_values: 使用量ポイントの値リストです。
        limit_result: 上限値ポイントの値リスト、
            例外、または None（空リスト）です。

    Returns:
        モック化されたクライアントです。
    """
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # 使用量の結果をモックします。
    usage_results: list[Any] = []
    for val in usage_values:
        mock_point = MagicMock()
        mock_point.value.int64_value = val
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        usage_results.append(mock_result)

    # 上限値の結果をモックします。
    if isinstance(limit_result, Exception):
        side_effects: list[Any] = [usage_results, limit_result]
    elif limit_result is None:
        side_effects = [usage_results, []]
    else:
        limit_results: list[Any] = []
        for val in limit_result:
            mock_point = MagicMock()
            mock_point.value.int64_value = val
            mock_result = MagicMock()
            mock_result.points = [mock_point]
            limit_results.append(mock_result)
        side_effects = [usage_results, limit_results]

    mock_client.list_time_series.side_effect = side_effects
    return mock_client


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
def test_get_quota_info_success(
    mock_client_class: MagicMock,
) -> None:
    """クォータ情報（使用量と上限値）の正常取得を検証します。"""
    _build_quota_mocks(
        mock_client_class,
        usage_values=[500, 463],
        limit_result=[15000],
    )

    creds = MagicMock()
    quota_info = get_quota_info(creds, "my-project")

    assert quota_info.used == 963
    assert quota_info.limit == 15000
    mock_client_class.assert_called_with(credentials=creds)


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_fallback(
    mock_client_class: MagicMock,
) -> None:
    """上限値取得失敗時のデフォルト値フォールバックを検証します。"""
    _build_quota_mocks(
        mock_client_class,
        usage_values=[200],
        limit_result=Exception("API Error"),
    )

    creds = MagicMock()
    quota_info = get_quota_info(creds, "my-project")

    assert quota_info.used == 200
    # 例外発生時は10000にフォールバックされます。
    assert quota_info.limit == 10000


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
@patch("youtube_tts.quota.ZoneInfo")
def test_get_quota_info_tz_error_fallback(
    mock_zoneinfo: MagicMock,
    mock_client_class: MagicMock,
) -> None:
    """タイムゾーン取得エラー時の過去24時間集計移行を検証します。"""
    # ZoneInfo で例外を発生させ、
    # 過去24時間（UTC）へのフォールバックを強制します。
    mock_zoneinfo.side_effect = Exception("ZoneInfo error")

    _build_quota_mocks(
        mock_client_class,
        usage_values=[120],
        limit_result=[5000],
    )

    creds = MagicMock()
    quota_info = get_quota_info(creds, "my-project")

    assert quota_info.used == 120
    assert quota_info.limit == 5000


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_midnight_boundary(
    mock_client_class: MagicMock,
) -> None:
    """時刻が午前0時ちょうどの場合の境界値補正を検証します。"""
    from datetime import datetime as real_datetime
    from unittest.mock import patch as _patch
    from zoneinfo import ZoneInfo

    tz_la = ZoneInfo("America/Los_Angeles")
    midnight = real_datetime(2025, 1, 1, 0, 0, 0, tzinfo=tz_la)

    _build_quota_mocks(
        mock_client_class,
        usage_values=[50],
        limit_result=[10000],
    )

    class MockDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore
            return midnight

    creds = MagicMock()
    
    with _patch("youtube_tts.quota.datetime", MockDatetime):
        get_quota_info(creds, "my-project")
        
    # エラーが発生せずに get_quota_info が完了すれば成功です。


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_empty(
    mock_client_class: MagicMock,
) -> None:
    """上限値リストが空の場合にデフォルト値となることを検証します。"""
    _build_quota_mocks(
        mock_client_class,
        usage_values=[100],
        limit_result=None,
    )

    creds = MagicMock()
    quota_info = get_quota_info(creds, "my-project")
    assert quota_info.limit == 10000


@patch("youtube_tts.quota.monitoring_v3.MetricServiceClient")
def test_get_quota_info_limit_no_points(
    mock_client_class: MagicMock,
) -> None:
    """上限値ポイントが空の場合にデフォルト値となることを検証します。"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # 使用量の結果をモックします。
    mock_point_usage = MagicMock()
    mock_point_usage.value.int64_value = 100
    mock_result_usage = MagicMock()
    mock_result_usage.points = [mock_point_usage]

    # ポイントが空の上限値結果をモックします。
    mock_result_limit = MagicMock()
    mock_result_limit.points = []

    mock_client.list_time_series.side_effect = [
        [mock_result_usage],
        [mock_result_limit],
    ]

    creds = MagicMock()
    quota_info = get_quota_info(creds, "my-project")
    assert quota_info.limit == 10000

