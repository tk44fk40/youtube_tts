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
import logging
import sys

LOGGER_NAME = "youtube_tts"

class TaggedLogger(logging.Logger):
    def _add_prefix(self, level: int, msg) -> str:
        msg_str = str(msg)
        stripped = msg_str.lstrip()
        if not stripped.startswith("["):
            level_name = logging.getLevelName(level)
            if level_name == "WARNING":
                level_name = "WARN"
            return f"[{level_name}] {msg_str}"
        return msg_str

    def debug(self, msg, *args, **kwargs):
        super().debug(self._add_prefix(logging.DEBUG, msg), *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        super().info(self._add_prefix(logging.INFO, msg), *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        super().warning(self._add_prefix(logging.WARNING, msg), *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        self.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        super().error(self._add_prefix(logging.ERROR, msg), *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        super().critical(self._add_prefix(logging.CRITICAL, msg), *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        super().exception(self._add_prefix(logging.ERROR, msg), *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        super().log(level, self._add_prefix(level, msg), *args, **kwargs)

logging.setLoggerClass(TaggedLogger)

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
