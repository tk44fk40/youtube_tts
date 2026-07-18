"""voicevox_test.py のテストを行うモジュールです。"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from voicevox_test import list_speakers, main


def test_list_speakers_success() -> None:
    """スピーカー一覧の取得および表示が正常に動作することを検証します。"""
    mock_client = MagicMock()
    mock_client.get_speakers.return_value = [
        {
            "name": "話者A",
            "styles": [
                {"id": 1, "name": "ノーマル"},
                {"id": 2, "name": "あま甘"},
            ],
        }
    ]
    with patch("builtins.print") as mock_print:
        list_speakers(mock_client)
        mock_print.assert_any_call(
            f"{'ID':<6} | {'話者名':<15} | {'スタイル':<15}"
        )


def test_list_speakers_failure() -> None:
    """スピーカー取得失敗時にプログラムが終了することを検証します。"""
    mock_client = MagicMock()
    mock_client.get_speakers.side_effect = Exception("API error")
    with pytest.raises(SystemExit) as exc_info:
        list_speakers(mock_client)
    assert exc_info.value.code == 1


@pytest.mark.parametrize(
    "env_speed, argv, expected_speed, list_speakers_called, "
    "list_devices_called, no_play, synth_fail, save_fail, play_fail",
    [
        (None, [], 1.0, False, False, False, False, False, False),
        ("1.5", [], 1.5, False, False, False, False, False, False),
        ("invalid", [], 1.0, False, False, False, False, False, False),
        (
            None,
            ["--list-speakers"],
            1.0,
            True,
            False,
            False,
            False,
            False,
            False,
        ),
        (
            None,
            ["--list-devices"],
            1.0,
            False,
            True,
            False,
            False,
            False,
            False,
        ),
        (None, ["--no-play"], 1.0, False, False, True, False, False, False),
        (None, [], 1.0, False, False, False, True, False, False),
        (None, [], 1.0, False, False, False, False, True, False),
        (None, [], 1.0, False, False, False, False, False, True),
    ],
)
@patch("voicevox_test.AudioPlayer")
@patch("voicevox_test.VoicevoxClient")
@patch("voicevox_test.list_speakers")
def test_voicevox_test_main(
    mock_list_speakers: MagicMock,
    mock_client_class: MagicMock,
    mock_player_class: MagicMock,
    env_speed: str | None,
    argv: list[str],
    expected_speed: float,
    list_speakers_called: bool,
    list_devices_called: bool,
    no_play: bool,
    synth_fail: bool,
    save_fail: bool,
    play_fail: bool,
) -> None:
    """main 関数の様々なパラメータや動作条件を検証します。"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.synthesize.return_value = b"wav_data"

    mock_player = MagicMock()
    mock_player_class.return_value = mock_player
    mock_player.target_sample_rate = 24000
    mock_player.query_devices.return_value = "Mock Devices"

    if synth_fail:
        mock_client.synthesize.side_effect = Exception("Synth error")
    if play_fail:
        mock_player.play_wav.side_effect = Exception("Play error")

    env_vars = {}
    if env_speed is not None:
        env_vars["VOICEVOX_SPEED_SCALE"] = env_speed

    sys_argv = ["voicevox_test.py"] + argv

    open_mock = mock_open()
    if save_fail:
        open_mock.side_effect = IOError("Save error")

    with (
        patch.dict(os.environ, env_vars),
        patch("sys.argv", sys_argv),
        patch("builtins.open", open_mock),
        patch("builtins.print") as mock_print,
    ):
        if synth_fail:
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
            return

        main()

        if list_speakers_called:
            mock_list_speakers.assert_called_once()
        elif list_devices_called:
            mock_player.query_devices.assert_called_once()
            mock_print.assert_any_call("Mock Devices")
        else:
            mock_client.synthesize.assert_called_once_with(
                text="これは、ボイスボックスの発声テストです。",
                volume_scale=1.0,
                speed_scale=expected_speed,
                target_sample_rate=None if no_play else 24000,
            )
            if not save_fail:
                open_mock().write.assert_called_once_with(b"wav_data")

            if not no_play:
                mock_player.play_wav.assert_called_once()


@patch("voicevox_test.AudioPlayer")
def test_voicevox_test_main_list_devices_player_none(
    mock_player_class: MagicMock,
) -> None:
    """--list-devices 指定時に player が None の場合を検証します。"""
    mock_player_class.return_value = None
    with (
        patch("sys.argv", ["voicevox_test.py", "--list-devices"]),
        patch("builtins.print") as mock_print,
    ):
        main()
        mock_print.assert_not_called()

