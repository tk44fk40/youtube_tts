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
"""スレッドセーフな再生キューと状態管理を提供するモジュールです。"""

import queue
import threading

from .models import SpeechItem


class SpeechQueue:
    """音声再生用アイテムのキューと、滞留している文字数をスレッドセーフに管理するクラスです。"""

    def __init__(self, maxsize: int = 50) -> None:
        """初期化します。

        Args:
            maxsize (int): キューの最大サイズです。
        """
        self._queue: queue.Queue[SpeechItem] = queue.Queue(maxsize=maxsize)
        self._char_count: int = 0
        self._lock = threading.Lock()

    def put(
        self, item: SpeechItem, block: bool = True, timeout: float | None = None
    ) -> None:
        """キューにアイテムを追加し、滞留文字数を加算します。"""
        self._queue.put(item, block=block, timeout=timeout)
        with self._lock:
            self._char_count += item.char_count

    def get(
        self, block: bool = True, timeout: float | None = None
    ) -> SpeechItem:
        """キューからアイテムを取得し、滞留文字数を減算します。"""
        item = self._queue.get(block=block, timeout=timeout)
        with self._lock:
            self._char_count = max(0, self._char_count - item.char_count)
        return item

    def get_nowait(self) -> SpeechItem:
        """ブロックせずにキューからアイテムを取得し、滞留文字数を減算します。"""
        return self.get(block=False)

    def task_done(self) -> None:
        """キューのタスク完了を通知します。"""
        self._queue.task_done()

    def empty(self) -> bool:
        """キューが空かどうかを返します。"""
        return self._queue.empty()

    def qsize(self) -> int:
        """キューに入っているアイテム数を返します。"""
        return self._queue.qsize()

    def full(self) -> bool:
        """キューが満杯かどうかを返します。"""
        return self._queue.full()

    @property
    def queued_char_count(self) -> int:
        """現在キューに滞留している合計文字数を返します。"""
        with self._lock:
            return self._char_count
