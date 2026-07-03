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
"""Read YouTube video and archive comments using VOICEVOX.

YouTubeの動画および過去配信アーカイブのコメントを VOICEVOX で読み上げる。
"""

import argparse
import os
import sys

from youtube_tts import (
    AppConfig,
    AudioPlayer,
    ObsClient,
    VoicevoxClient,
    YouTubeAuthenticator,
    YouTubeTtsApp,
    YouTubeVideoClient,
    extract_video_id,
    setup_logger,
)

# Constant definitions
# 定数定義
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")
SPEAKER_ID = int(os.getenv("VOICEVOX_SPEAKER_ID", "3"))


def main():
    env_speed = 1.0
    if "VOICEVOX_SPEED_SCALE" in os.environ:
        try:
            env_speed = float(os.environ["VOICEVOX_SPEED_SCALE"])
        except ValueError:
            pass

    env_auto_boost = os.getenv(
        "VOICEVOX_AUTO_SPEED_BOOST", "false"
    ).lower() in ("true", "1", "yes")

    env_max_speed = 2.2
    if "VOICEVOX_MAX_SPEED" in os.environ:
        try:
            env_max_speed = float(os.environ["VOICEVOX_MAX_SPEED"])
        except ValueError:
            pass

    parser = argparse.ArgumentParser(
        description="YouTube Video Comment TTS with VOICEVOX"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=env_speed,
        help=(
            "読み上げスピード（デフォルト: 1.0）。"
            "環境変数 VOICEVOX_SPEED_SCALE でも指定可能です。"
        ),
    )
    parser.add_argument(
        "--auto-speed-boost",
        action="store_true",
        default=env_auto_boost,
        help=(
            "キュー滞留時に読上げスピードを自動でブーストする機能を有効にする"
        ),
    )
    parser.add_argument(
        "--max-speed",
        type=float,
        default=env_max_speed,
        help=(
            "自動スピードブースト時の最大速度（デフォルト: 2.2）。"
            "最大2.2までに制限されます。"
        ),
    )
    parser.add_argument(
        "video_url_or_id",
        nargs="?",
        default=None,
        help="YouTube動画・アーカイブのURLまたは動画ID",
    )
    parser.add_argument(
        "-d",
        "--device",
        default=os.getenv("VOICEVOX_DEVICE"),
        help="出力オーディオデバイス名またはID",
    )
    parser.add_argument(
        "--chat-interval",
        type=float,
        default=20.0,
        help=("コメント取得の最短時間（秒）。デフォルトは20秒。"),
    )
    parser.add_argument(
        "--chat-log",
        default="chat_log.jsonl",
        help=("チャットログの保存先パス（デフォルト: chat_log.jsonl）。"),
    )
    parser.add_argument(
        "--backlog-counts",
        type=int,
        default=100,
        help=(
            "起動時に取得・読み上げる過去コメントの最大件数。"
            "-1を指定した場合は過去コメントをすべて読み上げます。"
            "デフォルトは100件。"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="詳細ログ（DEBUGタグ）を出力する",
    )
    args = parser.parse_args()

    logger = setup_logger(verbose=args.verbose)

    config = AppConfig(
        dictionary_path="dictionary.txt",
        ng_words_path="ng_words.txt",
        volume_path="volume.txt",
        chat_log_path=args.chat_log,
    )

    if "VOICEVOX_VOLUME_SCALE" in os.environ:
        try:
            config.volume_scale = float(os.environ["VOICEVOX_VOLUME_SCALE"])
        except Exception:
            pass

    config.reload_if_changed()
    config.speed_scale = args.speed
    config.auto_speed_boost = args.auto_speed_boost
    config.max_speed = min(args.max_speed, 2.2)

    dev_id = None
    device = args.device
    if device is not None:
        try:
            dev_id = int(device)
        except ValueError:
            dev_id = device

        try:
            import sounddevice as sd

            device_info = sd.query_devices(dev_id, "output")
            logger.info(
                f"出力デバイス: {device_info['name']} "
                f"(ID: {device_info['index']})"
            )
        except Exception as e:
            logger.warning(f"デバイス情報の取得に失敗しました: {e}")

    audio_player = AudioPlayer(default_device=dev_id)
    voicevox_client = VoicevoxClient(
        base_url=VOICEVOX_URL, speaker_id=SPEAKER_ID
    )

    try:
        voicevox_client.get_speakers()
    except Exception as e:
        logger.warning("VOICEVOX サーバーへの接続確認に失敗しました。")
        logger.warning(
            "      ※VOICEVOXが起動しているか、"
            "ホストURLおよびポート番号が正しいか確認してください。"
        )
        if args.verbose:
            logger.debug(f"  (エラー詳細: {e})")

    authenticator = YouTubeAuthenticator(
        client_secret_path=CLIENT_SECRET_FILE,
        token_path=TOKEN_FILE,
        scopes=None,
    )
    try:
        creds = authenticator.get_credentials()
    except Exception as e:
        logger.error("[ERROR] 認証に失敗しました。")
        if args.verbose:
            logger.debug(f"  (エラー詳細: {e})")
        sys.exit(1)

    video_client = YouTubeVideoClient(creds, verbose=args.verbose)

    if args.video_url_or_id:
        video_id = extract_video_id(args.video_url_or_id)
        chat_url = f"https://www.youtube.com/live_chat?v={video_id}&is_popout=1"
    else:
        logger.error("[ERROR] 動画URLまたはIDの指定が必要です。")
        sys.exit(1)

    logger.info(f"video_id: {video_id}")

    obs_password = os.getenv("OBS_WEBSOCKET_PASSWORD")
    obs_host = os.getenv("OBS_WEBSOCKET_HOST", "localhost")
    obs_port = int(os.getenv("OBS_WEBSOCKET_PORT", "4455"))
    obs_source_name = os.getenv("OBS_BROWSER_SOURCE_NAME", "チャット")

    obs_client = ObsClient(host=obs_host, port=obs_port, password=obs_password)
    obs_client.update_chat_url(obs_source_name, chat_url)

    app = YouTubeTtsApp(
        config=config,
        voicevox_client=voicevox_client,
        audio_player=audio_player,
        obs_client=obs_client,
        logger=logger,
    )

    try:
        app.run_video(
            video_client=video_client,
            video_id=video_id,
            chat_interval=args.chat_interval,
            verbose=args.verbose,
            backlog_counts=args.backlog_counts,
        )
    except Exception:
        logger.exception("Unexpected error")


if __name__ == "__main__":
    main()
