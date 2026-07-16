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

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuotaInfo:
    """YouTube API のクォータ使用状況を表すクラスです。"""

    used: int
    """当日の消費クォータ値です。"""
    limit: int
    """当日のクォータ上限値です。"""

    @property
    def remaining(self) -> int:
        """残りクォータ値を取得します。

        Returns:
            int: 残りクォータ値です。
        """
        return max(0, self.limit - self.used)

    @property
    def usage_percent(self) -> float:
        """クォータ使用率（パーセント）を取得します。

        Returns:
            float: クォータ使用率です。
        """
        return (self.used / self.limit) * 100 if self.limit > 0 else 0.0

    @property
    def speech_text(self) -> str:
        """クォータ使用状況を通知するための読み上げ用テキストを取得します。

        Returns:
            str: 読み上げ用テキストです。
        """
        return f"ぴんぽーん！クォータ使用量は {self.used} ユニットです。"


@dataclass(frozen=True)
class SuperChatDetails:
    """スーパーチャットの詳細情報を表すクラスです。"""

    amount_micros: int
    """マイクロ単位の金額です。"""
    currency: str
    """通貨コードです。"""
    display_string: str
    """画面表示用の金額文字列です。"""

    @property
    def amount(self) -> float:
        """マイクロ単位の金額を実数に換算した値を取得します。

        Returns:
            float: 換算後の金額です。
        """
        return self.amount_micros / 1000000

    def to_dict(self) -> dict[str, Any]:
        """ログ保存用の辞書表現を生成します。

        Returns:
            dict[str, Any]: ログ保存用の辞書表現です。
        """
        return {
            "amount_micros": self.amount_micros,
            "currency": self.currency,
            "display_string": self.display_string,
        }


@dataclass(frozen=True)
class YouTubeMessage:
    """YouTube API から受信したメッセージを表すクラスです。"""

    id: str
    """メッセージの一意なIDです。"""
    author_name: str
    """投稿者の表示名です。"""
    author_id: str
    """投稿者のチャンネルIDです。"""
    message: str
    """メッセージ本文の生テキストです。"""
    published_at: datetime.datetime
    """投稿日時です。"""
    message_type: str = "textMessageEvent"
    """メッセージの種類です。"""
    is_member: bool = False
    """メンバーシップ加入者であるかどうかを表す真偽値です。"""
    is_moderator: bool = False
    """モデレーターであるかどうかを表す真偽値です。"""
    is_owner: bool = False
    """配信主であるかどうかを表す真偽値です。"""
    super_chat: SuperChatDetails | None = None
    """スーパーチャット詳細情報です。"""

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> YouTubeMessage:
        """API レスポンス辞書から YouTubeMessage インスタンスを生成します。

        Args:
            item: API からの受信データ辞書です。

        Returns:
            YouTubeMessage: 生成されたインスタンスです。
        """
        # publishedAt のパース処理
        published_at_str = item.get("snippet", {}).get("publishedAt")
        if published_at_str:
            try:
                published_at = datetime.datetime.fromisoformat(
                    published_at_str.replace("Z", "+00:00")
                )
            except ValueError:
                published_at = datetime.datetime.now(datetime.timezone.utc)
        else:
            published_at = datetime.datetime.now(datetime.timezone.utc)

        author_details = item.get("authorDetails", {})
        snippet = item.get("snippet", {})

        super_chat = None
        super_chat_details = snippet.get("superChatDetails")
        if super_chat_details:
            super_chat = SuperChatDetails(
                amount_micros=super_chat_details.get("amountMicros", 0),
                currency=super_chat_details.get("currency", ""),
                display_string=super_chat_details.get(
                    "amountDisplayString", ""
                ),
            )

        return cls(
            id=item.get("id", ""),
            author_name=author_details.get("displayName", ""),
            author_id=author_details.get("channelId", ""),
            message=snippet.get("displayMessage", ""),
            published_at=published_at,
            message_type=snippet.get("type", "textMessageEvent"),
            is_member=author_details.get("isChatSponsor", False),
            is_moderator=author_details.get("isChatModerator", False),
            is_owner=author_details.get("isChatOwner", False),
            super_chat=super_chat,
        )

    def to_log_dict(self, video_id: str) -> dict[str, Any]:
        """ログファイル出力用の辞書を生成します。

        Args:
            video_id: 動画のIDです。

        Returns:
            dict[str, Any]: ログ用の辞書です。
        """
        # タイムスタンプは ISO8601 形式の文字列で出力します。
        timestamp_str = self.published_at.isoformat()
        if timestamp_str.endswith("+00:00"):
            timestamp_str = timestamp_str[:-6] + "Z"

        log_data = {
            "timestamp": timestamp_str,
            "video_id": video_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "message": self.message,
            "message_type": self.message_type,
            "is_member": self.is_member,
            "is_moderator": self.is_moderator,
            "is_owner": self.is_owner,
            "super_chat": (
                self.super_chat.to_dict() if self.super_chat else None
            ),
        }
        return log_data


@dataclass(frozen=True)
class SpeechItem:
    """読み上げキューに投入されるアイテムを表すクラスです。"""

    author: str
    """送信者名です。"""
    message: str
    """読み上げるメッセージ本文です。"""
    char_count: int
    """送信者名と本文の合計文字数です。"""

    @classmethod
    def from_youtube_message(
        cls,
        yt_message: YouTubeMessage,
        normalized_author: str,
        normalized_message: str,
    ) -> SpeechItem:
        """YouTubeMessage と正規化されたテキストから SpeechItem を生成します。

        Args:
            yt_message: 元の YouTubeMessage です。
            normalized_author: 正規化された送信者名です。
            normalized_message: 正規化されたメッセージ本文です。

        Returns:
            SpeechItem: 生成されたインスタンスです。
        """
        char_count = len(normalized_author) + len(normalized_message)
        return cls(
            author=normalized_author,
            message=normalized_message,
            char_count=char_count,
        )


@dataclass(frozen=True)
class VideoDetails:
    """動画または配信の詳細情報を表すクラスです。"""

    video_id: str
    """動画のIDです。"""
    channel_id: str
    """配信者のチャンネルIDです。"""
    title: str
    """動画のタイトルです。"""

    def is_owner(self, my_channel_id: str | None) -> bool:
        """指定されたチャンネルIDが配信主と一致するかどうかを判定します。

        Args:
            my_channel_id: 判定対象となる自分のチャンネルIDです。

        Returns:
            bool: 一致する場合は True、それ以外は False です。
        """
        return my_channel_id is not None and self.channel_id == my_channel_id
