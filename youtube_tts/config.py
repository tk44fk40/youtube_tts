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
"""アプリケーションの設定情報を管理するモジュールです。"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

from .logger import get_logger

logger = get_logger()


def normalize_nfkc(text: str) -> str:
    """Unicode NFKC 正規化を行うユーティリティ関数です。

    全角/半角の統一、互換文字の正規化を行います。
    AppConfig と TextProcessor の両方で使用されるため、
    モジュールレベルで定義しています。

    Args:
        text: 正規化対象の文字列です。

    Returns:
        正規化済みの文字列です。
    """
    return unicodedata.normalize("NFKC", text)


class AppConfig:
    """アプリケーションの設定を管理するクラスです。"""

    def __init__(
        self,
        dictionary_path: str | Path = "dictionary.txt",
        ng_words_path: str | Path = "ng_words.txt",
        volume_path: str | Path = "volume.txt",
        chat_log_path: str = "chat_log.jsonl",
    ) -> None:
        """設定情報を初期化し、各設定ファイルをロードします。

        Args:
            dictionary_path: 辞書ファイルのパスです。
            ng_words_path: NGワードファイルのパスです。
            volume_path: 音量設定ファイルのパスです。
            chat_log_path: チャットログファイルのパスです。
        """
        self.dictionary_file: Path = Path(dictionary_path)
        self.ng_word_file: Path = Path(ng_words_path)
        self.volume_file: Path = Path(volume_path)
        self.chat_log_path: str = chat_log_path

        self.volume_scale: float = 1.0
        self.speed_scale: float = 1.0
        self.auto_speed_boost: bool = False
        self.max_speed: float = 2.2
        self.replacements: dict[str, str] = {}
        self.ng_words: set[str] = set()

        self._dictionary_mtime: float | None = None
        self._ng_word_mtime: float | None = None
        self._volume_mtime: float | None = None

        # 起動時に一度ロードします。
        self.reload_if_changed()

    def _load_replacements(self) -> dict[str, str]:
        """変換辞書のロードを行います。

        辞書ファイルを読み込み、正規化した置換元文字列と置換後文字列の
        マッピングオブジェクトを生成して返します。

        Returns:
            正規化済みの置換元文字列をキー、置換後文字列を値とする辞書です。
        """
        replacements: dict[str, str] = {}
        try:
            with open(self.dictionary_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    src, dst = line.split("=", 1)
                    normalized_src = normalize_nfkc(src.strip()).lower()
                    replacements[normalized_src] = dst.strip()
        except OSError as e:
            logger.warning(f"辞書のロードに失敗しました: {e}")
        return replacements

    def _load_ng_words(self) -> set[str]:
        """NGワードのロードを行います。

        NGワードファイルを読み込み、正規化したNGワードの集合を返します。

        Returns:
            正規化済みのNGワードを含む集合です。
        """
        ng_words: set[str] = set()
        try:
            with open(self.ng_word_file, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    if not word:
                        continue
                    normalized_word = normalize_nfkc(word).lower()
                    ng_words.add(normalized_word)
        except OSError as e:
            logger.warning(f"NGワードのロードに失敗しました: {e}")
        return ng_words

    def reload_if_changed(self) -> None:
        """設定ファイルのリロードを行います。

        各設定ファイルのタイムスタンプを確認し、変更があれば再ロードします。
        """
        # 辞書ファイルをチェックします。
        if self.dictionary_file.exists():
            current_mtime = os.path.getmtime(self.dictionary_file)
            if current_mtime != self._dictionary_mtime:
                self._dictionary_mtime = current_mtime
                self.replacements = self._load_replacements()
                logger.info("[CONFIG] 辞書を再ロードしました。")

        # NGワードファイルをチェックします。
        if self.ng_word_file.exists():
            current_mtime = os.path.getmtime(self.ng_word_file)
            if current_mtime != self._ng_word_mtime:
                self._ng_word_mtime = current_mtime
                self.ng_words = self._load_ng_words()
                logger.info("[CONFIG] NGワードを再ロードしました。")

        # 音量設定ファイルをチェックします。
        if self.volume_file.exists():
            current_mtime = os.path.getmtime(self.volume_file)
            if current_mtime != self._volume_mtime:
                self._volume_mtime = current_mtime
                try:
                    with open(self.volume_file, "r", encoding="utf-8") as f:
                        val = float(f.read().strip())
                    if 0.0 <= val <= 2.0:
                        self.volume_scale = val
                        logger.info(
                            f"[CONFIG] 音量スケールを更新しました: "
                            f"{self.volume_scale}"
                        )
                    else:
                        logger.info(
                            "[CONFIG] 音量スケールが範囲外"
                            f"（0.0 - 2.0）です: {val}"
                        )
                except OSError as e:
                    logger.warning(f"volume.txt の読み込みに失敗しました: {e}")
                except ValueError as e:
                    logger.warning(f"volume.txt の値が無効です: {e}")
