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
"""AudioPlayer クラスの単体テストを行うモジュール。"""

import os
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts import AudioPlayer


def test_audio_initialization_pactl_success(monkeypatch):
    """pactl が存在しデフォルトレートが正常取得できる場合の初期化テスト。"""
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None
    )

    mock_res = MagicMock()
    mock_res.stdout = (
        "Default Sink: alsa_output.pci\n"
        "Default Sample Specification: s16le 2ch 48000Hz\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    assert player.target_sample_rate == 48000


def test_audio_initialization_pactl_failure_fallback(monkeypatch):
    """pactl がエラーを返した場合に既定のレートにフォールバックするテスト。"""
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None
    )

    def mock_run(*args, **kwargs):
        raise subprocess.SubprocessError("pactl failed")

    monkeypatch.setattr(subprocess, "run", mock_run)

    player = AudioPlayer()
    assert player.target_sample_rate == 24000


def test_query_devices_pactl_success(monkeypatch):
    """pactl が存在する場合のデバイス一覧取得テスト。"""
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None
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


def test_query_devices_aplay_success(monkeypatch):
    """pactl がなく aplay が存在する場合のデバイス一覧取得テスト。"""

    def mock_which(cmd):
        if cmd == "aplay":
            return "/usr/bin/aplay"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    mock_res = MagicMock()
    mock_res.stdout = (
        "null\n"
        "    Discard all samples\n"
        "default\n"
        "    Default ALSA Output\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    res = player.query_devices()
    assert "利用可能なオーディオ出力デバイス (aplay):" in res
    assert "default" in res
    assert "Discard" not in res  # インデント行は除外されること


def test_query_devices_pactl_failure_fallback_aplay(monkeypatch):
    """pactl が失敗したときに aplay へフォールバックするテスト。"""

    def mock_which(cmd):
        if cmd in ("pactl", "aplay"):
            return f"/usr/bin/{cmd}"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    def mock_run(cmd, *args, **kwargs):
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


def test_query_devices_no_tools(monkeypatch):
    """pactl も aplay も存在しない場合のテスト。"""
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    player = AudioPlayer()
    res = player.query_devices()
    assert "見つかりませんでした" in res


def test_play_wav_pacat(monkeypatch):
    """pacat を使用した再生処理のテスト。"""
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/pacat" if cmd == "pacat" else None
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


def test_play_wav_pacat_no_device(monkeypatch):
    """deviceが指定されない（None）場合の pacat での再生テスト。"""
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/pacat" if cmd == "pacat" else None
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


def test_play_wav_pw_play(monkeypatch):
    """pw-play を使用した再生処理（一時ファイル経由）のテスト。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pw-play" if cmd == "pw-play" else None,
    )

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # os.unlink をスパイしてパスを記録する
    unlinked_paths = []
    original_unlink = os.unlink

    def mock_unlink(path):
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
    assert os.path.exists(temp_path) is False  # 既に削除されていること
    assert temp_path in unlinked_paths
    assert mock_popen.call_args[1].get("stdin") is None
    mock_process.wait.assert_called_once()
    mock_process.communicate.assert_not_called()


def test_play_wav_aplay(monkeypatch):
    """aplay を使用した再生処理のテスト。"""

    def mock_which(cmd):
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


def test_play_wav_paplay(monkeypatch):
    """paplay を使用した再生処理（一時ファイル経由）のテスト。"""

    def mock_which(cmd):
        if cmd == "paplay":
            return "/usr/bin/paplay"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # os.unlink をスパイ
    unlinked_paths = []
    original_unlink = os.unlink

    def mock_unlink(path):
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


def test_play_wav_tempfile_unlink_error(monkeypatch):
    """一時ファイル削除例外をキャッチして debug ログ出力するテスト。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/pw-play" if cmd == "pw-play" else None,
    )

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # os.unlink を例外発生させる
    def mock_unlink(path):
        raise OSError("Unlink failed")

    monkeypatch.setattr(os, "unlink", mock_unlink)

    player = AudioPlayer()
    with patch("youtube_tts.audio.logger.debug") as mock_debug:
        player.play_wav(b"dummy_wav_data")

        # ログメッセージが含まれているか確認
        called_args = [call[0][0] for call in mock_debug.call_args_list]
        assert any("一時ファイルの削除に失敗しました" in arg for arg in called_args)


