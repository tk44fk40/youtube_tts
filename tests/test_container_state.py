"""VOICEVOX コンテナの状態・PID管理のテストモジュールです。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from youtube_tts.container_state import VoicevoxContainerStateManager


def test_state_manager_init(tmp_path: Path) -> None:
    """VoicevoxContainerStateManager の初期化をテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerStateManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )
    assert manager.lock_file_path == lock_file
    assert manager.state_file_path == state_file


def test_process_register_unregister(tmp_path: Path) -> None:
    """PID の登録と解除をテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerStateManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )

    count = manager.register_process()
    assert count == 1

    with open(state_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert os.getpid() in data["pids"]

    # 重複登録
    count_dup = manager.register_process()
    assert count_dup == 1

    remaining = manager.unregister_process()
    assert remaining == 0


def test_stale_pid_cleanup(tmp_path: Path) -> None:
    """死滅した PID が自動消去されるかテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerStateManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )

    dead_pid = 999999
    manager.write_active_pids([os.getpid(), dead_pid])

    active = manager.read_active_pids()
    assert dead_pid not in active
    assert os.getpid() in active


def test_read_active_pids_corrupted_json(tmp_path: Path) -> None:
    """破損した状態ファイルのハンドリングをテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerStateManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )

    state_file.write_text("invalid json")
    pids = manager.read_active_pids()
    assert pids == []


def test_is_process_alive_invalid_pid() -> None:
    """無効な PID に対する is_process_alive のテストを行います。"""
    assert VoicevoxContainerStateManager.is_process_alive(0) is False
    assert VoicevoxContainerStateManager.is_process_alive(-1) is False


def test_is_process_alive_exception() -> None:
    """OSError 発生時の is_process_alive の動作をテストします。"""
    with patch("os.kill", side_effect=OSError("No such process")):
        assert VoicevoxContainerStateManager.is_process_alive(12345) is False
