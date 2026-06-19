#!/usr/bin/env python3
# YouTube Data API クォータ使用量・使用率確認スクリプト

import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.cloud import monitoring_v3

# 認証スコープ。YouTubeの読み取りに加え、Cloud Monitoring APIの読み取り権限を追加
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/monitoring.read",
]

TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"


def get_project_id():
    """client_secret.json からプロジェクトIDを自動取得する"""
    if not Path(CLIENT_SECRET_FILE).exists():
        raise RuntimeError(f"{CLIENT_SECRET_FILE} が見つかりません。")

    with open(CLIENT_SECRET_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key in ["installed", "web"]:
        if key in data and "project_id" in data[key]:
            return data[key]["project_id"]

    raise RuntimeError("client_secret.json から project_id を取得できませんでした。")


def load_credentials():
    """OAuth認証情報の読み込みおよび更新。必要に応じて再認証を行う"""
    creds = None

    # token.json が存在する場合は読み込む
    if Path(TOKEN_FILE).exists():
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            pass

    # トークンが存在しない、または無効な場合
    if not creds or not creds.valid:
        # 有効期限切れでリフレッシュトークンがある場合は更新
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        # リフレッシュも失敗したか、初回認証またはスコープ変更時
        if not creds:
            if not Path(CLIENT_SECRET_FILE).exists():
                raise RuntimeError(
                    f"{CLIENT_SECRET_FILE} が見つかりません。Google Cloud Console からダウンロードして配置してください。"
                )

            print(
                "[INFO] 認証スコープの変更、または初回認証のためブラウザで認証を行います..."
            )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # 新しいトークンを保存
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds


def get_quota_info(creds, project_id):
    """Cloud Monitoring API からクォータ制限と過去24時間の消費量を取得する"""
    client = monitoring_v3.MetricServiceClient(credentials=creds)
    project_name = f"projects/{project_id}"

    # 直近24時間のデータを集計
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=1)

    interval = monitoring_v3.TimeInterval(
        {
            "end_time": {"seconds": int(now.timestamp())},
            "start_time": {"seconds": int(start_time.timestamp())},
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

    # 上限値は固定値10000とする
    quota_limit = 10000

    return total_used, quota_limit


def main():
    try:
        project_id = get_project_id()
        print("認証情報を確認中...")
        creds = load_credentials()

        print("クォータ情報を取得中...")
        used, limit = get_quota_info(creds, project_id)

        remaining = max(0, limit - used)
        usage_percent = (used / limit) * 100 if limit > 0 else 0

        print("\n================ YouTube API クォータ状況 ================")
        print(f"  GCP プロジェクト : {project_id}")
        print(f"  本日上限 (Limit) : {limit:,} units")
        print(f"  本日使用 (Used)  : {used:,} units")
        print(f"  残量 (Remaining) : {remaining:,} units")
        print(f"  使用率 (Usage)   : {usage_percent:.2f}%")
        print("==========================================================")

    except Exception as e:
        print(f"\n[エラー] クォータ情報の取得に失敗しました: {e}")
        if "billing to be enabled" in str(e):
            print("\n【原因と対策】")
            print("Cloud Monitoring API からクォータ情報を取得するには、GCPプロジェクトの課金設定（請求先アカウントの紐付け）が必要です。")
            print("課金設定を行っても、YouTube Data APIの無料枠（1日10,000ユニット）および Cloud Monitoring APIの無料枠の範囲内であれば料金は発生しません。")
            print("以下のURLから課金を有効にしてください:")
            print(f"  https://console.developers.google.com/billing/enable?project={project_id}")
            print("\n課金設定を行わずにクォータを確認したい場合は、Google Cloud Console から手動で確認してください:")
            print(f"  https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas?project={project_id}")
        else:
            print(
                "※GCP プロジェクトで 'Cloud Monitoring API' が有効になっているかご確認ください。"
            )


if __name__ == "__main__":
    main()
