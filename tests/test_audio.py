"""AudioPlayer クラスの単体テストを行うモジュールです。"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts import AudioPlayer


def test_audio_initialization_pactl_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pactl が存在する正常な初期化を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None,
    )

    mock_res = MagicMock()
    mock_res.stdout = (
        "Default Sink: alsa_output.pci\n"
        "Default Sample Specification: s16le 2ch 48000Hz\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    assert player.target_sample_rate == 48000


def test_audio_initialization_pactl_failure_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pactl エラー時のフォールバックを検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None,
    )

    def mock_run(*args: Any, **kwargs: Any) -> None:
        raise subprocess.SubprocessError("pactl failed")

    monkeypatch.setattr(subprocess, "run", mock_run)

    player = AudioPlayer()
    assert player.target_sample_rate == 24000


def test_query_devices_pactl_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pactl が存在する場合のデバイス一覧取得を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None,
    )

    mock_res = MagicMock()
    mock_res.stdout = (
        "0\talsa_output.pci-0000_00_1f.3.analog-stereo\n"
        "1\talsa_output.pci-0000_00_1f.3.hdmi-stereo\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    res = player.query_devices()
    assert "利用可能なオーディオ出力デバイス (pactl):" in res
    assert "ID: 0 -> alsa_output.pci-0000_00_1f.3.analog-stereo" in res


def test_query_devices_aplay_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aplay が存在する場合のデバイス一覧取得を検証します。"""

    def mock_which(cmd: str) -> str | None:
        if cmd == "aplay":
            return "/usr/bin/aplay"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    mock_res = MagicMock()
    mock_res.stdout = (
        "null\n    Discard all samples\ndefault\n    Default ALSA Output\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    res = player.query_devices()
    assert "利用可能なオーディオ出力デバイス (aplay):" in res
    assert "default" in res
    # インデント行は除外されることを検証します。
    assert "Discard" not in res


def test_query_devices_pactl_failure_fallback_aplay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pactl が失敗したときに aplay へフォールバックすることを検証します。"""

    def mock_which(cmd: str) -> str | None:
        if cmd in ("pactl", "aplay"):
            return f"/usr/bin/{cmd}"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    def mock_run(cmd: list[str], *args: Any, **kwargs: Any) -> MagicMock:
        if cmd[0] == "pactl":
            raise subprocess.SubprocessError("pactl failed")
        mock_res = MagicMock()
        mock_res.stdout = "default\n"
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)

    player = AudioPlayer()
    res = player.query_devices()
    assert "利用可能なオーディオ出力デバイス (aplay):" in res
    assert "default" in res


def test_query_devices_no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pactl も aplay も存在しない場合の動作を検証します。"""
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    player = AudioPlayer()
    res = player.query_devices()
    assert "見つかりませんでした" in res


def test_play_wav_pacat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pacat を使用した再生処理を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pacat" if cmd == "pacat" else None,
    )

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()
    player.play_wav(b"dummy_wav_data", device="my_device")

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "pacat" in cmd
    assert "-d" in cmd
    assert "my_device" in cmd
    assert mock_popen.call_args[1].get("stdin") == subprocess.PIPE
    mock_process.communicate.assert_called_once_with(input=b"dummy_wav_data")


def test_play_wav_pacat_no_device(monkeypatch: pytest.MonkeyPatch) -> None:
    """引数 device が指定されない場合の pacat での再生を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pacat" if cmd == "pacat" else None,
    )

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()
    player.play_wav(b"dummy")

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "pacat" in cmd
    assert "-d" not in cmd
    assert mock_popen.call_args[1].get("stdin") == subprocess.PIPE
    mock_process.communicate.assert_called_once_with(input=b"dummy")


def test_play_wav_pw_play(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pw-play を使用した再生処理（一時ファイル経由）を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pw-play" if cmd == "pw-play" else None,
    )

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # os.unlink をスパイしてパスを記録します。
    unlinked_paths = []
    original_unlink = os.unlink

    def mock_unlink(path: str) -> None:
        unlinked_paths.append(path)
        original_unlink(path)

    monkeypatch.setattr(os, "unlink", mock_unlink)

    player = AudioPlayer()
    player.play_wav(b"dummy_wav_data", device="my_device")

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "pw-play" in cmd
    assert "--target" in cmd
    assert "my_device" in cmd

    temp_path = cmd[1]
    assert temp_path.endswith(".wav")
    # 既に削除されていることを検証します。
    assert os.path.exists(temp_path) is False
    assert temp_path in unlinked_paths
    assert mock_popen.call_args[1].get("stdin") is None
    mock_process.wait.assert_called_once()
    mock_process.communicate.assert_not_called()


def test_play_wav_aplay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aplay を使用した再生処理を検証します。"""

    def mock_which(cmd: str) -> str | None:
        if cmd == "aplay":
            return "/usr/bin/aplay"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()
    player.play_wav(b"dummy_wav_data", device="my_device")

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "aplay" in cmd
    assert "-D" in cmd
    assert "my_device" in cmd
    assert mock_popen.call_args[1].get("stdin") == subprocess.PIPE
    mock_process.communicate.assert_called_once_with(input=b"dummy_wav_data")


