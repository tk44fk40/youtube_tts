import os
import re
import unicodedata
from .config import AppConfig

class TextProcessor:
    def __init__(self, config: AppConfig):
        self.config = config
        self.author_suffix = os.getenv("VOICEVOX_AUTHOR_SUFFIX", "さん")

    def normalize_text(self, text):
        return unicodedata.normalize("NFKC", text)

    def replace_words(self, message):
        normalized_message = self.normalize_text(message)
        for src, dst in self.config.replacements.items():
            pattern = re.compile(re.escape(src), re.IGNORECASE)
            normalized_message = pattern.sub(dst, normalized_message)
        return normalized_message

    def contains_ng_word(self, message):
        normalized_message = self.normalize_text(message).lower()
        for word in self.config.ng_words:
            if word in normalized_message:
                return True
        return False

    def normalize_author(self, author):
        author = self.normalize_text(author)
        author = author.strip()
        author = author.lstrip("@")
        author = author.strip()
        if not author:
            return author
        if not self.author_suffix:
            return author
        if author.endswith(self.author_suffix):
            return author
        return f"{author}{self.author_suffix}"

    def normalize_message(self, message):
        message = self.normalize_text(message)
        # URL除去
        message = re.sub(r"https?:\S+", "", message)
        # 草を圧縮
        message = re.sub(r"[wｗ]{3,}", " わら ", message, flags=re.IGNORECASE)
        # ! を圧縮
        message = re.sub(r"[!！]{2,}", "！", message)
        # ? を圧縮
        message = re.sub(r"[?？]{2,}", "？", message)
        # 絵文字除去
        message = re.sub(r"[\U00010000-\U0010ffff]", "", message)
        # 読み上げ辞書
        message = self.replace_words(message)
        message = message.strip()
        return message

    def normalize_comment(self, author, message):
        normalized_author = self.normalize_author(author)
        normalized_message = self.normalize_message(message)
        return normalized_author, normalized_message
