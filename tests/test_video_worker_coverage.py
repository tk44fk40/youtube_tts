"""video_worker の未カバー行を通すための追加カバレッジテストです。"""

from __future__ import annotations

import queue
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_tts.models import SpeechItem
from youtube_tts.workers.video import format_error_details, video_worker


def test_format_error_details_exceptions():
    """format_error_details で str() や repr() が失敗するオブジェクトを処理できるか検証します。"""
    class BadException1(Exception):
        def __str__(self):
            raise ValueError("str failed")

    class BadException2(Exception):
        def __str__(self):
            raise ValueError("str failed")
        def __repr__(self):
            raise ValueError("repr failed")

    err1 = BadException1()
    res1 = format_error_details(err1)
    # repr は成功するので BadException1(...) になるか、または str 扱い
    assert "BadException1" in res1

    err2 = BadException2()
    res2 = format_error_details(err2)
    assert res2 == "BadException2(details unavailable)"


def test_video_worker_backlog_handled_error():
    """初期バックログ取得でクォータエラーが handle された場合を検証します。"""
    app = MagicMock()
    # 初期状態で stop_event は False だが、ループを1回で抜けるように backlog_counts=1 にして
    # そこでエラーを発生させ、handled=True になるようにする。
    # すると app.logger.error("初期...") が呼ばれない。
    
    video_client = MagicMock()
    resp = Response({"status": 403})
    error = HttpError(resp, b"quotaExceeded")
    video_client.fetch_comment_threads.side_effect = error

    app.stop_event.is_set.side_effect = [False, True]  # 2回目の while 条件で False

    with patch("youtube_tts.workers.video.QuotaMonitor") as mock_qm_class:
        mock_qm_instance = mock_qm_class.return_value
        mock_qm_instance.handle_exceeded_error.return_value = True
        
        video_worker(
            app=app,
            video_client=video_client,
            video_id="video_123",
            creds="creds",
            quota_check=True,
            backlog_counts=1,
        )
        
    mock_qm_instance.handle_exceeded_error.assert_called_once_with(error)
    # handled=True なので error は呼ばれないはず
    app.logger.error.assert_not_called()


def test_video_worker_polling_handled_error():
    """リアルタイムポーリング取得でクォータエラーが handle された場合を検証します。"""
    app = MagicMock()
    app.stop_event.is_set.return_value = False  # polling loop
    
    video_client = MagicMock()
    # backlog 取得用 (正常)
    video_client.fetch_comment_threads.return_value = ([], "token", 3000)
    
    # polling 取得用 (エラー) を side_effect のリストで分ける
    resp = Response({"status": 403})
    error = HttpError(resp, b"quotaExceeded")
    
    call_count = 0
    def fetch_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000  # backlog 完了
        else:
            app.stop_event.is_set.return_value = True  # 一度エラーが起きたら抜けるように
            raise error

    video_client.fetch_comment_threads.side_effect = fetch_side_effect
    
    with patch("youtube_tts.workers.video.QuotaMonitor") as mock_qm_class, \
         patch("time.sleep"):
        mock_qm_instance = mock_qm_class.return_value
        mock_qm_instance.handle_exceeded_error.return_value = True
        
        video_worker(
            app=app,
            video_client=video_client,
            video_id="video_123",
            creds="creds",
            quota_check=True,
            backlog_counts=10,
        )
        
    mock_qm_instance.handle_exceeded_error.assert_called_once_with(error)
    app.logger.error.assert_not_called()


def test_video_worker_polling_check_and_talk():
    """ポーリングの最後に check_and_talk が呼ばれることを検証します。"""
    app = MagicMock()
    app.stop_event.is_set.return_value = False
    
    video_client = MagicMock()
    
    call_count = 0
    def fetch_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [], None, 3000  # backlog 完了
        else:
            app.stop_event.is_set.return_value = True # polling を1回で終える
            return [], None, 3000

    video_client.fetch_comment_threads.side_effect = fetch_side_effect
    
    with patch("youtube_tts.workers.video.QuotaMonitor") as mock_qm_class, \
         patch("time.sleep"):
        mock_qm_instance = mock_qm_class.return_value
        
        video_worker(
            app=app,
            video_client=video_client,
            video_id="video_123",
            creds="creds",
            quota_check=True,
            backlog_counts=10,
        )
        
    mock_qm_instance.check_and_talk.assert_called_once()
