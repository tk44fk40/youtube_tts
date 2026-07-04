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
"""YouTube TTS アプリケーション用のカスタムロギングモジュールです。

このモジュールは、タイムスタンプおよびログレベルの識別子を自動付与する
ロガーを提供します。メッセージの整形や重複プリフィックスの除去を
標準の Filter 機能を用いて処理します。

提供機能:
    - setup_logger: ロガーの初期化とフォーマット設定を行います。
    - get_logger: 初期化済みのロガーインスタンスを取得します。
"""

from __future__ import annotations

import logging

LOGGER_NAME = "youtube_tts"


class StripAndCleanupFilter(logging.Filter):
    """ログの整形と重複プリフィックスの除去を行うフィルタークラスです。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """ログレコードにフィルターを適用し、メッセージを整形します。

        メッセージの前後スペースをトリムし、レベル名との重複を防止します。

        Args:
            record: 整形対象のログレコード。

        Returns:
            常に True を返します。
        """
        if isinstance(record.msg, str):
            msg_str = record.msg.strip()
            pfx = f"[{record.levelname}]"

            # メッセージ先頭に同名のプリフィックスがある場合は除去します。
            if msg_str.startswith(pfx):
                msg_str = msg_str[len(pfx) :].strip()

            record.msg = msg_str
        return True


def setup_logger(verbose: bool = False) -> logging.Logger:
    """タイムスタンプとレベル名付きのロガーをセットアップします。

    メッセージの先頭に識別子を付与するカスタムロガーを初期化し、
    ログの出力閾値を指定されたレベル（DEBUG または INFO）に設定します。

    Args:
        verbose: True の場合はログレベルを DEBUG に、
            False の場合は INFO に設定します。

    Returns:
        初期化済みのロガーインスタンスを返します。
    """
    logger = logging.getLogger(LOGGER_NAME)

    if logger.handlers:
        logger.handlers.clear()

    # 引数に応じてログの出力閾値を DEBUG または INFO に設定します。
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # 標準エラー出力ストリームへ出力するハンドラを生成します。
    handler = logging.StreamHandler()

    # タイムスタンプ、ログレベル、メッセージを半角スペース区切りで指定します。
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(StripAndCleanupFilter())

    logger.addHandler(handler)
    logger.propagate = False

    return logger


def get_logger() -> logging.Logger:
    """ロガーを取得します。

    未初期化の場合は初期設定を実行します。

    Returns:
        取得されたロガーインスタンスを返します。
    """
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        setup_logger(verbose=False)
    return logger
