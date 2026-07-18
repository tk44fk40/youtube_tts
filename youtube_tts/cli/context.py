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
"""CLI 実行時のアプリケーションコンテキストの初期化を行うモジュールです。"""

import os
import sys
from typing import Any

from youtube_tts import (
    QUOTA_SCOPES,
    AppConfig,
    AudioPlayer,
    ObsClient,
    VoicevoxClient,
    YouTubeAuthenticator,
    YouTubeTtsApp,
    get_project_id,
    setup_logger,
)


def create_app_context(args: Any) -> tuple[YouTubeTtsApp, Any, str | None]:
    """CLI引数に基づいてアプリケーションの設定とクライアント群を初期化します。

    Args:
        args: argparse で解析済みの引数オブジェクト。

    Returns:
        tuple: (YouTubeTtsAppインスタンス,
            YouTubeAPIの認証情報, GCPプロジェクトID)
    """
    if getattr(args, "quota_talk", False):
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
    device = getattr(args, "device", None)
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

    voicevox_url = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")
    speaker_id = int(os.getenv("VOICEVOX_SPEAKER_ID", "3"))
    voicevox_client = VoicevoxClient(
        base_url=voicevox_url, speaker_id=speaker_id
    )

    try:
        voicevox_client.get_speakers()
    except Exception as e:
        logger.warning("VOICEVOX サーバーへの接続確認に失敗しました。")
        logger.warning(
            "      ※VOICEVOXが起動しているか、"
            "ホストURLおよびポート番号が正しいか確認してください。"
        )
        logger.debug(f"  (エラー詳細: {e})")

    quota_check = getattr(args, "quota_check", False)
    scopes = QUOTA_SCOPES if quota_check else None
    authenticator = YouTubeAuthenticator(
        client_secret_path="client_secret.json",
        token_path="token.json",
        scopes=scopes,
    )
    try:
        creds = authenticator.get_credentials()
    except Exception as e:
        logger.error("認証に失敗しました。")
        logger.debug(f"  (エラー詳細: {e})")
        sys.exit(1)

    obs_password = os.getenv("OBS_WEBSOCKET_PASSWORD")
    obs_host = os.getenv("OBS_WEBSOCKET_HOST", "localhost")
    obs_port = int(os.getenv("OBS_WEBSOCKET_PORT", "4455"))

    obs_client = ObsClient(host=obs_host, port=obs_port, password=obs_password)

    project_id = None
    if quota_check:
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

    return app, creds, project_id
