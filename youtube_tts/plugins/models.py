"""プラグインのマニフェスト, および通信用データモデルです。"""

from dataclasses import dataclass, field
from typing import Any, Literal

# 定数定義
DEFAULT_PLUGIN_TIMEOUT_SECONDS = 2.0
TRANSPORT_STDIO = "stdio"
TRANSPORT_HTTP = "http"


@dataclass
class PluginManifest:
    """プラグインのマニフェストデータモデルです。

    Attributes:
        name: プラグイン名。
        version: プラグインのバージョン文字列。
        type: プラグイン種別識別子。
        transport: 通信トランスポート ('stdio' または 'http')。
        command: stdio 通信時の実行コマンドリスト。
        url: http 通信時のエンドポイント URL。
        timeout_seconds: リクエストのタイムアウト秒数。
    """

    name: str
    version: str
    type: str
    transport: Literal["stdio", "http"]
    command: list[str] = field(default_factory=list)
    url: str | None = None
    timeout_seconds: float = DEFAULT_PLUGIN_TIMEOUT_SECONDS


@dataclass
class PluginMessage:
    """プラグイン間通信メッセージのペイロードモデルです。

    Attributes:
        request_id: 一意のリクエスト追跡 ID。
        action: 実行対象のアクション名。
        data: アクションに渡す追加データ辞書。
    """

    request_id: str
    action: str
    data: dict[str, Any] = field(default_factory=dict)
