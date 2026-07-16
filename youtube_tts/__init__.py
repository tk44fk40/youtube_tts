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
"""YouTube TTS パッケージの初期化モジュールです。

主要なクラス、関数、および定数をパッケージレベルでインポートできるようにします。
"""

from .app import YouTubeTtsApp
from .audio import AudioPlayer
from .auth import YOUTUBE_SCOPE, YouTubeAuthenticator
from .config import AppConfig
from .dictionary import TextProcessor
from .live import YouTubeLiveChatClient
from .logger import get_logger, setup_logger
from .models import (
    QuotaInfo,
    SpeechItem,
    SuperChatDetails,
    VideoDetails,
    YouTubeMessage,
)
from .obs import ObsClient
from .quota import QUOTA_SCOPES, get_project_id, get_quota_info
from .utils import extract_video_id
from .video import YouTubeVideoClient
from .voicevox import VoicevoxClient

__all__ = [
    "YouTubeAuthenticator",
    "YouTubeLiveChatClient",
    "YouTubeVideoClient",
    "VoicevoxClient",
    "AudioPlayer",
    "AppConfig",
    "TextProcessor",
    "ObsClient",
    "YOUTUBE_SCOPE",
    "QUOTA_SCOPES",
    "get_project_id",
    "get_quota_info",
    "setup_logger",
    "get_logger",
    "extract_video_id",
    "YouTubeTtsApp",
    "QuotaInfo",
    "SuperChatDetails",
    "YouTubeMessage",
    "SpeechItem",
    "VideoDetails",
]
