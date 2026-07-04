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
"""Tests for YouTubeTtsApp.video_worker.

YouTubeTtsApp.video_worker のテストモジュール。
"""

import queue
from unittest.mock import MagicMock

from youtube_tts import YouTubeVideoClient
import youtube_tts.workers.video  # noqa: F401


def test_video_worker_success(app):
    """正常に動画コメントを取得し、コメントキューが更新されるか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)

    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "User1",
                            "channelId": "ch1",
                        },
                        "snippet": {
                            "displayMessage": "Backlog1",
                            "publishedAt": "2026-07-03T10:00:00Z",
                        },
                    }
                ],
                "token_next",
                3000,
            )
        elif call_count == 2:
            return [], None, 3000
        else:
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",  # Duplicate of backlog, will be skipped
                        "authorDetails": {
                            "displayName": "User1",
                            "channelId": "ch1",
                        },
                        "snippet": {
                            "displayMessage": "Backlog1",
                            "publishedAt": "2026-07-03T10:00:00Z",
                        },
                    },
                    {
                        "id": "c2",  # New comment
                        "authorDetails": {
                            "displayName": "User2",
                            "channelId": "ch2",
                        },
                        "snippet": {
                            "displayMessage": "NewComment",
                            "publishedAt": "2026-07-03T10:05:00Z",
                        },
                    },
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 2
    assert app.queued_char_count == 32


def test_video_worker_backlog_counts_zero(app):
    """backlog_countsが0の場合に初期コメントロードがスキップされるか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=0,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_counts_negative(app):
    """backlog_countsが負数の場合に制限なしでロードできるか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    mock_video_client.fetch_comment_threads.return_value = ([], None, 3000)
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=-1,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_empty(app):
    """初期バックログが空の場合に正しく動作するか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    mock_video_client.fetch_comment_threads.return_value = ([], None, 3000)

    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_error(app):
    """初期バックログ取得中にエラーが発生しても処理が継続するか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    mock_video_client.fetch_comment_threads.side_effect = Exception("API error")

    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_ng_word(app):
    """初期バックログコメントの中にNGワードがある場合スキップされるか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    mock_video_client.fetch_comment_threads.return_value = (
        [
            {
                "id": "c1",
                "authorDetails": {"displayName": "User1", "channelId": "ch1"},
                "snippet": {
                    "displayMessage": "badword message",
                    "publishedAt": "2026-07-03T10:00:00Z",
                },
            }
        ],
        None,
        3000,
    )
    app.config.ng_words = ["badword"]
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_backlog_queue_full(app):
    """初期バックログ取得時にキューがいっぱいの場合スキップされるか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    mock_video_client.fetch_comment_threads.return_value = (
        [
            {
                "id": "c1",
                "authorDetails": {"displayName": "User1", "channelId": "ch1"},
                "snippet": {
                    "displayMessage": "Hello",
                    "publishedAt": "2026-07-03T10:00:00Z",
                },
            }
        ],
        None,
        3000,
    )

    app.comment_queue = queue.Queue(maxsize=1)
    app.comment_queue.put(("Existing", "Comment"))
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 1


def test_video_worker_polling_error(app):
    """メインポーリング中にエラーが発生した場合に正しくループを終了するか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)

    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            raise Exception("API error")

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.stop_event.is_set() is True


def test_video_worker_polling_ng_word(app):
    """メインポーリング時にNGワードを含むコメントがスキップされるか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    app.config.ng_words = ["badword"]

    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "User1",
                            "channelId": "ch1",
                        },
                        "snippet": {
                            "displayMessage": "badword message",
                            "publishedAt": "2026-07-03T10:05:00Z",
                        },
                    }
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_polling_queue_full(app):
    """メインポーリング時にキューがいっぱいの場合にコメントがスキップされるか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)

    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {
                            "displayName": "User1",
                            "channelId": "ch1",
                        },
                        "snippet": {
                            "displayMessage": "NewComment",
                            "publishedAt": "2026-07-03T10:05:00Z",
                        },
                    }
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.comment_queue = queue.Queue(maxsize=1)
    app.comment_queue.put(("Existing", "Comment"))

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 1


def test_video_worker_ng_word_verbose(app):
    """初期バックログでNGワードがあり、かつverboseがTrueの場合の分岐を検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    mock_video_client.fetch_comment_threads.return_value = (
        [
            {
                "id": "c1",
                "authorDetails": {"displayName": "User1", "channelId": "ch1"},
                "snippet": {
                    "displayMessage": "badword message",
                    "publishedAt": "2026-07-03T10:00:00Z",
                },
            }
        ],
        None,
        3000,
    )
    app.config.ng_words = ["badword"]
    app.stop_event.set()

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )


def test_video_worker_polling_ng_word_verbose(app):
    """リアルタイム監視時にNGワードがあり、かつverboseがTrueの場合の分岐を検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    app.config.ng_words = ["badword"]

    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {"displayName": "User1", "channelId": "ch1"},
                        "snippet": {
                            "displayMessage": "badword message",
                            "publishedAt": "2026-07-03T10:05:00Z",
                        },
                    }
                ],
                None,
                3000,
            )

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )
