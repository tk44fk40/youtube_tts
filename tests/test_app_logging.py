"""ロガーおよび setup_logger の動作を検証するテストモジュールです。"""

from __future__ import annotations

import logging
from io import StringIO

from youtube_tts import setup_logger
from youtube_tts.logger import get_logger


def test_setup_logger() -> None:
    """ログレベルに応じた出力を行うかを検証します。

    setup_logger が正しく設定され、ログレベルに応じた出力を行うかを検証します。
    """
    captured_output = StringIO()
    logger = setup_logger(verbose=True)

    # 既存ハンドラから出力を奪うため StreamHandler を一時追加します。
    handler = logging.StreamHandler(captured_output)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    try:
        logger.info("Hello Logger")
        logger.debug("Debug Info")

        output = captured_output.getvalue()
        lines = output.splitlines()

        assert len(lines) == 2
        assert "Hello Logger" in lines[0]
        assert "Debug Info" in lines[1]
        assert lines[0].startswith("[20")
    finally:
        # 他のテストに影響を及ぼさないようハンドラを削除します。
        logger.removeHandler(handler)


def test_logger_filter() -> None:
    """フィルターによる整形および重複除去を検証します。

    StripAndCleanupFilter がメッセージの前後スペースをトリムし、
    ログレベル名の重複プリフィックスを適切に除去できているかを検証します。
    """
    logger = get_logger()
    captured_output = StringIO()
    handler = logging.StreamHandler(captured_output)

    # テスト用にフォーマッターを設定します。
    formatter = logging.Formatter(fmt="[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)

    from youtube_tts.logger import StripAndCleanupFilter

    handler.addFilter(StripAndCleanupFilter())
    logger.addHandler(handler)

    try:
        # 重複プリフィックスがある場合です。
        logger.info("[INFO] Hello World")
        # 前後余白がある場合です。
        logger.info("  Whitespace  ")
        # 重複がない場合です。
        logger.info("Normal message")
        # 文字列以外の場合です。
        logger.info(12345)

        output = captured_output.getvalue()
        lines = output.splitlines()

        assert lines[0] == "[INFO] Hello World"
        assert lines[1] == "[INFO] Whitespace"
        assert lines[2] == "[INFO] Normal message"
        assert lines[3] == "[INFO] 12345"
    finally:
        # 他のテストに影響を及ぼさないようハンドラを削除します。
        logger.removeHandler(handler)
