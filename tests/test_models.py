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
"""データモデルの動作を検証するテストモジュールです。"""

from __future__ import annotations

from youtube_tts.models import CommentItem


def test_comment_item_creation() -> None:
    """CommentItem インスタンスが正しく作成されることを検証します。"""
    item = CommentItem(
        author="テスト送信者",
        message="テストメッセージです",
        char_count=12,
    )
    assert item.author == "テスト送信者"
    assert item.message == "テストメッセージです"
    assert item.char_count == 12
    # tupleとしての挙動も検証します。
    assert item[0] == "テスト送信者"
    assert item[1] == "テストメッセージです"
    assert len(item) == 2
