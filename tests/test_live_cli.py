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
"""Tests for youtube_live_voicevox.py CLI options and exceptions.

youtube_live_voicevox.py のCLIオプションと例外ハンドリングのテスト。
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from youtube_live_voicevox import main


@pytest.fixture(autouse=True)
def clean_environ():
    """テスト毎に環境変数を初期化するフィクスチャ。"""
    with patch.dict(os.environ, {"VOICEVOX_TTS_TEST": ""}):
        yield


@pytest.fixture(autouse=True)
def mock_voicevox_client_get_speakers():
    """VOICEVOXスピーカー取得をモック化するフィクスチャ。"""
    with patch(
        "youtube_live_voicevox.VoicevoxClient.get_speakers"
    ) as mock_get_speakers:
        yield mock_get_speakers


@pytest.fixture
def mock_cli_components():
    """主要コンポーネントを一括でモック化し、標準的な初期値を設定。"""
    with (
        patch("youtube_live_voicevox.YouTubeAuthenticator") as mock_auth,
        patch("youtube_live_voicevox.YouTubeLiveChatClient") as mock_live_client,
        patch("youtube_live_voicevox.YouTubeTtsApp") as mock_app_class,
        patch("youtube_live_voicevox.AudioPlayer") as mock_audio_player_class,
        patch("sounddevice.query_devices") as mock_query,
        patch("youtube_live_voicevox.extract_video_id") as mock_extract,
    ):
        mock_query.return_value = {"name": "test_device", "index": 6}

        mock_auth_instance = MagicMock()
        mock_auth.return_value = mock_auth_instance
        mock_auth_instance.get_credentials.return_value = MagicMock()

        mock_live_client_instance = MagicMock()
        mock_live_client.return_value = mock_live_client_instance
        mock_live_client_instance.get_current_live_video_id.return_value = (
            "live_vid",
            "live_url",
        )

        mock_extract.return_value = "video123"

        mock_app_instance = MagicMock()
        mock_app_class.return_value = mock_app_instance

        yield {
            "auth": mock_auth,
            "auth_instance": mock_auth_instance,
            "live_client": mock_live_client,
            "live_client_instance": mock_live_client_instance,
            "extract_video_id": mock_extract,
            "app_class": mock_app_class,
            "app_instance": mock_app_instance,
            "audio_player_class": mock_audio_player_class,
            "query_devices": mock_query,
        }


def test_live_cli_device_option(mock_cli_components):
    """-d オプションで指定したデバイスIDが使用されることを検証。"""
    components = mock_cli_components

    with patch("sys.argv", ["youtube_live_voicevox.py", "-d", "6", "video123"]):
        main()

    components["audio_player_class"].assert_called_with(default_device=6)
    components["extract_video_id"].assert_called_with("video123")
    components["app_class"].assert_called_once()
    components["app_instance"].run_live.assert_called_once()


@patch("youtube_live_voicevox.get_project_id")
def test_live_cli_quota_options(mock_get_project_id, mock_cli_components):
    """クォータやインターバルに関する各種オプションの指定を検証。"""
    components = mock_cli_components
    mock_get_project_id.return_value = "test-project-123"
    mock_creds = components["auth_instance"].get_credentials.return_value

    from youtube_tts import QUOTA_SCOPES

    argv = [
        "youtube_live_voicevox.py",
        "--quota-talk",
        "--chat-interval",
        "10",
        "--quota-interval",
        "30",
        "video123",
    ]
    with patch("sys.argv", argv):
        main()

    components["auth"].assert_called_with(
        client_secret_path="client_secret.json",
        token_path="token.json",
        scopes=QUOTA_SCOPES,
    )
    mock_get_project_id.assert_called_once()

    components["app_instance"].run_live.assert_called_with(
        live_client=components["live_client_instance"],
        video_id="video123",
        creds=mock_creds,
        quota_check=True,
        quota_talk=True,
        tts_test=None,
        chat_interval=10.0,
        quota_interval=30.0,
        stream_check_interval=180.0,
        project_id="test-project-123",
        verbose=False,
        backlog_seconds=10,
    )


def test_live_cli_speed_option(mock_cli_components):
    """--speed オプションが config.speed_scale に反映されることを検証。"""
    components = mock_cli_components

    with patch("sys.argv", ["youtube_live_voicevox.py", "--speed", "1.5", "video123"]):
        main()

    _, kwargs = components["app_class"].call_args
    assert kwargs["config"].speed_scale == 1.5


def test_live_cli_speed_boost_options(mock_cli_components):
    """スピードブーストオプションが正しく構成に反映されることを検証。"""
    components = mock_cli_components

    argv = [
        "youtube_live_voicevox.py",
        "--auto-speed-boost",
        "--max-speed",
        "1.8",
        "video123",
    ]
    with patch("sys.argv", argv):
        main()

    _, kwargs = components["app_class"].call_args
    assert kwargs["config"].auto_speed_boost is True
    assert kwargs["config"].max_speed == 1.8


def test_live_cli_chat_log_option(mock_cli_components):
    """--chat-log で指定したパスが構成に保存されることを検証。"""
    components = mock_cli_components

    argv = [
        "youtube_live_voicevox.py",
        "--chat-log",
        "custom_path.jsonl",
        "video123",
    ]
    with patch("sys.argv", argv):
        main()

    _, kwargs = components["app_class"].call_args
    assert kwargs["config"].chat_log_path == "custom_path.jsonl"


def test_live_cli_auth_failure(mock_cli_components):
    """認証に失敗した場合、ステータスコード1でシステム終了することを検証。"""
    components = mock_cli_components
    components["auth_instance"].get_credentials.side_effect = Exception("Auth Failure")

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["youtube_live_voicevox.py", "video123"]):
            main()
    assert exc_info.value.code == 1


def test_live_cli_video_id_auto_detection_success(mock_cli_components):
    """引数なしの場合に配信IDの自動検出が試みられることを検証。"""
    components = mock_cli_components
    mock_live_inst = components["live_client_instance"]

    with patch("sys.argv", ["youtube_live_voicevox.py"]):
        main()
    mock_live_inst.get_current_live_video_id.assert_called_once()


def test_live_cli_video_id_auto_detection_failure(mock_cli_components):
    """自動検出に失敗した場合、ステータスコード1で終了することを検証。"""
    components = mock_cli_components
    mock_live_inst = components["live_client_instance"]
    mock_live_inst.get_current_live_video_id.side_effect = RuntimeError(
        "No live stream found"
    )

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["youtube_live_voicevox.py"]):
            main()
    assert exc_info.value.code == 1
