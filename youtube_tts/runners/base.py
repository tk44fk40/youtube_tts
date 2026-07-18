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
"""アプリケーションの実行を管理する共通ランナーモジュールです。"""

import signal
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from youtube_tts.app import YouTubeTtsApp


class BaseRunner(ABC):
    """共通のシグナルハンドリングとライフサイクル管理を提供する基底ランナーです。"""

    def __init__(self, app: "YouTubeTtsApp") -> None:
        """初期化します。

        Args:
            app: YouTubeTtsApp インスタンス。
        """
        self.app = app

    def _handle_signal(self, signum: int, frame: any) -> None:
        """シグナル受信時のハンドラです。"""
        self.app.logger.info("シグナルを受信しました。シャットダウンしています...")
        self.app.stop_event.set()

    @abstractmethod
    def run_worker(self) -> None:
        """サブクラスで実装されるメインのワーカー処理です。"""
        pass

    def run(self) -> None:
        """シグナルハンドラを設定し、再生スレッドとワーカーを起動します。"""
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except ValueError:
            pass  # メインスレッド以外での実行時は無視します。

        from youtube_tts.workers.playback import playback_worker
        playback_thread = threading.Thread(target=lambda: playback_worker(self.app))
        playback_thread.start()

        try:
            self.run_worker()
        except Exception:
            self.app.logger.exception("予期しないエラーが発生しました。")
        finally:
            self.app.cleanup(playback_thread=playback_thread, wait_seconds=5)
