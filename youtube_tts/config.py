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
import os
import unicodedata
from pathlib import Path

from .logger import get_logger

logger = get_logger()


def normalize_nfkc(text: str) -> str:
    """Unicode NFKC 正規化を行うユーティリティ関数。

    全角/半角の統一、互換文字の正規化を行う。
    AppConfig と TextProcessor の両方で使用されるため、
    モジュールレベルで定義している。
    """
    return unicodedata.normalize("NFKC", text)


class AppConfig:
    def __init__(
        self,
        dictionary_path="dictionary.txt",
        ng_words_path="ng_words.txt",
        volume_path="volume.txt",
        chat_log_path="chat_log.jsonl",
    ):
        self.dictionary_file = Path(dictionary_path)
        self.ng_word_file = Path(ng_words_path)
        self.volume_file = Path(volume_path)
        self.chat_log_path = chat_log_path

        self.volume_scale = 1.0
        self.speed_scale = 1.0
        self.auto_speed_boost = False
        self.max_speed = 2.2
        self.replacements = {}
        self.ng_words = set()

        self._dictionary_mtime = None
        self._ng_word_mtime = None
        self._volume_mtime = None

        # 起動時に一度ロードする
        self.reload_if_changed()

    def _load_replacements(self):
        """変換辞書のロード

        dictionary.txt を読み込んで
        {正規化済みキー: 置換後文字列} の辞書を返す。
        """
        replacements = {}
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
            logger.warning(f"Failed to load dictionary: {e}")
        return replacements

    def _load_ng_words(self):
        """NGワードのロード

        ng_words.txt を読み込んで
        {正規化済みNGワード} の集合を返す。
        """
        ng_words = set()
        try:
            with open(self.ng_word_file, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    if not word:
                        continue
                    normalized_word = normalize_nfkc(word).lower()
                    ng_words.add(normalized_word)
        except OSError as e:
            logger.warning(f"Failed to load ng_words: {e}")
        return ng_words

    def reload_if_changed(self):
        """設定ファイルのリロード

        各設定ファイルのタイムスタンプを確認し、
        変更があれば再ロードする。
        """
        # dictionary.txt のチェック
        if self.dictionary_file.exists():
            current_mtime = os.path.getmtime(self.dictionary_file)
            if current_mtime != self._dictionary_mtime:
                self._dictionary_mtime = current_mtime
                self.replacements = self._load_replacements()
                logger.info("[CONFIG] dictionary reloaded")

        # ng_words.txt のチェック
        if self.ng_word_file.exists():
            current_mtime = os.path.getmtime(self.ng_word_file)
            if current_mtime != self._ng_word_mtime:
                self._ng_word_mtime = current_mtime
                self.ng_words = self._load_ng_words()
                logger.info("[CONFIG] ng words reloaded")

        # volume.txt のチェック
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
                            f"[CONFIG] volume scale updated: "
                            f"{self.volume_scale}"
                        )
                    else:
                        logger.info(
                            f"[CONFIG] volume scale out of range "
                            f"(0.0 - 2.0): {val}"
                        )
                except OSError as e:
                    logger.warning(f"Failed to read volume.txt: {e}")
                except ValueError as e:
                    logger.warning(f"Invalid volume value in volume.txt: {e}")
