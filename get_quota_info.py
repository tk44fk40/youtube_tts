#!/usr/bin/env python3
#
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
"""YouTube Data API のクォータ使用状況を確認するスクリプトです。"""

from __future__ import annotations

from youtube_tts import (
    QUOTA_SCOPES,
    YouTubeAuthenticator,
    get_logger,
    get_project_id,
    get_quota_info,
)

SCOPES = QUOTA_SCOPES

TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"


def main() -> None:
    """GCP プロジェクトのクォータ情報を取得してコンソールに出力します。"""
    logger = get_logger()
    project_id: str | None = None
    try:
        project_id = get_project_id()
        logger.info("認証情報を確認中...")
        authenticator = YouTubeAuthenticator(
            client_secret_path=CLIENT_SECRET_FILE,
            token_path=TOKEN_FILE,
            scopes=SCOPES,
        )
        creds = authenticator.get_credentials()

        logger.info("クォータ情報を取得中...")
        used, limit = get_quota_info(creds, project_id)

        remaining = max(0, limit - used)
        usage_percent = (used / limit) * 100 if limit > 0 else 0

        print(
            "\n================ YouTube API クォータ状況 ================"
        )
        print(f"  GCP プロジェクト : {project_id}")
        print(f"  本日上限 (Limit) : {limit:,} units")
        print(f"  本日使用 (Used)  : {used:,} units")
        print(f"  残量 (Remaining) : {remaining:,} units")
        print(f"  使用率 (Usage)   : {usage_percent:.2f}%")
        print("==========================================================")

    except Exception as e:  # noqa: BLE001
        logger.error(f"クォータ情報の取得に失敗しました: {e}")
        if "billing to be enabled" in str(e):
            print("\n【原因と対策】")
            print(
                "Cloud Monitoring API からクォータ情報を取得するには、"
                "GCP プロジェクトの課金設定（請求先アカウントの紐付け）"
                "が必要です。"
            )
            print(
                "課金設定を行っても、YouTube Data API の無料枠"
                "（1 日 10,000 ユニット）および"
                " Cloud Monitoring API の"
                "無料枠の範囲内であれば料金は発生しません。"
            )
            print("以下の URL から課金を有効にしてください:")
            if project_id:
                print(
                    "  https://console.developers.google.com/billing/enable"
                    f"?project={project_id}"
                )
            print(
                "\n課金設定を行わずにクォータを確認したい場合は、"
                "Google Cloud Console から手動で確認してください:"
            )
            if project_id:
                print(
                    "  https://console.cloud.google.com/apis/api/"
                    f"youtube.googleapis.com/quotas?project={project_id}"
                )
        else:
            print(
                "※ GCP プロジェクトで 'Cloud Monitoring API' が"
                "有効になっているかご確認ください。"
            )


if __name__ == "__main__":
    main()
