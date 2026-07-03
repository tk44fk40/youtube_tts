from unittest.mock import MagicMock

import numpy as np

from youtube_tts import AudioPlayer


def test_audio_initialization_success(mock_sd):
    mock_sd.query_devices.return_value = {
        "name": "default",
        "default_samplerate": 48000,
    }
    player = AudioPlayer(default_device="custom_device")
    assert player.target_sample_rate == 48000
    assert mock_sd.default.device == "custom_device"
    mock_sd.query_devices.assert_called_once_with(None, "output")


def test_audio_initialization_default_none(mock_sd):
    mock_sd.query_devices.return_value = {
        "name": "default",
        "default_samplerate": 48000,
    }
    # Create mock property to verify it was not set
    #
    # 設定されなかったことを検証するためにモックプロパティを作成する
    mock_sd.default = MagicMock()
    player = AudioPlayer()
    assert player.target_sample_rate == 48000
    # Verify sd.default.device is not assigned
    #
    # sd.default.device が割り当てられていないことを検証する
    assert not mock_sd.default.mock_calls


def test_audio_initialization_no_device(mock_sd):
    mock_sd.query_devices.side_effect = Exception("No output device found")
    player = AudioPlayer()
    # Fallback sampling rate for headless or CI environments
    #
    # 画面なし（headless）やCI環境などのための
    # フォールバックサンプリングレート
    assert player.target_sample_rate == 24000


def test_audio_initialization_autodetect_pipewire(mock_sd):
    mock_sd.query_devices.side_effect = [
        [
            {"name": "HDMI 1", "max_output_channels": 8},
            {"name": "pipewire, ALSA", "max_output_channels": 128},
        ],
        {"name": "pipewire, ALSA", "default_samplerate": 44100},
    ]
    mock_sd.default = MagicMock()
    player = AudioPlayer()
    assert mock_sd.default.device == 1
    assert player.target_sample_rate == 44100


def test_audio_initialization_autodetect_pulse(mock_sd):
    mock_sd.query_devices.side_effect = [
        [
            {"name": "HDMI 1", "max_output_channels": 8},
            {"name": "pulse, ALSA", "max_output_channels": 32},
        ],
        {"name": "pulse, ALSA", "default_samplerate": 48000},
    ]
    mock_sd.default = MagicMock()
    player = AudioPlayer()
    assert mock_sd.default.device == 1
    assert player.target_sample_rate == 48000


def test_resample_audio():
    player = AudioPlayer()
    audio = np.array([100, 200, 300, 400], dtype=np.int16)

    assert np.array_equal(player.resample_audio(audio, 24000, 24000), audio)

    resampled = player.resample_audio(audio, 24000, 12000)
    assert len(resampled) == 2
    assert resampled[0] == 100
    assert resampled[1] == 400


def test_play_wav_success(mock_sd, dummy_wav_bytes):
    mock_sd.query_devices.return_value = {
        "name": "default",
        "default_samplerate": 24000,
    }
    player = AudioPlayer()

    player.play_wav(dummy_wav_bytes)

    mock_sd.play.assert_called_once()
    _, kwargs = mock_sd.play.call_args
    assert kwargs["samplerate"] == 24000
    mock_sd.get_stream.assert_called_once()


def test_play_wav_loop_waits_for_stream_completion(
    mock_sd, dummy_wav_bytes
):
    """ストリーム完了までの待機ループを検証する。"""
    mock_sd.query_devices.return_value = {
        "name": "default",
        "default_samplerate": 24000,
    }
    player = AudioPlayer()

    # 1回目は active=True、2回目は active=False を返すようにモックを設定
    from unittest.mock import PropertyMock

    type(mock_sd.get_stream.return_value).active = PropertyMock(
        side_effect=[True, False]
    )

    player.play_wav(dummy_wav_bytes)

    mock_sd.play.assert_called_once()
    mock_sd.get_stream.assert_called_once()


def test_play_wav_with_device_switch(mock_sd, dummy_wav_bytes):
    mock_sd.query_devices.return_value = {
        "name": "default",
        "default_samplerate": 24000,
    }
    player = AudioPlayer()

    player.play_wav(dummy_wav_bytes, device="3")
    # Verify that global default.device is not modified
    #
    # グローバルな default.device が
    # 書き換えられていないことを確認
    assert mock_sd.default.device != 3
    # Assert that it is passed to sd.play instead
    #
    # 代わりに、sd.play の引数に
    # 渡されていることをアサートする
    mock_sd.play.assert_called_once()
    _, kwargs = mock_sd.play.call_args
    assert kwargs["device"] == 3


def test_play_wav_invalid_device_name(mock_sd, dummy_wav_bytes):
    mock_sd.query_devices.return_value = {
        "name": "default",
        "default_samplerate": 24000,
    }
    player = AudioPlayer()

    player.play_wav(dummy_wav_bytes, device="default")
    # Verify that global default.device is not modified
    #
    # グローバルな default.device が
    # 書き換えられていないことを確認
    assert mock_sd.default.device != "default"
    # Assert that it is passed to sd.play instead
    #
    # 代わりに、sd.play の引数に
    # 渡されていることをアサートする
    mock_sd.play.assert_called_once()
    _, kwargs = mock_sd.play.call_args
    assert kwargs["device"] == "default"


def test_query_devices(mock_sd):
    mock_sd.query_devices.return_value = {"name": "dummy"}
    player = AudioPlayer()
    res = player.query_devices(device=1, kind="output")
    assert res == {"name": "dummy"}
    mock_sd.query_devices.assert_called_with(1, "output")


def test_audio_stop_exception(mock_sd, caplog):
    mock_sd.stop.side_effect = Exception("sounddevice error")
    player = AudioPlayer()

    with caplog.at_level("WARNING"):
        player.stop()

    assert any(
        "sounddevice stop failed" in record.message for record in caplog.records
    )


def test_audio_initialization_autodetect_hostapi_pulse(mock_sd):
    """ホストAPI名が PulseAudio の場合に自動検出されることを検証する。"""
    mock_sd.query_hostapis.return_value = [
        {"name": "ALSA"},
        {"name": "PulseAudio"},
    ]
    mock_sd.query_devices.side_effect = [
        [
            {"name": "HDMI 1", "max_output_channels": 8, "hostapi": 0},
            {"name": "Default Sink", "max_output_channels": 32, "hostapi": 1},
        ],
        {"name": "Default Sink", "default_samplerate": 48000},
    ]
    mock_sd.default = MagicMock()
    player = AudioPlayer()
    assert mock_sd.default.device == 1
    assert player.target_sample_rate == 48000


def test_audio_initialization_autodetect_invalid_hostapi_index(mock_sd):
    """ホストAPIインデックスが範囲外でも正常に処理されることを検証する。"""
    mock_sd.query_hostapis.return_value = [{"name": "ALSA"}]
    mock_sd.query_devices.side_effect = [
        [
            {"name": "HDMI 1", "max_output_channels": 8, "hostapi": 99},
            {"name": "Default Sink", "max_output_channels": 32, "hostapi": 0},
        ],
        {"name": "Default Sink", "default_samplerate": 48000},
    ]
    mock_sd.default = MagicMock()
    AudioPlayer()
    assert mock_sd.default.device == 1

