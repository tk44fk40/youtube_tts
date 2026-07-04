"""VoicevoxClient のテストモジュールです。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from youtube_tts import VoicevoxClient


def test_get_speakers_success():
    """VOICEVOX スピーカー情報が正常に取得できることを検証。"""
    # テスト用のフェイク URL で VoicevoxClient を生成します
    client = VoicevoxClient(base_url="http://fake-vox")

    with patch("requests.get") as mock_get:
        # /speakers エンドポイントの正常レスポンスをモックします
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"name": "ずんだもん", "styles": []}]
        mock_get.return_value = mock_resp

        speakers = client.get_speakers()

        # スピーカー名が正しく取得できていることを確認します
        assert speakers[0]["name"] == "ずんだもん"
        # 正しい URL が呼ばれていることを確認します
        mock_get.assert_called_once_with("http://fake-vox/speakers")


def test_get_speakers_connection_error():
    """接続エラー時に RuntimeError が発生することを検証。"""
    client = VoicevoxClient(base_url="http://fake-vox")

    with patch("requests.get") as mock_get:
        # サーバーへの接続が拒否された状況をシミュレートします
        mock_get.side_effect = (
            requests.exceptions.ConnectionError("Connection refused")
        )

        with pytest.raises(RuntimeError) as excinfo:
            client.get_speakers()

        # エラーメッセージに期待する文字列が含まれることを確認します
        assert "VOICEVOXサーバーへの接続に失敗しました" in str(excinfo.value)


def test_synthesize_success():
    """VOICEVOX で音声合成（synthesis）が正常に動作することを検証。"""
    client = VoicevoxClient(base_url="http://fake-vox", speaker_id=3)

    with patch("requests.post") as mock_post:
        # audio_query エンドポイントのレスポンスをモックします
        mock_query_resp = MagicMock()
        mock_query_resp.json.return_value = {
            "outputSamplingRate": 24000,
            "volumeScale": 1.0,
            "speedScale": 1.0,
        }

        # synthesis エンドポイントのレスポンスをモックします
        mock_synth_resp = MagicMock()
        mock_synth_resp.content = b"fake_wav_data"

        # 1 回目: audio_query、2 回目: synthesis の順で返します
        mock_post.side_effect = [mock_query_resp, mock_synth_resp]

        wav_data = client.synthesize(
            "こんにちは",
            volume_scale=1.5,
            speed_scale=1.2,
            target_sample_rate=48000,
        )

        # 返却バイト列が期待値と一致することを確認します
        assert wav_data == b"fake_wav_data"
        # audio_query と synthesis の 2 回呼ばれることを確認します
        assert mock_post.call_count == 2

        # audio_query 呼び出しの引数を検証します
        first_call = mock_post.call_args_list[0]
        assert first_call[0][0] == "http://fake-vox/audio_query"
        assert first_call[1]["params"] == {"text": "こんにちは", "speaker": 3}

        # synthesis 呼び出しの引数とクエリデータを検証します
        second_call = mock_post.call_args_list[1]
        assert second_call[0][0] == "http://fake-vox/synthesis"
        assert second_call[1]["params"] == {"speaker": 3}
        assert second_call[1]["json"]["volumeScale"] == 1.5
        assert second_call[1]["json"]["speedScale"] == 1.2
        assert second_call[1]["json"]["outputSamplingRate"] == 48000


def test_synthesize_success_no_rate():
    """サンプリングレート未指定時の音声合成を検証。"""
    client = VoicevoxClient(base_url="http://fake-vox", speaker_id=3)

    with patch("requests.post") as mock_post:
        # デフォルトのサンプリングレートを持つレスポンスをモックします
        mock_query_resp = MagicMock()
        mock_query_resp.json.return_value = {
            "outputSamplingRate": 24000,
            "volumeScale": 1.0,
            "speedScale": 1.0,
        }

        mock_synth_resp = MagicMock()
        mock_synth_resp.content = b"fake_wav_data"

        mock_post.side_effect = [mock_query_resp, mock_synth_resp]

        # target_sample_rate を省略して呼び出します
        wav_data = client.synthesize("こんにちは")

        # 正常にバイト列が返ることを確認します
        assert wav_data == b"fake_wav_data"
        assert mock_post.call_count == 2


def test_synthesize_http_error():
    """音声合成リクエスト時に HTTPError が適切に送出されることを検証。"""
    client = VoicevoxClient(base_url="http://fake-vox", speaker_id=3)

    with patch("requests.post") as mock_post:
        # raise_for_status() で HTTP エラーを発生させます
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Internal Server Error"
        )
        mock_post.return_value = mock_resp

        # HTTPError が呼び出し元へ伝播することを確認します
        with pytest.raises(requests.exceptions.HTTPError):
            client.synthesize("こんにちは")
