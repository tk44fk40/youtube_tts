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
"""VOICEVOX を使用して YouTube Live チャットコメントを読み上げるスクリプトです。"""

from __future__ import annotations

import os
import sys

from youtube_tts import YouTubeLiveChatClient, extract_video_id
from youtube_tts.cli.context import create_app_context
from youtube_tts.cli.parser import create_live_parser
from youtube_tts.runners.live import LiveRunner


def main() -> None:
    """VOICEVOX を使用した YouTube Live チャット読み上げの
    メイン処理を実行します。
    """
    parser = create_live_parser()
    args = parser.parse_args()

    app, creds, project_id = create_app_context(args)

    live_client = YouTubeLiveChatClient(creds, verbose=args.verbose)

    if args.video_url_or_id:
        video_id = extract_video_id(args.video_url_or_id)
        chat_url = (
            f"https://www.youtube.com/live_chat?v={video_id}&is_popout=1"
        )
    else:
        try:
            video_id, chat_url = live_client.get_current_live_video_id()
        except RuntimeError as e:
            app.logger.error(f"ライブ動画IDの自動検出に失敗しました: {e}")
            sys.exit(1)

        app.logger.info(f"現在のライブ配信動画IDを自動検出しました: {video_id}")
        app.logger.info(f"チャットURL: {chat_url}")

    app.logger.info(f"video_id: {video_id}")

    obs_source_name = os.getenv("OBS_BROWSER_SOURCE_NAME", "チャット")
    app.obs_client.update_chat_url(obs_source_name, chat_url)

    runner = LiveRunner(
        app=app,
        live_client=live_client,
        video_id=video_id,
        creds=creds,
        quota_check=getattr(args, "quota_check", False),
        quota_talk=getattr(args, "quota_talk", False),
        tts_test=getattr(args, "tts_test", None),
        chat_interval=args.chat_interval,
        quota_interval=args.quota_interval,
        stream_check_interval=args.stream_check_interval,
        project_id=project_id,
        verbose=args.verbose,
        backlog_seconds=args.backlog_seconds,
    )
    
    try:
        runner.run()
    except Exception:
        app.logger.exception("予期しないエラーが発生しました。")


if __name__ == "__main__":
    main()
