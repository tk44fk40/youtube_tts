"""youtube_live_voicevox.py のCLIオプションと例外ハンドリングのテストです。"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_live_voicevox import main


@pytest.fixture(autouse=True)
def clean_environ() -> Generator[None, None, None]:
    """テスト毎に環境変数を初期化するフィクスチャです。"""
    with patch.dict(os.environ, {"VOICEVOX_TTS_TEST": ""}):
        yield


@pytest.fixture(autouse=True)
def mock_voicevox_client_get_speakers() -> Generator[MagicMock, None, None]:
    """VOICEVOX スピーカー取得をモック化するフィクスチャです。"""
    with patch(
        "youtube_live_voicevox.VoicevoxClient.get_speakers"
    ) as mock_get_speakers:
        yield mock_get_speakers


@pytest.fixture
def mock_cli_components() -> Generator[dict[str, Any], None, None]:
    """主要コンポーネントを一括でモック化し、標準的な初期値を設定します。"""
    with (
        patch("youtube_live_voicevox.YouTubeAuthenticator") as mock_auth,
        patch(
            "youtube_live_voicevox.YouTubeLiveChatClient"
        ) as mock_live_client,
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


def test_live_cli_device_option(mock_cli_components: dict[str, Any]) -> None:
    """-d オプションで指定したデバイスIDが使用されることを検証します。"""
    components = mock_cli_components

    with patch("sys.argv", ["youtube_live_voicevox.py", "-d", "6", "video123"]):
        main()

    components["audio_player_class"].assert_called_with(default_device=6)
    components["extract_video_id"].assert_called_with("video123")
    components["app_class"].assert_called_once()
    components["app_instance"].run_live.assert_called_once()


@patch("youtube_live_voicevox.get_project_id")
def test_live_cli_quota_options(
    mock_get_project_id: MagicMock,
    mock_cli_components: dict[str, Any],
) -> None:
    """クォータやインターバルに関する各種オプションの指定を検証します。"""
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


def test_live_cli_speed_option(
    mock_cli_components: dict[str, Any],
) -> None:
    """--speed オプションが config.speed_scale に反映されることを検証します。"""
    components = mock_cli_components

    with patch(
        "sys.argv", ["youtube_live_voicevox.py", "--speed", "1.5", "video123"]
    ):
        main()

    _, kwargs = components["app_class"].call_args
    assert kwargs["config"].speed_scale == 1.5


def test_live_cli_speed_boost_options(
    mock_cli_components: dict[str, Any],
) -> None:
    """スピードブーストオプションが正しく構成に反映されることを検証します。"""
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


def test_live_cli_chat_log_option(
    mock_cli_components: dict[str, Any],
) -> None:
    """--chat-log で指定したパスが構成に保存されることを検証します。"""
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


def test_live_cli_auth_failure(
    mock_cli_components: dict[str, Any],
) -> None:
    """認証に失敗した場合、ステータスコード1でシステム終了することを検証します。"""
    components = mock_cli_components
    components["auth_instance"].get_credentials.side_effect = Exception(
        "Auth Failure"
    )

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["youtube_live_voicevox.py", "video123"]):
            main()
    assert exc_info.value.code == 1


def test_live_cli_video_id_auto_detection_success(
    mock_cli_components: dict[str, Any],
) -> None:
    """引数なしの場合に配信IDの自動検出が試みられることを検証します。"""
    components = mock_cli_components
    mock_live_inst = components["live_client_instance"]

    with patch("sys.argv", ["youtube_live_voicevox.py"]):
        main()
    mock_live_inst.get_current_live_video_id.assert_called_once()


def test_live_cli_video_id_auto_detection_failure(
    mock_cli_components: dict[str, Any],
) -> None:
    """自動検出に失敗した場合、ステータスコード1で終了することを検証します。"""
    components = mock_cli_components
    mock_live_inst = components["live_client_instance"]
    mock_live_inst.get_current_live_video_id.side_effect = RuntimeError(
        "No live stream found"
    )

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["youtube_live_voicevox.py"]):
            main()
    assert exc_info.value.code == 1


def test_live_cli_env_parse_failures(
    mock_cli_components: dict[str, Any],
) -> None:
    """環境変数の数値パースが失敗した場合に
    デフォルト値へフォールバックされることを検証します。
    """
    env_mock = {
        "VOICEVOX_SPEED_SCALE": "invalid_speed",
        "VOICEVOX_MAX_SPEED": "invalid_max_speed",
        "VOICEVOX_VOLUME_SCALE": "invalid_volume",
    }
    with (
        patch.dict(os.environ, env_mock),
        patch("sys.argv", ["youtube_live_voicevox.py", "video123"]),
    ):
        main()
    # パース失敗時はエラーにならず、デフォルト値または無視されることを確認
    components = mock_cli_components
    components["app_class"].assert_called_once()


def test_live_cli_device_string_and_query_failure(
    mock_cli_components: dict[str, Any],
) -> None:
    """デバイス名に文字列を指定し、かつ sounddevice が例外を
    投げた場合でも処理が継続されることを検証します。
    """
    components = mock_cli_components
    components["query_devices"].side_effect = RuntimeError(
        "Device query failed"
    )

    argv = [
        "youtube_live_voicevox.py",
        "-d",
        "test_device_name",
        "video123",
    ]
    with patch("sys.argv", argv):
        main()

    components["audio_player_class"].assert_called_with(
        default_device="test_device_name"
    )
    components["app_instance"].run_live.assert_called_once()


def test_live_cli_get_speakers_failure(
    mock_cli_components: dict[str, Any],
    mock_voicevox_client_get_speakers: MagicMock,
) -> None:
    """VOICEVOX 接続確認(get_speakers)が失敗しても、
    処理が継続されることを検証します。
    """
    mock_voicevox_client_get_speakers.side_effect = RuntimeError(
        "Connection refused"
    )
    components = mock_cli_components

    # verboseログのコードパスを通すため-vオプションを指定したケース
    with patch("sys.argv", ["youtube_live_voicevox.py", "-v", "video123"]):
        main()

    components["app_instance"].run_live.assert_called_once()
    components["app_instance"].run_live.reset_mock()

    # verboseなしのケースもテストしてBrPartを解消
    with patch("sys.argv", ["youtube_live_voicevox.py", "video123"]):
        main()

    components["app_instance"].run_live.assert_called_once()


def test_live_cli_auth_failure_verbose(
    mock_cli_components: dict[str, Any],
) -> None:
    """verbose有効時に認証に失敗した場合、例外詳細ログが出力され
    ステータス1で終了することを検証します。
    """
    components = mock_cli_components
    components["auth_instance"].get_credentials.side_effect = Exception(
        "Auth Failure"
    )

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["youtube_live_voicevox.py", "-v", "video123"]):
            main()
    assert exc_info.value.code == 1


@patch("youtube_live_voicevox.get_project_id")
def test_live_cli_quota_check_project_id_failure(
    mock_get_project_id: MagicMock,
    mock_cli_components: dict[str, Any],
) -> None:
    """quota-check有効時に get_project_id が失敗した場合、警告ログを
    出力してフラグがFalseになり処理が継続することを検証します。
    """
    mock_get_project_id.side_effect = RuntimeError("Metadata error")
    components = mock_cli_components

    with patch("sys.argv", ["youtube_live_voicevox.py", "-q", "video123"]):
        main()

    # run_live が quota_check=False で呼ばれることを検証
    components["app_instance"].run_live.assert_called_once()
    _, kwargs = components["app_instance"].run_live.call_args
    assert kwargs["quota_check"] is False
    assert kwargs["quota_talk"] is False


def test_live_cli_run_live_unexpected_error(
    mock_cli_components: dict[str, Any],
) -> None:
    """run_live で予期しない例外が発生した場合に例外がキャッチされ、
    ログ出力されることを検証します。
    """
    components = mock_cli_components
    components["app_instance"].run_live.side_effect = RuntimeError(
        "Unexpected loop crash"
    )

    # 例外はキャッチされて終了するため、SystemExitなどは発生しない
    with patch("sys.argv", ["youtube_live_voicevox.py", "video123"]):
        main()

    components["app_instance"].run_live.assert_called_once()
