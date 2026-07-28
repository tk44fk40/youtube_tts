"""youtube_live_voicevox.py の例外ハンドリングおよびエラー処理のテストです。"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_live_voicevox import main


@pytest.fixture(autouse=True)
def clean_environ() -> Generator[None, None, None]:
    """テスト毎に環境変数をクリアするフィクスチャです。"""
    env_keys = [
        "VOICEVOX_TTS_TEST",
        "VOICEVOX_AUTO_SPEED_BOOST",
        "VOICEVOX_SPEED_SCALE",
        "VOICEVOX_MAX_SPEED",
        "VOICEVOX_VOLUME_SCALE",
    ]
    with patch.dict(os.environ):
        for key in env_keys:
            os.environ.pop(key, None)
        yield


@pytest.fixture(autouse=True)
def mock_voicevox_client_get_speakers() -> Generator[MagicMock, None, None]:
    """VOICEVOX スピーカー取得をモック化するフィクスチャです。"""
    with patch(
        "youtube_tts.cli.context.VoicevoxClient.get_speakers"
    ) as mock_get_speakers:
        yield mock_get_speakers


@pytest.fixture
def mock_cli_components() -> Generator[dict[str, Any], None, None]:
    """主要コンポーネントを一括でモック化し、標準的な初期値を設定します。"""
    with (
        patch("youtube_tts.cli.context.YouTubeAuthenticator") as mock_auth,
        patch(
            "youtube_live_voicevox.YouTubeLiveChatClient"
        ) as mock_live_client,
        patch("youtube_tts.cli.context.YouTubeTtsApp") as mock_app_class,
        patch("youtube_tts.cli.context.AudioPlayer") as mock_audio_player_class,
        patch("sounddevice.query_devices") as mock_query,
        patch("youtube_live_voicevox.extract_video_id") as mock_extract,
        patch("youtube_live_voicevox.LiveRunner") as mock_runner_class,
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

        mock_runner_instance = MagicMock()
        mock_runner_class.return_value = mock_runner_instance

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
            "runner_class": mock_runner_class,
            "runner_instance": mock_runner_instance,
        }


@pytest.mark.parametrize(
    "verbose, argv_extra",
    [
        (False, []),
        (True, ["-v"]),
    ],
)
def test_live_cli_auth_failure(
    mock_cli_components: dict[str, Any],
    verbose: bool,
    argv_extra: list[str],
) -> None:
    """認証に失敗した場合、ステータスコード1で終了することを検証します。"""
    components = mock_cli_components
    components["auth_instance"].get_credentials.side_effect = Exception(
        "Auth Failure"
    )

    argv = ["youtube_live_voicevox.py"] + argv_extra + ["video123"]
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", argv):
            main()
    assert exc_info.value.code == 1


def test_live_cli_env_parse_failures(
    mock_cli_components: dict[str, Any],
) -> None:
    """環境変数の数値パース失敗時のデフォルトへの倒しを検証します。"""
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
    components = mock_cli_components
    components["app_class"].assert_called_once()


def test_live_cli_device_string_and_query_failure(
    mock_cli_components: dict[str, Any],
) -> None:
    """デバイス名指定かつ sounddevice 例外時の処理継続を検証します。"""
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
    components["runner_instance"].run.assert_called_once()


def test_live_cli_get_speakers_failure(
    mock_cli_components: dict[str, Any],
    mock_voicevox_client_get_speakers: MagicMock,
) -> None:
    """VOICEVOX 接続確認失敗時の処理継続を検証します。"""
    mock_voicevox_client_get_speakers.side_effect = RuntimeError(
        "Connection refused"
    )
    components = mock_cli_components

    with patch("sys.argv", ["youtube_live_voicevox.py", "-v", "video123"]):
        main()

    components["runner_instance"].run.assert_called_once()
    components["runner_instance"].run.reset_mock()

    with patch("sys.argv", ["youtube_live_voicevox.py", "video123"]):
        main()

    components["runner_instance"].run.assert_called_once()


@patch("youtube_tts.cli.context.get_project_id")
def test_live_cli_quota_check_project_id_failure(
    mock_get_project_id: MagicMock,
    mock_cli_components: dict[str, Any],
) -> None:
    """quota-checkで get_project_id 失敗時の処理継続を検証します。"""
    mock_get_project_id.side_effect = RuntimeError("Metadata error")
    components = mock_cli_components

    with patch("sys.argv", ["youtube_live_voicevox.py", "-q", "video123"]):
        main()

    components["runner_instance"].run.assert_called_once()
    _, kwargs = components["runner_class"].call_args
    assert kwargs["quota_check"] is False
    assert kwargs["quota_talk"] is False


def test_live_cli_run_live_unexpected_error(
    mock_cli_components: dict[str, Any],
) -> None:
    """Run で予期しない例外発生時のキャッチとログ出力を検証します。"""
    components = mock_cli_components
    components["runner_instance"].run.side_effect = RuntimeError(
        "Unexpected loop crash"
    )

    with patch("sys.argv", ["youtube_live_voicevox.py", "video123"]):
        main()

    components["runner_instance"].run.assert_called_once()


def test_live_cli_keyboard_interrupt_during_context(
    mock_cli_components: dict[str, Any],
) -> None:
    """コンテキスト生成中に KeyboardInterrupt が発生した場合の終了検証です。"""
    components = mock_cli_components
    components[
        "auth_instance"
    ].get_credentials.side_effect = KeyboardInterrupt()

    with patch("sys.exit", side_effect=SystemExit(130)) as mock_exit:
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["youtube_live_voicevox.py", "video123"]):
                main()
        assert exc_info.value.code == 130
        mock_exit.assert_called_once_with(130)


def test_live_cli_keyboard_interrupt_during_live_id(
    mock_cli_components: dict[str, Any],
) -> None:
    """ライブID取得中に KeyboardInterrupt が発生した場合の終了検証です。"""
    components = mock_cli_components
    components[
        "live_client_instance"
    ].get_current_live_video_id.side_effect = KeyboardInterrupt()

    with patch("sys.exit", side_effect=SystemExit(130)) as mock_exit:
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["youtube_live_voicevox.py"]):
                main()
        assert exc_info.value.code == 130
        mock_exit.assert_called_once_with(130)


def test_live_cli_keyboard_interrupt_during_run(
    mock_cli_components: dict[str, Any],
) -> None:
    """runner.run中に KeyboardInterrupt が発生した場合の終了検証です。"""
    components = mock_cli_components
    components["runner_instance"].run.side_effect = KeyboardInterrupt()

    with patch("sys.argv", ["youtube_live_voicevox.py", "video123"]):
        main()

    components["runner_instance"].run.assert_called_once()
    components["app_instance"].logger.info.assert_any_call(
        "ユーザーによって処理が中断されました。"
    )


def test_invalid_speaker_id_env_in_parser() -> None:
    """パーサーの ENV_VOICEVOX_SPEAKER_ID 不正値例外処理を検証します。"""
    from youtube_tts.cli.parser import create_live_parser

    with patch.dict(os.environ, {"VOICEVOX_SPEAKER_ID": "invalid"}):
        parser = create_live_parser()
        args = parser.parse_args([])
        assert args.speaker_id == 3


def test_invalid_speaker_id_env_in_context(
    mock_cli_components: dict[str, Any],
) -> None:
    """コンテキストの ENV_VOICEVOX_SPEAKER_ID 不正値例外処理を検証します。"""
    from youtube_tts.cli.context import create_app_context
    from youtube_tts.cli.parser import create_live_parser

    with patch.dict(os.environ, {"VOICEVOX_SPEAKER_ID": "invalid"}):
        with patch("youtube_tts.cli.context.VoicevoxClient") as mock_vclient:
            parser = create_live_parser()
            args = parser.parse_args([])
            delattr(args, "speaker_id")
            create_app_context(args)
            mock_vclient.assert_called_once()
            _, kwargs = mock_vclient.call_args
            assert kwargs.get("speaker_id") == 3
