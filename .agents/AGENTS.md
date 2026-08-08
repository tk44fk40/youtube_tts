# youtube_tts 開発ルール

## 1. 基本規約 & 出力
- **簡潔さ**: 冗長な説明を避け、事実のみを出力すること。
- **言語**: コードコメント、Docstring、ドキュメント、Issue、PR、チャット履歴のタイトル等は全て日本語で記述すること。
- **図の出力**: 図を出力する場合はアーティファクトとして出力し参照を促すこと。

## 2. コマンド & スクリプト実行
- Python スクリプトおよびツールの実行には必ず `uv run` を使用すること。
- GitHub への操作には `gh` コマンドを使用すること。

## 3. コーディング規約 & Docstring
- **スタイル**: PEP 8 準拠。1行最大88文字（Ruff標準）。
- **Docstring**: 全モジュール/クラス/関数に Google スタイル Docstring (日本語) を記述。

## 4. コード品質 & 自動検証
- Python 3.12 準拠。
- `uv run basedpyright` をエラー 0 件で通過すること。
- `uv run ruff check --fix .` および `uv run ruff format .` に準拠すること。
- 除外ルール（カバレッジや Ruff ルール）の変更・追加は必ず事前承認を得ること。

## 5. 自律開発ワークフロー
- 実装・検証・Issue・PR・スカッシュマージ等の具体的な手順については、[autonomous-code-workflow](file:///.agents/skills/autonomous-code-workflow/SKILL.md) スキルに完全準拠して実施すること。
