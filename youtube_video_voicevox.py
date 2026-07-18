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
"""VOICEVOX を使用して YouTube 動画のコメントを読み上げるスクリプトです。"""

from __future__ import annotations

import sys

from youtube_tts import YouTubeVideoClient, extract_video_id
from youtube_tts.cli.context import create_app_context
from youtube_tts.cli.parser import create_video_parser
from youtube_tts.runners.video import VideoRunner


def main() -> None:
    """VOICEVOX を使用した YouTube 動画コメント読み上げの
    メイン処理を実行します。
    """
    parser = create_video_parser()
    args = parser.parse_args()

    if not args.video_url_or_id:
        parser.print_help()
        sys.exit(1)
    video_id = extract_video_id(args.video_url_or_id)

    try:
        app, creds, project_id = create_app_context(args)
    except KeyboardInterrupt:
        sys.exit(130)

    video_client = YouTubeVideoClient(creds)
    app.logger.info(f"video_id: {video_id}")

    runner = VideoRunner(
        app=app,
        video_client=video_client,
        video_id=video_id,
        creds=creds,
        quota_check=getattr(args, "quota_check", False),
        quota_talk=getattr(args, "quota_talk", False),
        quota_interval=args.quota_interval,
        project_id=project_id,
        chat_interval=args.chat_interval,
        verbose=args.verbose,
        backlog_counts=args.backlog_counts,
    )

    try:
        runner.run()
    except KeyboardInterrupt:
        app.logger.info("ユーザーによって処理が中断されました。")
    except Exception:
        app.logger.exception("予期しないエラーが発生しました。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
