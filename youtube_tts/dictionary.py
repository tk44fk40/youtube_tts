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
import re

from .config import AppConfig, normalize_nfkc


class TextProcessor:
    def __init__(self, config: AppConfig):
        self.config = config
        self.author_suffix = os.getenv("VOICEVOX_AUTHOR_SUFFIX", "さん")

        # replace_words で使う正規表現パターンのキャッシュ。
        # config.replacements の同一性 (is) で変更を検知し、
        # 辞書リロード時に自動更新する。
        self._compiled_replacements: list[tuple[re.Pattern, str]] = []
        # キャッシュ有効性の確認用
        # (config.replacements のオブジェクト参照)
        self._replacements_ref = None

    def normalize_text(self, text: str) -> str:
        """NFKC 正規化を行う

        （互換性のために公開メソッドとして維持）。
        """
        return normalize_nfkc(text)

    def _ensure_compiled(self):
        """正規表現パターンの再コンパイル

        config.replacements が更新されていた場合、
        正規表現パターンを再コンパイルする。

        config.reload_if_changed() が新しい dict オブジェクトを
        代入するため、オブジェクト同一性 (is) で変更を検知できる。
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
        （例: 先に読み上げ辞書を適用すると、辞書内の変換ルールが
        URL除去や草の変換に影響を及ぼす可能性があるため）

        URL除去 → スタンプ除去 → 顔文字除去 →
        草圧縮 → 記号圧縮 → 絵文字除去 →
        読み上げ辞書適用 の順に処理する。
        """
        message = normalize_nfkc(message)
        # URL 除去
        message = re.sub(r"https?:\S+", "", message)

        # スタンプ（YouTubeカスタム絵文字
        # コロン表記 :emoji_name:）の除去
        message = re.sub(r":[^:\s]+:", "", message)

        # 括弧なし・特定の代表的な顔文字の除去
        message = re.sub(r"m\([\s_]+\)m|m\(\._\.\)m", "", message)
        message = re.sub(r"(?<![a-zA-Z0-9])[tT]_[tT](?![a-zA-Z0-9])", "", message)
        message = re.sub(
            r"(?<![a-zA-Z0-9])orz(?![a-zA-Z0-9])",
            "",
            message,
            flags=re.IGNORECASE,
        )

        # 括弧付き顔文字の除去
        # 括弧（半角・全角）で囲まれており、
        # かつ中に日本語の通常文字
        # （ひらがな、カタカナ、漢字）、英数字、スペース、
        # 一般的な句読点・長音記号（ー）以外の文字（記号など）が
        # 1文字以上含まれるものを除去
        message = re.sub(
            r"(\(|（)[^)\n（）]*?"
            r"[^ぁ-んァ-ヶ一-龠々a-zA-Z0-9\s!！?？、。，．・ー]"
            r"[^)\n（）]*?(\)|）)",
            "",
            message,
        )

        # 1文字または2文字の w/W だけの
        # メッセージの場合、「わら」に変換
        # (3文字以上の w は後続の処理で
        # 「わら」に変換される)
        if re.match(r"^[wW]{1,2}$", message):
            message = "わら"
        else:
            # 直前が日本語、句読点、感嘆符、
            # または閉じ括弧類である
            # 1〜2文字の w/W を「わら」に変換
            # (かつ、直後に英数字が続かないこと)
            message = re.sub(
                r"(?<=[ぁ-んァ-ヶ一-龠々!！?？、。，．・)）"
                r"\]］}｝>＞」』,.ー〜～~])([wW]{1,2})(?!\w)",
                " わら ",
                message,
                flags=re.IGNORECASE,
            )
        # 「www」「ｗｗｗ」など
        # 3文字以上の草を「わら」に変換
        message = re.sub(r"[wW]{3,}", " わら ", message, flags=re.IGNORECASE)
        # 連続する感嘆符・疑問符を1文字に圧縮
        message = re.sub(r"[!！]{2,}", "！", message)
        message = re.sub(r"[?？]{2,}", "？", message)
        # サロゲートペア領域（絵文字等）および
        # BMP領域の絵文字・記号を除去
        message = re.sub(r"[\U00010000-\U0010ffff]", "", message)
        message = re.sub(
            r"[\u2600-\u27BF\u2300-\u23FF\u2B00-\u2BFF\u25A0-\u25FF]",
            "",
            message,
        )
        # 読み上げ辞書適用
        message = self.replace_words(message)
        return message.strip()

    def normalize_comment(self, author: str, message: str) -> tuple[str, str]:
        """著者名とメッセージをまとめて正規化して返す。"""
        return self.normalize_author(author), self.normalize_message(message)
