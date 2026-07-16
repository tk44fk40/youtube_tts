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
"""YouTubeのライブ配信に関連する操作を行うモジュールです。"""

from __future__ import annotations

from googleapiclient.errors import HttpError

from .client import BaseYouTubeClient, logger
from .models import YouTubeMessage


class YouTubeLiveChatClient(BaseYouTubeClient):
    """YouTube のライブ配信やチャットに特化したクライアントです。"""

    def get_live_chat_id(self, video_id: str) -> str:
        """動画IDに対応するアクティブなライブチャットIDを取得します。

        Args:
            video_id (str): YouTubeの動画IDです。

        Returns:
            str: ライブチャットID（activeLiveChatId）です。

        Raises:
            RuntimeError: 動画が見つからない場合、
                または activeLiveChatId が取得できない場合です。
            HttpError: YouTube APIの呼び出しに失敗した場合です。
        """
        try:
            response = (
                self.youtube.videos()
                .list(part="liveStreamingDetails", id=video_id)
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            raise

        items = response.get("items", [])
        if not items:
            raise RuntimeError("video not found")

        details = items[0].get("liveStreamingDetails", {})
        live_chat_id = details.get("activeLiveChatId")
        if not live_chat_id:
            raise RuntimeError("activeLiveChatId not found")

        return live_chat_id

    def get_current_live_video_id(self) -> tuple[str, str]:
        """現在配信中の自身のライブ配信動画IDとチャットURLを取得します。

        Returns:
            tuple[str, str]: 動画IDとポップアウトチャットURLのタプル
                (video_id, chat_url)です。

        Raises:
            RuntimeError: 配信中のライブ放送が見つからない場合です。
            HttpError: YouTube APIの呼び出しに失敗した場合です。
        """
        try:
            response = (
                self.youtube.liveBroadcasts()
                .list(part="id,status", mine=True)
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            raise

        items = response.get("items", [])
        for item in items:
            status = item.get("status", {}).get("lifeCycleStatus")
            if status == "live":
                vid = item.get("id")
                chat_url = (
                    f"https://www.youtube.com/live_chat?v={vid}&is_popout=1"
                )
                return vid, chat_url

        raise RuntimeError(
            "No live broadcast found. "
            "Please start a live stream or pass VIDEO_ID as an argument."
        )

    def fetch_chat_messages(
        self, live_chat_id: str, page_token: str | None = None
    ) -> tuple[list[YouTubeMessage], str | None, int]:
        """指定されたライブチャットIDからチャットメッセージを取得します。

        Args:
            live_chat_id (str): 対象のライブチャットIDです。
            page_token (str | None, optional): 次のページから
                データを取得するためのトークンです。デフォルトは None です。

        Returns:
            tuple[list[YouTubeMessage], str | None, int]:
                以下の3つの要素を含むタプルです。
                - list[YouTubeMessage]: メッセージオブジェクトのリスト。
                - str | None: 次のページを取得するためのトークンです。
                    存在しない場合は None です。
                - int: 次回呼び出しまでの推奨ポーリング間隔（ミリ秒）です。

        Raises:
            HttpError: YouTube APIの呼び出しに失敗した場合です。
        """
        try:
            response = (
                self.youtube.liveChatMessages()
                .list(
                    liveChatId=live_chat_id,
                    part="snippet,authorDetails",
                    pageToken=page_token,
                    maxResults=200,
                )
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            raise

        items = response.get("items", [])
        messages = [YouTubeMessage.from_dict(item) for item in items]
        next_page_token = response.get("nextPageToken")
        polling_interval_min = 3000
        polling_interval = max(
            response.get("pollingIntervalMillis", polling_interval_min),
            polling_interval_min,
        )

        return messages, next_page_token, polling_interval

    def check_stream_active(self, video_id: str) -> bool:
        """対象のライブ配信がアクティブ（配信中）か確認します。

        APIエラーなどチェック自体に失敗した場合は、
        処理継続を優先して True を返します。

        Args:
            video_id (str): 確認対象の動画IDです。

        Returns:
            bool: 配信が継続している（activeLiveChatId が存在する）場合は
                True です。動画が存在しない、または配信が終了している場合は
                False です。
        """
        try:
            vresp = (
                self.youtube.videos()
                .list(part="liveStreamingDetails", id=video_id)
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            logger.warning(f"動画ステータスの確認中にエラーが発生しました: {e}")
            return True

        items = vresp.get("items", [])
        if not items:
            logger.info("動画が見つかりません。配信が終了したと判断します。")
            return False

        details = items[0].get("liveStreamingDetails", {})
        active_chat = details.get("activeLiveChatId")
        if not active_chat:
            logger.info(
                "activeLiveChatId が見つかりません。"
                "配信が終了した可能性があります。"
            )
            return False

        return True
