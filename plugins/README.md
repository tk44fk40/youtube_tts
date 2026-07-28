# Plugins Directory

このディレクトリ配下に各プラグインのフォルダを配置します。

## 配置構造

```text
plugins/
  ├── my_http_plugin/
  │   └── manifest.json (HTTP 方式: 別途起動中の Web サーバー等の URL を指定)
  ├── my_stdio_plugin/
  │   ├── manifest.json
  │   └── main.py (stdio 方式: サブプロセスとして起動する実行ファイル)
  └── ...
```

## `manifest.json` の仕様

プラグインフォルダ直下に `manifest.json` を配置します。

### 1. `http` トランスポートの場合
外部または別プロセスで起動している HTTP エンドポイントへリクエストを送信します。プラグインフォルダ内に実行ファイルを配置する必要はありません。

```json
{
  "name": "my_custom_bot",
  "version": "1.0.0",
  "type": "bot_engine",
  "transport": "http",
  "url": "http://localhost:8080/on_message"
}
```

### 2. `stdio` トランスポートの場合
指定されたコマンドでサブプロセスを起動し、標準入出力（stdin / stdout）を介してメッセージをやり取りします。

```json
{
  "name": "my_stdio_bot",
  "version": "1.0.0",
  "type": "bot_engine",
  "transport": "stdio",
  "command": ["python3", "main.py"]
}
```
