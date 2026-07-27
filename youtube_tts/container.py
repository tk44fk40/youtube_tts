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
"""VOICEVOX Engine コンテナの生命周期管理を行うモジュールです。"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests


class VoicevoxContainerManager:
    """VOICEVOX Engine コンテナの作成・起動・管理を行うクラスです。"""

    def __init__(
        self,
        container_name: str = "voicevox-engine",
        image_name: str = "docker.io/voicevox/voicevox_engine:cpu-latest",
        port: int = 50021,
        host: str = "127.0.0.1",
        container_cmd: str | None = None,
        lock_file_path: str | Path = "/tmp/youtube_tts_voicevox_runners.lock",
        state_file_path: str | Path = "/tmp/youtube_tts_voicevox_runners.json",
    ) -> None:
        """VoicevoxContainerManager を初期化します。

        Args:
            container_name: コンテナ名です。
            image_name: VOICEVOX のコンテナイメージ名です。
            port: バインドするポート番号です。
            host: バインドするホストアドレスです。
            container_cmd: コンテナ実行コマンド (podman / docker) です。
            lock_file_path: プロセス排他ロックファイルのパスです。
            state_file_path: アクティブ PID 管理ファイルのパスです。
        """
        self.container_name = container_name
        self.image_name = image_name
        self.port = port
        self.host = host
        self.lock_file_path = Path(lock_file_path)
        self.state_file_path = Path(state_file_path)
        self._managed_by_this_process = False

        if container_cmd is not None:
            self.container_cmd = container_cmd
        else:
            env_cmd = os.getenv("CONTAINER_CMD")
            if env_cmd:
                self.container_cmd = env_cmd
            elif shutil.which("podman"):
                self.container_cmd = "podman"
            elif shutil.which("docker"):
                self.container_cmd = "docker"
            else:
                self.container_cmd = "podman"

    @property
    def base_url(self) -> str:
        """VOICEVOX サーバーのベース URL です。

        Returns:
            str: VOICEVOX サーバーのベース URL です。
        """
        return f"http://{self.host}:{self.port}"

    def is_container_cmd_available(self) -> bool:
        """Podman または Docker コマンドが利用可能かを判定します。

        Returns:
            bool: 利用可能であれば True、それ以外は False です。
        """
        return shutil.which(self.container_cmd) is not None

    def is_server_ready(self, timeout: float = 2.0) -> bool:
        """VOICEVOX サーバーが応答可能か確認します。

        Args:
            timeout: リクエストのタイムアウト時間（秒）です。

        Returns:
            bool: 応答可能であれば True、それ以外は False です。
        """
        try:
            response = requests.get(f"{self.base_url}/version", timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False

    def is_container_running(self) -> bool:
        """コンテナが実行中か判定します。

        Returns:
            bool: 実行中であれば True、それ以外は False です。
        """
        if not self.is_container_cmd_available():
            return False
        try:
            res = subprocess.run(
                [
                    self.container_cmd,
                    "ps",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            names = [
                line.strip() for line in res.stdout.splitlines() if line.strip()
            ]
            return self.container_name in names
        except Exception:
            return False

    def is_container_exists(self) -> bool:
        """コンテナが存在（停止中含む）するか判定します。

        Returns:
            bool: 存在していれば True、それ以外は False です。
        """
        if not self.is_container_cmd_available():
            return False
        try:
            res = subprocess.run(
                [
                    self.container_cmd,
                    "ps",
                    "-a",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            names = [
                line.strip() for line in res.stdout.splitlines() if line.strip()
            ]
            return self.container_name in names
        except Exception:
            return False

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

    def _with_lock(self, func: Any) -> Any:
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

    def _read_active_pids(self) -> list[int]:
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

    def _write_active_pids(self, pids: list[int]) -> None:
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
            pids = self._read_active_pids()
            my_pid = os.getpid()
            if my_pid not in pids:
                pids.append(my_pid)
            self._write_active_pids(pids)
            return len(pids)

        return self._with_lock(_do)

    def unregister_process(self) -> int:
        """現在のプロセス PID を登録解除し、残りの登録数を返します。

        Returns:
            int: 解除後の残りのアクティブなプロセス数です。
        """

        def _do() -> int:
            pids = self._read_active_pids()
            my_pid = os.getpid()
            if my_pid in pids:
                pids.remove(my_pid)
            self._write_active_pids(pids)
            return len(pids)

        return self._with_lock(_do)

    def ensure_started(
        self,
        logger: logging.Logger | None = None,
        wait_timeout: float = 60.0,
    ) -> bool:
        """VOICEVOX コンテナを確保・起動します。

        Args:
            logger: ログ出力に使用するロガーオブジェクトです。
            wait_timeout: 起動完了を待機する最大時間（秒）です。

        Returns:
            bool: 使用可能状態であれば True、それ以外は False です。
        """
        # 1. すでにサーバーが起動・応答していればそのまま使用
        if self.is_server_ready():
            self.register_process()
            return True

        # 2. コンテナコマンド（Podman/Docker）が使えるか判定
        if not self.is_container_cmd_available():
            if logger:
                logger.warning(
                    f"コンテナ '{self.container_cmd}' が利用不可です。"
                )
                logger.warning(
                    "自動起動をスキップします。"
                    "VOICEVOX を別途起動してください。"
                )
            return False

        self.register_process()
        self._managed_by_this_process = True

        # 3. コンテナの状態を確認して起動または作成
        if self.is_container_running():
            pass
        elif self.is_container_exists():
            if logger:
                logger.info(f"既存コンテナ '{self.container_name}' を起動中...")
            subprocess.run(
                [self.container_cmd, "start", self.container_name],
                check=False,
            )
        else:
            if logger:
                logger.warning("VOICEVOX コンテナを作成・起動しています。")
                logger.warning(
                    "初回はイメージ取得に時間を要する場合があります..."
                )
            cmd = [
                self.container_cmd,
                "run",
                "-d",
                "--name",
                self.container_name,
                "--restart",
                "unless-stopped",
                "-p",
                f"{self.host}:{self.port}:50021",
                self.image_name,
            ]
            subprocess.run(cmd, check=False)

        # 4. サーバーの準備が整うまで待機
        start_time = time.time()
        while time.time() - start_time < wait_timeout:
            if self.is_server_ready():
                if logger:
                    logger.info("VOICEVOX サーバーの準備が完了しました。")
                return True
            time.sleep(1.0)

        if logger:
            logger.error("VOICEVOX 起動待ちがタイムアウトしました。")
        return False

    def stop_if_last(self, logger: logging.Logger | None = None) -> bool:
        """自分が最後のプロセスの場合はコンテナを停止します。

        Args:
            logger: ログ出力に使用するロガーオブジェクトです。

        Returns:
            bool: コンテナ停止を実行した場合は True、それ以外は False です。
        """
        remaining_count = self.unregister_process()
        if remaining_count == 0 and self.is_container_running():
            if logger:
                logger.info(
                    f"プロセス終了のため '{self.container_name}' を停止中..."
                )
            subprocess.run(
                [self.container_cmd, "stop", self.container_name],
                check=False,
            )
            return True
        return False
