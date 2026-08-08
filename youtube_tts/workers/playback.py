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
"""音声再生ワーカーを定義するモジュールです。"""

from __future__ import annotations

import queue
from typing import TYPE_CHECKING

from youtube_tts.constants import (
    BOOST_DURATION_MAX,
    BOOST_DURATION_MIN,
    CHAR_RATE_PER_SECOND_BASE,
    DEFAULT_MAX_SPEED,
    LOG_PREFIX_TALK,
    MAX_SPEED_SCALE,
)

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp  # pragma: no cover
    from youtube_tts.models import SpeechItem


def calculate_playback_speed(
    base_speed: float,
    remaining_chars: int,
    max_speed_limit: float = DEFAULT_MAX_SPEED,
) -> float:
    """キューに溜まっている文字数に基づいて再生速度を動的に計算します。

    Args:
        base_speed: 基本の再生速度。
        remaining_chars: キューに溜まっている文字数。
        max_speed_limit: 設定上の最大再生速度。

    Returns:
        計算された再生速度。
    """
    if remaining_chars <= 0:
        return base_speed

    rate_at_base = CHAR_RATE_PER_SECOND_BASE * base_speed
    estimated_duration = remaining_chars / rate_at_base if rate_at_base > 0 else 0.0
    max_speed = min(max_speed_limit, MAX_SPEED_SCALE)

    if base_speed >= max_speed:
        return base_speed

    if estimated_duration <= BOOST_DURATION_MIN:
        return base_speed
    if estimated_duration >= BOOST_DURATION_MAX:
        return max_speed

    ratio = (estimated_duration - BOOST_DURATION_MIN) / (
        BOOST_DURATION_MAX - BOOST_DURATION_MIN
    )
    return base_speed + (max_speed - base_speed) * ratio


def playback_worker(app: YouTubeTtsApp) -> None:
    """コメント再生キューを監視し、順次再生するスレッドワーカーです。

    Args:
        app: YouTubeTtsApp インスタンス。

    """
    while not app.stop_event.is_set():
        try:
            item: SpeechItem = app.speech_queue.get(timeout=1)
            author = item.author
            message = item.message
            remaining_chars = app.speech_queue.queued_char_count
        except queue.Empty:
            continue

        text = f"{author} {message}"

        base_speed = app.config.speed_scale
        speed = base_speed

        if app.config.auto_speed_boost and remaining_chars > 0:
            max_speed_limit = getattr(app.config, "max_speed", DEFAULT_MAX_SPEED)
            speed = calculate_playback_speed(
                base_speed=base_speed,
                remaining_chars=remaining_chars,
                max_speed_limit=max_speed_limit,
            )
            app.logger.info(f"{LOG_PREFIX_TALK} {text} (Speed: {speed:.2f}x)")
        else:
            app.logger.info(f"{LOG_PREFIX_TALK} {text}")

        app.speak(text, speed_scale=speed)
        app.speech_queue.task_done()
