import os
from pathlib import Path
import unicodedata

class AppConfig:
    def __init__(self, dictionary_path="dictionary.txt", ng_words_path="ng_words.txt", volume_path="volume.txt"):
        self.dictionary_file = Path(dictionary_path)
        self.ng_word_file = Path(ng_words_path)
        self.volume_file = Path(volume_path)

        self.volume_scale = 1.0
        self.replacements = {}
        self.ng_words = set()

        self._dictionary_mtime = None
        self._ng_word_mtime = None
        self._volume_mtime = None

        # Initial load
        self.reload_if_changed()

    def _normalize_text(self, text):
        return unicodedata.normalize("NFKC", text)

    def _load_replacements(self):
        replacements = {}
        with open(self.dictionary_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                src, dst = line.split("=", 1)
                normalized_src = self._normalize_text(src.strip()).lower()
                replacements[normalized_src] = dst.strip()
        return replacements

    def _load_ng_words(self):
        ng_words = set()
        with open(self.ng_word_file, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if not word:
                    continue
                normalized_word = self._normalize_text(word).lower()
                ng_words.add(normalized_word)
        return ng_words

    def reload_if_changed(self):
        # dictionary.txt
        if self.dictionary_file.exists():
            current_mtime = os.path.getmtime(self.dictionary_file)
            if current_mtime != self._dictionary_mtime:
                self._dictionary_mtime = current_mtime
                self.replacements = self._load_replacements()
                print("[CONFIG] dictionary reloaded")

        # ng_words.txt
        if self.ng_word_file.exists():
            current_mtime = os.path.getmtime(self.ng_word_file)
            if current_mtime != self._ng_word_mtime:
                self._ng_word_mtime = current_mtime
                self.ng_words = self._load_ng_words()
                print("[CONFIG] ng words reloaded")

        # volume.txt
        if self.volume_file.exists():
            current_mtime = os.path.getmtime(self.volume_file)
            if current_mtime != self._volume_mtime:
                self._volume_mtime = current_mtime
                try:
                    with open(self.volume_file, "r", encoding="utf-8") as f:
                        val = float(f.read().strip())
                        if 0.0 <= val <= 2.0:
                            self.volume_scale = val
                            print(f"[CONFIG] volume scale updated: {self.volume_scale}")
                        else:
                            print(f"[CONFIG] volume scale out of range (0.0 - 2.0): {val}")
                except Exception as e:
                    print(f"[WARN] Failed to reload volume.txt: {e}")