def test_play_wav_paplay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Paplay を使用した再生処理（一時ファイル経由）を検証します。"""

    def mock_which(cmd: str) -> str | None:
        if cmd == "paplay":
            return "/usr/bin/paplay"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # os.unlink をスパイします。
    unlinked_paths = []
    original_unlink = os.unlink

    def mock_unlink(path: str) -> None:
        unlinked_paths.append(path)
        original_unlink(path)

    monkeypatch.setattr(os, "unlink", mock_unlink)

    player = AudioPlayer()
    player.play_wav(b"dummy_wav_data", device="my_device")

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "paplay" in cmd
    assert "-d" in cmd
    assert "my_device" in cmd

    temp_path = cmd[1]
    assert temp_path.endswith(".wav")
    assert os.path.exists(temp_path) is False
    assert temp_path in unlinked_paths
    assert mock_popen.call_args[1].get("stdin") is None
    mock_process.wait.assert_called_once()
    mock_process.communicate.assert_not_called()


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

    # os.unlink で例外を発生させます。
    def mock_unlink(path: str) -> None:
        raise OSError("Unlink failed")

    monkeypatch.setattr(os, "unlink", mock_unlink)

    player = AudioPlayer()
    with patch("youtube_tts.audio.logger.debug") as mock_debug:
        player.play_wav(b"dummy_wav_data")

        # ログメッセージが含まれているか確認します。
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
    mock_old_process.poll.return_value = None  # 動作中の状態です。

    mock_new_process = MagicMock()

    processes = [mock_old_process, mock_new_process]

    def mock_popen(*args: Any, **kwargs: Any) -> MagicMock:
        return processes.pop(0)

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()
    # 最初の再生を行います。
    player.play_wav(b"first")
    # 2回目の再生を行います。
    player.play_wav(b"second")

    mock_old_process.kill.assert_called_once()
    mock_old_process.wait.assert_called_once()


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


def test_stop_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常なプロセスの停止処理を検証します。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # 動作中の状態です。

    player.process = mock_process
    player.stop()

    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_called_once()


def test_stop_timeout_and_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terminate 処理がタイムアウトしたときに kill を試みることを検証します。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(["cmd"], 1),
        None,
    ]

    player.process = mock_process
    player.stop()

    mock_process.terminate.assert_called_once()
    mock_process.kill.assert_called_once()


def test_stop_exception_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """停止時の例外警告ログ出力を検証します。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_process.terminate.side_effect = Exception("failed to terminate")

    player.process = mock_process

    with patch("youtube_tts.audio.logger.warning") as mock_warning:
        player.stop()
        mock_warning.assert_called_once()
        assert (
            "外部再生プロセスの停止中にエラーが発生しました"
            in mock_warning.call_args[0][0]
        )


def test_audio_initialization_pactl_no_hz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pactl info に Hz の表記がない場合の動作を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None,
    )

    mock_res = MagicMock()
    mock_res.stdout = "Default Sample Specification: s16le 2ch 48000\n"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    assert player.target_sample_rate == 24000


def test_query_devices_pactl_invalid_tab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pactl の出力に無効行がある場合を検証します。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None,
    )

    mock_res = MagicMock()
    mock_res.stdout = "invalidline_without_tab\n"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    res = player.query_devices()
    # 無効行はスキップされ、ヘッダーのみが返ります。
    assert "利用可能なオーディオ出力デバイス (pactl):" in res
    assert "invalidline" not in res


def test_play_wav_aplay_no_device(monkeypatch: pytest.MonkeyPatch) -> None:
    """引数 device が指定されない場合の aplay での再生を検証します。"""

    def mock_which(cmd: str) -> str | None:
        return "/usr/bin/aplay" if cmd == "aplay" else None

    monkeypatch.setattr(shutil, "which", mock_which)

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # default_device が None の状態です。
    player = AudioPlayer()
    player.play_wav(b"dummy")

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "aplay" in cmd
    # デバイス指定オプションがないことを検証します。
    assert "-D" not in cmd


def test_play_wav_paplay_no_device(monkeypatch: pytest.MonkeyPatch) -> None:
    """引数 device が指定されない場合の paplay での再生を検証します。"""

    def mock_which(cmd: str) -> str | None:
        return "/usr/bin/paplay" if cmd == "paplay" else None

    monkeypatch.setattr(shutil, "which", mock_which)

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()
    player.play_wav(b"dummy")

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "paplay" in cmd
    assert "-d" not in cmd


def test_stop_no_process() -> None:
    """再生プロセスが存在しない状態での stop メソッド呼び出しを検証します。"""
    player = AudioPlayer()
    player.process = None
    # 例外等が発生せず正常に動作することを確認します。
    player.stop()


def test_stop_already_terminated() -> None:
    """プロセス終了後の停止処理を検証します。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    # 既に終了した状態です。
    mock_process.poll.return_value = 0

    player.process = mock_process
    player.stop()
    # terminate が呼ばれないことを検証します。
    mock_process.terminate.assert_not_called()


def test_query_devices_aplay_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aplay 実行時に例外が発生した場合の動作を検証します。"""

    def mock_which(cmd: str) -> str | None:
        return "/usr/bin/aplay" if cmd == "aplay" else None

    monkeypatch.setattr(shutil, "which", mock_which)

    def mock_run(*args: Any, **kwargs: Any) -> None:
        raise subprocess.SubprocessError("aplay failed")

    monkeypatch.setattr(subprocess, "run", mock_run)

    player = AudioPlayer()
    res = player.query_devices()
    assert "利用可能なオーディオデバイス検出コマンド" in res


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
