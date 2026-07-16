"""AudioPlayer の停止処理を検証するテストモジュールです。"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from youtube_tts import AudioPlayer


def test_stop_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常なプロセスの停止処理を検証します。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = None

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


def test_stop_no_process() -> None:
    """再生プロセスが存在しない状態での stop メソッド呼び出しを検証します。"""
    player = AudioPlayer()
    player.process = None
    player.stop()


def test_stop_already_terminated() -> None:
    """プロセス終了後の停止処理を検証します。"""
    player = AudioPlayer()
    mock_process = MagicMock()
    mock_process.poll.return_value = 0

    player.process = mock_process
    player.stop()
    mock_process.terminate.assert_not_called()
