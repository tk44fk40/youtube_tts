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
from googleapiclient.errors import HttpError

from .client import BaseYouTubeClient, logger


class YouTubeVideoClient(BaseYouTubeClient):
    """YouTubeの動画詳細およびコメントスレッドに特化したクライアントクラス"""

    def fetch_comment_threads(
        self,
        video_id: str,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> tuple[list[dict], str | None, int]:
        """コメントスレッドの取得

        指定された動画IDからコメントスレッドを取得し、
            チャット形式に整形して返す。

        Args:
            video_id (str): 対象の動画ID。
            page_token (str | None, optional): 次のページからデータを
                取得するためのトークン。デフォルトは None。
            max_results (int, optional): 1回の要求で取得する最大件数。
                デフォルトは 100。

        Returns:
            tuple[list[dict], str | None, int]: 以下の3つの要素を含むタプル。
                - list[dict]: ライブチャットに構造を合わせた、
                    整形済みのコメントオブジェクトのリスト。
                - str | None: 次のページを取得するためのトークン。
                    存在しない場合は None。
                - int: 次回呼び出しまでの固定ポーリング間隔（3000ミリ秒）。

        Raises:
            HttpError: YouTube APIの呼び出しに失敗した場合。
        """
        try:
            response = (
                self.youtube.commentThreads()
                .list(
                    videoId=video_id,
                    part="snippet",
                    pageToken=page_token,
                    maxResults=max_results,
                    order="time",
                )
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            raise

        raw_items = response.get("items", [])
        items = []
        for item in raw_items:
            try:
                top_comment = item.get("snippet", {}).get("topLevelComment", {})
                comment_id = top_comment.get("id")
                comment_snippet = top_comment.get("snippet", {})
                author = comment_snippet.get("authorDisplayName", "")
                message = comment_snippet.get("textOriginal", "")
                published_at = comment_snippet.get("publishedAt", "")
                author_channel_id = comment_snippet.get("authorChannelId", {}).get(
                    "value", ""
                )

                if comment_id:
                    items.append(
                        {
                            "id": comment_id,
                            "authorDetails": {
                                "displayName": author,
                                "channelId": author_channel_id,
                            },
                            "snippet": {
                                "type": "commentEvent",
                                "displayMessage": message,
                                "publishedAt": published_at,
                            },
                        }
                    )
            except Exception as ex:
                logger.warning(f"Failed to parse comment: {ex}")
                continue

        next_page_token = response.get("nextPageToken")
        polling_interval = 3000

        return items, next_page_token, polling_interval
