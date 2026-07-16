"""AudioPlayer の再生処理を検証するテストモジュールです。"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts import AudioPlayer


@pytest.mark.parametrize(
    "cmd_name, device, use_tempfile, expected_opt",
    [
        ("pacat", "my_device", False, "-d"),
        ("pacat", None, False, None),
        ("pw-play", "my_device", True, "--target"),
        ("pw-play", None, True, None),
        ("aplay", "my_device", False, "-D"),
        ("aplay", None, False, None),
        ("paplay", "my_device", True, "-d"),
        ("paplay", None, True, None),
    ],
)
def test_play_wav_commands(
    monkeypatch: pytest.MonkeyPatch,
    cmd_name: str,
    device: str | None,
    use_tempfile: bool,
    expected_opt: str | None,
) -> None:
    """各再生コマンドによる再生処理を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: f"/usr/bin/{cmd_name}" if cmd == cmd_name else None,
    )

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    unlinked_paths = []
    if use_tempfile:
        original_unlink = os.unlink

        def mock_unlink(path: str) -> None:
            unlinked_paths.append(path)
            original_unlink(path)

        monkeypatch.setattr(os, "unlink", mock_unlink)

    player = AudioPlayer()
    player.play_wav(b"dummy_wav_data", device=device)

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert cmd_name in cmd

    if expected_opt:
        assert expected_opt in cmd
        assert device in cmd

    if use_tempfile:
        temp_path = cmd[1]
        assert temp_path.endswith(".wav")
        assert os.path.exists(temp_path) is False
        assert temp_path in unlinked_paths
        assert mock_popen.call_args[1].get("stdin") is None
        mock_process.wait.assert_called_once()
    else:
        assert mock_popen.call_args[1].get("stdin") == subprocess.PIPE
        mock_process.communicate.assert_called_once_with(
            input=b"dummy_wav_data"
        )


def test_play_wav_tempfile_unlink_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一時ファイル削除例外時のログ出力を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pw-play" if cmd == "pw-play" else None,
    )

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    def mock_unlink(path: str) -> None:
        raise OSError("Unlink failed")

    monkeypatch.setattr(os, "unlink", mock_unlink)

    player = AudioPlayer()
    with patch("youtube_tts.audio.logger.debug") as mock_debug:
        player.play_wav(b"dummy_wav_data")

        called_args = [call[0][0] for call in mock_debug.call_args_list]
        assert any(
            "一時ファイルの削除に失敗しました" in arg for arg in called_args
        )


def test_play_wav_no_commands_raise_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """利用可能なコマンドがない場合に例外が発生することを検証します。"""
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    player = AudioPlayer()
    with pytest.raises(RuntimeError) as exc_info:
        player.play_wav(b"dummy_wav_data")
    assert "利用可能な再生コマンド" in str(exc_info.value)


def test_play_wav_kills_existing_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """再生中に新しい再生要求があった際、古いプロセスを終了させることを検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/aplay" if cmd == "aplay" else None,
    )

    mock_old_process = MagicMock()
    mock_old_process.poll.return_value = None

    mock_new_process = MagicMock()

    processes = [mock_old_process, mock_new_process]

    def mock_popen(*args: Any, **kwargs: Any) -> MagicMock:
        return processes.pop(0)

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()
    player.play_wav(b"first")
    player.play_wav(b"second")

    mock_old_process.kill.assert_called_once()
    mock_old_process.wait.assert_called_once()


def test_play_wav_kills_existing_process_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """古い再生プロセスの強制終了中に例外が発生した場合を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/aplay" if cmd == "aplay" else None,
    )

    mock_old_process = MagicMock()
    mock_old_process.poll.return_value = None
    mock_old_process.kill.side_effect = Exception("kill failed")

    mock_new_process = MagicMock()

    processes = [mock_old_process, mock_new_process]

    def mock_popen(*args: Any, **kwargs: Any) -> MagicMock:
        return processes.pop(0)

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()
    player.play_wav(b"first")
    player.play_wav(b"second")

    mock_old_process.kill.assert_called_once()


def test_play_wav_interrupt_and_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """中断が発生した際の停止処理を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/aplay" if cmd == "aplay" else None,
    )

    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_process.communicate.side_effect = KeyboardInterrupt()

    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: mock_process
    )

    player = AudioPlayer()
    with pytest.raises(KeyboardInterrupt):
        player.play_wav(b"dummy")

    mock_process.terminate.assert_called_once()
