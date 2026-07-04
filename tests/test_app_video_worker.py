"""YouTubeTtsApp.video_worker のテストモジュール。"""

import queue
from unittest.mock import MagicMock, patch

import youtube_tts.workers.video  # noqa: F401
from youtube_tts import YouTubeVideoClient


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


def test_video_worker_backlog_remaining_exhausted(app):
    """バックログ取得の remaining_to_fetch が 0 になって break するか検証。

    backlog_counts=1 のとき 1件取得後に remaining_to_fetch が 0 に
    なり、次ループ先頭の L49 の break が実行されることを確認する。
    """
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # ページトークンを持たせて L72 での break を防ぐ
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {"displayName": "U1"},
                        "snippet": {"displayMessage": "Hello"},
                    }
                ],
                "next_token",
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        backlog_counts=1,
    )

    assert app.comment_queue.qsize() == 1


@patch("time.sleep")
def test_video_worker_backlog_error_verbose_true(mock_sleep, app):
    """バックログ取得エラー時に verbose=True でデバッグログが出るか検証。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("バックログ取得エラー")
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


@patch("time.sleep")
def test_video_worker_backlog_error_verbose_false(mock_sleep, app):
    """バックログ取得エラー時に verbose=False の分岐を検証する。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("バックログ取得エラー")
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=False,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


@patch("time.sleep")
def test_video_worker_backlog_unlimited_remaining(mock_sleep, app):
    """backlog_counts=-1 のとき
    remaining_to_fetch が None になることを検証する。
    """
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # ページトークンなし → break
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {"displayName": "U1"},
                        "snippet": {"displayMessage": "Hello"},
                    }
                ],
                None,
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        backlog_counts=-1,
    )

    assert app.comment_queue.qsize() == 1


@patch("time.sleep")
def test_video_worker_backlog_ng_word_verbose_actual(mock_sleep, app):
    """バックログ取得時に NG ワード + verbose=True の場合を検証。

    stop_event を事前設定せず実際に NG ワード分岐を通過させる。
    """
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    app.config.ng_words = ["badword"]
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {"displayName": "User1"},
                        "snippet": {"displayMessage": "badword message"},
                    }
                ],
                None,
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


@patch("time.sleep")
def test_video_worker_backlog_queue_full_actual(mock_sleep, app):
    """バックログ取得時にキューが満杯の場合に L92-93 をカバーする。

    stop_event を事前設定せず実際にキューフル分岐を通過させる。
    """
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {"displayName": "User1"},
                        "snippet": {"displayMessage": "Hello"},
                    }
                ],
                None,
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.comment_queue = queue.Queue(maxsize=1)
    app.comment_queue.put(("Existing", "Comment"))

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 1


@patch("time.sleep")
def test_video_worker_polling_verbose_false(mock_sleep, app):
    """ポーリングループで verbose=False のときの分岐をカバーする。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
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
                        "authorDetails": {"displayName": "User1"},
                        "snippet": {"displayMessage": "Hello"},
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
        verbose=False,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 1


def test_video_worker_polling_error_verbose_false(app):
    """ポーリングエラー時に verbose=False の分岐を検証する。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000
        else:
            raise Exception("polling error")

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=False,
        backlog_counts=10,
    )

    assert app.stop_event.is_set() is True


@patch("time.sleep")
def test_video_worker_polling_ng_word_verbose_false(mock_sleep, app):
    """ポーリング時に NG ワード + verbose=False の分岐を検証する。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    app.config.ng_words = ["badword"]
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
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
                        "authorDetails": {"displayName": "User1"},
                        "snippet": {"displayMessage": "badword message"},
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
        verbose=False,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


@patch("time.sleep")
def test_video_worker_backlog_ng_word_verbose_false(mock_sleep, app):
    """バックログ取得時に NG ワード + verbose=False の分岐を検証する。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    app.config.ng_words = ["badword"]
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                [
                    {
                        "id": "c1",
                        "authorDetails": {"displayName": "User1"},
                        "snippet": {"displayMessage": "badword message"},
                    }
                ],
                None,
                3000,
            )
        else:
            app.stop_event.set()
            return [], None, 3000

    mock_video_client.fetch_comment_threads.side_effect = fetch_side_effect

    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=False,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0
