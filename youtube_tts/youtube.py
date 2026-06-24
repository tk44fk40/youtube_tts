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
import sys
from urllib.parse import parse_qs, urlparse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .logger import get_logger

logger = get_logger()

class YouTubeChatClient:
    def __init__(self, credentials, verbose=False):
        self.youtube = build("youtube", "v3", credentials=credentials)
        self.verbose = verbose

    def extract_video_id(self, value):
        if "youtube.com" not in value and "youtu.be" not in value:
            return value

        parsed = urlparse(value)

        # Extract video ID from youtu.be/<id> format URL
        #
        # youtu.be/<id> 形式のURLから動画IDを抽出する
        if parsed.netloc == "youtu.be":
            return parsed.path.lstrip("/")

        # Extract video ID from youtube.com/watch?v=<id> format URL
        #
        # youtube.com/watch?v=<id> 形式のURLから動画IDを抽出する
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            if "v" in query:
                return query["v"][0]

        # Extract video ID from youtube.com/live/<id> format URL
        #
        # youtube.com/live/<id> 形式のURLから動画IDを抽出する
        if parsed.path.startswith("/live/"):
            parts = parsed.path.split("/")
            if len(parts) >= 3:
                return parts[2]

        raise RuntimeError("failed to extract video id")

    def get_live_chat_id(self, video_id):
        try:
            response = (
                self.youtube.videos()
                .list(part="liveStreamingDetails", id=video_id)
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            # Delegate re-throwing exceptions to the caller
            #
            # 例外の再スローは呼び出し元に委ねる
            raise

        items = response.get("items", [])
        if not items:
            raise RuntimeError("video not found")

        details = items[0].get("liveStreamingDetails", {})
        live_chat_id = details.get("activeLiveChatId")
        if not live_chat_id:
            raise RuntimeError("activeLiveChatId not found")

        return live_chat_id

    def get_current_live_video_id(self):
        try:
            response = (
                self.youtube.liveBroadcasts()
                .list(part="id,status", mine=True)
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            # Delegate re-throwing exceptions to the caller
            #
            # 例外の再スローは呼び出し元に委ねる
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

    def fetch_chat_messages(self, live_chat_id, page_token=None):
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
            # Delegate re-throwing exceptions to the caller
            #
            # 例外の再スローは呼び出し元に委ねる
            raise

        items = response.get("items", [])
        next_page_token = response.get("nextPageToken")
        polling_interval_min = 3000
        polling_interval = max(
            response.get("pollingIntervalMillis", polling_interval_min),
            polling_interval_min,
        )

        return items, next_page_token, polling_interval

    def check_stream_active(self, video_id) -> bool:
        try:
            vresp = (
                self.youtube.videos()
                .list(part="liveStreamingDetails", id=video_id)
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            logger.warning(f"Error checking video status: {e}")
            # Prioritize continuation on check failure (assume streaming)
            #
            # チェック失敗時は継続を優先（配信中と見なす）
            return True
        
        items = vresp.get("items", [])
        if not items:
            logger.info("Video not found; assuming stream ended")
            return False

        details = items[0].get("liveStreamingDetails", {})
        active_chat = details.get("activeLiveChatId")
        if not active_chat:
            logger.info("activeLiveChatId missing; stream likely ended")
            return False

        return True

    def _handle_api_error(self, e: HttpError):
        """Detects YouTube API exceptions and outputs detailed guidance
        according to the cause.

        This method only logs the error and does not re-throw the exception,
        allowing the caller to decide the action (continue or stop) based on
        the exception type.

        YouTube APIの例外を検知し、
        発生原因に応じた詳細なガイダンスを日本語で出力する。

        このメソッドはログ出力のみ行い、例外の再スローは行わない。
        呼び出し元が例外の種類に応じて動作（継続 or 停止）を選択
        できるようにするため。
        """
        err_msg = str(e)
        if e.resp.status == 403:
            if "quotaExceeded" in err_msg:
                logger.error(
                    "[ERROR] YouTube API の本日の"
                    "無料枠上限（クォータ）を超過しました。"
                )
                logger.error(
                    "        - 太平洋時間 0:00"
                    "（日本時間の午後4時〜5時頃）に"
                    "制限がリセットされるまでお待ちください。"
                )
                logger.error(
                    "        - または、別の "
                    "Google Cloud プロジェクトの "
                    "client_secret.json を使用してください。"
                )
            elif "commentsDisabled" in err_msg:
                logger.error(
                    "[ERROR] この動画・アーカイブは"
                    "コメント機能がオフ（無効）に設定されています。"
                )
                logger.error(
                    "        - コメント（チャット）機能が"
                    "有効な動画・配信のURLを指定してください。"
                )
            else:
                # Insufficient permissions, members-only, or private video, etc.
                # 権限不足・メンバー限定・非公開動画など
                logger.error(
                    "[ERROR] 指定された動画・配信への"
                    "アクセス権限がありません。"
                )
                logger.error(
                    "        - メンバー限定配信、非公開、または"
                    "限定公開の動画ではないかご確認ください。"
                )
                logger.error(
                    "        - 閲覧権限がある正しい "
                    "Google アカウントで"
                    "再認証（token.json を削除して再実行）"
                    "してください。"
                )
        else:
            logger.error(
                f"[ERROR] YouTube API エラーが発生しました "
                f"(ステータスコード: {e.resp.status})"
            )

        if getattr(self, "verbose", False):
            logger.debug(f"  (エラー詳細: {err_msg.strip()})")

    def get_my_channel_id(self):
        if not hasattr(self, "_my_channel_id"):
            try:
                response = (
                    self.youtube.channels()
                    .list(part="id", mine=True)
                    .execute()
                )
                items = response.get("items", [])
                if items:
                    self._my_channel_id = items[0]["id"]
                else:
                    self._my_channel_id = None
            except Exception as ex:
                logger.warning(f"Failed to get my channel ID: {ex}")
                self._my_channel_id = None
        return self._my_channel_id

    def get_video_details(self, video_id):
        try:
            response = (
                self.youtube.videos()
                .list(part="snippet,liveStreamingDetails", id=video_id)
                .execute()
            )
        except HttpError as e:
            self._handle_api_error(e)
            raise
        
        items = response.get("items", [])
        if not items:
            raise RuntimeError("video not found")
        return items[0]

    def fetch_comment_threads(self, video_id, page_token=None, max_results=100):
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
                author_channel_id = (
                    comment_snippet.get("authorChannelId", {})
                    .get("value", "")
                )
                
                if comment_id:
                    items.append({
                        "id": comment_id,
                        "authorDetails": {
                            "displayName": author,
                            "channelId": author_channel_id
                        },
                        "snippet": {
                            "type": "commentEvent",
                            "displayMessage": message,
                            "publishedAt": published_at
                        }
                    })
            except Exception as ex:
                logger.warning(f"Failed to parse comment: {ex}")
                continue

        next_page_token = response.get("nextPageToken")
        polling_interval = 3000

        return items, next_page_token, polling_interval
