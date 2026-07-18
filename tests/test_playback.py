"""playback_worker モジュールのテストです。"""

from __future__ import annotations

import queue
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
    """base_speed が max_speed_limit 以上の場合は
    base_speed がそのまま返るか検証します。"""
    assert calculate_playback_speed(2.5, 100, 2.2) == 2.5
    assert calculate_playback_speed(2.2, 100, 2.2) == 2.2


def test_calculate_playback_speed_short_duration():
    """推定再生時間が 10 秒以下の場合は
    base_speed がそのまま返るか検証します。"""
    # base_speed=1.0 -> rate=6.0
    # remaining_chars=30 -> duration=5.0s (<= 10.0)
    assert calculate_playback_speed(1.0, 30, 2.2) == 1.0


def test_calculate_playback_speed_long_duration():
    """推定再生時間が 40 秒以上の場合は max_speed が返るか検証します。"""
    # base_speed=1.0 -> rate=6.0
    # remaining_chars=300 -> duration=50.0s (>= 40.0)
    assert calculate_playback_speed(1.0, 300, 2.2) == 2.2


def test_calculate_playback_speed_medium_duration():
    """推定再生時間が 10〜40 秒の間の場合は、
    線形補間された速度が返るか検証します。"""
    # base_speed=1.0 -> rate=6.0
    # remaining_chars=150 -> duration=25.0s
    # ratio = (25.0 - 10.0) / (40.0 - 10.0) = 15.0 / 30.0 = 0.5
    # expected_speed = 1.0 + (2.2 - 1.0) * 0.5 = 1.0 + 1.2 * 0.5 = 1.6
    assert calculate_playback_speed(1.0, 150, 2.2) == 1.6


def test_calculate_playback_speed_zero_base_speed():
    """base_speed が 0 の場合でもゼロ除算が起きないか検証します。"""
    # base_speed=0.0 -> rate=0.0 -> duration=0.0s (<= 10.0)
    assert calculate_playback_speed(0.0, 100, 2.2) == 0.0


def test_playback_worker_empty_queue():
    """キューが空の場合に continue されることを検証します。"""
    app = MagicMock()
    app.stop_event.is_set.side_effect = [False, True]
    app.speech_queue.get.side_effect = queue.Empty

    playback_worker(app)

    app.speak.assert_not_called()


def test_playback_worker_process_item_no_boost():
    """auto_speed_boost が False の場合に
    通常の速度で再生されることを検証します。"""
    app = MagicMock()
    app.stop_event.is_set.side_effect = [False, True]

    item = SpeechItem(author="Test", message="Hello", char_count=5)
    app.speech_queue.get.return_value = item
    app.speech_queue.queued_char_count = 100

    app.config.auto_speed_boost = False
    app.config.speed_scale = 1.2

    playback_worker(app)

    app.logger.info.assert_called_with("[TALK] Test Hello")
    app.speak.assert_called_once_with("Test Hello", speed_scale=1.2)
    app.speech_queue.task_done.assert_called_once()


def test_playback_worker_process_item_with_boost():
    """auto_speed_boost が True で残り文字数がある場合に
    速度が調整されることを検証します。"""
    app = MagicMock()
    app.stop_event.is_set.side_effect = [False, True]

    item = SpeechItem(author="Test", message="Hello", char_count=5)
    app.speech_queue.get.return_value = item
    # 300文字で1.0xの場合、推定時間は50秒となりmax_speed(2.2)になる
    app.speech_queue.queued_char_count = 300

    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    playback_worker(app)

    app.logger.info.assert_called_with("[TALK] Test Hello (Speed: 2.20x)")
    app.speak.assert_called_once_with("Test Hello", speed_scale=2.2)
