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
"""YouTube 動画・アーカイブ用のランナーモジュールです。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from youtube_tts.video import YouTubeVideoClient

from .base import BaseRunner

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp


class VideoRunner(BaseRunner):
    """動画・アーカイブのコメント監視と再生を管理するランナークラスです。"""

    def __init__(
        self,
        app: YouTubeTtsApp,
        video_client: YouTubeVideoClient,
        video_id: str,
        creds: Any | None = None,
        quota_check: bool = False,
        quota_talk: bool = False,
        quota_interval: float = 180.0,
        project_id: str | None = None,
        chat_interval: float = 20.0,
        verbose: bool = False,
        backlog_counts: int = 100,
    ) -> None:
        """初期化します。"""
        super().__init__(app)
        self.video_client = video_client
        self.video_id = video_id
        self.creds = creds
        self.quota_check = quota_check
        self.quota_talk = quota_talk
        self.quota_interval = quota_interval
        self.project_id = project_id
        self.chat_interval = chat_interval
        self.app.verbose = verbose
        self.backlog_counts = backlog_counts

    def run_worker(self) -> None:
        """動画ワーカーを実行します。"""
        from youtube_tts.workers.video import video_worker

        video_worker(
            app=self.app,
            video_client=self.video_client,
            video_id=self.video_id,
            # 将来的に workers/video.py を修正して creds,
            # quota_check 等を受け取るようにするが、
            # 現在のインターフェースに合わせて呼び出す
            chat_interval=self.chat_interval,
            verbose=self.app.verbose,
            backlog_counts=self.backlog_counts,
        )
