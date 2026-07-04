from youtube_tts import AppConfig


def test_config_initial_load(tmp_path):
    dict_file = tmp_path / "dictionary.txt"
    ng_file = tmp_path / "ng_words.txt"
    vol_file = tmp_path / "volume.txt"

    dict_file.write_text("apple = 林檎\nbanana = バナナ", encoding="utf-8")
    ng_file.write_text("badword\n  \n", encoding="utf-8")
    vol_file.write_text("0.5", encoding="utf-8")

    config = AppConfig(
        dictionary_path=dict_file,
        ng_words_path=ng_file,
        volume_path=vol_file,
        chat_log_path="custom_chat.jsonl",
    )

    assert config.volume_scale == 0.5
    assert config.replacements == {"apple": "林檎", "banana": "バナナ"}
    assert config.ng_words == {"badword"}
    assert config.chat_log_path == "custom_chat.jsonl"

    config_default = AppConfig(
        dictionary_path=dict_file, ng_words_path=ng_file, volume_path=vol_file
    )
    assert config_default.chat_log_path == "chat_log.jsonl"


def test_config_reload_on_change(tmp_path):
    dict_file = tmp_path / "dictionary.txt"
    ng_file = tmp_path / "ng_words.txt"
    vol_file = tmp_path / "volume.txt"

    dict_file.touch()
    ng_file.touch()
    vol_file.write_text("1.0")

    config = AppConfig(
        dictionary_path=dict_file, ng_words_path=ng_file, volume_path=vol_file
    )

    assert config.volume_scale == 1.0

    # Apply changes
    #
    # 変更を適用する
    vol_file.write_text("1.5")
    dict_file.write_text("orange = オレンジ")
    ng_file.write_text("spam")

    config.reload_if_changed()

    assert config.volume_scale == 1.5
    assert config.replacements == {"orange": "オレンジ"}
    assert config.ng_words == {"spam"}


def test_config_volume_invalid(tmp_path, caplog):
    vol_file = tmp_path / "volume.txt"
    vol_file.write_text("1.0")

    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=tmp_path / "ng.txt",
        volume_path=vol_file,
    )

    # Invalid case 1: Not a float
    #
    # 無効なケース 1: 浮動小数点数ではない
    vol_file.write_text("invalid_float")
    with caplog.at_level("WARNING"):
        config.reload_if_changed()
    assert config.volume_scale == 1.0
    assert any(
        "Invalid volume value in volume.txt" in record.message
        for record in caplog.records
    )
    caplog.clear()

    # Invalid case 2: Out of range (max 2.0)
    #
    # 無効なケース 2: 範囲外 (最大 2.0)
    vol_file.write_text("2.5")
    with caplog.at_level("INFO"):
        config.reload_if_changed()
    assert config.volume_scale == 1.0
    assert any(
        "volume scale out of range" in record.message for record in caplog.records
    )


def test_config_dictionary_invalid(tmp_path):
    dict_file = tmp_path / "dictionary.txt"
    dict_file.write_text(
        "apple = 林檎\ninvalid_line_no_equal\nbanana = バナナ", encoding="utf-8"
    )

    config = AppConfig(
        dictionary_path=dict_file,
        ng_words_path=tmp_path / "ng.txt",
        volume_path=tmp_path / "vol.txt",
    )

    # Ignore invalid lines and load valid lines
    #
    # 無効な行を無視し、正常な行をロードする
    assert config.replacements == {"apple": "林檎", "banana": "バナナ"}


def test_config_ng_words_missing_and_empty_lines(tmp_path):
    # Non-existent file
    #
    # 存在しないファイル
    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=tmp_path / "non_existent_ng.txt",
        volume_path=tmp_path / "vol.txt",
    )
    assert config.ng_words == set()

    # Empty or blank lines
    #
    # 空行または空白行
    ng_file = tmp_path / "ng_words.txt"
    ng_file.write_text("\n   \nspam\n\n", encoding="utf-8")

    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=ng_file,
        volume_path=tmp_path / "vol.txt",
    )
    assert config.ng_words == {"spam"}


def test_config_load_os_errors(tmp_path, caplog):
    import time
    from unittest.mock import patch

    dict_file = tmp_path / "dictionary.txt"
    ng_file = tmp_path / "ng_words.txt"
    vol_file = tmp_path / "volume.txt"

    dict_file.touch()
    ng_file.touch()
    vol_file.write_text("1.0")

    config = AppConfig(
        dictionary_path=dict_file, ng_words_path=ng_file, volume_path=vol_file
    )

    # Update timestamp to trigger reload
    #
    # タイムスタンプを更新して再ロードを促す
    time.sleep(0.01)
    dict_file.touch()
    ng_file.touch()
    vol_file.touch()

    with patch("builtins.open", side_effect=OSError("Permission Denied")):
        with caplog.at_level("WARNING"):
            config.reload_if_changed()

    combined_output = "\n".join(record.message for record in caplog.records)

    assert "Failed to load dictionary: Permission Denied" in combined_output
    assert "Failed to load ng_words: Permission Denied" in combined_output
    assert "Failed to read volume.txt: Permission Denied" in combined_output
