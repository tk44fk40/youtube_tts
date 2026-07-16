"""AudioPlayer の初期化とデバイス検出処理を検証するテストモジュールです。"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any
from unittest.mock import MagicMock

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
    assert "利用可能なオーディオ出力デバイス (pactl):" in res
    assert "invalidline" not in res


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
