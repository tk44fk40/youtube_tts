import io
import wave
import numpy as np
import sounddevice as sd

class AudioPlayer:
    def __init__(self, default_device="default"):
        self.default_device = default_device
        sd.default.device = default_device

        # Query default sample rate for output device
        try:
            device_info = sd.query_devices(None, 'output')
            self.target_sample_rate = int(device_info['default_samplerate'])
        except Exception:
            self.target_sample_rate = 24000

        sd.default.samplerate = self.target_sample_rate

    def query_devices(self, device=None, kind=None):
        return sd.query_devices(device, kind)

    def resample_audio(self, audio, source_sample_rate, target_sample_rate):
        if source_sample_rate == target_sample_rate:
            return audio

        duration = len(audio) / source_sample_rate
        old_time = np.linspace(0, duration, num=len(audio))
        new_length = int(duration * target_sample_rate)
        new_time = np.linspace(0, duration, num=new_length)
        resampled_audio = np.interp(new_time, old_time, audio).astype(np.int16)
        return resampled_audio

    def play_wav(self, wav_content, device=None, target_sample_rate=None):
        wav_io = io.BytesIO(wav_content)
        with wave.open(wav_io, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            pcm_data = wav_file.readframes(wav_file.getnframes())

        audio = np.frombuffer(pcm_data, dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels)

        # Switch to specified device if provided
        if device is not None:
            try:
                dev_id = int(device)
            except ValueError:
                dev_id = device
            sd.default.device = dev_id

        # Determine sampling rate for playback
        play_rate = target_sample_rate or self.target_sample_rate
        audio = self.resample_audio(audio, sample_rate, play_rate)

        sd.play(audio, samplerate=play_rate)
        sd.wait()

    def stop(self):
        try:
            sd.stop()
        except Exception as e:
            print(f"[WARN] sounddevice stop failed: {e}")
