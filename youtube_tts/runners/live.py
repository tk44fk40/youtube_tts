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
"""YouTube Live 配信用のランナーモジュールです。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from youtube_tts.live import YouTubeLiveChatClient

from .base import BaseRunner

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp


class LiveRunner(BaseRunner):
    """ライブ配信のチャット監視と再生を管理するランナークラスです。"""

    def __init__(
        self,
        app: YouTubeTtsApp,
        live_client: YouTubeLiveChatClient,
        video_id: str,
        creds: Any | None = None,
        quota_check: bool = False,
        quota_talk: bool = False,
        tts_test: str | None = None,
        chat_interval: float = 20.0,
        quota_interval: float = 180.0,
        stream_check_interval: float = 180.0,
        project_id: str | None = None,
        verbose: bool = False,
        backlog_seconds: int = 10,
    ) -> None:
        """初期化します。"""
        super().__init__(app)
        self.live_client = live_client
        self.video_id = video_id
        self.creds = creds
        self.quota_check = quota_check
        self.quota_talk = quota_talk
        self.tts_test = tts_test
        self.chat_interval = chat_interval
        self.quota_interval = quota_interval
        self.stream_check_interval = stream_check_interval
        self.project_id = project_id
        self.app.verbose = verbose
        self.backlog_seconds = backlog_seconds

    def run_worker(self) -> None:
        """ライブワーカーを実行します。"""
        from youtube_tts.workers.live import live_worker

        live_worker(
            app=self.app,
            live_client=self.live_client,
            video_id=self.video_id,
            creds=self.creds,
            quota_check=self.quota_check,
            quota_talk=self.quota_talk,
            tts_test=self.tts_test,
            chat_interval=self.chat_interval,
            quota_interval=self.quota_interval,
            stream_check_interval=self.stream_check_interval,
            project_id=self.project_id,
            verbose=self.app.verbose,
            backlog_seconds=self.backlog_seconds,
        )
