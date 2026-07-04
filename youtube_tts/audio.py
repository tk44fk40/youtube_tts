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
"""音声の再生およびオーディオデバイスの制御を行うモジュール。"""

import os
import shutil
import subprocess
import tempfile
import threading

from .logger import get_logger

logger = get_logger()


class AudioPlayer:
    """音声の再生およびオーディオデバイスの制御を行うクラス。

    システムにインストールされている外部再生コマンド (pacat や aplay 等)
    を利用して、WAV 音声データの再生とデバイスの問い合わせを行います。
    """

    def __init__(self, default_device=None):
        """オーディオプレイヤーを初期化する。

        Args:
            default_device (int or str, optional):
                デフォルトで使用する出力オーディオデバイスの名前またはID。
        """
        self.default_device = default_device
        self.target_sample_rate = 24000
        self.process = None
        self._lock = threading.Lock()

        # デスクトップのデフォルトサンプリングレートの取得を試みる
        if shutil.which("pactl"):
            try:
                res = subprocess.run(
                    ["pactl", "info"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=2.0,
                )
                for line in res.stdout.splitlines():
                    if "Default Sample Specification" in line:
                        parts = line.split()
                        for part in parts:
                            if part.endswith("Hz"):
                                self.target_sample_rate = int(part[:-2])
                                break
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "pactl によるデフォルトサンプリングレート"
                    f"取得に失敗しました: {e}"
                )

    def query_devices(self, device=None, kind=None):
        """利用可能なオーディオデバイスの情報を取得する。

        Args:
            device (int or str, optional): デバイス名またはID（未使用）。
            kind (str, optional): デバイスの種類（未使用）。

        Returns:
            str: 整形されたデバイス情報の一覧文字列。
        """
        if shutil.which("pactl"):
            try:
                res = subprocess.run(
                    ["pactl", "list", "short", "sinks"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=2.0,
                )
                lines = res.stdout.strip().splitlines()
                output = ["利用可能なオーディオ出力デバイス (pactl):"]
                for line in lines:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        output.append(f"  ID: {parts[0]} -> {parts[1]}")
                return "\n".join(output)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"pactl の実行に失敗しました: {e}")

        if shutil.which("aplay"):
            try:
                res = subprocess.run(
                    ["aplay", "-L"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=2.0,
                )
                lines = res.stdout.strip().splitlines()
                output = ["利用可能なオーディオ出力デバイス (aplay):"]
                for line in lines:
                    if line.startswith((" ", "\t")):
                        continue
                    output.append(f"  {line.strip()}")
                return "\n".join(output)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"aplay の実行に失敗しました: {e}")

        return (
            "利用可能なオーディオデバイス検出コマンド "
            "(pactl, aplay) が見つかりませんでした。"
        )

    def play_wav(self, wav_content, device=None, target_sample_rate=None):
        """WAV音声データを再生する。

        Args:
            wav_content (bytes): WAVファイルのバイナリデータ。
            device (int or str, optional): 再生に使用するデバイス。
            target_sample_rate (int, optional):
                再生サンプリングレート（未使用）。

        Raises:
            RuntimeError: 利用可能な再生コマンドが見つからない場合。
        """
        play_device = device if device is not None else self.default_device
        temp_file_path = None

        # コマンドの特定と引数の組み立て
        if shutil.which("pacat"):
            cmd = ["pacat", "--playback", "--file-format=wav"]
            if play_device is not None:
                cmd += ["-d", str(play_device)]
            use_stdin = True
        elif shutil.which("aplay"):
            cmd = ["aplay", "-"]
            if play_device is not None:
                cmd += ["-D", str(play_device)]
            use_stdin = True
        elif shutil.which("pw-play"):
            # pw-play は標準入力を受け付けないため、一時ファイルを作成する
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                f.write(wav_content)
                temp_file_path = f.name
            cmd = ["pw-play", temp_file_path]
            if play_device is not None:
                cmd += ["--target", str(play_device)]
            use_stdin = False
        elif shutil.which("paplay"):
            # paplay は標準入力を受け付けないため、一時ファイルを作成する
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                f.write(wav_content)
                temp_file_path = f.name
            cmd = ["paplay", temp_file_path]
            if play_device is not None:
                cmd += ["-d", str(play_device)]
            use_stdin = False
        else:
            raise RuntimeError(
                "利用可能な再生コマンド (pacat, aplay, pw-play, paplay) "
                "が見つかりません。"
            )

        with self._lock:
            # 既に動いているプロセスがあれば念のため停止する
            if self.process and self.process.poll() is None:
                try:
                    self.process.kill()
                    self.process.wait()
                except Exception as e:  # noqa: BLE001
                    logger.debug(
                        "古いプロセスの強制終了中に"
                        f"エラーが発生しました: {e}"
                    )
            if use_stdin:
                self.process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            else:
                self.process = subprocess.Popen(cmd)

        try:
            if use_stdin:
                # 標準入力に WAV を流し込み、終了を待機する
                self.process.communicate(input=wav_content)
            else:
                # プロセスの終了を直接待機する
                self.process.wait()
        except KeyboardInterrupt:
            logger.info("再生がユーザーによって中断されました。")
            self.stop()
            raise
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:  # noqa: BLE001
                    logger.debug(
                        "一時ファイルの削除に失敗しました: "
                        f"{temp_file_path}, {e}"
                    )

    def stop(self):
        """再生中の音声を停止する。"""
        with self._lock:
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                    # 猶予を与えて終了を待つ
                    try:
                        self.process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"外部再生プロセスの停止中にエラーが発生しました: {e}"
                    )
                finally:
                    self.process = None
