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
"""YouTube API 接続用の認証管理モジュール。

このモジュールは、OAuth2 認証フローを処理し、YouTube API への
アクセス資格情報を取得・保存するための YouTubeAuthenticator クラスを
提供します。
"""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


class YouTubeAuthenticator:
    """YouTube API の OAuth2 認証を管理するクラス。"""

    def __init__(
        self,
        client_secret_path="client_secret.json",
        token_path="token.json",
        scopes=None,
    ):
        """YouTubeAuthenticator クラスを初期化します。

        Args:
            client_secret_path: Google Cloud Console から取得した
                OAuth 2.0 クライアントシークレットファイルのパス。
            token_path: 認証トークンをキャッシュとして保存・ロードする
                ためのファイルパス。
            scopes: 要求する OAuth2 スコープのリスト。デフォルトは
                YouTube への書き込み権限（YOUTUBE_SCOPE）です。
        """
        self.client_secret_path = Path(client_secret_path)
        self.token_path = Path(token_path)
        self.scopes = scopes or [YOUTUBE_SCOPE]

    def get_credentials(self) -> Credentials:
        """有効な OAuth2 資格情報を取得します。

        キャッシュされたトークンが存在し有効であればそれを使用し、
        期限切れの場合は更新を試みます。それ以外の場合は
        ローカルサーバーを起動し、ブラウザ経由で新規に認証を行います。

        Returns:
            認証済みの Credentials オブジェクト。

        Raises:
            RuntimeError: クライアントシークレットファイルが
                見つからない場合に発生します。
        """
        creds = None

        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path), self.scopes
                )
            except Exception:  # noqa: BLE001
                # キャッシュファイルが破損している、又はパースできない場合に、
                # 一旦ファイルを削除して再認証を促す
                try:
                    self.token_path.unlink()
                except OSError:
                    pass

        # トークンファイルが存在しない、または無効な場合
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:  # noqa: BLE001
                    creds = None

            if not creds:
                if not self.client_secret_path.exists():
                    raise RuntimeError(
                        f"{self.client_secret_path.name} was not found. "
                        "Please download it from Google Cloud Console "
                        "and place it in the workspace."
                    )
                # 初回認証、またはトークンの更新に失敗した場合
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret_path), self.scopes
                )
                creds = flow.run_local_server(port=0)

            # 取得した認証情報を保存する
            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        return creds
