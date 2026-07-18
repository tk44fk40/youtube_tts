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
"""YouTube 動画コメント監視ワーカーを定義するモジュールです。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..models import SpeechItem, YouTubeMessage
from ..video import YouTubeVideoClient
from .quota_monitor import QuotaMonitor

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp


def format_error_details(error: Exception) -> str:
    """ログに出力するために例外の詳細を安全に整形します。"""
    try:
        return str(error)
    except Exception:
        pass
    try:
        return repr(error)
    except Exception:
        return f"{type(error).__name__}(details unavailable)"


def video_worker(
    app: YouTubeTtsApp,
    video_client: YouTubeVideoClient,
    video_id: str,
    creds: Any | None = None,
    quota_check: bool = False,
    quota_talk: bool = False,
    quota_interval: float = 180.0,
    project_id: str | None = None,
    chat_interval: float = 20.0,
    verbose: bool = False,
    backlog_counts: int = 100,
) -> None:
    """YouTube 動画コメントの定期取得を行い、キューへ送るワーカーです。"""
    quota_monitor = (
        QuotaMonitor(
            app=app,
            creds=creds,
            project_id=project_id,
            quota_talk=quota_talk,
            interval=quota_interval,
        )
        if quota_check
        else None
    )

    app.logger.info(
        "初期コメントのバックログをロードしています "
        f"(制限: {backlog_counts})..."
    )
    backlog_items = []
    page_token = None
    remaining_to_fetch = backlog_counts if backlog_counts >= 0 else None

    while not app.stop_event.is_set():
        if remaining_to_fetch is not None and remaining_to_fetch <= 0:
            break
        max_results = (
            min(remaining_to_fetch, 100)
            if remaining_to_fetch is not None
            else 100
        )

        error_occurred = None
        try:
            items, page_token, _ = video_client.fetch_comment_threads(
                video_id, page_token=page_token, max_results=max_results
            )
        except Exception as e:  # noqa: BLE001
            error_occurred = e

        if error_occurred:
            handled = False
            if quota_monitor:
                handled = quota_monitor.handle_exceeded_error(error_occurred)
            if not handled:
                app.logger.error("初期コメントスレッドの取得に失敗しました。")
                app.logger.debug(
                    f"(エラー詳細: {format_error_details(error_occurred)})"
                )
            break

        if not items:
            break

        backlog_items.extend(items)
        if remaining_to_fetch is not None:
            remaining_to_fetch -= len(items)

        if not page_token:
            break

    backlog_items.reverse()
    for message in backlog_items:
        if isinstance(message, dict):
            message = YouTubeMessage.from_dict(message)
        app.is_and_mark_processed(message.id)
        app.write_chat_log(message, video_id)

        author = message.author_name
        msg_text = message.message

        if app.text_processor.contains_ng_word(msg_text):
            if verbose:
                app.logger.info(f"[SKIP(NG)] {author}: {msg_text}")
            continue

        app.logger.info(f"[COMMENT] {author}: {msg_text}")
        author, msg_text = app.text_processor.normalize_comment(
            author, msg_text
        )

        if app.speech_queue.full():
            app.logger.info(f"[SKIP(QUEUE)] {author}: {msg_text}")
            continue

        speech_item = SpeechItem.from_youtube_message(message, author, msg_text)
        app.speech_queue.put(speech_item)

    while not app.stop_event.is_set():
        app.config.reload_if_changed()
        app.logger.debug("最新の動画コメントを取得しています...")

        error_occurred = None
        try:
            res = video_client.fetch_comment_threads(
                video_id, page_token=None, max_results=100
            )
            items, _, polling_interval = res
        except Exception as e:  # noqa: BLE001
            error_occurred = e
            polling_interval = chat_interval * 1000

        if error_occurred:
            handled = False
            if quota_monitor:
                handled = quota_monitor.handle_exceeded_error(error_occurred)
            if not handled:
                app.logger.error("コメントスレッドの取得に失敗しました。")
                app.logger.debug(
                    f"(エラー詳細: {format_error_details(error_occurred)})"
                )
            app.stop_event.set()
            return

        app.logger.debug(
            f"{len(items)} 件のアイテムを取得しました。 "
            f"(polling_interval: {polling_interval}ms)"
        )

        items.reverse()
        for message in items:
            if isinstance(message, dict):
                message = YouTubeMessage.from_dict(message)
            if app.is_and_mark_processed(message.id):
                continue

            app.write_chat_log(message, video_id)

            author = message.author_name
            msg_text = message.message

            if app.text_processor.contains_ng_word(msg_text):
                if verbose:
                    app.logger.info(f"[SKIP(NG)] {author}: {msg_text}")
                continue

            app.logger.info(f"[COMMENT] {author}: {msg_text}")
            author, msg_text = app.text_processor.normalize_comment(
                author, msg_text
            )

            if app.speech_queue.full():
                app.logger.info(f"[SKIP(QUEUE)] {author}: {msg_text}")
                continue

            speech_item = SpeechItem.from_youtube_message(
                message, author, msg_text
            )
            app.speech_queue.put(speech_item)

        if quota_monitor:
            quota_monitor.check_and_talk()

        time.sleep(max(polling_interval / 1000, chat_interval))
