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

import queue
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.errors import HttpError

from ..live import YouTubeLiveChatClient
from ..models import CommentItem
from ..quota import get_quota_info


def get_next_quota_reset_time() -> Any:
    """太平洋時間における次のクォータリセット時刻を算出する。

    Returns:
        datetime: 次のリセット予定時刻。
    """
    try:
        from zoneinfo import ZoneInfo

        tz_la = ZoneInfo("America/Los_Angeles")
    except Exception:  # noqa: BLE001
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


def format_reset_time_for_speech(reset_time: Any) -> str:
    """リセット時刻を音声読み上げ用の文字列にフォーマットする。

    Args:
        reset_time: クォータリセット予定時刻。

    Returns:
        str: 読み上げ用テキスト。
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
    app: Any,
    live_client: YouTubeLiveChatClient,
    video_id: str,
    creds: Any = None,
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
    """YouTube Live チャットコメントの定期取得を行い、キューへ送るワーカー。

    Args:
        app: YouTubeTtsApp インスタンス。
        live_client: YouTubeLiveChatClient インスタンス.
        video_id: 動画のID。
        creds: 認証資格。
        quota_check: クォータを監視するかどうか。
        quota_talk: クォータ超過時に読み上げるかどうか。
        tts_test: テスト用のTTSテキスト。
        chat_interval: コメント取得インターバル（秒）。
        quota_interval: クォータ監視インターバル（秒）。
        stream_check_interval: 配信状態チェックインターバル（秒）。
        project_id: GCPのプロジェクトID。
        verbose: 詳細ログを出力するかどうか。
        backlog_seconds: 遡って取得する秒数。
    """
    try:
        video_details = live_client.get_video_details(video_id)
    except Exception as e:  # noqa: BLE001
        app.logger.error("[ERROR] 動画情報の取得に失敗しました。")
        if verbose:
            app.logger.debug(f"  (エラー詳細: {e})")
        app.stop_event.set()
        return

    my_channel_id = live_client.get_my_channel_id()
    channel_id = video_details.get("snippet", {}).get("channelId")
    is_mine = my_channel_id is not None and channel_id == my_channel_id

    if tts_test and is_mine:
        app.logger.info(f"[TTS-TEST] {tts_test}")
        app.speak(tts_test)

    try:
        live_chat_id = live_client.get_live_chat_id(video_id)
        app.logger.info(f"liveChatId: {live_chat_id}")
    except Exception as e:  # noqa: BLE001
        app.logger.error("[ERROR] liveChatId の取得に失敗しました。")
        if verbose:
            app.logger.debug(f"  (エラー詳細: {e})")
        app.stop_event.set()
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

    while not app.stop_event.is_set():
        app.config.reload_if_changed()

        if verbose:
            app.logger.debug(
                f"Fetching chat messages (pageToken: {next_page_token})"
            )

        try:
            res = live_client.fetch_chat_messages(
                live_chat_id, page_token=next_page_token
            )
            items, next_page_token, polling_interval = res
        except Exception as e:  # noqa: BLE001
            is_quota_exceeded = False
            try:
                if isinstance(e, HttpError) and e.resp.status == 403:
                    content_str = ""
                    if hasattr(e, "content") and e.content:
                        try:
                            content_str = e.content.decode("utf-8")
                        except Exception as ex:  # noqa: BLE001
                            app.logger.debug(
                                "コンテンツのデコードに失敗しました: %s",
                                ex,
                            )
                    if (
                        "quotaExceeded" in str(e)
                        or "quotaExceeded" in content_str
                    ):
                        is_quota_exceeded = True
            except Exception as ex:  # noqa: BLE001
                app.logger.debug("クォータチェックエラー: %s", ex)

            if is_quota_exceeded:
                if quota_talk:
                    while not app.comment_queue.empty():
                        try:
                            app.comment_queue.get_nowait()
                            app.comment_queue.task_done()
                        except queue.Empty:
                            break

                    try:
                        reset_time = get_next_quota_reset_time()
                        reset_str = format_reset_time_for_speech(reset_time)
                        quota_message = (
                            f"ぴんぽーん！残念！"
                            f"クォータを超過しました。"
                            f"{reset_str}頃までお待ち下さい。"
                        )
                    except Exception as ex:  # noqa: BLE001
                        app.logger.warning(
                            f"リセット予定時刻の取得に失敗しました: {ex}"
                        )
                        quota_message = (
                            "ぴんぽーん！残念！クォータを超過しました。"
                        )

                    app.logger.info(f"[QUOTA] {quota_message}")
                    quota_author = ""
                    char_count = len(quota_message)
                    with app.queue_lock:
                        app.queued_char_count = char_count
                    app.comment_queue.put(
                        CommentItem(quota_author, quota_message, char_count)
                    )

                    timeout = time.time() + 5.0
                    while (
                        not app.comment_queue.empty() and time.time() < timeout
                    ):
                        time.sleep(0.1)

            app.logger.error("[ERROR] チャットの取得に失敗しました。")
            if verbose:
                app.logger.debug(f"  (エラー詳細: {e})")
            app.stop_event.set()
            return

        if verbose:
            app.logger.debug(
                f"Fetched {len(items)} items. "
                f"next_page_token: {next_page_token}, "
                f"polling_interval: {polling_interval}ms"
            )

        for item in items:
            message_id = item["id"]
            if app.is_and_mark_processed(message_id):
                continue

            app.write_chat_log(item, video_id)

            if threshold_time is not None:
                published_at_str = item.get("snippet", {}).get("publishedAt")
                if published_at_str:
                    try:
                        published_at = datetime.fromisoformat(published_at_str)
                        if published_at < threshold_time:
                            author_name = item["authorDetails"]["displayName"]
                            app.logger.debug(
                                f"[SKIP(PAST)] {author_name}: "
                                f"{item['snippet']['displayMessage']} "
                                f"(published at {published_at_str})"
                            )
                            continue
                    except ValueError as ex:
                        app.logger.warning(
                            f"Failed to parse publishedAt: "
                            f"{published_at_str}, error: {ex}"
                        )

            author = item["authorDetails"]["displayName"]
            message = item["snippet"]["displayMessage"]

            if app.text_processor.contains_ng_word(message):
                app.logger.info(f"[SKIP(NG)] {author}: {message}")
                continue

            app.logger.info(f"[CHAT] {author}: {message}")
            proc = app.text_processor
            author, message = proc.normalize_comment(author, message)

            if app.comment_queue.full():
                app.logger.info(f"[SKIP(QUEUE)] {author}: {message}")
                continue

            char_count = len(author) + len(message)
            with app.queue_lock:
                app.queued_char_count += char_count
            app.comment_queue.put(CommentItem(author, message, char_count))

        now = time.time()

        # 配信アクティブ状態の確認
        if now - last_stream_check_time >= stream_check_interval:
            if verbose:
                app.logger.debug("Checking stream active status...")
            is_active = live_client.check_stream_active(video_id)
            if verbose:
                app.logger.debug(f"Stream active status: {is_active}")
            if not is_active:
                app.stop_event.set()
                return
            last_stream_check_time = now

        # クォータ使用量の確認
        if (
            quota_check
            and creds
            and project_id
            and (now - last_quota_check_time >= quota_interval)
        ):
            if verbose:
                app.logger.debug("Fetching quota info...")
            try:
                used, limit = get_quota_info(creds, project_id)
                remaining = max(0, limit - used)
                usage_percent = (used / limit) * 100 if limit > 0 else 0
                app.logger.info(
                    f"[QUOTA] Used: {used:,} / {limit:,} "
                    f"({usage_percent:.2f}%), Remaining: {remaining:,}"
                )

                is_diff = used != app.last_spoken_used
                if quota_talk and is_diff and not app.comment_queue.full():
                    quota_author = ""
                    quota_message = (
                        f"ぴんぽーん！クォータ使用量は {used} ユニットです。"
                    )
                    char_count = len(quota_author) + len(quota_message)
                    with app.queue_lock:
                        app.queued_char_count += char_count
                    app.comment_queue.put(
                        CommentItem(quota_author, quota_message, char_count)
                    )
                    app.last_spoken_used = used
            except Exception as e:  # noqa: BLE001
                app.logger.warning(
                    "[WARNING] クォータ情報の取得に失敗しました。"
                )
                if verbose:
                    app.logger.debug(f"  (エラー詳細: {e})")
            last_quota_check_time = now

        time.sleep(max(polling_interval / 1000, chat_interval))