def test_play_wav_no_commands_raise_error(monkeypatch):
    """利用可能なコマンドがない場合に例外が発生することのテスト。"""
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    player = AudioPlayer()
    with pytest.raises(RuntimeError) as exc_info:
        player.play_wav(b"dummy_wav_data")
    assert "利用可能な再生コマンド" in str(exc_info.value)


def test_play_wav_kills_existing_process(monkeypatch):
    """再生中に新しい再生要求があった際、古いプロセスを終了させるテスト。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/aplay" if cmd == "aplay" else None,
    )

    mock_old_process = MagicMock()
    mock_old_process.poll.return_value = None  # 動作中

    mock_new_process = MagicMock()

    processes = [mock_old_process, mock_new_process]

    def mock_popen(*args, **kwargs):
        return processes.pop(0)

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()
    # 最初の再生
    player.play_wav(b"first")
    # 2回目の再生
    player.play_wav(b"second")

    mock_old_process.kill.assert_called_once()
    mock_old_process.wait.assert_called_once()


def test_play_wav_interrupt_and_stop(monkeypatch):
    """KeyboardInterrupt が発生したときに適切に停止し、再送出するテスト。"""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: "/usr/bin/aplay" if cmd == "aplay" else None,
    )

    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_process.communicate.side_effect = KeyboardInterrupt()

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_process)

    player = AudioPlayer()
    with pytest.raises(KeyboardInterrupt):
        player.play_wav(b"dummy")

    mock_process.terminate.assert_called_once()


def test_stop_normal(monkeypatch):
    """stop() メソッドが正常に動いているプロセスを停止させるテスト。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # 動作中

    player.process = mock_process
    player.stop()

    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_called_once()


def test_stop_timeout_and_kill(monkeypatch):
    """terminate がタイムアウトしたときに kill を試みるテスト。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_process.wait.side_effect = [subprocess.TimeoutExpired(["cmd"], 1), None]

    player.process = mock_process
    player.stop()

    mock_process.terminate.assert_called_once()
    mock_process.kill.assert_called_once()


def test_stop_exception_handling(monkeypatch):
    """stop() 内で例外が発生したときにログ警告を出して例外を握りつぶさないテスト。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_process.terminate.side_effect = Exception("failed to terminate")

    player.process = mock_process

    with patch("youtube_tts.audio.logger.warning") as mock_warning:
        player.stop()
        mock_warning.assert_called_once()
        assert "外部再生プロセスの停止中にエラーが発生しました" in mock_warning.call_args[0][0]


def test_audio_initialization_pactl_no_hz(monkeypatch):
    """pactl info に Hz の表記がない場合のテスト。"""
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None
    )

    mock_res = MagicMock()
    mock_res.stdout = "Default Sample Specification: s16le 2ch 48000\n"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    assert player.target_sample_rate == 24000


def test_query_devices_pactl_invalid_tab(monkeypatch):
    """pactl list short sinks の出力にタブ文字がない行が含まれるテスト。"""
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/pactl" if cmd == "pactl" else None
    )

    mock_res = MagicMock()
    mock_res.stdout = "invalidline_without_tab\n"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    player = AudioPlayer()
    res = player.query_devices()
    # 無効行はスキップされ、ヘッダーのみが返る
    assert "利用可能なオーディオ出力デバイス (pactl):" in res
    assert "invalidline" not in res


def test_play_wav_aplay_no_device(monkeypatch):
    """deviceが指定されない（None）場合の aplay での再生テスト。"""

    def mock_which(cmd):
        return "/usr/bin/aplay" if cmd == "aplay" else None

    monkeypatch.setattr(shutil, "which", mock_which)

    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    player = AudioPlayer()  # default_device = None
    player.play_wav(b"dummy")

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "aplay" in cmd
    assert "-D" not in cmd  # デバイス指定オプションがないこと


def test_play_wav_paplay_no_device(monkeypatch):
    """deviceが指定されない（None）場合の paplay での再生テスト。"""

    def mock_which(cmd):
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


def test_stop_no_process():
    """再生プロセスが存在しない状態での stop() 呼び出しテスト。"""
    player = AudioPlayer()
    player.process = None
    player.stop()  # 例外等が発生せず正常にパスすること


def test_stop_already_terminated():
    """再生プロセスが既に終了している状態での stop() 呼び出しテスト。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = 0  # 終了済み

    player.process = mock_process
    player.stop()
    # terminate が呼ばれないこと
    mock_process.terminate.assert_not_called()

