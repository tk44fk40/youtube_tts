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


def create_base_parser(description: str) -> argparse.ArgumentParser:
    """Live/Video 共通の引数を持つパーサーを作成します。"""
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

    parser = argparse.ArgumentParser(description=description)
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
        help="キュー滞留時に読上げスピードを自動でブーストする機能を有効にする",
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
        help="YouTube Live配信のURLまたは動画IDを指定します。",
    )
    parser.add_argument(
        "-d",
        "--device",
        default=os.getenv("VOICEVOX_DEVICE"),
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
        default=20.0,
        help="コメント取得の最短時間（秒）を指定します。デフォルトは20秒です。",
    )
    parser.add_argument(
        "--chat-log",
        default="chat_log.jsonl",
        help="チャットログの保存先パスを指定します\n"
        "（デフォルト: chat_log.jsonl）。",
    )
    parser.add_argument(
        "--quota-interval",
        type=float,
        default=180.0,
        help="使用量の取得の最短時間（秒）を指定します。デフォルトは180秒です。",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="詳細ログ（DEBUGタグ）を出力します。",
    )
    return parser


def create_live_parser() -> argparse.ArgumentParser:
    """Live用のパーサーを作成します。"""
    parser = create_base_parser("YouTube Live Chat TTS with VOICEVOX")
    _TTS_TEST_DEFAULT = "ぴんぽーん！チャット読上げのテストです"
    parser.add_argument(
        "--tts-test",
        nargs="?",
        const=_TTS_TEST_DEFAULT,
        default=os.getenv("VOICEVOX_TTS_TEST") or None,
        metavar="TEXT",
        help=(
            "起動時に自分のライブ配信であれば指定したテキストを読み上げます。"
            f"テキストを省略した場合は「{_TTS_TEST_DEFAULT}」を使用します。"
            "環境変数 VOICEVOX_TTS_TEST でも指定可能です。"
        ),
    )
    parser.add_argument(
        "--backlog-seconds",
        type=int,
        default=10,
        help=(
            "起動時に読み上げる過去コメントの遡り時間（秒）を指定します。"
            "-1を指定した場合は過去コメントをすべて読み上げます。"
            "デフォルトは10秒です。"
        ),
    )
    parser.add_argument(
        "--stream-check-interval",
        type=float,
        default=180.0,
        help=(
            "配信アクティブ状態チェックの最短時間(秒) を指定します。"
            "デフォルトは180秒です。"
        ),
    )
    return parser


def create_video_parser() -> argparse.ArgumentParser:
    """Video用のパーサーを作成します。"""
    parser = create_base_parser("YouTube Video/Archive Chat TTS with VOICEVOX")
    parser.add_argument(
        "--backlog-counts",
        type=int,
        default=100,
        help=(
            "起動時に読み込む過去コメント（バックログ）の件数を指定します。"
            "デフォルトは100件です。負数を指定すると制限なしになります。"
        ),
    )
    return parser
