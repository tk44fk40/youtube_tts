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
import argparse
import os
import sys

from youtube_tts import AudioPlayer, VoicevoxClient, get_logger

logger = get_logger()

DEFAULT_HOST = "http://127.0.0.1:50021"
DEFAULT_SPEAKER = 3
DEFAULT_TEXT = "これは、ボイスボックスの発声テストです。"
DEFAULT_OUTPUT = "test.wav"
DEFAULT_VOLUME = 1.0


def list_speakers(client: VoicevoxClient):
    try:
        speakers = client.get_speakers()
    except Exception as e:  # noqa: BLE001
        logger.error(f"{e}")
        sys.exit(1)

    print(f"{'ID':<6} | {'話者名':<15} | {'スタイル':<15}")
    print("-" * 45)
    for spk in speakers:
        name = spk.get("name", "Unknown")
        for style in spk.get("styles", []):
            style_name = style.get("name", "")
            style_id = style.get("id", "")
            print(f"{style_id:<6} | {name:<15} | {style_name:<15}")


def main():
    env_speed = 1.0
    if "VOICEVOX_SPEED_SCALE" in os.environ:
        try:
            env_speed = float(os.environ["VOICEVOX_SPEED_SCALE"])
        except ValueError:
            pass

    parser = argparse.ArgumentParser(
        description="VOICEVOX 発声テストスクリプト"
    )
    parser.add_argument(
        "-t", "--text", default=DEFAULT_TEXT, help="発声させるテキスト"
    )
    parser.add_argument(
        "-s",
        "--speaker",
        type=int,
        default=DEFAULT_SPEAKER,
        help="話者スタイルID",
    )
    parser.add_argument(
        "-o", "--output", default=DEFAULT_OUTPUT, help="保存先WAVファイルパス"
    )
    parser.add_argument(
        "-H", "--host", default=DEFAULT_HOST, help="VOICEVOXのURL"
    )
    parser.add_argument(
        "-d", "--device", default=None, help="出力オーディオデバイス名またはID"
    )
    parser.add_argument(
        "-r",
        "--samplerate",
        type=int,
        default=None,
        help="生成サンプリングレート（未指定時はデバイスの既定値を使用）",
    )
    parser.add_argument(
        "-v",
        "--volume",
        type=float,
        default=DEFAULT_VOLUME,
        help="音量比（デフォルト: 1.0）",
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
        "--list-speakers",
        action="store_true",
        help="利用可能な話者スタイル一覧を表示",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="オーディオデバイス一覧を表示",
    )
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="再生をスキップしてファイル保存のみ行う",
    )

    args = parser.parse_args()

    client = VoicevoxClient(base_url=args.host, speaker_id=args.speaker)

    if args.list_speakers:
        list_speakers(client)
        return

    player = None
    if args.list_devices or not args.no_play:
        player = AudioPlayer(default_device=args.device)

    if args.list_devices:
        if player is not None:
            print(player.query_devices())
        return

    # 出力デバイスの規定サンプリングレートを調べる
    target_sample_rate = args.samplerate
    if target_sample_rate is None and not args.no_play and player is not None:
        target_sample_rate = player.target_sample_rate
        logger.info(
            f"出力デバイス: {args.device or 'Default'} "
            f"(想定サンプリングレート: {target_sample_rate}Hz)"
        )

    try:
        logger.info(f"音声合成中: 「{args.text}」 (話者ID: {args.speaker})")
        wav_content = client.synthesize(
            text=args.text,
            volume_scale=args.volume,
            speed_scale=args.speed,
            target_sample_rate=target_sample_rate,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"音声合成に失敗しました: {e}")
        sys.exit(1)

    # WAVファイル保存
    try:
        with open(args.output, "wb") as f:
            f.write(wav_content)
        logger.info(f"音声ファイルを保存しました: {args.output}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"ファイルの保存に失敗しました: {e}")

    if not args.no_play:
        logger.info(
            f"再生中... (サンプリングレート: "
            f"{target_sample_rate or player.target_sample_rate}Hz)"
        )
        try:
            player.play_wav(
                wav_content,
                device=args.device,
                target_sample_rate=target_sample_rate,
            )
            logger.info("再生完了")
        except Exception as e:  # noqa: BLE001
            logger.error(f"再生に失敗しました: {e}")
            print("\n利用可能なオーディオデバイス一覧:", file=sys.stderr)
            print(player.query_devices())
            print(
                "\nヒント: --device 引数で適切なデバイス名または"
                "IDを指定して実行してください。",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
