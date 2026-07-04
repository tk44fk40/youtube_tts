from unittest.mock import MagicMock, patch

import pytest
import requests

from youtube_tts import VoicevoxClient


def test_get_speakers_success():
    client = VoicevoxClient(base_url="http://fake-vox")

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"name": "ずんだもん", "styles": []}]
        mock_get.return_value = mock_resp

        speakers = client.get_speakers()
        assert speakers[0]["name"] == "ずんだもん"
        mock_get.assert_called_once_with("http://fake-vox/speakers")


def test_get_speakers_connection_error():
    client = VoicevoxClient(base_url="http://fake-vox")

    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(RuntimeError) as excinfo:
            client.get_speakers()
        assert "VOICEVOXサーバーへの接続に失敗しました" in str(excinfo.value)


def test_synthesize_success():
    client = VoicevoxClient(base_url="http://fake-vox", speaker_id=3)

    with patch("requests.post") as mock_post:
        # Response to audio_query
        #
        # audio_query に対するレスポンス
        mock_query_resp = MagicMock()
        mock_query_resp.json.return_value = {
            "outputSamplingRate": 24000,
            "volumeScale": 1.0,
            "speedScale": 1.0,
        }

        # Response to synthesis
        #
        # synthesis に対するレスポンス
        mock_synth_resp = MagicMock()
        mock_synth_resp.content = b"fake_wav_data"

        mock_post.side_effect = [mock_query_resp, mock_synth_resp]

        wav_data = client.synthesize(
            "こんにちは",
            volume_scale=1.5,
            speed_scale=1.2,
            target_sample_rate=48000,
        )
        assert wav_data == b"fake_wav_data"

        assert mock_post.call_count == 2

        first_call = mock_post.call_args_list[0]
        assert first_call[0][0] == "http://fake-vox/audio_query"
        assert first_call[1]["params"] == {"text": "こんにちは", "speaker": 3}

        second_call = mock_post.call_args_list[1]
        assert second_call[0][0] == "http://fake-vox/synthesis"
        assert second_call[1]["params"] == {"speaker": 3}
        assert second_call[1]["json"]["volumeScale"] == 1.5
        assert second_call[1]["json"]["speedScale"] == 1.2
        assert second_call[1]["json"]["outputSamplingRate"] == 48000


def test_synthesize_success_no_rate():
    client = VoicevoxClient(base_url="http://fake-vox", speaker_id=3)

    with patch("requests.post") as mock_post:
        mock_query_resp = MagicMock()
        mock_query_resp.json.return_value = {
            "outputSamplingRate": 24000,
            "volumeScale": 1.0,
            "speedScale": 1.0,
        }

        mock_synth_resp = MagicMock()
        mock_synth_resp.content = b"fake_wav_data"

        mock_post.side_effect = [mock_query_resp, mock_synth_resp]

        wav_data = client.synthesize("こんにちは")
        assert wav_data == b"fake_wav_data"
        assert mock_post.call_count == 2


def test_synthesize_http_error():
    client = VoicevoxClient(base_url="http://fake-vox", speaker_id=3)

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Internal Server Error"
        )
        mock_post.return_value = mock_resp

        with pytest.raises(requests.exceptions.HTTPError):
            client.synthesize("こんにちは")
