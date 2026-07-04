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
"""YouTube TTS アプリケーションクラス。"""

import json
import queue
import signal
import threading
import time
from collections import deque
from datetime import datetime, timezone


from .audio import AudioPlayer
from .config import AppConfig
from .dictionary import TextProcessor
from .live import YouTubeLiveChatClient
from .logger import get_logger
from .obs import ObsClient
from .video import YouTubeVideoClient
from .voicevox import VoicevoxClient

# 定数定義
QUEUE_MAXSIZE = 50
MAX_PROCESSED_MESSAGE_IDS = 1000


class YouTubeTtsApp:
    """Manages the execution state and lifecycle of the entire
    YouTube Live chat TTS tool.

    YouTube Live チャット読み上げツール全体の実行状態・ライフサイクルを
    管理するクラス
    """

    def __init__(
        self,
        config: AppConfig,
        voicevox_client: VoicevoxClient,
        audio_player: AudioPlayer,
        obs_client: ObsClient = None,
        logger=None,
    ):
        self.config = config
        self.text_processor = TextProcessor(config)
        self.voicevox_client = voicevox_client
        self.audio_player = audio_player
        self.obs_client = obs_client

        if logger is None:
            self.logger = get_logger()
        else:
            self.logger = logger

        # Initialize runtime state
        # 実行時状態の初期化
        self.comment_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
        self.stop_event = threading.Event()
        self.processed_message_ids = set()
        self.processed_message_queue = deque()
        self.max_processed_message_ids = MAX_PROCESSED_MESSAGE_IDS
        self.last_spoken_used = None
        self.queued_char_count = 0
        self.queue_lock = threading.Lock()
        self.verbose = False

    def speak(self, text: str, speed_scale: float = None):
        """Synthesizes and plays the specified text using VOICEVOX.

        指定されたテキストを VOICEVOX で音声合成し再生する。
        """
        if speed_scale is None:
            speed_scale = self.config.speed_scale
        try:
            # Audio synthesis
            # 音声合成
            wav_bytes = self.voicevox_client.synthesize(
                text=text,
                volume_scale=self.config.volume_scale,
                speed_scale=speed_scale,
                target_sample_rate=self.audio_player.target_sample_rate,
            )
            # Audio playback
            # 音声再生
            self.audio_player.play_wav(wav_bytes)
        except Exception as e:
            self.logger.error("[ERROR] 音声の合成または再生に失敗しました。")
            self.logger.error(
                "        - VOICEVOX サーバーが起動しているか確認してください。"
            )
            self.logger.error(
                "        - 出力オーディオデバイスの設定を確認してください。"
            )
            if getattr(self, "verbose", False):
                self.logger.debug(f"  (エラー詳細: {e})")

    def is_and_mark_processed(self, message_id: str) -> bool:
        """Determines whether the message ID has been processed, and adds it to
        history if not.

        メッセージIDが処理済みかどうかを判定し、未処理なら履歴に追加する。
        """
        if message_id in self.processed_message_ids:
            return True

        self.processed_message_ids.add(message_id)
        self.processed_message_queue.append(message_id)
        if len(self.processed_message_queue) > self.max_processed_message_ids:
            oldest_message_id = self.processed_message_queue.popleft()
            self.processed_message_ids.discard(oldest_message_id)
        return False

    def write_chat_log(self, item: dict, video_id: str):
        """Saves received chat/comment events in JSONL format.

        受信したチャット/コメントのイベントをJSONL形式で保存する。
        """
        published_at_str = item.get("snippet", {}).get("publishedAt")
        if not published_at_str:
            published_at_str = datetime.now(timezone.utc).isoformat()

        author_details = item.get("authorDetails", {})
        snippet = item.get("snippet", {})

        log_data = {
            "timestamp": published_at_str,
            "video_id": video_id,
            "author_id": author_details.get("channelId"),
            "author_name": author_details.get("displayName", ""),
            "message": snippet.get("displayMessage", ""),
            "message_type": snippet.get("type", "textMessageEvent"),
            "is_member": author_details.get("isChatSponsor", False),
            "is_moderator": author_details.get("isChatModerator", False),
            "is_owner": author_details.get("isChatOwner", False),
            "super_chat": None,
        }

        super_chat_details = snippet.get("superChatDetails")
        if super_chat_details:
            log_data["super_chat"] = {
                "amount_micros": super_chat_details.get("amountMicros"),
                "currency": super_chat_details.get("currency"),
                "display_string": super_chat_details.get("amountDisplayString"),
            }

        try:
            with open(self.config.chat_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
        except Exception as e:
            self.logger.error(f"[ERROR] チャットログの保存に失敗しました: {e}")

    def playback_worker(self):
        """Thread worker that monitors the comment queue and plays comments.
        コメント再生キューを監視し、順次再生するスレッドワーカー。
        """
        from .workers.playback import playback_worker

        playback_worker(self)

    def _get_next_quota_reset_time(self):
        """Calculates the next quota reset time in Pacific Time.

        太平洋時間における次のクォータリセット時刻を算出する。
        """
        from .workers.live import get_next_quota_reset_time

        return get_next_quota_reset_time()

    def _format_reset_time_for_speech(self, reset_time):
        """Formats the reset time into a string for read-aloud speech.

        リセット時刻を音声読み上げ用の文字列にフォーマットする。
        """
        from .workers.live import format_reset_time_for_speech

        return format_reset_time_for_speech(reset_time)

    def live_worker(
        self,
        live_client: YouTubeLiveChatClient,
        video_id: str,
        creds=None,
        quota_check: bool = False,
        quota_talk: bool = False,
        tts_test: str | None = None,
        chat_interval: float = 20.0,
        quota_interval: float = 180.0,
        stream_check_interval: float = 180.0,
        project_id: str | None = None,
        verbose: bool = False,
        backlog_seconds: int = 10,
    ):
        """Thread worker that periodically fetches YouTube Live chat comments.

        YouTube Live チャットコメントの定期取得を行い、キューへ送るワーカー。
        """
        from .workers.live import live_worker

        live_worker(
            app=self,
            live_client=live_client,
            video_id=video_id,
            creds=creds,
            quota_check=quota_check,
            quota_talk=quota_talk,
            tts_test=tts_test,
            chat_interval=chat_interval,
            quota_interval=quota_interval,
            stream_check_interval=stream_check_interval,
            project_id=project_id,
            verbose=verbose,
            backlog_seconds=backlog_seconds,
        )

    def video_worker(
        self,
        video_client: YouTubeVideoClient,
        video_id: str,
        chat_interval: float = 20.0,
        verbose: bool = False,
        backlog_counts: int = 100,
    ):
        """Thread worker that periodically fetches YouTube video comments.

        YouTube 動画コメントの定期取得を行い、キューへ送るワーカー。
        """
        from .workers.video import video_worker

        video_worker(
            app=self,
            video_client=video_client,
            video_id=video_id,
            chat_interval=chat_interval,
            verbose=verbose,
            backlog_counts=backlog_counts,
        )

    def cleanup(self, playback_thread=None, wait_seconds=5):
        """Cleanup method to stop threads and stop audio.

        スレッド停止、オーディオ停止を行うクリーンアップ。
        """
        self.logger.info("Cleaning up...")
        self.stop_event.set()
        self.audio_player.stop()

        end_time = time.time() + wait_seconds
        while time.time() < end_time and not self.comment_queue.empty():
            time.sleep(0.1)

        while True:
            try:
                self.comment_queue.get_nowait()
                self.comment_queue.task_done()
            except queue.Empty:
                break

        if playback_thread is not None:
            try:
                playback_thread.join(timeout=wait_seconds)
            except Exception:
                pass

        self.logger.info("Cleanup complete")

    def run_live(
        self,
        live_client: YouTubeLiveChatClient,
        video_id: str,
        creds=None,
        quota_check: bool = False,
        quota_talk: bool = False,
        tts_test: str = None,
        chat_interval: float = 20.0,
        quota_interval: float = 180.0,
        stream_check_interval: float = 180.0,
        project_id: str = None,
        verbose: bool = False,
        backlog_seconds: int = 10,
    ):
        """Starts the live stream monitoring loop and playback worker.

        ライブ配信のチャット監視と再生スレッドを開始する。
        """
        self.verbose = verbose

        def handle_signal(signum, frame):
            self.logger.info("Signal received, shutting down...")
            self.stop_event.set()

        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except ValueError:
            pass

        playback_thread = threading.Thread(target=self.playback_worker)
        playback_thread.start()

        try:
            self.live_worker(
                live_client=live_client,
                video_id=video_id,
                creds=creds,
                quota_check=quota_check,
                quota_talk=quota_talk,
                tts_test=tts_test,
                chat_interval=chat_interval,
                quota_interval=quota_interval,
                stream_check_interval=stream_check_interval,
                project_id=project_id,
                verbose=verbose,
                backlog_seconds=backlog_seconds,
            )
        except Exception:
            self.logger.exception("Unexpected error")
        finally:
            self.cleanup(playback_thread=playback_thread, wait_seconds=5)

    def run_video(
        self,
        video_client: YouTubeVideoClient,
        video_id: str,
        chat_interval: float = 20.0,
        verbose: bool = False,
        backlog_counts: int = 100,
    ):
        """Starts the video comments monitoring loop and playback worker.

        動画・アーカイブコメントの監視と再生スレッドを開始する。
        """
        self.verbose = verbose

        def handle_signal(signum, frame):
            self.logger.info("Signal received, shutting down...")
            self.stop_event.set()

        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except ValueError:
            pass

        playback_thread = threading.Thread(target=self.playback_worker)
        playback_thread.start()

        try:
            self.video_worker(
                video_client=video_client,
                video_id=video_id,
                chat_interval=chat_interval,
                verbose=verbose,
                backlog_counts=backlog_counts,
            )
        except Exception:
            self.logger.exception("Unexpected error")
        finally:
            self.cleanup(playback_thread=playback_thread, wait_seconds=5)
