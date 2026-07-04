"""utils.py に実装された動画ID抽出関数の
テストを行うモジュール。

通常URL、短縮URL、ライブ配信URL、ID直接入力のほか、
パラメータやパスが不正な場合のエラー境界値を
網羅して検証します。
"""

import pytest

from youtube_tts.utils import extract_video_id


def test_extract_video_id_success():
    """正常な入力値および各種URLから動画IDが抽出できるか検証。"""
    # 1. 直接動画ID
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    # 2. 通常視聴URL
    assert (
        extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    )

    # 3. 短縮URL
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    # 4. ライブ配信URL
    assert extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_failure():
    """ドメインが一致しても構造が不正なら RuntimeError になるか。"""
    # 不正なパス
    with pytest.raises(RuntimeError, match="failed to extract video id"):
        extract_video_id("https://www.youtube.com/invalid_path")

    # vパラメータ欠落
    with pytest.raises(RuntimeError, match="failed to extract video id"):
        extract_video_id("https://www.youtube.com/watch?id=dQw4w9WgXcQ")

    # ライブID欠落
    with pytest.raises(RuntimeError, match="failed to extract video id"):
        extract_video_id("https://www.youtube.com/live/")
