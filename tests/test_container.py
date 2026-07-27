"""VoicevoxContainerManager の単体テストです。"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from youtube_tts.container import VoicevoxContainerManager


def test_container_manager_init(tmp_path) -> None:
    """初期化パラメータが正しくセットされるかテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerManager(
        container_name="test-voicevox",
        container_cmd="podman",
        lock_file_path=lock_file,
        state_file_path=state_file,
    )
    assert manager.container_name == "test-voicevox"
    assert manager.container_cmd == "podman"
    assert manager.base_url == "http://127.0.0.1:50021"


def test_container_manager_cmd_resolution(tmp_path) -> None:
    """環境変数および shutil.which によるコマンド判定のテストです。"""
    with patch.dict(os.environ, {"CONTAINER_CMD": "custom-cmd"}):
        manager = VoicevoxContainerManager()
        assert manager.container_cmd == "custom-cmd"

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("shutil.which", side_effect=lambda cmd: cmd == "docker"),
    ):
        manager = VoicevoxContainerManager()
        assert manager.container_cmd == "docker"

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("shutil.which", return_value=None),
    ):
        manager = VoicevoxContainerManager()
        assert manager.container_cmd == "podman"


def test_process_register_unregister(tmp_path) -> None:
    """プロセスの登録・解除およびアクティブカウントのテストです。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )

    # 未登録状態での解除テスト
    count_unreg = manager.unregister_process()
    assert count_unreg == 0

    count1 = manager.register_process()
    assert count1 == 1

    my_pid = os.getpid()
    active_pids = manager._read_active_pids()
    assert my_pid in active_pids

    count2 = manager.unregister_process()
    assert count2 == 0
    assert my_pid not in manager._read_active_pids()


def test_stale_pid_cleanup(tmp_path) -> None:
    """死滅 PID が自動クリーンアップされるかテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )

    fake_dead_pid = 999999
    manager._write_active_pids([fake_dead_pid, os.getpid()])

    active_pids = manager._read_active_pids()
    assert fake_dead_pid not in active_pids
    assert os.getpid() in active_pids


def test_read_active_pids_corrupted_json(tmp_path) -> None:
    """状態ファイル破損時のフォールバックをテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    state_file.write_text("invalid json content", encoding="utf-8")
    manager = VoicevoxContainerManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )
    assert manager._read_active_pids() == []


@patch("youtube_tts.container.subprocess.run")
def test_stop_if_last(mock_run, tmp_path) -> None:
    """最後のプロセスの時のみ停止コマンドが呼ばれるかテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )

    manager._write_active_pids([os.getpid(), 888888])

    with (
        patch.object(
            VoicevoxContainerManager,
            "is_process_alive",
            side_effect=lambda pid: True,
        ),
        patch.object(
            VoicevoxContainerManager, "is_container_running", return_value=True
        ),
    ):
        stopped = manager.stop_if_last()
        assert stopped is False
        mock_run.assert_not_called()

    manager._write_active_pids([os.getpid()])

    with (
        patch.object(
            VoicevoxContainerManager,
            "is_process_alive",
            side_effect=lambda pid: pid == os.getpid(),
        ),
        patch.object(
            VoicevoxContainerManager, "is_container_running", return_value=True
        ),
    ):
        logger = MagicMock()
        stopped = manager.stop_if_last(logger=logger)
        assert stopped is True
        mock_run.assert_called_once_with(
            ["podman", "stop", "voicevox-engine"], check=False
        )

    # logger が None の場合の動作テスト
    manager._write_active_pids([os.getpid()])
    with (
        patch.object(
            VoicevoxContainerManager,
            "is_process_alive",
            side_effect=lambda pid: pid == os.getpid(),
        ),
        patch.object(
            VoicevoxContainerManager, "is_container_running", return_value=True
        ),
    ):
        stopped_no_logger = manager.stop_if_last(logger=None)
        assert stopped_no_logger is True


