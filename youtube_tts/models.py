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
"""データモデルを定義するモジュールです。"""


class CommentItem(tuple):
    """キューに投入されるチャットやコメントのアイテムを表現するクラス。"""

    def __new__(cls, author: str, message: str, char_count: int):
        """新しい CommentItem インスタンスを作成します。

        Args:
            author: 送信者名。
            message: メッセージ本文。
            char_count: 文字数。
        """
        return super().__new__(cls, (author, message))

    def __init__(self, author: str, message: str, char_count: int):
        """CommentItem インスタンスを初期化します。

        Args:
            author: 送信者名。
            message: メッセージ本文。
            char_count: 文字数。
        """
        self.author = author
        self.message = message
        self.char_count = char_count
