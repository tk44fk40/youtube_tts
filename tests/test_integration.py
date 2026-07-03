from unittest.mock import MagicMock, patch

from youtube_tts import AppConfig, AudioPlayer, TextProcessor, VoicevoxClient


@patch("requests.post")
@patch.object(AudioPlayer, "play_wav")
def test_tts_pipeline_integration(
    mock_play_wav, mock_post, tmp_path, dummy_wav_bytes
):
    # 1. Set up config files in temporary directory
    #
    # 1. 一時ディレクトリに設定ファイルをセットアップする
    dict_file = tmp_path / "dictionary.txt"
    ng_file = tmp_path / "ng_words.txt"
    vol_file = tmp_path / "volume.txt"

    dict_file.write_text("apple = 林檎", encoding="utf-8")
    ng_file.write_text("spam", encoding="utf-8")
    vol_file.write_text("1.2", encoding="utf-8")

    # 2. Initialize each class
    #
    # 2. 各クラスを初期化する
    config = AppConfig(
        dictionary_path=dict_file, ng_words_path=ng_file, volume_path=vol_file
    )
    processor = TextProcessor(config)
    vox_client = VoicevoxClient(base_url="http://mock-vox", speaker_id=3)
    player = AudioPlayer()

    # 3. Set up mocks
    #
    # 3. モックをセットアップする
    mock_query_resp = MagicMock()
    mock_query_resp.json.return_value = {
        "outputSamplingRate": 24000,
        "volumeScale": 1.0,
    }
    mock_synth_resp = MagicMock()
    mock_synth_resp.content = dummy_wav_bytes
    mock_post.side_effect = [mock_query_resp, mock_synth_resp]

    # 4. Run pipeline: fetch chat -> normalize -> synthesize -> play
    #
    # 4. パイプラインを実行: チャット取得 -> 正規化 ->音声合成 -> 再生
    author = "@Taro"
    message = "I like apple"

    # A. Normalization (TextProcessor)
    #
    # A. 正規化 (TextProcessor)
    normalized_author, normalized_msg = processor.normalize_comment(
        author, message
    )
    assert normalized_author == "Taroさん"
    assert normalized_msg == "I like 林檎"
    assert processor.contains_ng_word(normalized_msg) is False

    # B. Audio synthesis (VoicevoxClient)
    #
    # B. 音声合成 (VoicevoxClient)
    talk_text = f"{normalized_author} {normalized_msg}"
    wav_data = vox_client.synthesize(
        text=talk_text,
        volume_scale=config.volume_scale,
        target_sample_rate=player.target_sample_rate,
    )
    assert wav_data == dummy_wav_bytes

    # C. Audio playback (AudioPlayer)
    #
    # C. 音声再生 (AudioPlayer)
    player.play_wav(wav_data)

    # 5. Assertion (Verification)
    # Verify that the volume scale requested in audio synthesis is 1.2
    #
    # 5. アサーション（検証）
    # 音声合成で要求された音量比が 1.2 であることを確認
    assert mock_post.call_count == 2
    synthesis_call_json = mock_post.call_args_list[1][1]["json"]
    assert synthesis_call_json["volumeScale"] == 1.2

    # Verify AudioPlayer call
    #
    # AudioPlayer の呼び出し検証
    mock_play_wav.assert_called_once_with(wav_data)
