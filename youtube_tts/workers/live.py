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
"""YouTube Live コメント監視ワーカーを定義するモジュールです。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from ..live import YouTubeLiveChatClient
from ..models import SpeechItem, VideoDetails, YouTubeMessage
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


def live_worker(
    app: YouTubeTtsApp,
    live_client: YouTubeLiveChatClient,
    video_id: str,
    creds: Any | None = None,
    quota_check: bool = False,
    quota_talk: bool = False,
    tts_test: str | None = None,
    chat_interval: float = 20.0,
    quota_interval: float = 180.0,
    stream_check_interval: float = 180.0,
    project_id: str | None = None,
    verbose: bool = False,
    backlog_seconds: int = 10,
) -> None:
    """YouTube Live チャットコメントの定期取得を行い、
    キューへ送るワーカーです。"""
    try:
        video_details = live_client.get_video_details(video_id)
        if isinstance(video_details, dict):
            snippet = video_details.get("snippet", {})
            video_details = VideoDetails(
                video_id=video_id,
                channel_id=snippet.get("channelId", ""),
                title=snippet.get("title", ""),
            )
    except Exception as e:  # noqa: BLE001
        app.logger.error("動画情報の取得に失敗しました。")
        app.logger.debug(f"(エラー詳細: {format_error_details(e)})")
        app.stop_event.set()
        return

    my_channel_id = live_client.get_my_channel_id()
    is_mine = video_details.is_owner(my_channel_id)

    if tts_test and is_mine:
        app.logger.info(f"[TTS-TEST] {tts_test}")
        app.speak(tts_test)

    try:
        live_chat_id = live_client.get_live_chat_id(video_id)
        app.logger.info(f"ライブチャットID: {live_chat_id}")
    except Exception as e:  # noqa: BLE001
        app.logger.error("ライブチャットIDの取得に失敗しました。")
        app.logger.debug(f"(エラー詳細: {format_error_details(e)})")
        app.stop_event.set()
        return

    if backlog_seconds >= 0:
        threshold_time = datetime.now(timezone.utc) - timedelta(
            seconds=backlog_seconds
        )
    else:
        threshold_time = None

    next_page_token = None
    last_stream_check_time = time.time()

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

    while not app.stop_event.is_set():
        app.config.reload_if_changed()

        app.logger.debug(
            f"チャットメッセージを取得しています (pageToken: {next_page_token})"
        )

        error_occurred = None
        try:
            res = live_client.fetch_chat_messages(
                live_chat_id, page_token=next_page_token
            )
            items, next_page_token, polling_interval = res
        except Exception as e:  # noqa: BLE001
            # 例外ブロック内での複雑な処理を避け、状態を記録するにとどめます。
            error_occurred = e
            polling_interval = chat_interval * 1000

        # チャット取得でエラーが発生した場合の対応処理
        if error_occurred:
            handled = False
            if quota_monitor:
                handled = quota_monitor.handle_exceeded_error(error_occurred)

            if not handled:
                app.logger.error("チャットの取得に失敗しました。")
                err_det = format_error_details(error_occurred)
                app.logger.debug(f"(エラー詳細: {err_det})")

            app.stop_event.set()
            return

        app.logger.debug(
            f"{len(items)} 件のアイテムを取得しました。 "
            f"(next_page_token: {next_page_token}, "
            f"polling_interval: {polling_interval}ms)"
        )

        for message in items:
            if isinstance(message, dict):
                message = YouTubeMessage.from_dict(message)

            if app.is_and_mark_processed(message.id):
                continue

            app.write_chat_log(message, video_id)

            if threshold_time is not None:
                if message.published_at < threshold_time:
                    app.logger.debug(
                        f"[SKIP(過去コメント)] {message.author_name}: "
                        f"{message.message} "
                        f"(投稿日時: {message.published_at.isoformat()})"
                    )
                    continue

            author = message.author_name
            msg_text = message.message

            if app.text_processor.contains_ng_word(msg_text):
                app.logger.info(f"[SKIP(NG)] {author}: {msg_text}")
                continue

            app.logger.info(f"[CHAT] {author}: {msg_text}")
            proc = app.text_processor
            author, msg_text = proc.normalize_comment(author, msg_text)

            if app.speech_queue.full():
                app.logger.info(f"[SKIP(QUEUE)] {author}: {msg_text}")
                continue

            speech_item = SpeechItem.from_youtube_message(
                message, author, msg_text
            )
            app.speech_queue.put(speech_item)

        now = time.time()

        # 配信がアクティブであるか確認します。
        if now - last_stream_check_time >= stream_check_interval:
            app.logger.debug("配信のアクティブ状態を確認しています...")
            is_active = live_client.check_stream_active(video_id)
            app.logger.debug(f"配信アクティブ状態: {is_active}")
            if not is_active:
                app.stop_event.set()
                return
            last_stream_check_time = now

        # クォータの使用量を確認します。
        if quota_monitor:
            quota_monitor.check_and_talk()

        time.sleep(max(polling_interval / 1000, chat_interval))
