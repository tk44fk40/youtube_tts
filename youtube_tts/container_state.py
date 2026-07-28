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
"""VOICEVOX コンテナの排他制御・状態管理モジュールです。"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any, Callable


class VoicevoxContainerStateManager:
    """プロセス間の排他ロックとアクティブ PID の管理クラスです。"""

    def __init__(
        self,
        lock_file_path: str | Path = "/tmp/youtube_tts_voicevox_runners.lock",
        state_file_path: str | Path = "/tmp/youtube_tts_voicevox_runners.json",
    ) -> None:
        """VoicevoxContainerStateManager を初期化します。

        Args:
            lock_file_path: プロセス排他ロックファイルのパスです。
            state_file_path: アクティブ PID 管理ファイルのパスです。
        """
        self.lock_file_path = Path(lock_file_path)
        self.state_file_path = Path(state_file_path)

    @staticmethod
    def is_process_alive(pid: int) -> bool:
        """指定された PID のプロセスが生きているか判定します。

        Args:
            pid: 判定対象のプロセス ID です。

        Returns:
            bool: 生きている場合は True、それ以外は False です。
        """
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def with_lock(self, func: Callable[[], Any]) -> Any:
        """ファイルロックを取得して同期的に関数を実行します。

        Args:
            func: ロック内で実行する呼び出し可能オブジェクトです。

        Returns:
            Any: 関数 `func` の実行結果です。
        """
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_file_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                return func()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def read_active_pids(self) -> list[int]:
        """登録中のアクティブ PID を取得し死滅 PID を消去します。

        Returns:
            list[int]: アクティブな PID のリストです。
        """
        if not self.state_file_path.exists():
            return []
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                pids = data.get("pids", [])
                active_pids = [
                    pid for pid in pids if self.is_process_alive(pid)
                ]
                return active_pids
        except Exception:
            return []

    def write_active_pids(self, pids: list[int]) -> None:
        """アクティブな PID のリストを状態ファイルに保存します。

        Args:
            pids: 保存する PID のリストです。
        """
        self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file_path, "w", encoding="utf-8") as f:
            json.dump({"pids": pids}, f)

    def register_process(self) -> int:
        """現在のプロセス PID を登録し、最新の登録数を返します。

        Returns:
            int: 登録後のアクティブなプロセス数です。
        """

        def _do() -> int:
            pids = self.read_active_pids()
            my_pid = os.getpid()
            if my_pid not in pids:
                pids.append(my_pid)
            self.write_active_pids(pids)
            return len(pids)

        return self.with_lock(_do)

    def unregister_process(self) -> int:
        """現在のプロセス PID を登録解除し、残りの登録数を返します。

        Returns:
            int: 解除後の残りのアクティブなプロセス数です。
        """

        def _do() -> int:
            pids = self.read_active_pids()
            my_pid = os.getpid()
            if my_pid in pids:
                pids.remove(my_pid)
            self.write_active_pids(pids)
            return len(pids)

        return self.with_lock(_do)
