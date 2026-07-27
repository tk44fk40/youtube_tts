---
name: testing-coverage
description: uv runを使用したモジュール単位の局所テストと目標カバレッジ99%の計測手順
---

# テストとカバレッジ計測

本スキルは、`uv run` を用いたモジュール単位でのテスト実行およびカバレッジ測定の手順を定めます。

## 適用手順

1. **局所テストの実行**
   - 変更対象のモジュールごとにローカルテストを実行します。
   - コマンド例:

     ```bash
     uv run pytest tests/path/to/test_module.py
     ```

   - エラーが発生した場合は、解消されるまで修正とテストを繰り返し実行します。

2. **カバレッジの計測**
   - モジュールごとのエラーが解消されたら、カバレッジを計測します。
   - コマンド例:

     ```bash
     uv run pytest --cov=src/path/to/module tests/path/to/test_module.py
     ```

   - **目標カバレッジ**: 99% 以上を達成しているか確認してください。
