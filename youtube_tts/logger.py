import logging
import sys

LOGGER_NAME = "youtube_tts"

def setup_logger(verbose: bool = False) -> logging.Logger:
    """セットアップ済みのロガーを取得または作成します。

    Args:
        verbose: True の場合、ログレベルを DEBUG に設定します。False の場合は INFO。
    """
    logger = logging.getLogger(LOGGER_NAME)
    
    # ハンドラの重複登録を防ぐ
    if logger.handlers:
        logger.handlers.clear()
        
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # 標準出力用ハンドラ
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # タイムスタンプフォーマットの指定 (例: [2026-06-20 22:15:30] メッセージ)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # ログ伝播を無効化し、親ロガーによる重複出力を防ぐ
    logger.propagate = False
    
    return logger

def get_logger() -> logging.Logger:
    """現在のロガーインスタンスを取得します。

    未セットアップの場合は、デフォルト設定 (verbose=False) でセットアップします。
    """
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        setup_logger(verbose=False)
    return logger
StandardLogger = get_logger()
