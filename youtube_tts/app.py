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
"""YouTube TTS Application class and workers.

YouTube TTS アプリケーションクラスと各種ワーカー。
"""

import json
import queue
import signal
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from googleapiclient.errors import HttpError

from .audio import AudioPlayer
from .config import AppConfig
from .dictionary import TextProcessor
from .live import YouTubeLiveChatClient
from .logger import get_logger
from .obs import ObsClient
from .quota import get_quota_info
from .video import YouTubeVideoClient
from .voicevox import VoicevoxClient

# Constant definitions
# 定数定義
QUEUE_MAXSIZE = 50
MAX_PROCESSED_MESSAGE_IDS = 1000


class CommentItem(tuple):
    """Represents a chat/comment item in the queue.

    キューに投入されるチャット/コメントアイテムを表現するクラス。
    """

    def __new__(cls, author, message, char_count):
        return super().__new__(cls, (author, message))

    def __init__(self, author, message, char_count):
        self.char_count = char_count


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
        while not self.stop_event.is_set():
            try:
                item = self.comment_queue.get(timeout=1)
                author, message = item
                char_count = getattr(item, "char_count", None)
                if char_count is None:
                    char_count = len(author) + len(message)

                with self.queue_lock:
                    self.queued_char_count = max(
                        0, self.queued_char_count - char_count
                    )
                    remaining_chars = self.queued_char_count
            except queue.Empty:
                continue

            text = f"{author} {message}"

            base_speed = self.config.speed_scale
            speed = base_speed

            if self.config.auto_speed_boost and remaining_chars > 0:
                rate_at_base = 6.0 * base_speed
                estimated_duration = (
                    remaining_chars / rate_at_base if rate_at_base > 0 else 0
                )
                max_speed = min(getattr(self.config, "max_speed", 2.2), 2.2)

                if base_speed < max_speed:
                    if estimated_duration <= 10.0:
                        speed = base_speed
                    elif estimated_duration >= 40.0:
                        speed = max_speed
                    else:
                        ratio = (estimated_duration - 10.0) / (40.0 - 10.0)
                        speed = base_speed + (max_speed - base_speed) * ratio

                self.logger.info(f"[TALK] {text} (Speed: {speed:.2f}x)")
            else:
                self.logger.info(f"[TALK] {text}")

            self.speak(text, speed_scale=speed)
            self.comment_queue.task_done()

    def _get_next_quota_reset_time(self):
        """Calculates the next quota reset time in Pacific Time.

        太平洋時間における次のクォータリセット時刻を算出する。
        """
        try:
            from zoneinfo import ZoneInfo

            tz_la = ZoneInfo("America/Los_Angeles")
        except Exception:
            now_utc = datetime.now(timezone.utc)
            if 3 <= now_utc.month <= 11:
                tz_la = timezone(timedelta(hours=-7))  # PDT
            else:
                tz_la = timezone(timedelta(hours=-8))  # PST

        now_la = datetime.now(tz_la)
        next_reset_la = (now_la + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return next_reset_la.astimezone()

    def _format_reset_time_for_speech(self, reset_time):
        """Formats the reset time into a string for read-aloud speech.

        リセット時刻を音声読み上げ用の文字列にフォーマットする。
        """
        now_local = datetime.now().astimezone()
        delta_days = (reset_time.date() - now_local.date()).days

        time_str = f"{reset_time.hour}時"
        if reset_time.minute > 0:
            time_str += f"{reset_time.minute}分"

        if delta_days == 0:
            day_prefix = "今日"
        elif delta_days == 1:
            day_prefix = "明日"
        else:
            day_prefix = f"{reset_time.month}月{reset_time.day}日"

        return f"{day_prefix}の{time_str}"

    def live_worker(
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
        """Thread worker that periodically fetches YouTube Live chat comments.

        YouTube Live チャットコメントの定期取得を行い、キューへ送るワーカー。
        """
        # Get own channel ID and video channel ID for is_mine matching
        # チャンネルID判定用の自チャンネルIDおよび動画チャンネルIDの取得
        try:
            video_details = live_client.get_video_details(video_id)
        except Exception as e:
            self.logger.error("[ERROR] 動画情報の取得に失敗しました。")
            if verbose:
                self.logger.debug(f"  (エラー詳細: {e})")
            self.stop_event.set()
            return

        my_channel_id = live_client.get_my_channel_id()
        channel_id = video_details.get("snippet", {}).get("channelId")
        is_mine = my_channel_id is not None and channel_id == my_channel_id

        if tts_test and is_mine:
            self.logger.info(f"[TTS-TEST] {tts_test}")
            self.speak(tts_test)

        try:
            live_chat_id = live_client.get_live_chat_id(video_id)
            self.logger.info(f"liveChatId: {live_chat_id}")
        except Exception as e:
            self.logger.error("[ERROR] liveChatId の取得に失敗しました。")
            if verbose:
                self.logger.debug(f"  (エラー詳細: {e})")
            self.stop_event.set()
            return

        if backlog_seconds >= 0:
            threshold_time = datetime.now(timezone.utc) - timedelta(
                seconds=backlog_seconds
            )
        else:
            threshold_time = None

        next_page_token = None
        last_quota_check_time = 0
        last_stream_check_time = time.time()

        while not self.stop_event.is_set():
            self.config.reload_if_changed()

            if verbose:
                self.logger.debug(
                    f"Fetching chat messages (pageToken: {next_page_token})"
                )

            try:
                items, next_page_token, polling_interval = (
                    live_client.fetch_chat_messages(
                        live_chat_id, page_token=next_page_token
                    )
                )
            except Exception as e:
                is_quota_exceeded = False
                try:
                    if isinstance(e, HttpError) and e.resp.status == 403:
                        content_str = ""
                        if hasattr(e, "content") and e.content:
                            try:
                                content_str = e.content.decode("utf-8")
                            except Exception:
                                pass
                        if (
                            "quotaExceeded" in str(e)
                            or "quotaExceeded" in content_str
                        ):
                            is_quota_exceeded = True
                except Exception:
                    pass

                if is_quota_exceeded:
                    if quota_talk:
                        while not self.comment_queue.empty():
                            try:
                                self.comment_queue.get_nowait()
                                self.comment_queue.task_done()
                            except queue.Empty:
                                break

                        try:
                            reset_time = self._get_next_quota_reset_time()
                            reset_str = self._format_reset_time_for_speech(
                                reset_time
                            )
                            quota_message = (
                                f"ぴんぽーん！残念！"
                                f"クォータを超過しました。"
                                f"{reset_str}頃までお待ち下さい。"
                            )
                        except Exception as ex:
                            self.logger.warning(
                                f"リセット予定時刻の取得に失敗しました: {ex}"
                            )
                            quota_message = (
                                "ぴんぽーん！残念！クォータを超過しました。"
                            )

                        self.logger.info(f"[QUOTA] {quota_message}")
                        quota_author = ""
                        char_count = len(quota_message)
                        with self.queue_lock:
                            self.queued_char_count = char_count
                        self.comment_queue.put(
                            CommentItem(quota_author, quota_message, char_count)
                        )

                        timeout = time.time() + 5.0
                        while (
                            not self.comment_queue.empty()
                            and time.time() < timeout
                        ):
                            time.sleep(0.1)

                self.logger.error("[ERROR] チャットの取得に失敗しました。")
                if verbose:
                    self.logger.debug(f"  (エラー詳細: {e})")
                self.stop_event.set()
                return

            if verbose:
                self.logger.debug(
                    f"Fetched {len(items)} items. "
                    f"next_page_token: {next_page_token}, "
                    f"polling_interval: {polling_interval}ms"
                )

            for item in items:
                message_id = item["id"]
                if self.is_and_mark_processed(message_id):
                    continue

                self.write_chat_log(item, video_id)

                if threshold_time is not None:
                    published_at_str = item.get("snippet", {}).get(
                        "publishedAt"
                    )
                    if published_at_str:
                        try:
                            published_at = datetime.fromisoformat(
                                published_at_str.replace("Z", "+00:00")
                            )
                            if published_at < threshold_time:
                                author_name = item["authorDetails"][
                                    "displayName"
                                ]
                                self.logger.debug(
                                    f"[SKIP(PAST)] {author_name}: "
                                    f"{item['snippet']['displayMessage']} "
                                    f"(published at {published_at_str})"
                                )
                                continue
                        except ValueError as e:
                            self.logger.warning(
                                f"Failed to parse publishedAt: "
                                f"{published_at_str}, error: {e}"
                            )

                author = item["authorDetails"]["displayName"]
                message = item["snippet"]["displayMessage"]

                if self.text_processor.contains_ng_word(message):
                    self.logger.info(f"[SKIP(NG)] {author}: {message}")
                    continue

                self.logger.info(f"[CHAT] {author}: {message}")
                author, message = self.text_processor.normalize_comment(
                    author, message
                )

                if self.comment_queue.full():
                    self.logger.info(f"[SKIP(QUEUE)] {author}: {message}")
                    continue

                char_count = len(author) + len(message)
                with self.queue_lock:
                    self.queued_char_count += char_count
                self.comment_queue.put(CommentItem(author, message, char_count))

            now = time.time()

            # Stream active check
            if now - last_stream_check_time >= stream_check_interval:
                if verbose:
                    self.logger.debug("Checking stream active status...")
                is_active = live_client.check_stream_active(video_id)
                if verbose:
                    self.logger.debug(f"Stream active status: {is_active}")
                if not is_active:
                    self.stop_event.set()
                    return
                last_stream_check_time = now

            # Quota usage check
            if (
                quota_check
                and creds
                and project_id
                and (now - last_quota_check_time >= quota_interval)
            ):
                if verbose:
                    self.logger.debug("Fetching quota info...")
                try:
                    used, limit = get_quota_info(creds, project_id)
                    remaining = max(0, limit - used)
                    usage_percent = (used / limit) * 100 if limit > 0 else 0
                    self.logger.info(
                        f"[QUOTA] Used: {used:,} / {limit:,} "
                        f"({usage_percent:.2f}%), Remaining: {remaining:,}"
                    )

                    if quota_talk and used != self.last_spoken_used:
                        if not self.comment_queue.full():
                            quota_author = ""
                            quota_message = (
                                "ぴんぽーん！クォータ使用量は "
                                f"{used} ユニットです。"
                            )
                            char_count = len(quota_author) + len(quota_message)
                            with self.queue_lock:
                                self.queued_char_count += char_count
                            self.comment_queue.put(
                                CommentItem(
                                    quota_author, quota_message, char_count
                                )
                            )
                            self.last_spoken_used = used
                except Exception as e:
                    self.logger.warning(
                        "[WARNING] クォータ情報の取得に失敗しました。"
                    )
                    if verbose:
                        self.logger.debug(f"  (エラー詳細: {e})")
                last_quota_check_time = now

            time.sleep(max(polling_interval / 1000, chat_interval))

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
        # Fetch initial backlog comments
        # 初期バックログ読み込み
        self.logger.info(
            f"Loading initial comments backlog (limit: {backlog_counts})..."
        )
        backlog_items = []
        page_token = None
        remaining_to_fetch = backlog_counts if backlog_counts >= 0 else None

        while not self.stop_event.is_set():
            if remaining_to_fetch is not None and remaining_to_fetch <= 0:
                break
            max_results = (
                min(remaining_to_fetch, 100)
                if remaining_to_fetch is not None
                else 100
            )

            try:
                items, page_token, _ = video_client.fetch_comment_threads(
                    video_id, page_token=page_token, max_results=max_results
                )
            except Exception as e:
                self.logger.error(
                    "[ERROR] 初期コメントスレッドの取得に失敗しました。"
                )
                if verbose:
                    self.logger.debug(f"  (エラー詳細: {e})")
                break

            if not items:
                break

            backlog_items.extend(items)
            if remaining_to_fetch is not None:
                remaining_to_fetch -= len(items)

            if not page_token:
                break

        backlog_items.reverse()
        for item in backlog_items:
            message_id = item["id"]
            self.is_and_mark_processed(message_id)
            self.write_chat_log(item, video_id)

            author = item["authorDetails"]["displayName"]
            message = item["snippet"]["displayMessage"]

            if self.text_processor.contains_ng_word(message):
                if verbose:
                    self.logger.info(f"[SKIP(NG)] {author}: {message}")
                continue

            self.logger.info(f"[COMMENT] {author}: {message}")
            author, message = self.text_processor.normalize_comment(
                author, message
            )

            if self.comment_queue.full():
                self.logger.info(f"[SKIP(QUEUE)] {author}: {message}")
                continue

            char_count = len(author) + len(message)
            with self.queue_lock:
                self.queued_char_count += char_count
            self.comment_queue.put(CommentItem(author, message, char_count))

        # Main polling loop
        while not self.stop_event.is_set():
            self.config.reload_if_changed()

            if verbose:
                self.logger.debug("Fetching latest video comments...")

            try:
                # Video mode fetches the first page to monitor new comments
                # 動画モードでは最新の新着コメントを監視するため、page_token=Noneにする
                items, _, polling_interval = (
                    video_client.fetch_comment_threads(
                        video_id, page_token=None, max_results=100
                    )
                )
            except Exception as e:
                self.logger.error(
                    "[ERROR] コメントスレッドの取得に失敗しました。"
                )
                if verbose:
                    self.logger.debug(f"  (エラー詳細: {e})")
                self.stop_event.set()
                return

            if verbose:
                self.logger.debug(
                    f"Fetched {len(items)} items. "
                    f"polling_interval: {polling_interval}ms"
                )

            # Chronological order
            items.reverse()

            for item in items:
                message_id = item["id"]
                if self.is_and_mark_processed(message_id):
                    continue

                self.write_chat_log(item, video_id)

                author = item["authorDetails"]["displayName"]
                message = item["snippet"]["displayMessage"]

                if self.text_processor.contains_ng_word(message):
                    self.logger.info(f"[SKIP(NG)] {author}: {message}")
                    continue

                self.logger.info(f"[COMMENT] {author}: {message}")
                author, message = self.text_processor.normalize_comment(
                    author, message
                )

                if self.comment_queue.full():
                    self.logger.info(f"[SKIP(QUEUE)] {author}: {message}")
                    continue

                char_count = len(author) + len(message)
                with self.queue_lock:
                    self.queued_char_count += char_count
                self.comment_queue.put(CommentItem(author, message, char_count))

            time.sleep(max(polling_interval / 1000, chat_interval))

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
