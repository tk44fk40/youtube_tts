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
from .logger import get_logger

logger = get_logger()


class ObsClient:
    def __init__(self, host="localhost", port=4455, password=None):
        self.host = host
        self.port = port
        self.password = password

        # obs-websocket-py のインポートを一度だけ試みてキャッシュする
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
        if not source_name:
            return False

        if not self.password:
            logger.info("[OBS] OBS_WEBSOCKET_PASSWORD is not set; skipping OBS update")
            return False

        if not self._available:
            logger.warning(
                "[OBS] obs-websocket library is not installed; "
                "install obs-websocket-py to enable OBS integration"
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
        except Exception as e:
            logger.error(f"[OBS] チャットURL設定失敗 (エラー詳細: {e})")
            logger.error(
                "      ※OBS Studioが起動しているか、"
                "およびWebSocketサーバー(ポート4455)の"
                "設定を確認してください。"
            )
            return False
