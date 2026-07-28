"""STDIO および HTTP 通信のトランスポート実装モジュールです。"""

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any

import httpx

from youtube_tts.logger import get_logger
from youtube_tts.plugins.models import PluginManifest, PluginMessage

logger = get_logger()

# 定数定義
DEFAULT_PROCESS_WAIT_TIMEOUT = 1.0


class BaseTransport(ABC):
    """プラグイン用トランスポートの抽象基底クラスです。"""

    @abstractmethod
    async def send_and_receive(
        self, message: PluginMessage, timeout_seconds: float
    ) -> dict[str, Any]:
        """プラグインへメッセージを送信し, 応答を受信します。

        Args:
            message: 送信するメッセージオブジェクト。
            timeout_seconds: 応答待ちの最大タイムアウト秒数。

        Returns:
            プラグインからの応答辞書。
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """トランスポートを終了しリソースを解放します。"""
        pass


class StdioTransport(BaseTransport):
    """stdin / stdout パイプを介して通信する STDIO トランスポートです。"""

    def __init__(self, manifest: PluginManifest) -> None:
        """マニフェストを指定して StdioTransport を初期化します。

        Args:
            manifest: プラグインのマニフェスト設定。
        """
        self._manifest = manifest
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        """サブプロセスが起動していることを確認し, 未起動なら起動します。

        Returns:
            起動済みの asyncio サブプロセスインスタンス。

        Raises:
            ValueError: コマンドリストが空の場合。
        """
        if self._process is None or self._process.returncode is not None:
            if not self._manifest.command:
                raise ValueError("マニフェストのコマンドリストが空です。")

            logger.info(
                "STDIO プラグインのサブプロセスを開始します",
                extra={"command": self._manifest.command},
            )
            self._process = await asyncio.create_subprocess_exec(
                *self._manifest.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._stderr_task = asyncio.create_task(self._read_stderr())

        return self._process

    async def _read_stderr(self) -> None:
        """サブプロセスの標準エラー出力を読み取り, ログへ記録します。"""
        if self._process is None or self._process.stderr is None:
            return

        while True:
            line = await self._process.stderr.readline()
            if not line:
                break
            logger.warning(
                "プラグイン STDERR 出力",
                extra={
                    "plugin_name": self._manifest.name,
                    "stderr": line.decode().strip(),
                },
            )

    async def send_and_receive(
        self, message: PluginMessage, timeout_seconds: float
    ) -> dict[str, Any]:
        """STDIN へメッセージを書き込み, STDOUT から応答を読み取ります。

        Args:
            message: 送信する PluginMessage ペイロード。
            timeout_seconds: タイムアウト秒数。

        Returns:
            プラグインからの応答辞書。

        Raises:
            RuntimeError: パイプが利用不能またはクローズされた場合。
            ValueError: 応答フォーマットが不正な場合。
            TimeoutError: 処理がタイムアウトした場合。
        """
        process = await self._ensure_process()

        if process.stdin is None or process.stdout is None:
            raise RuntimeError("サブプロセスのパイプが利用できません。")

        payload_bytes = (
            json.dumps(asdict(message)) + "\n"
        ).encode("utf-8")

        try:
            process.stdin.write(payload_bytes)
            await process.stdin.drain()

            line_bytes = await asyncio.wait_for(
                process.stdout.readline(), timeout=timeout_seconds
            )
            if not line_bytes:
                raise RuntimeError("標準出力が予期せずクローズされました。")

            response_data = json.loads(line_bytes.decode("utf-8"))
            if not isinstance(response_data, dict):
                raise ValueError(
                    "応答フォーマットが不正です。JSON 辞書が期待されます。"
                )
            return response_data
        except asyncio.TimeoutError:
            logger.error(
                "STDIO プラグインタイムアウト",
                extra={"plugin_name": self._manifest.name},
            )
            await self.close()
            raise TimeoutError(
                f"プラグイン '{self._manifest.name}' が "
                f"{timeout_seconds} 秒でタイムアウトしました。"
            )

    async def close(self) -> None:
        """サブプロセスを終了し, タスクの完了を待ちます。"""
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()

        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(
                    self._process.wait(), timeout=DEFAULT_PROCESS_WAIT_TIMEOUT
                )
            except (asyncio.TimeoutError, ProcessLookupError):
                if self._process.returncode is None:
                    self._process.kill()
        self._process = None


class HttpTransport(BaseTransport):
    """プラグイン用 HTTP POST トランスポートです。"""

    def __init__(self, manifest: PluginManifest) -> None:
        """マニフェストを指定して HttpTransport を初期化します。

        Args:
            manifest: プラグインのマニフェスト設定。
        """
        self._manifest = manifest
        self._client = httpx.AsyncClient()

    async def send_and_receive(
        self, message: PluginMessage, timeout_seconds: float
    ) -> dict[str, Any]:
        """設定された URL へ POST リクエストを送信します。

        Args:
            message: 送信する PluginMessage ペイロード。
            timeout_seconds: タイムアウト秒数。

        Returns:
            プラグインからの応答辞書。

        Raises:
            ValueError: URL が未設定または応答が不正な場合。
            TimeoutError: HTTP リクエストがタイムアウトした場合。
            RuntimeError: HTTP リクエストが失敗した場合。
        """
        if not self._manifest.url:
            raise ValueError("HTTP トランスポート用の URL が未設定です。")

        headers = {
            "X-Request-ID": message.request_id,
            "Content-Type": "application/json",
        }
        try:
            response = await self._client.post(
                self._manifest.url,
                json=asdict(message),
                headers=headers,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            res_json = response.json()
            if not isinstance(res_json, dict):
                raise ValueError(
                    "HTTP プラグイン応答は JSON 辞書である必要があります。"
                )
            return res_json
        except (ValueError, TimeoutError):
            raise
        except httpx.TimeoutException:
            logger.error(
                "HTTP プラグインタイムアウト",
                extra={"plugin_name": self._manifest.name},
            )
            raise TimeoutError(
                f"プラグイン '{self._manifest.name}' の "
                "HTTP リクエストがタイムアウトしました。"
            )
        except Exception as err:
            logger.error(
                "HTTP プラグインリクエスト失敗",
                extra={
                    "plugin_name": self._manifest.name,
                    "error": str(err),
                },
            )
            raise RuntimeError(
                f"HTTP プラグインリクエストエラー: {err}"
            ) from err

    async def close(self) -> None:
        """内部の HTTP クライアントをクローズします。"""
        await self._client.aclose()
