"""YouTubeTtsApp.video_worker の動作を検証するテストモジュールです。"""

from __future__ import annotations

import queue
from typing import Any
from unittest.mock import MagicMock, patch

from youtube_tts import YouTubeVideoClient


def test_video_worker_success(app: Any) -> None:
    """正常に動画コメントを取得し、コメントキューが更新されるかを検証します。"""
    # YouTubeVideoClient のモックを作成します。
    mock_video_client = MagicMock(spec=YouTubeVideoClient)

    call_count = 0

    # API呼び出しのモック動作を定義します。
    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # 1回目は初期バックログ用コメントを返します。
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
            # 2回目はバックログ取得のループ終了条件を満たすために空を返します。
            return [], None, 3000
        else:
            # 3回目はメインループ内での動作として、
            # 重複と新規コメントを返します。
            app.stop_event.set()
            return (
                [
                    {
                        "id": "c1",  # バックログとの重複のためスキップされます
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
                        "id": "c2",  # 新規コメントとしてキューに格納されます
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

    # 対象のワーカー関数を実行します。
    app.video_worker(
        video_client=mock_video_client,
        video_id="video_123",
        chat_interval=0.01,
        verbose=True,
        backlog_counts=10,
    )

    # 取得したコメント数および文字数が想定通りか検証します。
    assert app.comment_queue.qsize() == 2
    assert app.queued_char_count == 32


def test_video_worker_backlog_counts_zero(app: Any) -> None:
    """backlog_countsが0の場合に初期コメントロードがスキップされるかを検証します。"""
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


def test_video_worker_backlog_counts_negative(app: Any) -> None:
    """backlog_countsが負数の場合に制限なしでロードできるかを検証します。"""
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


def test_video_worker_backlog_empty(app: Any) -> None:
    """初期バックログが空の場合に正しく動作するかを検証します。"""
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


def test_video_worker_backlog_error(app: Any) -> None:
    """初期バックログ取得中にエラーが発生しても処理が継続するかを検証します。"""
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


def test_video_worker_backlog_ng_word(app: Any) -> None:
    """初期バックログ内のNGワードスキップ処理を検証します。"""
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


def test_video_worker_backlog_queue_full(app: Any) -> None:
    """初期バックログ取得時にキューがいっぱいの場合スキップされるかを検証します。"""
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


def test_video_worker_polling_error(app: Any) -> None:
    """メインポーリング中エラー発生時のループ終了を検証します。"""
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


def test_video_worker_polling_ng_word(app: Any) -> None:
    """メインポーリング時のNGワードスキップ処理を検証します。"""
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


def test_video_worker_polling_queue_full(app: Any) -> None:
    """メインポーリング時のキュー満杯によるスキップを検証します。"""
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


def test_video_worker_ng_word_verbose(app: Any) -> None:
    """初期バックログのNGワードかつ詳細出力ありの場合を検証します。"""
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


def test_video_worker_polling_ng_word_verbose(app: Any) -> None:
    """リアルタイム監視時のNGワードかつ詳細出力ありを検証します。"""
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


def test_video_worker_backlog_remaining_exhausted(app: Any) -> None:
    """バックログ取得の remaining_to_fetch が 0 になって break するか検証。

    backlog_counts=1 のとき、1 件取得後に
    remaining_to_fetch が 0 になり、
    次のループ先頭で break が実行されることを検証します。
    """
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    call_count = 0

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        """フェッチのサイドエフェクト。"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # ページトークンを持たせてループ途中での break を防ぎます。
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


def test_video_worker_backlog_error_emits_debug_log(app: Any) -> None:
    """バックログ取得エラー時に DEBUG ログが出ることを検証します。"""
    mock_video_client = MagicMock(spec=YouTubeVideoClient)
    mock_video_client.fetch_comment_threads.side_effect = Exception(
        "バックログ取得エラー"
    )

    with patch.object(app.logger, "debug") as mock_debug:
        app.video_worker(
            video_client=mock_video_client,
            video_id="video_123",
            chat_interval=0.01,
            verbose=False,
            backlog_counts=10,
        )

    mock_debug.assert_called()
    assert app.comment_queue.qsize() == 0


@patch("time.sleep")
def test_video_worker_backlog_error_verbose_false(
    mock_sleep: Any,
    app: Any,
) -> None:
    """バックログ取得エラー時に
    verbose=False の分岐を検証します。
    """
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
def test_video_worker_backlog_unlimited_remaining(
    mock_sleep: Any,
    app: Any,
) -> None:
    """backlog_counts=-1 のとき、
    remaining_to_fetch が None になることを検証します。
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
def test_video_worker_backlog_ng_word_verbose_actual(
    mock_sleep: Any,
    app: Any,
) -> None:
    """バックログ取得時に NG ワード + verbose=True の場合を検証。

    stop_event を事前設定せず実際に NG ワード分岐を通過させるを検証します。
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
def test_video_worker_backlog_queue_full_actual(
    mock_sleep: Any,
    app: Any,
) -> None:
    """バックログ取得時にキューが満杯の場合の処理を検証します。

    stop_event を事前設定せず実際にキューが満杯の分岐を通過させて検証します。
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
def test_video_worker_polling_verbose_false(
    mock_sleep: Any,
    app: Any,
) -> None:
    """ポーリングループで、
    verbose=False のときの分岐を検証します。
    """
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


def test_video_worker_polling_error_verbose_false(app: Any) -> None:
    """ポーリングエラー時に verbose=False の分岐をを検証します。"""
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
def test_video_worker_polling_ng_word_verbose_false(
    mock_sleep: Any,
    app: Any,
) -> None:
    """ポーリング時に NG ワードかつ
    verbose=False の分岐を検証します。
    """
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
def test_video_worker_backlog_ng_word_verbose_false(
    mock_sleep: Any,
    app: Any,
) -> None:
    """バックログ取得時に NG ワードかつ
    verbose=False の分岐を検証します。
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
        verbose=False,
        backlog_counts=10,
    )

    assert app.comment_queue.qsize() == 0


def test_video_worker_success_with_dataclasses(app: Any) -> None:
    """本番用のデータクラスオブジェクトをモックとして返し、
    キャストがバイパスされることを検証します。
    """
    from datetime import datetime, timezone

    from youtube_tts.models import YouTubeMessage

    mock_video_client = MagicMock(spec=YouTubeVideoClient)

    call_count = 0
    now = datetime.now(timezone.utc)

    def fetch_side_effect(video_id, page_token=None, max_results=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # バックログコメント
            return (
                [
                    YouTubeMessage(
                        id="c1",
                        author_name="User1",
                        author_id="ch1",
                        message="Hello",
                        published_at=now,
                    )
                ],
                None,
                3000,
            )
        else:
            # ポーリングコメント
            app.stop_event.set()
            return (
                [
                    YouTubeMessage(
                        id="c2",
                        author_name="User2",
                        author_id="ch2",
                        message="World",
                        published_at=now,
                    )
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
