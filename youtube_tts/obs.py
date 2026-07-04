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
"""OBS Studio との連携を行うモジュールです。

このモジュールは、obs-websocket-py ライブラリを介して OBS Studio の
WebSocket サーバーに接続し、各種操作を行う ObsClient クラスを
提供します。
"""

from __future__ import annotations

from .logger import get_logger

logger = get_logger()


class ObsClient:
    """OBS Studio の WebSocket 接続を管理するクラスです。"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4455,
        password: str | None = None,
    ) -> None:
        """ObsClient クラスを初期化します。

        Args:
            host: OBS Studio の WebSocket サーバーのホスト名。
            port: WebSocket サーバーのポート番号。
            password: WebSocket サーバーの認証パスワード。
                未設定の場合は接続をスキップします。
        """
        self.host = host
        self.port = port
        self.password = password

        # obs-websocket-py のインポートを一度だけ試みてキャッシュします。
        try:
            from obswebsocket import obsws
            from obswebsocket import requests as obs_requests

            self._obsws = obsws
            self._obs_requests = obs_requests
            self._available = True
        except ImportError:
            self._obsws = None
            self._obs_requests = None
            self._available = False

    def update_chat_url(self, source_name: str, url: str) -> bool:
        """OBS Studio の指定したソースの URL を更新します。

        Args:
            source_name: URL を更新する OBS のブラウザソース名。
                空文字列の場合は何も行わずに False を返します。
            url: 設定するチャット表示用 URL。

        Returns:
            設定に成功した場合は True、スキップまたは失敗した場合は False を
            返します。
        """
        if not source_name:
            return False

        if not self.password:
            logger.info(
                "[OBS] OBS_WEBSOCKET_PASSWORD が設定されていません。"
                "OBSの更新をスキップします。"
            )
            return False

        if not self._available:
            logger.warning(
                "[OBS] obs-websocket "
                "ライブラリがインストールされていません。"
                "OBS連携を有効にするには obs-websocket-py を"
                "インストールしてください。"
            )
            return False

        try:
            ws = self._obsws(self.host, self.port, self.password)
            ws.connect()
            ws.call(
                self._obs_requests.SetInputSettings(
                    inputName=source_name, inputSettings={"url": url}
                )
            )
            ws.disconnect()
            logger.info("[OBS] チャットURL設定成功")
            logger.info(f"      URL: {url}")
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"[OBS] チャットURL設定失敗 (エラー詳細: {e})")
            logger.error(
                "      ※OBS Studioが起動しているか、"
                "およびWebSocketサーバー(ポート4455)の"
                "設定を確認してください。"
            )
            return False