@patch("youtube_tts.container.subprocess.run")
def test_ensure_started_server_already_ready(mock_run, tmp_path) -> None:
    """サーバー準備完了時の挙動をテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )

    with patch.object(
        VoicevoxContainerManager, "is_server_ready", return_value=True
    ):
        res = manager.ensure_started()
        assert res is True
        mock_run.assert_not_called()


def test_is_container_cmd_available(tmp_path) -> None:
    """コンテナコマンドの存在判定をテストします。"""
    manager = VoicevoxContainerManager(container_cmd="non_existent_cmd_12345")
    assert manager.is_container_cmd_available() is False
    assert manager.is_container_running() is False
    assert manager.is_container_exists() is False


@patch("youtube_tts.container.requests.get")
def test_is_server_ready(mock_get, tmp_path) -> None:
    """サーバーの応答状態確認をテストします。"""
    manager = VoicevoxContainerManager()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    assert manager.is_server_ready() is True

    mock_resp.status_code = 500
    assert manager.is_server_ready() is False

    mock_get.side_effect = Exception("Connection error")
    assert manager.is_server_ready() is False


@patch("youtube_tts.container.subprocess.run")
def test_is_container_running_and_exists(mock_run, tmp_path) -> None:
    """コンテナの実行・存在確認メソッドをテストします。"""
    manager = VoicevoxContainerManager(container_cmd="podman")
    with patch.object(
        VoicevoxContainerManager,
        "is_container_cmd_available",
        return_value=True,
    ):
        mock_run.return_value = MagicMock(
            stdout="voicevox-engine\nother-container\n"
        )
        assert manager.is_container_running() is True
        assert manager.is_container_exists() is True

        mock_run.return_value = MagicMock(stdout="other-container\n")
        assert manager.is_container_running() is False

        mock_run.side_effect = Exception("Subprocess error")
        assert manager.is_container_running() is False
        assert manager.is_container_exists() is False


@patch("youtube_tts.container.subprocess.run")
def test_ensure_started_flows(mock_run, tmp_path) -> None:
    """ensure_started の各フローをテストします。"""
    lock_file = tmp_path / "test.lock"
    state_file = tmp_path / "test.json"
    manager = VoicevoxContainerManager(
        lock_file_path=lock_file,
        state_file_path=state_file,
    )

    logger = MagicMock()

    # コマンド利用不可 (logger あり/なし)
    with (
        patch.object(
            VoicevoxContainerManager, "is_server_ready", return_value=False
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_cmd_available",
            return_value=False,
        ),
    ):
        assert manager.ensure_started(logger=logger) is False
        assert manager.ensure_started(logger=None) is False

    # 既存コンテナ起動 (logger あり/なし)
    ready_state = [False, True, False, True]
    with (
        patch.object(
            VoicevoxContainerManager,
            "is_server_ready",
            side_effect=lambda: ready_state.pop(0) if ready_state else True,
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_cmd_available",
            return_value=True,
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_running",
            return_value=False,
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_exists",
            return_value=True,
        ),
    ):
        assert manager.ensure_started(logger=logger) is True
        assert manager.ensure_started(logger=None) is True

    # 新規コンテナ作成 (logger あり/なし)
    ready_state2 = [False, True, False, True]
    with (
        patch.object(
            VoicevoxContainerManager,
            "is_server_ready",
            side_effect=lambda: ready_state2.pop(0) if ready_state2 else True,
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_cmd_available",
            return_value=True,
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_running",
            return_value=False,
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_exists",
            return_value=False,
        ),
    ):
        assert manager.ensure_started(logger=logger) is True
        assert manager.ensure_started(logger=None) is True

    # タイムアウト (logger あり/なし)
    with (
        patch.object(
            VoicevoxContainerManager, "is_server_ready", return_value=False
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_cmd_available",
            return_value=True,
        ),
        patch.object(
            VoicevoxContainerManager,
            "is_container_running",
            return_value=True,
        ),
    ):
        assert manager.ensure_started(logger=logger, wait_timeout=0.1) is False
        assert manager.ensure_started(logger=None, wait_timeout=0.1) is False


def test_is_process_alive_invalid_pid() -> None:
    """無効な PID に対する is_process_alive のテストです。"""
    assert VoicevoxContainerManager.is_process_alive(0) is False
    assert VoicevoxContainerManager.is_process_alive(-1) is False
