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
"""コメントの読み上げ用テキスト整形および正規化を行うモジュールです。

このモジュールは、YouTube のチャットやコメント内の URL 除去、顔文字除去、
草の変換、辞書による単語置換などのテキスト処理を提供する
TextProcessor クラスを提供します。
"""

from __future__ import annotations

import os
import re

from .config import AppConfig, normalize_nfkc


class TextProcessor:
    """YouTube のチャットやコメントを音声読み上げ用に整形するクラスです。"""

    def __init__(self, config: AppConfig) -> None:
        """TextProcessor を初期化します。

        Args:
            config: 設定ファイルを管理する AppConfig インスタンス。
        """
        self.config = config
        self.author_suffix: str = os.getenv("VOICEVOX_AUTHOR_SUFFIX", "さん")

        # replace_words で使う正規表現パターンのキャッシュです。
        # config.replacements の同一性 (is) で変更を検知し、
        # 辞書リロード時に自動更新します。
        self._compiled_replacements: list[tuple[re.Pattern[str], str]] = []
        # キャッシュ有効性の確認用です。
        # (config.replacements のオブジェクト参照)
        self._replacements_ref: dict[str, str] | None = None

    def normalize_text(self, text: str) -> str:
        """Unicode NFKC 正規化を行います。

        互換性のためにパブリックメソッドとして維持されています。

        Args:
            text: 正規化対象の文字列。

        Returns:
            NFKC 正規化後の文字列。
        """
        return normalize_nfkc(text)

    def _ensure_compiled(self) -> None:
        """読み上げ置換用の正規表現パターンを必要に応じて再コンパイルします。

        config.replacements が更新されていた場合に再コンパイルを実行します。
        config.reload_if_changed() が新しい辞書オブジェクトを代入するため、
        オブジェクトの同一性 (is) で変更を検知します。
        """
        if self.config.replacements is not self._replacements_ref:
            self._replacements_ref = self.config.replacements
            self._compiled_replacements = [
                (re.compile(re.escape(src), re.IGNORECASE), dst)
                for src, dst in self.config.replacements.items()
            ]

    def replace_words(self, message: str) -> str:
        """読み上げ辞書に従ってメッセージ内の単語を置換します。

        Args:
            message: 置換対象のメッセージ。

        Returns:
            単語置換後のメッセージ。
        """
        self._ensure_compiled()
        normalized = normalize_nfkc(message)
        for pattern, dst in self._compiled_replacements:
            normalized = pattern.sub(dst, normalized)
        return normalized

    def contains_ng_word(self, message: str) -> bool:
        """メッセージに NG ワードが含まれているかどうかを判定します。

        Args:
            message: 判定対象のメッセージ。

        Returns:
            NG ワードが含まれている場合は True、含まれていない場合は False。
        """
        normalized = normalize_nfkc(message).lower()
        for word in self.config.ng_words:
            if word in normalized:
                return True
        return False

    def normalize_author(self, author: str) -> str:
        """投稿者名を読み上げ用に正規化します。

        NFKC 正規化、先頭の @ 記号の除去、および設定された敬称
        （suffix）の付与を行います。

        Args:
            author: 正規化対象の投稿者名。

        Returns:
            正規化後の投稿者名。
        """
        author = normalize_nfkc(author).strip().lstrip("@").strip()
        if not author:
            return author
        if not self.author_suffix:
            return author
        if author.endswith(self.author_suffix):
            return author
        return f"{author}{self.author_suffix}"

    def normalize_message(self, message: str) -> str:
        """メッセージを音声読み上げ用に正規化します。

        各置換処理が互いに干渉するのを防ぐため、以下の順序で処理します：
        URL 除去 → スタンプ除去 → 顔文字除去 → 草圧縮 →
        記号圧縮 → 絵文字除去 → 読み上げ辞書適用

        Args:
            message: 正規化対象のメッセージ。

        Returns:
            正規化後のメッセージ。
        """
        message = normalize_nfkc(message)
        # URL を除去します。
        message = re.sub(r"https?:\S+", "", message)

        # スタンプ（YouTube カスタム絵文字コロン表記 :emoji_name:）を
        # 除去します。
        message = re.sub(r":[^:\s]+:", "", message)

        # 括弧なし・特定の代表的な顔文字を除去します。
        message = re.sub(r"m\([\s_]+\)m|m\(\._\.\)m", "", message)
        message = re.sub(
            r"(?<![a-zA-Z0-9])[tT]_[tT](?![a-zA-Z0-9])", "", message
        )
        message = re.sub(
            r"(?<![a-zA-Z0-9])orz(?![a-zA-Z0-9])",
            "",
            message,
            flags=re.IGNORECASE,
        )

        # 括弧付き顔文字を除去します。
        # 括弧（半角・全角）で囲まれており、
        # かつ中に日本語の通常文字（ひらがな、カタカナ、漢字）、英数字、
        # スペース、一般的な句読点・長音記号（ー）以外の文字（記号など）が
        # 1文字以上含まれるものを除去します。
        message = re.sub(
            r"(\(|（)[^)\n（）]*?"
            r"[^ぁ-んァ-ヶ一-龠々a-zA-Z0-9\s!！?？、。，．・ー]"
            r"[^)\n（）]*?(\)|）)",
            "",
            message,
        )

        # 1文字または2文字の w/W だけのメッセージの場合、「わら」に変換します。
        # (3文字以上の w は後続の処理で「わら」に変換されます)
        if re.match(r"^[wW]{1,2}$", message):
            message = "わら"
        else:
            # 直前が日本語、句読点、感嘆符、または閉じ括弧類である
            # 1〜2文字の w/W を「わら」に変換します。
            # (かつ、直後に英数字が続かないこと)
            message = re.sub(
                r"(?<=[ぁ-んァ-ヶ一-龠々!！?？、。，．・)）"
                r"\]］}｝>＞」』,.ー〜～~])([wW]{1,2})(?!\w)",
                " わら ",
                message,
                flags=re.IGNORECASE,
            )
        # 「www」「ｗｗｗ」など 3文字以上の草を「わら」に変換します。
        message = re.sub(r"[wW]{3,}", " わら ", message, flags=re.IGNORECASE)
        # 連続する感嘆符・疑問符を1文字に圧縮します。
        message = re.sub(r"[!！]{2,}", "！", message)
        message = re.sub(r"[?？]{2,}", "？", message)
        # サロゲートペア領域（絵文字等）および BMP領域の絵文字・記号を
        # 除去します。
        message = re.sub(r"[\U00010000-\U0010ffff]", "", message)
        message = re.sub(
            r"[\u2600-\u27BF\u2300-\u23FF\u2B00-\u2BFF\u25A0-\u25FF]",
            "",
            message,
        )
        # 読み上げ辞書を適用します。
        message = self.replace_words(message)
        return message.strip()

    def normalize_comment(
        self, author: str, message: str
    ) -> tuple[str, str]:
        """投稿者名とメッセージをまとめて正規化します。

        Args:
            author: 投稿者名。
            message: メッセージ。

        Returns:
            正規化された投稿者名とメッセージのタプル。
        """
        return self.normalize_author(author), self.normalize_message(message)
