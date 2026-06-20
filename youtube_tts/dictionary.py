import os
import re
import unicodedata
from .config import AppConfig, normalize_nfkc


class TextProcessor:
    def __init__(self, config: AppConfig):
        self.config = config
        self.author_suffix = os.getenv("VOICEVOX_AUTHOR_SUFFIX", "さん")

        # replace_words で使う正規表現パターンのキャッシュ。
        # config.replacements の同一性 (is) で変更を検知し、辞書リロード時に自動更新する。
        self._compiled_replacements: list[tuple[re.Pattern, str]] = []
        self._replacements_ref = None  # キャッシュ有効性の確認用 (config.replacements のオブジェクト参照)

    def normalize_text(self, text: str) -> str:
        """NFKC 正規化を行う（互換性のために公開メソッドとして維持）。"""
        return normalize_nfkc(text)

    def _ensure_compiled(self):
        """config.replacements が更新されていた場合、正規表現パターンを再コンパイルする。
        
        config.reload_if_changed() が新しい dict オブジェクトを代入するため、
        オブジェクト同一性 (is) で変更を検知できる。
        """
        if self.config.replacements is not self._replacements_ref:
            self._replacements_ref = self.config.replacements
            self._compiled_replacements = [
                (re.compile(re.escape(src), re.IGNORECASE), dst)
                for src, dst in self.config.replacements.items()
            ]

    def replace_words(self, message: str) -> str:
        """読み上げ辞書に従ってメッセージ内の単語を置換する。"""
        self._ensure_compiled()
        normalized = normalize_nfkc(message)
        for pattern, dst in self._compiled_replacements:
            normalized = pattern.sub(dst, normalized)
        return normalized

    def contains_ng_word(self, message: str) -> bool:
        """メッセージに NG ワードが含まれているかどうかを判定する。"""
        normalized = normalize_nfkc(message).lower()
        for word in self.config.ng_words:
            if word in normalized:
                return True
        return False

    def normalize_author(self, author: str) -> str:
        """著者名を正規化する（NFKC、@ 除去、suffix 付与）。"""
        author = normalize_nfkc(author).strip().lstrip("@").strip()
        if not author:
            return author
        if not self.author_suffix:
            return author
        if author.endswith(self.author_suffix):
            return author
        return f"{author}{self.author_suffix}"

    def normalize_message(self, message: str) -> str:
        """メッセージを読み上げ用に正規化する。
        
        各置換処理が互いに干渉するのを防ぐため、以下の順序で処理する。
        （例: 先に読み上げ辞書を適用すると、辞書内の変換ルールがURL除去や草の変換に影響を及ぼす可能性があるため）
        
        URL除去 → 草圧縮 → 記号圧縮 → 絵文字除去 → 読み上げ辞書適用 の順に処理する。
        """
        message = normalize_nfkc(message)
        # URL 除去
        message = re.sub(r"https?:\S+", "", message)
        # 1文字または2文字の w/W だけのメッセージの場合、「わら」に変換
        # (3文字以上の w は後続の処理で「わら」に変換される)
        if re.match(r"^[wW]{1,2}$", message):
            message = "わら"
        else:
            # 直前が日本語、句読点、感嘆符、または閉じ括弧類である 1〜2文字の w/W を「わら」に変換
            # (かつ、直後に英数字が続かないこと)
            message = re.sub(
                r"(?<=[ぁ-んァ-ヶ一-龠々!！?？、。，．・)）\]］}｝>＞」』,.])([wW]{1,2})(?!\w)",
                " わら ",
                message,
                flags=re.IGNORECASE
            )
        # 「www」「ｗｗｗ」など3文字以上の草を「わら」に変換
        message = re.sub(r"[wW]{3,}", " わら ", message, flags=re.IGNORECASE)
        # 連続する感嘆符・疑問符を1文字に圧縮
        message = re.sub(r"[!！]{2,}", "！", message)
        message = re.sub(r"[?？]{2,}", "？", message)
        # サロゲートペア領域（絵文字等）を除去
        message = re.sub(r"[\U00010000-\U0010ffff]", "", message)
        # 読み上げ辞書適用
        message = self.replace_words(message)
        return message.strip()

    def normalize_comment(self, author: str, message: str) -> tuple[str, str]:
        """著者名とメッセージをまとめて正規化して返す。"""
        return self.normalize_author(author), self.normalize_message(message)
