#!/usr/bin/env python3
# YouTube Data API クォータ使用量・使用率確認スクリプト

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from youtube_tts import (
    YouTubeAuthenticator,
    QUOTA_SCOPES,
    get_project_id,
    get_quota_info,
)

SCOPES = QUOTA_SCOPES

TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"


def main():
    try:
        project_id = get_project_id()
        print("認証情報を確認中...")
        authenticator = YouTubeAuthenticator(
            client_secret_path=CLIENT_SECRET_FILE,
            token_path=TOKEN_FILE,
            scopes=SCOPES
        )
        creds = authenticator.get_credentials()

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
