"""プラグインの自動認識および実行を行うマネージャーモジュールです。"""

import json
import uuid
from pathlib import Path
from typing import Any

from youtube_tts.logger import get_logger
from youtube_tts.plugins.models import (
    TRANSPORT_HTTP,
    TRANSPORT_STDIO,
    PluginManifest,
    PluginMessage,
)
from youtube_tts.plugins.transports import (
    BaseTransport,
    HttpTransport,
    StdioTransport,
)

logger = get_logger()

# 定数定義
DEFAULT_MANIFEST_FILENAME = "manifest.json"
DEFAULT_PLUGINS_DIR = "plugins"


class PluginManager:
    """プラグインの自動認識や実行を管理します。"""

    def __init__(self, plugins_dir: str | Path = DEFAULT_PLUGINS_DIR) -> None:
        """プラグインディレクトリを指定して PluginManager を初期化します。

        Args:
            plugins_dir: プラグインサブフォルダを含むディレクトリパス。
        """
        self._plugins_dir = Path(plugins_dir)
        self._plugins: dict[str, tuple[PluginManifest, BaseTransport]] = {}

    def scan_plugins(self) -> None:
        """プラグインディレクトリをスキャンしてマニフェストを読み込みます。"""
        self._plugins.clear()
        if not self._plugins_dir.exists() or not self._plugins_dir.is_dir():
            logger.info(
                "プラグインディレクトリが存在しないか、ディレクトリではありません",
                extra={"path": str(self._plugins_dir)},
            )
            return

        for path in self._plugins_dir.iterdir():
            if path.is_dir():
                manifest_path = path / DEFAULT_MANIFEST_FILENAME
                if manifest_path.exists() and manifest_path.is_file():
                    try:
                        self._load_plugin(manifest_path)
                    except Exception as err:
                        logger.error(
                            "プラグインマニフェストの読み込みに失敗しました",
                            extra={
                                "manifest_path": str(manifest_path),
                                "error": str(err),
                            },
                        )

    def _load_plugin(self, manifest_path: Path) -> None:
        """マニフェストをパースし, トランスポートをインスタンス化します。

        Args:
            manifest_path: manifest.json のパス。

        Raises:
            ValueError: サポートされていないトランスポート種別の場合。
        """
        with open(manifest_path, encoding="utf-8") as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, dict):
            raise ValueError("マニフェストは JSON 辞書である必要があります。")

        manifest = PluginManifest(**raw_data)

        transport: BaseTransport
        if manifest.transport == TRANSPORT_STDIO:
            transport = StdioTransport(manifest)
        elif manifest.transport == TRANSPORT_HTTP:
            transport = HttpTransport(manifest)
        else:
            raise ValueError(f"未対応トランスポート種別: {manifest.transport}")

        self._plugins[manifest.name] = (manifest, transport)
        logger.info(
            "プラグインが正常に読み込まれました",
            extra={
                "name": manifest.name,
                "type": manifest.type,
                "transport": manifest.transport,
            },
        )

    def get_plugin_names(self) -> list[str]:
        """読み込まれているプラグイン名の一覧を取得します。

        Returns:
            プラグイン名文字列のリスト。
        """
        return list(self._plugins.keys())

    async def execute(
        self, plugin_name: str, action: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """特定プラグインのアクションをエラー処理付きで実行します。

        Args:
            plugin_name: 対象のプラグイン名。
            action: プラグインへ送るアクション名。
            data: アクション実行用データ辞書。

        Returns:
            プラグイン実行結果の辞書。

        Raises:
            KeyError: 指定されたプラグイン名が未登録の場合。
        """
        if plugin_name not in self._plugins:
            raise KeyError(f"プラグイン '{plugin_name}' は登録されていません。")

        manifest, transport = self._plugins[plugin_name]
        request_id = str(uuid.uuid4())
        message = PluginMessage(request_id=request_id, action=action, data=data or {})

        try:
            return await transport.send_and_receive(message, manifest.timeout_seconds)
        except Exception as err:
            logger.error(
                "プラグイン実行エラーを安全に捕捉しました",
                extra={
                    "plugin_name": plugin_name,
                    "action": action,
                    "error": str(err),
                },
            )
            return {"status": "error", "error": str(err)}

    async def close(self) -> None:
        """すべてのプラグイントランスポートを終了します。"""
        for name, (_, transport) in self._plugins.items():
            try:
                await transport.close()
            except Exception as err:
                logger.error(
                    "トランスポートの終了処理中にエラーが発生しました",
                    extra={"plugin_name": name, "error": str(err)},
                )
        self._plugins.clear()
