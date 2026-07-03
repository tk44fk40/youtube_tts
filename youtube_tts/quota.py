# Copyright 2026 tk44fk40
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""YouTube Data API のクォータ使用状況を取得するモジュール。

このモジュールは、Google Cloud Monitoring API を利用して、
YouTube Data API の本日分のクォータ消費量および上限値を取得する
機能を提供します。
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.cloud import monitoring_v3

from .auth import YOUTUBE_SCOPE
from .logger import get_logger

logger = get_logger()

CLIENT_SECRET_FILE = "client_secret.json"

QUOTA_SCOPES = [
    YOUTUBE_SCOPE,
    "https://www.googleapis.com/auth/monitoring.read",
]


def get_project_id(client_secret_path=CLIENT_SECRET_FILE):
    """client_secret.json からプロジェクトIDを自動取得します。

    Args:
        client_secret_path: Google Cloud Console から取得した
            OAuth 2.0 クライアントシークレットファイルのパス。

    Returns:
        取得されたプロジェクトID。

    Raises:
        RuntimeError: クライアントシークレットファイルが見つからない、
            または project_id が見つからない場合に発生します。
    """
    path = Path(client_secret_path)
    if not path.exists():
        raise RuntimeError(f"{path.name} が見つかりません。")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key in ["installed", "web"]:
        if key in data and "project_id" in data[key]:
            return data[key]["project_id"]

    raise RuntimeError(f"{path.name} から project_id を取得できませんでした。")


def get_quota_info(creds, project_id):
    """YouTube API のクォータ消費量と上限値を取得します。

    Cloud Monitoring API を使用して、太平洋時間（PT）の本日午前0時から
    現在までの消費量と、プロジェクトに設定されている1日あたりの
    クォータ制限の上限値を取得します。

    Args:
        creds: Google API クライアントライブラリの認証情報オブジェクト。
        project_id: クォータ情報を取得する Google Cloud プロジェクトのID。

    Returns:
        消費されたクォータ（int）と、クォータの上限値（int）のタプル。
    """
    client = monitoring_v3.MetricServiceClient(credentials=creds)
    project_name = f"projects/{project_id}"

    # YouTube Data APIのクォータ制限（Queries per day）は
    # 太平洋時間の午前0時にリセットされるため、
    # 太平洋時間（America/Los_Angeles）基準で
    # 本日の午前0時からのデータを集計する。
    # タイムゾーンの取得に失敗した場合は、
    # 過去24時間（UTC）での集計にフォールバックする。
    try:
        tz_la = ZoneInfo("America/Los_Angeles")
        now_la = datetime.now(tz_la)
        today_start_la = now_la.replace(hour=0, minute=0, second=0, microsecond=0)
        start_sec = int(today_start_la.timestamp())
        end_sec = int(now_la.timestamp())
        if start_sec >= end_sec:
            end_sec = start_sec + 1
    except Exception:  # noqa: BLE001
        now = datetime.now(UTC)
        start_sec = int((now - timedelta(days=1)).timestamp())
        end_sec = int(now.timestamp())

    interval = monitoring_v3.TimeInterval(
        {
            "end_time": {"seconds": end_sec},
            "start_time": {"seconds": start_sec},
        }
    )

    # クォータ消費量 (net_usage) フィルター
    usage_filter = (
        'metric.type="serviceruntime.googleapis.com/quota/rate/net_usage" '
        'AND resource.labels.service="youtube.googleapis.com"'
    )

    # 使用量の取得
    usage_results = client.list_time_series(
        request={
            "name": project_name,
            "filter": usage_filter,
            "interval": interval,
            "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        }
    )
    total_used = 0
    for result in usage_results:
        for point in result.points:
            total_used += point.value.int64_value

    # 上限値 (Limit) の取得。
    # 失敗した場合はデフォルト値 10000 とする
    quota_limit = 10000
    try:
        limit_interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": end_sec},
                "start_time": {"seconds": max(start_sec - 3600, end_sec - 3600)},
            }
        )
        limit_filter = (
            'metric.type="serviceruntime.googleapis.com/quota/limit" '
            'AND resource.labels.service="youtube.googleapis.com" '
            'AND metric.labels.limit_name="defaultPerDayPerProject"'
        )
        limit_results = client.list_time_series(
            request={
                "name": project_name,
                "filter": limit_filter,
                "interval": limit_interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        for result in limit_results:
            if result.points:
                quota_limit = result.points[0].value.int64_value
                break
    except Exception as e:  # noqa: BLE001
        logger.debug(f"クォータ上限値の取得に失敗しました（デフォルト値を使用）: {e}")

    return total_used, quota_limit
