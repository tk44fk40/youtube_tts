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
import io
import wave
import numpy as np

from .logger import get_logger

logger = get_logger()


class AudioPlayer:
    """音声の再生およびオーディオデバイスの制御を行うクラス。"""

    def __init__(self, default_device=None):
        """オーディオプレイヤーを初期化する。

        Args:
            default_device (int or str, optional):
                デフォルトで使用する出力オーディオデバイスの名前またはID。
                指定しない場合は、pipewire または pulse を自動検出します。
        """
        import sounddevice as sd

        if default_device is None:
            # サウンドサーバーデバイスの自動検出を試みる。
            # Linux環境での競合回避と接続安定化のため、
            # pipewire, pulse, pulseaudio, default を優先して検索する。
            try:
                devices = sd.query_devices()
                if isinstance(devices, dict):
                    devices = [devices]
                hostapis = sd.query_hostapis()
                preferred_keywords = [
                    "pipewire",
                    "pulse",
                    "pulseaudio",
                    "default",
                ]
                found_device = None
                for keyword in preferred_keywords:
                    for i, dev in enumerate(devices):
                        if dev.get("max_output_channels", 0) > 0:
                            name = dev.get("name", "").lower()
                            # ホストAPI名も判定対象に含める
                            api_idx = dev.get("hostapi")
                            api_name = ""
                            if (
                                api_idx is not None
                                and 0 <= api_idx < len(hostapis)
                            ):
                                api_name = (
                                    hostapis[api_idx].get("name", "").lower()
                                )

                            if keyword in name or keyword in api_name:
                                found_device = i
                                break
                    if found_device is not None:
                        break
                if found_device is not None:
                    default_device = found_device
            except Exception:
                pass

        self.default_device = default_device
        if default_device is not None:
            sd.default.device = default_device

        # 出力デバイスのデフォルトサンプリングレートを問い合わせる
        try:
            device_info = sd.query_devices(None, "output")
            self.target_sample_rate = int(device_info["default_samplerate"])
        except Exception:
            self.target_sample_rate = 24000

        sd.default.samplerate = self.target_sample_rate

    def query_devices(self, device=None, kind=None):
        """利用可能なオーディオデバイスの情報を取得する。

        Args:
            device (int or str, optional): デバイス名またはID。
            kind (str, optional): 'input' または 'output'。

        Returns:
            dict or list: デバイス情報。
        """
        import sounddevice as sd

        return sd.query_devices(device, kind)

    def resample_audio(self, audio, source_sample_rate, target_sample_rate):
        """簡易的な線形補間によるリサンプリング処理。

        高音質化や複雑なオーディオ変換用ではなく、
        簡易的な再生用レート変換に使用されます。

        Args:
            audio (numpy.ndarray): 元のオーディオデータ。
            source_sample_rate (int): 元のサンプリングレート。
            target_sample_rate (int): 変換先のサンプリングレート。

        Returns:
            numpy.ndarray: リサンプリングされたオーディオデータ。
        """
        if source_sample_rate == target_sample_rate:
            return audio

        duration = len(audio) / source_sample_rate
        old_time = np.linspace(0, duration, num=len(audio))
        new_length = int(duration * target_sample_rate)
        new_time = np.linspace(0, duration, num=new_length)
        resampled_audio = np.interp(new_time, old_time, audio).astype(np.int16)
        return resampled_audio

    def play_wav(self, wav_content, device=None, target_sample_rate=None):
        """WAV音声データを再生する。

        Args:
            wav_content (bytes): WAVファイルのバイナリデータ。
            device (int or str, optional): 再生に使用するデバイス。
            target_sample_rate (int, optional): 再生サンプリングレート。
        """
        import sounddevice as sd

        wav_io = io.BytesIO(wav_content)
        with wave.open(wav_io, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            pcm_data = wav_file.readframes(wav_file.getnframes())

        audio = np.frombuffer(pcm_data, dtype=np.int16)

        # デバイスが指定された場合は sd.play の引数に渡す play_device を特定。
        # デバイス未指定の場合は self.default_device を使用。
        play_device = None
        if device is not None:
            try:
                play_device = int(device)
            except ValueError:
                play_device = device
        else:
            play_device = self.default_device

        # 再生時のサンプリングレートを決定
        play_rate = target_sample_rate or self.target_sample_rate
        audio = self.resample_audio(audio, sample_rate, play_rate)

        # sd.play に直接デバイスを渡すことで、
        # グローバルな sd.default.device の書き換えを防ぐ
        sd.play(audio, samplerate=play_rate, device=play_device)
        sd.wait()

    def stop(self):
        """再生中の音声を停止する。"""
        try:
            import sounddevice as sd

            sd.stop()
        except Exception as e:
            logger.warning(f"sounddevice stop failed: {e}")
