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
"""VOICEVOX を使用して YouTube Live チャットコメントを
読み上げるスクリプトです。
"""

from __future__ import annotations

import argparse
import os
import sys

from youtube_tts import (
    QUOTA_SCOPES,
    AppConfig,
    AudioPlayer,
    ObsClient,
    VoicevoxClient,
    YouTubeAuthenticator,
    YouTubeLiveChatClient,
    YouTubeTtsApp,
    extract_video_id,
    get_project_id,
    setup_logger,
)

# 定数定義
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")
SPEAKER_ID = int(os.getenv("VOICEVOX_SPEAKER_ID", "3"))


def main() -> None:
    """VOICEVOX を使用した YouTube Live チャット読み上げの
    メイン処理を実行します。
    """
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
        description="YouTube Live Chat TTS with VOICEVOX"
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
        help="YouTube Live配信のURLまたは動画ID",
    )
    parser.add_argument(
        "-d",
        "--device",
        default=os.getenv("VOICEVOX_DEVICE"),
        help="出力オーディオデバイス名またはID",
    )
    parser.add_argument(
        "-q",
        "--quota-check",
        action="store_true",
        help="デバッグ用のクォータ情報確認機能を有効にする",
    )
    parser.add_argument(
        "--quota-talk",
        action="store_true",
        help="クォータ使用量の読上げ機能を有効にする",
    )
    _TTS_TEST_DEFAULT = "ぴんぽーん！チャット読上げのテストです"
    parser.add_argument(
        "--tts-test",
        nargs="?",
        const=_TTS_TEST_DEFAULT,
        default=os.getenv("VOICEVOX_TTS_TEST") or None,
        metavar="TEXT",
        help=(
            "起動時に自分のライブ配信であれば"
            "指定したテキストを読み上げる。"
            f"テキストを省略した場合は「{_TTS_TEST_DEFAULT}」を使用。"
            "環境変数 VOICEVOX_TTS_TEST でも指定可能。"
        ),
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
        "--backlog-seconds",
        type=int,
        default=10,
        help=(
            "起動時に読み上げる過去コメントの遡り時間（秒）。"
            "-1を指定した場合は過去コメントをすべて読み上げます。"
            "デフォルトは10秒。"
        ),
    )
    parser.add_argument(
        "--quota-interval",
        type=float,
        default=180.0,
        help=("使用量の取得の最短時間（秒）。デフォルトは180秒。"),
    )
    parser.add_argument(
        "--stream-check-interval",
        type=float,
        default=180.0,
        help=(
            "配信アクティブ状態チェックの最短時間（秒）。デフォルトは180秒。"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="詳細ログ（DEBUGタグ）を出力する",
    )
    args = parser.parse_args()

    if args.quota_talk:
        args.quota_check = True

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

    scopes = QUOTA_SCOPES if args.quota_check else None
    authenticator = YouTubeAuthenticator(
        client_secret_path=CLIENT_SECRET_FILE,
        token_path=TOKEN_FILE,
        scopes=scopes,
    )
    try:
        creds = authenticator.get_credentials()
    except Exception as e:
        logger.error("[ERROR] 認証に失敗しました。")
        if args.verbose:
            logger.debug(f"  (エラー詳細: {e})")
        sys.exit(1)

    live_client = YouTubeLiveChatClient(creds, verbose=args.verbose)

    if args.video_url_or_id:
        video_id = extract_video_id(args.video_url_or_id)
        chat_url = f"https://www.youtube.com/live_chat?v={video_id}&is_popout=1"
    else:
        try:
            video_id, chat_url = live_client.get_current_live_video_id()
        except RuntimeError as e:
            logger.error(f"[ERROR] ライブ動画IDの自動検出に失敗しました: {e}")
            sys.exit(1)

        logger.info(f"auto-detected current live video_id: {video_id}")
        logger.info(f"chat URL: {chat_url}")

    logger.info(f"video_id: {video_id}")

    obs_password = os.getenv("OBS_WEBSOCKET_PASSWORD")
    obs_host = os.getenv("OBS_WEBSOCKET_HOST", "localhost")
    obs_port = int(os.getenv("OBS_WEBSOCKET_PORT", "4455"))
    obs_source_name = os.getenv("OBS_BROWSER_SOURCE_NAME", "チャット")

    obs_client = ObsClient(host=obs_host, port=obs_port, password=obs_password)
    obs_client.update_chat_url(obs_source_name, chat_url)

    project_id = None
    if args.quota_check:
        try:
            project_id = get_project_id()
        except Exception as e:
            logger.warning(
                "クォータチェックを有効にできませんでした "
                f"(project_id 取得失敗): {e}"
            )
            args.quota_check = False
            args.quota_talk = False

    app = YouTubeTtsApp(
        config=config,
        voicevox_client=voicevox_client,
        audio_player=audio_player,
        obs_client=obs_client,
        logger=logger,
    )

    try:
        app.run_live(
            live_client=live_client,
            video_id=video_id,
            creds=creds,
            quota_check=args.quota_check,
            quota_talk=args.quota_talk,
            tts_test=args.tts_test,
            chat_interval=args.chat_interval,
            quota_interval=args.quota_interval,
            stream_check_interval=args.stream_check_interval,
            project_id=project_id,
            verbose=args.verbose,
            backlog_seconds=args.backlog_seconds,
        )
    except Exception:
        logger.exception("Unexpected error")


if __name__ == "__main__":
    main()
