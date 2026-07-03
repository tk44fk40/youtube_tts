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
"""YouTube Data API との通信および共通処理を提供する基盤モジュール。

このモジュールは、YouTube API クライアントの基底クラスと、
認証情報の管理・エラーハンドリングの共通機能を提供します。
"""

import contextlib

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .logger import get_logger

logger = get_logger()


class BaseYouTubeClient:
    """YouTube APIとの通信および共通処理を管理する基盤クラス。"""

    def __init__(self, credentials, verbose: bool = False):
        """BaseYouTubeClient を初期化します。

        Args:
            credentials: Google API の認証情報オブジェクト。
            verbose: 詳細なデバッグログを出力するかどうか。
                デフォルトは False。
        """
        self.youtube = build("youtube", "v3", credentials=credentials)
        self.verbose = verbose

    def get_my_channel_id(self) -> str | None:
        """認証ユーザー自身の YouTube チャンネル ID を取得します。

        Returns:
            チャンネル ID。取得に失敗した場合は None。
        """
        if not hasattr(self, "_my_channel_id"):
            try:
                response = self.youtube.channels().list(part="id", mine=True).execute()
                items = response.get("items", [])
                if items:
                    self._my_channel_id = items[0]["id"]
                else:
                    self._my_channel_id = None
            except Exception as ex:  # noqa: BLE001
                logger.warning(
                    f"自分のチャンネル ID の取得に失敗しました: {ex}"
                )
                self._my_channel_id = None
        return self._my_channel_id

    def get_video_details(self, video_id: str) -> dict:
        """YouTube 動画の詳細情報を取得します。

        snippet および liveStreamingDetails を含む詳細情報を
        取得します。

        Args:
            video_id: YouTube の動画 ID。

        Returns:
            動画の詳細情報を含む API レスポンスのアイテムオブジェクト。

        Raises:
            RuntimeError: 動画が見つからない場合。
            HttpError: YouTube API の呼び出しに失敗した場合。
        """
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

    def _handle_api_error(self, e: HttpError) -> None:
        """YouTube API エラーを検知し、原因に応じたガイダンスをログ出力します。

        このメソッドはログ出力のみ行い、例外の再スローは行いません。
        呼び出し元が例外の種類に応じて
        動作（継続 / 停止）を選択できるようにするためです。

        Args:
            e: 発生した YouTube API のエラーオブジェクト。
        """
        err_msg = str(e)
        if getattr(e, "content", None):
            with contextlib.suppress(Exception):
                err_msg += " " + e.content.decode("utf-8")

        if e.resp.status == 403:
            if "quotaExceeded" in err_msg:
                logger.error(
                    "[ERROR] YouTube API の本日の無料枠上限（クォータ）を超過しました。"
                )
                logger.error(
                    "  - 太平洋時間 0:00（日本時間の午後4時〜5時頃）に"
                    "制限がリセットされるまでお待ちください。"
                )
                logger.error(
                    "  - または、別の Google Cloud プロジェクトの "
                    "client_secret.json を使用してください。"
                )
            elif "commentsDisabled" in err_msg:
                logger.error(
                    "[ERROR] この動画・アーカイブはコメント機能がオフ"
                    "（無効）に設定されています。"
                )
                logger.error(
                    "  - コメント（チャット）機能が有効な動画・配信の"
                    "URLを指定してください。"
                )
            else:
                logger.error(
                    "[ERROR] 指定された動画・配信へのアクセス権限がありません。"
                )
                logger.error(
                    "  - メンバー限定配信、非公開、"
                    "または限定公開の動画ではないかご確認ください。"
                )
                logger.error(
                    "  - 閲覧権限がある正しい Google アカウントで"
                    "再認証（token.json を削除して再実行）してください。"
                )
        else:
            msg = "[ERROR] YouTube API エラーが発生しました"
            logger.error(f"{msg} (ステータスコード: {e.resp.status})")

        if getattr(self, "verbose", False):
            logger.debug(f"  (エラー詳細: {err_msg.strip()})")
