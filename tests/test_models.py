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

import datetime

from youtube_tts.models import (
    QuotaInfo,
    SpeechItem,
    SuperChatDetails,
    VideoDetails,
    YouTubeMessage,
)


def test_quota_info() -> None:
    """QuotaInfo のプロパティが正しく計算されることを検証します。"""
    quota = QuotaInfo(used=3000, limit=10000)
    assert quota.used == 3000
    assert quota.limit == 10000
    assert quota.remaining == 7000
    assert quota.usage_percent == 30.0
    assert quota.speech_text == (
        "ぴんぽーん！クォータ使用量は 3000 ユニットです。"
    )


def test_super_chat_details() -> None:
    """SuperChatDetails のプロパティが正しく計算・変換されることを

    検証します。
    """
    details = SuperChatDetails(
        amount_micros=10000000,
        currency="JPY",
        display_string="￥10,000",
    )
    assert details.amount_micros == 10000000
    assert details.currency == "JPY"
    assert details.display_string == "￥10,000"
    assert details.amount == 10.0
    assert details.to_dict() == {
        "amount_micros": 10000000,
        "currency": "JPY",
        "display_string": "￥10,000",
    }


def test_youtube_message_from_dict() -> None:
    """YouTubeMessage.from_dict が正しくインスタンスを生成することを

    検証します。
    """
    item = {
        "id": "msg-123",
        "authorDetails": {
            "channelId": "ch-abc",
            "displayName": "送信者A",
            "isChatSponsor": True,
            "isChatModerator": False,
            "isChatOwner": True,
        },
        "snippet": {
            "type": "textMessageEvent",
            "displayMessage": "こんにちは",
            "publishedAt": "2026-07-16T15:00:00.000Z",
        },
    }
    msg = YouTubeMessage.from_dict(item)
    assert msg.id == "msg-123"
    assert msg.author_name == "送信者A"
    assert msg.author_id == "ch-abc"
    assert msg.message == "こんにちは"
    assert msg.published_at.year == 2026
    assert msg.published_at.month == 7
    assert msg.published_at.day == 16
    assert msg.message_type == "textMessageEvent"
    assert msg.is_member is True
    assert msg.is_moderator is False
    assert msg.is_owner is True
    assert msg.super_chat is None


def test_youtube_message_with_super_chat() -> None:
    """スーパーチャットを含む YouTubeMessage が正しく生成されることを

    検証します。
    """
    item = {
        "id": "msg-456",
        "authorDetails": {
            "channelId": "ch-def",
            "displayName": "送信者B",
        },
        "snippet": {
            "type": "superChatEvent",
            "displayMessage": "スパチャです",
            "publishedAt": "2026-07-16T16:00:00Z",
            "superChatDetails": {
                "amountMicros": 5000000,
                "currency": "JPY",
                "amountDisplayString": "￥5,000",
            },
        },
    }
    msg = YouTubeMessage.from_dict(item)
    assert msg.super_chat is not None
    assert msg.super_chat.amount_micros == 5000000
    assert msg.super_chat.currency == "JPY"
    assert msg.super_chat.display_string == "￥5,000"
    assert msg.super_chat.amount == 5.0

    log_dict = msg.to_log_dict("video-xyz")
    assert log_dict["super_chat"] == {
        "amount_micros": 5000000,
        "currency": "JPY",
        "display_string": "￥5,000",
    }


def test_speech_item() -> None:
    """SpeechItem が正しく生成されることを検証します。"""
    msg = YouTubeMessage(
        id="1",
        author_name="Alice",
        author_id="a",
        message="Hello",
        published_at=datetime.datetime.now(datetime.timezone.utc),
    )
    item = SpeechItem.from_youtube_message(msg, "アリス", "ハロー")
    assert item.author == "アリス"
    assert item.message == "ハロー"
    assert item.char_count == 6

    # JSTタイムゾーンでのto_log_dictを検証します。
    # (endswith("+00:00")がFalseになるルートのカバー)
    from zoneinfo import ZoneInfo

    msg_jst = YouTubeMessage(
        id="2",
        author_name="Bob",
        author_id="b",
        message="Hi",
        published_at=datetime.datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    log_dict_jst = msg_jst.to_log_dict("video-xyz")
    assert not log_dict_jst["timestamp"].endswith("Z")
    assert "+09:00" in log_dict_jst["timestamp"]


def test_video_details() -> None:
    """VideoDetails が正しく動作することを検証します。"""
    video = VideoDetails(video_id="vid", channel_id="ch-owner", title="Live")
    assert video.video_id == "vid"
    assert video.channel_id == "ch-owner"
    assert video.title == "Live"
    assert video.is_owner("ch-owner") is True
    assert video.is_owner("ch-other") is False
    assert video.is_owner(None) is False
