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

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp  # pragma: no cover
    from youtube_tts.models import SpeechItem



def playback_worker(app: YouTubeTtsApp) -> None:
    """コメント再生キューを監視し、順次再生するスレッドワーカーです。

    Args:
        app: YouTubeTtsApp インスタンス。

    """
    while not app.stop_event.is_set():
        try:
            item: SpeechItem = app.comment_queue.get(timeout=1)
            author = item.author
            message = item.message
            char_count = item.char_count

            with app.queue_lock:
                app.queued_char_count = max(
                    0, app.queued_char_count - char_count
                )
                remaining_chars = app.queued_char_count
        except queue.Empty:
            continue

        text = f"{author} {message}"

        base_speed = app.config.speed_scale
        speed = base_speed

        if app.config.auto_speed_boost and remaining_chars > 0:
            rate_at_base = 6.0 * base_speed
            estimated_duration = (
                remaining_chars / rate_at_base if rate_at_base > 0 else 0
            )
            max_speed = min(getattr(app.config, "max_speed", 2.2), 2.2)

            if base_speed < max_speed:
                if estimated_duration <= 10.0:
                    speed = base_speed
                elif estimated_duration >= 40.0:
                    speed = max_speed
                else:
                    ratio = (estimated_duration - 10.0) / (40.0 - 10.0)
                    speed = base_speed + (max_speed - base_speed) * ratio

            app.logger.info(f"[TALK] {text} (Speed: {speed:.2f}x)")
        else:
            app.logger.info(f"[TALK] {text}")

        app.speak(text, speed_scale=speed)
        app.comment_queue.task_done()
