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

import queue
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from googleapiclient.errors import HttpError

from ..live import YouTubeLiveChatClient
from ..models import QuotaInfo, SpeechItem, VideoDetails, YouTubeMessage
from ..quota import get_quota_info

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp


def get_next_quota_reset_time() -> datetime:
    """太平洋時間における次のクォータリセット時刻を算出します。

    Returns:
        datetime: 次のリセット予定時刻です。
    """
    from zoneinfo import ZoneInfo

    tz_la = ZoneInfo("America/Los_Angeles")
    now_la = datetime.now(tz_la)
    next_reset_la = (now_la + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_reset_la.astimezone()


def format_reset_time_for_speech(reset_time: datetime) -> str:
    """リセット時刻を音声読み上げ用の文字列にフォーマットします。

    Args:
        reset_time (datetime): クォータリセット予定時刻です。

    Returns:
        str: 読み上げ用テキストです。
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


def is_quota_exceeded_error(error: Exception) -> bool:
    """HTTP 403 のクォータ超過エラーかどうかを判定します。"""
    # APIの例外の形は環境差異があるため、ステータスと本文を確認して判定する。
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


def enqueue_quota_message(app: YouTubeTtsApp, message: str) -> None:
    """キューを空にして、クォータ超過メッセージを再生キューへ積みます。"""
    # 直前のコメントが残っている場合に備えて、通知メッセージを優先して再生する。
    while not app.comment_queue.empty():
        try:
            app.comment_queue.get_nowait()
            app.comment_queue.task_done()
        except queue.Empty:
            break

    char_count = len(message)
    with app.queue_lock:
        app.queued_char_count = char_count
    app.comment_queue.put(SpeechItem("", message, char_count))


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
    """YouTube Live チャットコメントの定期取得を行い、キューへ送るワーカーです。

    Args:
        app (YouTubeTtsApp): YouTubeTtsApp インスタンスです。
        live_client (YouTubeLiveChatClient):
            YouTubeLiveChatClient インスタンスです。
        video_id (str): 動画のIDです。
        creds (Any | None): 認証資格です。デフォルトは None です。
        quota_check (bool): クォータを監視するかどうかを表す真偽値です。
            デフォルトは False です。
        quota_talk (bool): クォータ超過時に読み上げるかどうかを表す真偽値です。
            デフォルトは False です。
        tts_test (str | None): テスト用のTTSテキストです。
            デフォルトは None です。
        chat_interval (float): コメント取得インターバル（秒）です。
            デフォルトは 20.0 です。
        quota_interval (float): クォータ監視インターバル（秒）です。
            デフォルトは 180.0 です。
        stream_check_interval (float): 配信状態チェックインターバル（秒）です。
            デフォルトは 180.0 です。
        project_id (str | None): GCPのプロジェクトIDです。
            デフォルトは None です。
        verbose (bool): 詳細ログを出力するかどうかを表す真偽値です。
            デフォルトは False です。
        backlog_seconds (int): 遡って取得する秒数です。
            デフォルトは 10 です。
    """
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
    last_quota_check_time = 0
    last_stream_check_time = time.time()

    while not app.stop_event.is_set():
        # 設定ファイルの変更を反映したうえで、次のポーリング周期へ進む。
        app.config.reload_if_changed()

        app.logger.debug(
            f"チャットメッセージを取得しています (pageToken: {next_page_token})"
        )

        try:
            res = live_client.fetch_chat_messages(
                live_chat_id, page_token=next_page_token
            )
            items, next_page_token, polling_interval = res
        except Exception as e:  # noqa: BLE001
            # クォータ超過時のみ、音声読み上げ用の案内メッセージをキューへ流す。
            is_quota_exceeded = is_quota_exceeded_error(e)

            if is_quota_exceeded and quota_talk:
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
                    quota_message = "ぴんぽーん！残念！クォータを超過しました。"

                # 画面表示用のメッセージをログに残し、再生キューへ優先して積む。
                app.logger.info(f"[QUOTA] {quota_message}")
                enqueue_quota_message(app, quota_message)

                # 再生キューに入れた案内メッセージが処理されるまで少し待つ。
                timeout = time.time() + 5.0
                while not app.comment_queue.empty() and time.time() < timeout:
                    time.sleep(0.1)

            app.logger.error("チャットの取得に失敗しました。")
            app.logger.debug(f"(エラー詳細: {format_error_details(e)})")
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

            if app.comment_queue.full():
                app.logger.info(f"[SKIP(QUEUE)] {author}: {msg_text}")
                continue

            speech_item = SpeechItem.from_youtube_message(
                message, author, msg_text
            )
            with app.queue_lock:
                app.queued_char_count += speech_item.char_count
            app.comment_queue.put(speech_item)

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
        if (
            quota_check
            and creds
            and project_id
            and (now - last_quota_check_time >= quota_interval)
        ):
            app.logger.debug("クォータ情報を取得しています...")
            try:
                quota_info = get_quota_info(creds, project_id)
                if isinstance(quota_info, tuple):
                    quota_info = QuotaInfo(
                        used=quota_info[0], limit=quota_info[1]
                    )
                app.logger.info(
                    f"[QUOTA] 使用量: {quota_info.used:,} / "
                    f"{quota_info.limit:,} "
                    f"({quota_info.usage_percent:.2f}%), "
                    f"残量: {quota_info.remaining:,}"
                )

                is_diff = quota_info.used != app.last_spoken_used
                if quota_talk and is_diff and not app.comment_queue.full():
                    quota_author = ""
                    quota_message = quota_info.speech_text
                    speech_item = SpeechItem(
                        quota_author, quota_message, len(quota_message)
                    )
                    with app.queue_lock:
                        app.queued_char_count += speech_item.char_count
                    app.comment_queue.put(speech_item)
                    app.last_spoken_used = quota_info.used
            except Exception as e:  # noqa: BLE001
                app.logger.warning("クォータ情報の取得に失敗しました。")
                app.logger.debug(f"(エラー詳細: {e})")
            last_quota_check_time = now

        time.sleep(max(polling_interval / 1000, chat_interval))
