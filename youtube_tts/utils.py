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
"""YouTube 関連のユーティリティ関数を提供するモジュール。

このモジュールは、YouTube の動画URLやIDから動画IDを抽出する
ユーティリティ関数を提供します。
"""

from urllib.parse import parse_qs, urlparse


def extract_video_id(value: str) -> str:
    """URLまたは文字列からYouTubeの動画IDを抽出します。

    youtu.be/<id>、youtube.com/watch?v=<id>、youtube.com/live/<id>
    の形式に対応しています。URL形式でない場合は入力値をそのまま返します。

    Args:
        value: YouTubeの動画URL（各種形式）、または動画IDの文字列。

    Returns:
        抽出されたYouTubeの動画ID。

    Raises:
        RuntimeError: 対応しているURL形式であるにもかかわらず、
            動画IDの抽出に失敗した場合。
    """
    if "youtube.com" not in value and "youtu.be" not in value:
        return value

    parsed = urlparse(value)

    # youtu.be/<id> 形式のURLから動画IDを抽出する
    if parsed.netloc == "youtu.be":
        return parsed.path.lstrip("/")

    # youtube.com/watch?v=<id> 形式のURLから動画IDを抽出する
    if parsed.path == "/watch":
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]

    # youtube.com/live/<id> 形式のURLから動画IDを抽出する
    if parsed.path.startswith("/live/"):
        parts = parsed.path.split("/")
        if len(parts) >= 3 and parts[2]:
            return parts[2]

    raise RuntimeError("failed to extract video id")
