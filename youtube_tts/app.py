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
"""YouTube TTS アプリケーションのコンテキストクラスです。"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any

from .audio import AudioPlayer
from .config import AppConfig
from .dictionary import TextProcessor
from .logger import get_logger
from .models import YouTubeMessage
from .obs import ObsClient
from .queue import SpeechQueue
from .voicevox import VoicevoxClient

# 定数を定義します。
QUEUE_MAXSIZE = 50
MAX_PROCESSED_MESSAGE_IDS = 1000


class YouTubeTtsApp:
    """YouTube Live のチャット読み上げツール全体の実行状態とコンテキストを
    保持するクラスです。
    """

    def __init__(
        self,
        config: AppConfig,
        voicevox_client: VoicevoxClient,
        audio_player: AudioPlayer,
        obs_client: ObsClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.text_processor = TextProcessor(config)
        self.voicevox_client = voicevox_client
        self.audio_player = audio_player
        self.obs_client = obs_client

        if logger is None:
            self.logger = get_logger()
        else:
            self.logger = logger

        # 実行時状態の初期化
        self.speech_queue = SpeechQueue(maxsize=QUEUE_MAXSIZE)
        self.stop_event = threading.Event()
        self.processed_message_ids = set()
        self.processed_message_queue = deque()
        self.max_processed_message_ids = MAX_PROCESSED_MESSAGE_IDS
        self.last_spoken_used = None
        self.verbose = False

    def speak(self, text: str, speed_scale: float | None = None) -> None:
        """指定されたテキストを VOICEVOX で音声合成し再生します。

        Args:
            text: 音声合成するテキストです。
            speed_scale: 再生速度のスケールです。

        """
        if speed_scale is None:
            speed_scale = self.config.speed_scale
        try:
            # 音声を合成します。
            wav_bytes = self.voicevox_client.synthesize(
                text=text,
                volume_scale=self.config.volume_scale,
                speed_scale=speed_scale,
                target_sample_rate=self.audio_player.target_sample_rate,
            )
            # 音声を再生します。
            self.audio_player.play_wav(wav_bytes)
        except Exception as e:
            self.logger.error("音声の合成または再生に失敗しました。")
            self.logger.error(
                "- VOICEVOX サーバーが起動しているか確認してください。"
            )
            self.logger.error(
                "- 出力オーディオデバイスの設定を確認してください。"
            )
            self.logger.debug(f"(エラー詳細: {e})")

    def is_and_mark_processed(self, message_id: str) -> bool:
        """メッセージIDが処理済みかどうかを判定し、未処理なら履歴に追加します。

        Args:
            message_id: 重複再生を防止するための一意なメッセージ ID です。

        Returns:
            bool: 処理済みの場合は True、未処理の場合は False です。

        """
        if message_id in self.processed_message_ids:
            return True

        self.processed_message_ids.add(message_id)
        self.processed_message_queue.append(message_id)
        if len(self.processed_message_queue) > self.max_processed_message_ids:
            oldest_message_id = self.processed_message_queue.popleft()
            self.processed_message_ids.discard(oldest_message_id)
        return False

    def write_chat_log(
        self, message: YouTubeMessage | dict[str, Any], video_id: str
    ) -> None:
        """受信したチャット/コメントのイベントを JSONL 形式で保存します。

        Args:
            message: YouTubeMessage または辞書オブジェクトです。
            video_id: 動画のIDです。

        """
        if isinstance(message, dict):
            message = YouTubeMessage.from_dict(message)
        log_data = message.to_log_dict(video_id)
        try:
            with open(self.config.chat_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
        except Exception as e:
            self.logger.error(f"チャットログの保存に失敗しました: {e}")

    def cleanup(
        self,
        playback_thread: threading.Thread | None = None,
        wait_seconds: int = 5,
    ) -> None:
        """スレッド停止、オーディオ停止を行うクリーンアップ処理です。

        Args:
            playback_thread: 再生スレッドです。
            wait_seconds: 待機秒数です。

        """
        self.logger.info("クリーンアップを実行しています...")
        self.stop_event.set()
        self.audio_player.stop()

        end_time = time.time() + wait_seconds
        while time.time() < end_time and not self.speech_queue.empty():
            time.sleep(0.1)

        while not self.speech_queue.empty():
            self.speech_queue.get_nowait()
            self.speech_queue.task_done()

        if playback_thread is not None:
            try:
                playback_thread.join(timeout=wait_seconds)
            except Exception:
                pass

        self.logger.info("クリーンアップが完了しました。")
