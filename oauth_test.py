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
"""OAuth 認証を行い、トークンを保存するスクリプトです。"""

from __future__ import annotations

import sys

from youtube_tts import YouTubeAuthenticator, get_logger

TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"


def main() -> None:
    """OAuth 認証を実行し、アクセストークンを取得および保存します。"""
    logger = get_logger()
    try:
        authenticator = YouTubeAuthenticator(
            client_secret_path=CLIENT_SECRET_FILE, token_path=TOKEN_FILE
        )
        creds = authenticator.get_credentials()
        logger.info("認証成功: %s...", creds.token[:32])
    except Exception as e:  # noqa: BLE001
        logger.error("認証に失敗しました: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
