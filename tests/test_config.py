import pytest
from pathlib import Path
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
        volume_path=vol_file
    )

    assert config.volume_scale == 0.5
    assert config.replacements == {"apple": "林檎", "banana": "バナナ"}
    assert config.ng_words == {"badword"}

def test_config_reload_on_change(tmp_path):
    dict_file = tmp_path / "dictionary.txt"
    ng_file = tmp_path / "ng_words.txt"
    vol_file = tmp_path / "volume.txt"

    dict_file.touch()
    ng_file.touch()
    vol_file.write_text("1.0")

    config = AppConfig(
        dictionary_path=dict_file,
        ng_words_path=ng_file,
        volume_path=vol_file
    )

    assert config.volume_scale == 1.0

    # Apply changes
    vol_file.write_text("1.5")
    dict_file.write_text("orange = オレンジ")
    ng_file.write_text("spam")

    config.reload_if_changed()

    assert config.volume_scale == 1.5
    assert config.replacements == {"orange": "オレンジ"}
    assert config.ng_words == {"spam"}

def test_config_volume_invalid(tmp_path, capsys):
    vol_file = tmp_path / "volume.txt"
    vol_file.write_text("1.0")

    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=tmp_path / "ng.txt",
        volume_path=vol_file
    )

    # Invalid case 1: Not a float
    vol_file.write_text("invalid_float")
    config.reload_if_changed()
    assert config.volume_scale == 1.0
    captured = capsys.readouterr()
    assert "Failed to reload volume.txt" in captured.out or "Failed to reload volume.txt" in captured.err

    # Invalid case 2: Out of range (max 2.0)
    vol_file.write_text("2.5")
    config.reload_if_changed()
    assert config.volume_scale == 1.0
    captured = capsys.readouterr()
    assert "volume scale out of range" in captured.out or "volume scale out of range" in captured.err

def test_config_dictionary_invalid(tmp_path):
    dict_file = tmp_path / "dictionary.txt"
    dict_file.write_text("apple = 林檎\ninvalid_line_no_equal\nbanana = バナナ", encoding="utf-8")

    config = AppConfig(
        dictionary_path=dict_file,
        ng_words_path=tmp_path / "ng.txt",
        volume_path=tmp_path / "vol.txt"
    )

    # Ignore invalid line and load normal lines
    assert config.replacements == {"apple": "林檎", "banana": "バナナ"}

def test_config_ng_words_missing_and_empty_lines(tmp_path):
    # Non-existent file
    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=tmp_path / "non_existent_ng.txt",
        volume_path=tmp_path / "vol.txt"
    )
    assert config.ng_words == set()

    # Empty/whitespace lines
    ng_file = tmp_path / "ng_words.txt"
    ng_file.write_text("\n   \nspam\n\n", encoding="utf-8")
    
    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=ng_file,
        volume_path=tmp_path / "vol.txt"
    )
    assert config.ng_words == {"spam"}
