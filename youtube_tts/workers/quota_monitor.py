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
"""クォータの監視と読み上げを管理するモジュールです。"""

from __future__ import annotations

import queue
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from googleapiclient.errors import HttpError

from youtube_tts.models import QuotaInfo, SpeechItem
from youtube_tts.quota import get_quota_info

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp


class QuotaMonitor:
    """YouTube Data API のクォータ使用状況を監視し、
    超過時や定期的な読み上げを管理するクラスです。
    """

    def __init__(
        self,
        app: YouTubeTtsApp,
        creds: Any | None,
        project_id: str | None,
        quota_talk: bool = False,
        interval: float = 180.0,
    ) -> None:
        """初期化します。"""
        self.app = app
        self.creds = creds
        self.project_id = project_id
        self.quota_talk = quota_talk
        self.interval = interval
        self.last_check_time = 0.0
        self.last_spoken_used: int | None = None

    def get_next_reset_time(self) -> datetime:
        """太平洋時間における次のクォータリセット時刻を算出します。"""
        from zoneinfo import ZoneInfo

        tz_la = ZoneInfo("America/Los_Angeles")
        now_la = datetime.now(tz_la)
        next_reset_la = (now_la + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return next_reset_la.astimezone()

    def format_reset_time(self, reset_time: datetime) -> str:
        """リセット時刻を音声読み上げ用の文字列にフォーマットします。"""
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

    def is_quota_exceeded_error(self, error: Exception) -> bool:
        """HTTP 403 のクォータ超過エラーかどうかを判定します。"""
        if not isinstance(error, HttpError):
            return False

        resp_status = getattr(getattr(error, "resp", None), "status", None)
        if resp_status != 403:
            return False

        content = getattr(error, "content", None)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        elif not isinstance(content, str):
            content = ""

        return "quotaExceeded" in str(error) or "quotaExceeded" in content

    def enqueue_quota_message(self, message: str) -> None:
        """キューを空にして、クォータ超過メッセージを再生キューへ積みます。"""
        # 直前のコメントが残っている場合に備えて、通知メッセージを優先して再生する。
        while not self.app.speech_queue.empty():
            try:
                self.app.speech_queue.get_nowait()
                self.app.speech_queue.task_done()
            except queue.Empty:
                break

        char_count = len(message)
        speech_item = SpeechItem("", message, char_count)
        self.app.speech_queue.put(speech_item)

    def handle_exceeded_error(self, error: Exception) -> bool:
        """例外がクォータ超過エラーであれば案内メッセージをキューに追加し True を返します。"""
        if not self.is_quota_exceeded_error(error):
            return False

        if self.quota_talk:
            try:
                reset_time = self.get_next_reset_time()
                reset_str = self.format_reset_time(reset_time)
                quota_message = (
                    f"ぴんぽーん！残念！"
                    f"クォータを超過しました。"
                    f"{reset_str}頃までお待ち下さい。"
                )
            except Exception as ex:  # noqa: BLE001
                self.app.logger.warning(
                    f"リセット予定時刻の取得に失敗しました: {ex}"
                )
                quota_message = "ぴんぽーん！残念！クォータを超過しました。"

            self.app.logger.info(f"[QUOTA] {quota_message}")
            self.enqueue_quota_message(quota_message)

            # 再生キューに入れた案内メッセージが処理されるまで少し待つ
            timeout = time.time() + 5.0
            while not self.app.speech_queue.empty() and time.time() < timeout:
                time.sleep(0.1)

        return True

    def check_and_talk(self) -> None:
        """指定インターバルに基づきクォータ使用量を取得・読み上げます。"""
        if not self.creds or not self.project_id:
            return

        now = time.time()
        if now - self.last_check_time < self.interval:
            return

        self.app.logger.debug("クォータ情報を取得しています...")
        try:
            quota_info = get_quota_info(self.creds, self.project_id)
            if isinstance(quota_info, tuple):
                quota_info = QuotaInfo(
                    used=quota_info[0], limit=quota_info[1]
                )
            self.app.logger.info(
                f"[QUOTA] 使用量: {quota_info.used:,} / "
                f"{quota_info.limit:,} "
                f"({quota_info.usage_percent:.2f}%), "
                f"残量: {quota_info.remaining:,}"
            )

            is_diff = quota_info.used != self.last_spoken_used
            if self.quota_talk and is_diff and not self.app.speech_queue.full():
                quota_author = ""
                quota_message = quota_info.speech_text
                speech_item = SpeechItem(
                    quota_author, quota_message, len(quota_message)
                )
                self.app.speech_queue.put(speech_item)
                self.last_spoken_used = quota_info.used
        except Exception as e:  # noqa: BLE001
            self.app.logger.warning("クォータ情報の取得に失敗しました。")
            self.app.logger.debug(f"(エラー詳細: {e})")

        self.last_check_time = now
