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
from typing import TYPE_CHECKING

from ..models import CommentItem
from ..video import YouTubeVideoClient

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp


def video_worker(
    app: YouTubeTtsApp,
    video_client: YouTubeVideoClient,
    video_id: str,
    chat_interval: float = 20.0,
    verbose: bool = False,
    backlog_counts: int = 100,
) -> None:
    """YouTube 動画コメントの定期取得を行い、キューへ送るワーカーです。

    Args:
        app (YouTubeTtsApp): YouTubeTtsApp インスタンスです。
        video_client (YouTubeVideoClient): YouTubeVideoClient
            インスタンスです。
        video_id (str): 動画のIDです。
        chat_interval (float): コメント取得インターバル（秒）です。
        verbose (bool): 詳細ログを出力するかどうかです。
        backlog_counts (int): 読み込む初期バックログの件数です。
    """
    app.logger.info(
        "初期コメントのバックログをロードしています "
        f"(制限: {backlog_counts})..."
    )
    backlog_items = []
    page_token = None
    # 読み込む初期バックログの制限数（負数の場合は制限なし）を設定します。
    remaining_to_fetch = backlog_counts if backlog_counts >= 0 else None

    # 初期コメントのバックログ取得ループです。
    while not app.stop_event.is_set():
        if remaining_to_fetch is not None and remaining_to_fetch <= 0:
            break
        max_results = (
            min(remaining_to_fetch, 100)
            if remaining_to_fetch is not None
            else 100
        )

        try:
            # YouTube API から動画のコメントスレッドを取得します。
            items, page_token, _ = video_client.fetch_comment_threads(
                video_id, page_token=page_token, max_results=max_results
            )
        except Exception as e:  # noqa: BLE001
            app.logger.error(
                "初期コメントスレッドの取得に失敗しました。"
            )
            if verbose:
                app.logger.debug(f"  (エラー詳細: {e})")
            break

        if not items:
            break

        backlog_items.extend(items)
        if remaining_to_fetch is not None:
            remaining_to_fetch -= len(items)

        if not page_token:
            break

    # 取得したコメントを古い順に処理するために並べ替えます。
    backlog_items.reverse()
    for item in backlog_items:
        message_id = item["id"]
        app.is_and_mark_processed(message_id)
        app.write_chat_log(item, video_id)

        author = item["authorDetails"]["displayName"]
        message = item["snippet"]["displayMessage"]

        # NGワードが含まれるコメントはスキップします。
        if app.text_processor.contains_ng_word(message):
            if verbose:
                app.logger.info(f"[SKIP(NG)] {author}: {message}")
            continue

        app.logger.info(f"[COMMENT] {author}: {message}")
        author, message = app.text_processor.normalize_comment(author, message)

        # 読み上げキューが満杯の場合はスキップします。
        if app.comment_queue.full():
            app.logger.info(f"[SKIP(QUEUE)] {author}: {message}")
            continue

        # 文字数カウントを更新し、読み上げキューへ追加します。
        char_count = len(author) + len(message)
        with app.queue_lock:
            app.queued_char_count += char_count
        app.comment_queue.put(CommentItem(author, message, char_count))

    # コメントのリアルタイム監視ポーリングループです。
    while not app.stop_event.is_set():
        app.config.reload_if_changed()

        if verbose:
            app.logger.debug("最新の動画コメントを取得しています...")

        try:
            # 最新のコメントを最大100件取得します。
            res = video_client.fetch_comment_threads(
                video_id, page_token=None, max_results=100
            )
            items, _, polling_interval = res
        except Exception as e:  # noqa: BLE001
            app.logger.error("コメントスレッドの取得に失敗しました。")
            if verbose:
                app.logger.debug(f"  (エラー詳細: {e})")
            app.stop_event.set()
            return

            app.logger.debug(
                f"{len(items)} 件のアイテムを取得しました。 "
                f"(polling_interval: {polling_interval}ms)"
            )

        # 取得したコメントを古い順に処理します。
        items.reverse()

        for item in items:
            message_id = item["id"]
            # 既に処理済みのコメントはスキップします。
            if app.is_and_mark_processed(message_id):
                continue

            app.write_chat_log(item, video_id)

            author = item["authorDetails"]["displayName"]
            message = item["snippet"]["displayMessage"]

            # NGワードが含まれるコメントはスキップします。
            if app.text_processor.contains_ng_word(message):
                if verbose:
                    app.logger.info(f"[SKIP(NG)] {author}: {message}")
                continue

            app.logger.info(f"[COMMENT] {author}: {message}")
            author, message = app.text_processor.normalize_comment(
                author, message
            )

            # 読み上げキューが満杯の場合はスキップします。
            if app.comment_queue.full():
                app.logger.info(f"[SKIP(QUEUE)] {author}: {message}")
                continue

            # 文字数カウントを更新し、読み上げキューへ追加します。
            char_count = len(author) + len(message)
            with app.queue_lock:
                app.queued_char_count += char_count
            app.comment_queue.put(CommentItem(author, message, char_count))

        # APIで指定されたポーリング間隔または設定値の
        # いずれか大きい時間待機します。
        time.sleep(max(polling_interval / 1000, chat_interval))

