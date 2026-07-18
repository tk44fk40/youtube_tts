"""QuotaMonitor のカバレッジを向上させるためのテストモジュールです。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_tts.workers.quota_monitor import QuotaMonitor


def test_format_reset_time_delta_days():
    """format_reset_time で明日やそれ以降の日付が
    正しくフォーマットされるか検証します。"""
    monitor = QuotaMonitor(app=MagicMock(), creds=None, project_id=None)

    with patch("youtube_tts.workers.quota_monitor.datetime") as mock_datetime:
        # 現在時刻を 2026-07-01 に固定
        now_local = datetime(2026, 7, 1).astimezone()
        mock_datetime.now.return_value = now_local

        # 今日 (delta_days == 0)
        reset_time_today = datetime(2026, 7, 1, 15, 30).astimezone()
        assert monitor.format_reset_time(reset_time_today) == "今日の15時30分"

        # 明日 (delta_days == 1)
        reset_time_tomorrow = datetime(2026, 7, 2, 16, 0).astimezone()
        assert monitor.format_reset_time(reset_time_tomorrow) == "明日の16時"

        # それ以降 (delta_days > 1)
        reset_time_future = datetime(2026, 7, 3, 17, 15).astimezone()
        res = monitor.format_reset_time(reset_time_future)
        assert res == "7月3日の17時15分"


def test_is_quota_exceeded_error_not_http_error():
    """HttpError でない例外が False になるか検証します。"""
    monitor = QuotaMonitor(app=MagicMock(), creds=None, project_id=None)
    assert monitor.is_quota_exceeded_error(ValueError("Some error")) is False


def test_is_quota_exceeded_error_not_403():
    """ステータスが 403 ではない HttpError が False になるか検証します。"""
    monitor = QuotaMonitor(app=MagicMock(), creds=None, project_id=None)
    resp = Response({"status": 404})
    error = HttpError(resp, b"Not Found")
    assert monitor.is_quota_exceeded_error(error) is False


def test_is_quota_exceeded_error_content_str_or_bytes():
    """content が bytes 以外の場合でも処理できるか検証します。"""
    monitor = QuotaMonitor(app=MagicMock(), creds=None, project_id=None)
    resp = Response({"status": 403})

    # bytes の場合
    error1 = HttpError(resp, b"quotaExceeded")
    assert monitor.is_quota_exceeded_error(error1) is True

    # 文字列の場合 (モックで差し替え)
    error2 = HttpError(resp, b"")
    error2.content = "quotaExceeded"
    assert monitor.is_quota_exceeded_error(error2) is True

    # どちらでもない場合
    error3 = HttpError(resp, b"")
    error3.content = None
    # 例外の文字列表現に quotaExceeded が含まれる場合
    with patch(
        "googleapiclient.errors.HttpError.__str__", return_value="quotaExceeded"
    ):
        assert monitor.is_quota_exceeded_error(error3) is True


def test_handle_exceeded_error_not_exceeded():
    """クォータ超過ではないエラーの場合に False を返すか検証します。"""
    monitor = QuotaMonitor(app=MagicMock(), creds=None, project_id=None)
    assert monitor.handle_exceeded_error(ValueError("error")) is False


@patch("time.sleep")
def test_handle_exceeded_error_talk_exception(mock_sleep):
    """リセット予定時刻の取得に失敗した際のフォールバックを検証します。"""
    app = MagicMock()
    # empty を返すようにしてループを即抜けるようにする
    app.speech_queue.empty.return_value = True

    monitor = QuotaMonitor(
        app=app, creds=None, project_id=None, quota_talk=True
    )

    # is_quota_exceeded_error は True を返す
    monitor.is_quota_exceeded_error = MagicMock(return_value=True)
    # get_next_reset_time で例外を発生させる
    monitor.get_next_reset_time = MagicMock(side_effect=Exception("Time error"))

    assert monitor.handle_exceeded_error(Exception("test")) is True
    app.logger.warning.assert_called()
    app.speech_queue.put.assert_called()
    # フォールバックメッセージがエンキューされることの確認
    call_args = app.speech_queue.put.call_args[0][0]
    assert call_args.message == "ぴんぽーん！残念！クォータを超過しました。"


@patch("time.sleep")
def test_handle_exceeded_error_wait_drain(mock_sleep):
    """エンキュー後にメッセージが処理されるまで待機するかを検証します。"""
    from youtube_tts.queue import SpeechQueue

    app = MagicMock()
    app.speech_queue = SpeechQueue()
    # 実際にキューから取り出さないと empty にならないため、
    # モックの time.time() で 1 回ループした後に timeout となるよう設定する。
    # ただし SpeechQueue を使うとキューに積まれたメッセージが残るため、
    # empty() は False となり続ける。time.time() 側で抜ける必要がある。

    monitor = QuotaMonitor(
        app=app, creds=None, project_id=None, quota_talk=True
    )
    monitor.is_quota_exceeded_error = MagicMock(return_value=True)
    monitor.get_next_reset_time = MagicMock(
        return_value=datetime(2026, 7, 1, 15, 30)
    )
    monitor.format_reset_time = MagicMock(return_value="今日の15時30分")

    with patch("time.time", side_effect=[100.0, 100.1, 105.1]):
        assert monitor.handle_exceeded_error(Exception("test")) is True

    assert mock_sleep.call_count >= 1


def test_check_and_talk_no_creds():
    """creds または project_id がない場合に即リターンするか検証します。"""
    monitor = QuotaMonitor(app=MagicMock(), creds=None, project_id=None)
    monitor.check_and_talk()
    # nothing happens


@patch("youtube_tts.workers.quota_monitor.get_quota_info")
def test_check_and_talk_queue_full(mock_get_quota):
    """キューが満杯の場合にエンキューがスキップされることを検証します。"""
    app = MagicMock()
    app.speech_queue.full.return_value = True

    monitor = QuotaMonitor(
        app=app, creds="creds", project_id="proj", quota_talk=True, interval=0.0
    )
    monitor.last_spoken_used = 100
    mock_get_quota.return_value = (500, 1000)  # (used, limit)

    monitor.check_and_talk()
    app.speech_queue.put.assert_not_called()
    # is_diff であってもスキップされたため、last_spoken_used は更新されない
    assert monitor.last_spoken_used == 100


@patch("youtube_tts.workers.quota_monitor.get_quota_info")
def test_check_and_talk_exception(mock_get_quota):
    """クォータ取得中に例外が発生した場合の処理を検証します。"""
    app = MagicMock()

    monitor = QuotaMonitor(
        app=app, creds="creds", project_id="proj", quota_talk=True, interval=0.0
    )
    mock_get_quota.side_effect = Exception("API error")

    monitor.check_and_talk()
    app.logger.warning.assert_called_with("クォータ情報の取得に失敗しました。")
