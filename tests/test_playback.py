"""再生ワーカーと自動スピードブースト機能のテストです。"""

from __future__ import annotations

from unittest.mock import MagicMock

from youtube_tts.models import SpeechItem
from youtube_tts.workers.playback import (
    calculate_playback_speed,
    playback_worker,
)


def test_calculate_playback_speed_no_remaining():
    """残りの文字数が 0 以下の場合は base_speed がそのまま返るか検証します。"""
    assert calculate_playback_speed(1.0, 0, 2.2) == 1.0
    assert calculate_playback_speed(1.5, -5, 2.2) == 1.5


def test_calculate_playback_speed_base_exceeds_max():
    """base_speed が max_speed_limit 以上のケースを検証します。"""
    assert calculate_playback_speed(2.5, 100, 2.2) == 2.5
    assert calculate_playback_speed(2.2, 100, 2.2) == 2.2


def test_calculate_playback_speed_short_duration():
    """推定再生時間が 10 秒以下のケースを検証します。"""
    assert calculate_playback_speed(1.0, 30, 2.2) == 1.0


def test_calculate_playback_speed_long_duration():
    """推定再生時間が 40 秒以上の場合は max_speed が返るか検証します。"""
    assert calculate_playback_speed(1.0, 300, 2.2) == 2.2


def test_calculate_playback_speed_medium_duration():
    """推定再生時間が 10〜40 秒の間のケースを検証します。"""
    assert calculate_playback_speed(1.0, 150, 2.2) == 1.6


def test_playback_worker_stop_immediately():
    """stop_event が最初からセット時の即座終了を検証します。"""
    app = MagicMock()
    app.stop_event.is_set.return_value = True

    playback_worker(app)

    app.speech_queue.get.assert_not_called()


def test_playback_worker_process_item_no_boost():
    """auto_speed_boost が False 時の通常の再生速度を検証します。"""
    app = MagicMock()
    app.stop_event.is_set.side_effect = [False, True]
    app.config.auto_speed_boost = False
    app.config.speed_scale = 1.2

    item = SpeechItem(author="Test", message="Hello", char_count=5)
    app.speech_queue.get.return_value = item
    app.speech_queue.queued_char_count = 100

    playback_worker(app)

    app.logger.info.assert_called_with("[TALK] Test Hello")
    app.speak.assert_called_once_with("Test Hello", speed_scale=1.2)
    app.speech_queue.task_done.assert_called_once()


def test_playback_worker_process_item_with_boost():
    """auto_speed_boost が True 時の速度調整を検証します。"""
    app = MagicMock()
    app.stop_event.is_set.side_effect = [False, True]
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    item = SpeechItem(author="Test", message="Hello", char_count=5)
    app.speech_queue.get.return_value = item
    app.speech_queue.queued_char_count = 300

    playback_worker(app)

    app.logger.info.assert_called_with("[TALK] Test Hello (Speed: 2.20x)")
    app.speak.assert_called_once_with("Test Hello", speed_scale=2.2)
    app.speech_queue.task_done.assert_called_once()
