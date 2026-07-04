"""utils.py に実装された動画 ID 抽出関数のテストを行うモジュール。

通常 URL、短縮 URL、ライブ配信 URL、ID 直接入力のほか、
パラメータやパスが不正な場合のエラー境界値を
網羅して検証します。
"""

from __future__ import annotations

import pytest

from youtube_tts.utils import extract_video_id


def test_extract_video_id_success() -> None:
    """正常な入力値および各種 URL から動画 ID が抽出できるか検証します。"""
    # 1. 直接動画 ID
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    # 2. 通常視聴 URL
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"

    # 3. 短縮 URL
    assert (
        extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    )

    # 4. ライブ配信 URL
    live_url = "https://www.youtube.com/live/dQw4w9WgXcQ"
    assert extract_video_id(live_url) == "dQw4w9WgXcQ"


def test_extract_video_id_failure() -> None:
    """ドメインが一致しても構造が不正なら RuntimeError になるか検証します。"""
    # 不正なパス
    with pytest.raises(RuntimeError, match="動画 ID の抽出に失敗しました。"):
        extract_video_id("https://www.youtube.com/invalid_path")

    # v パラメータ欠落
    with pytest.raises(RuntimeError, match="動画 ID の抽出に失敗しました。"):
        extract_video_id("https://www.youtube.com/watch?id=dQw4w9WgXcQ")

    # ライブ ID 欠落
    with pytest.raises(RuntimeError, match="動画 ID の抽出に失敗しました。"):
        extract_video_id("https://www.youtube.com/live/")
