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
"""CLI 引数の解析を提供するモジュールです。"""

import argparse
import os

from youtube_tts.constants import (
    DEFAULT_BACKLOG_COUNTS,
    DEFAULT_BACKLOG_SECONDS,
    DEFAULT_CHAT_INTERVAL,
    DEFAULT_CHAT_LOG_FILE,
    DEFAULT_MAX_SPEED,
    DEFAULT_QUOTA_INTERVAL,
    DEFAULT_SPEAKER_ID,
    DEFAULT_SPEED_SCALE,
    DEFAULT_STREAM_CHECK_INTERVAL,
    ENV_VOICEVOX_AUTO_SPEED_BOOST,
    ENV_VOICEVOX_DEVICE,
    ENV_VOICEVOX_MAX_SPEED,
    ENV_VOICEVOX_SPEAKER_ID,
    ENV_VOICEVOX_SPEED_SCALE,
    ENV_VOICEVOX_TTS_TEST,
)


def create_base_parser(description: str) -> argparse.ArgumentParser:
    """Live/Video 共通の引数を持つパーサーを作成します。

    Args:
        description: パーサーの説明テキストです。

    Returns:
        argparse.ArgumentParser: 構築されたベースパーサーオブジェクトです。
    """
    env_speed = DEFAULT_SPEED_SCALE
    if ENV_VOICEVOX_SPEED_SCALE in os.environ:
        try:
            env_speed = float(os.environ[ENV_VOICEVOX_SPEED_SCALE])
        except ValueError:
            pass

    env_auto_boost = os.getenv(ENV_VOICEVOX_AUTO_SPEED_BOOST, "false").lower() in (
        "true",
        "1",
        "yes",
    )

    env_max_speed = DEFAULT_MAX_SPEED
    if ENV_VOICEVOX_MAX_SPEED in os.environ:
        try:
            env_max_speed = float(os.environ[ENV_VOICEVOX_MAX_SPEED])
        except ValueError:
            pass

    env_speaker_id = DEFAULT_SPEAKER_ID
    if ENV_VOICEVOX_SPEAKER_ID in os.environ:
        try:
            env_speaker_id = int(os.environ[ENV_VOICEVOX_SPEAKER_ID])
        except ValueError:
            pass

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--speaker-id",
        type=int,
        default=env_speaker_id,
        help=(
            f"VOICEVOX の話者 ID（デフォルト: {DEFAULT_SPEAKER_ID}）。"
            f"環境変数 {ENV_VOICEVOX_SPEAKER_ID} でも指定可能です。"
        ),
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=env_speed,
        help=(
            f"読み上げスピード（デフォルト: {DEFAULT_SPEED_SCALE}）。"
            f"環境変数 {ENV_VOICEVOX_SPEED_SCALE} でも指定可能です。"
        ),
    )
    parser.add_argument(
        "--auto-speed-boost",
        action="store_true",
        default=env_auto_boost,
        help="キュー滞留時に読上げスピードを自動でブーストする機能を有効にする",
    )
    parser.add_argument(
        "--max-speed",
        type=float,
        default=env_max_speed,
        help=(
            "自動スピードブースト時の最大速度"
            f"（デフォルト: {DEFAULT_MAX_SPEED}）。"
            f"最大{DEFAULT_MAX_SPEED}までに制限されます。"
        ),
    )
    parser.add_argument(
        "video_url_or_id",
        nargs="?",
        default=None,
        help="YouTube Live配信のURLまたは動画IDを指定します。",
    )
    parser.add_argument(
        "-d",
        "--device",
        default=os.getenv(ENV_VOICEVOX_DEVICE),
        help="出力オーディオデバイス名またはIDを指定します。",
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
    parser.add_argument(
        "--chat-interval",
        type=float,
        default=DEFAULT_CHAT_INTERVAL,
        help=(
            "コメント取得の最短時間（秒）を指定します。"
            f"デフォルトは{int(DEFAULT_CHAT_INTERVAL)}秒です。"
        ),
    )
    parser.add_argument(
        "--chat-log",
        default=DEFAULT_CHAT_LOG_FILE,
        help=(
            "チャットログの保存先パスを指定します\n"
            f"（デフォルト: {DEFAULT_CHAT_LOG_FILE}）。"
        ),
    )
    parser.add_argument(
        "--quota-interval",
        type=float,
        default=DEFAULT_QUOTA_INTERVAL,
        help=(
            "使用量の取得の最短時間（秒）を指定します。"
            f"デフォルトは{int(DEFAULT_QUOTA_INTERVAL)}秒です。"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="詳細ログ（DEBUGタグ）を出力します。",
    )
    parser.add_argument(
        "--no-manage-container",
        action="store_true",
        help="VOICEVOX Engine コンテナの自動起動・管理機能を無効化します。",
    )
    return parser


def create_live_parser() -> argparse.ArgumentParser:
    """Live用のパーサーを作成します。

    Returns:
        argparse.ArgumentParser: Live配信チャット用のパーサーオブジェクトです。
    """
    parser = create_base_parser("YouTube Live Chat TTS with VOICEVOX")
    _TTS_TEST_DEFAULT = "ぴんぽーん！チャット読上げのテストです"
    parser.add_argument(
        "--tts-test",
        nargs="?",
        const=_TTS_TEST_DEFAULT,
        default=os.getenv(ENV_VOICEVOX_TTS_TEST) or None,
        metavar="TEXT",
        help=(
            "起動時に自分のライブ配信であれば指定したテキストを読み上げます。"
            f"テキストを省略した場合は「{_TTS_TEST_DEFAULT}」を使用します。"
            f"環境変数 {ENV_VOICEVOX_TTS_TEST} でも指定可能です。"
        ),
    )
    parser.add_argument(
        "--backlog-seconds",
        type=int,
        default=DEFAULT_BACKLOG_SECONDS,
        help=(
            "起動時に読み上げる過去コメントの遡り時間（秒）を指定します。"
            "-1を指定した場合は過去コメントをすべて読み上げます。"
            f"デフォルトは{DEFAULT_BACKLOG_SECONDS}秒です。"
        ),
    )
    parser.add_argument(
        "--stream-check-interval",
        type=float,
        default=DEFAULT_STREAM_CHECK_INTERVAL,
        help=(
            "配信アクティブ状態チェックの最短時間(秒) を指定します。"
            f"デフォルトは{int(DEFAULT_STREAM_CHECK_INTERVAL)}秒です。"
        ),
    )
    return parser


def create_video_parser() -> argparse.ArgumentParser:
    """Video用のパーサーを作成します。

    Returns:
        argparse.ArgumentParser: 動画コメント用パーサーです。
    """
    parser = create_base_parser("YouTube Video/Archive Chat TTS with VOICEVOX")
    parser.add_argument(
        "--backlog-counts",
        type=int,
        default=DEFAULT_BACKLOG_COUNTS,
        help=(
            "起動時に読み込む過去コメント（バックログ）の件数を指定します。"
            f"デフォルトは{DEFAULT_BACKLOG_COUNTS}件です。負数を指定すると制限なしになります。"
        ),
    )
    return parser
