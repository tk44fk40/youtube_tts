"""AppConfig クラスの単体テストを行うモジュールです。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from youtube_tts import AppConfig

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import LogCaptureFixture


def test_config_initial_load(tmp_path: Path) -> None:
    """設定ファイルの初期ロードが正常に行われるか検証します。"""
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


def test_config_reload_on_change(tmp_path: Path) -> None:
    """設定ファイルが更新された際に正しく再ロードされるか検証します。"""
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

    # 変更を適用します。
    vol_file.write_text("1.5")
    dict_file.write_text("orange = オレンジ")
    ng_file.write_text("spam")

    config.reload_if_changed()

    assert config.volume_scale == 1.5
    assert config.replacements == {"orange": "オレンジ"}
    assert config.ng_words == {"spam"}

    # タイムスタンプが変わっていない状態で再度リロードを呼び出します。
    # ログ出力やデータの更新が行われないことを確認します。
    config.reload_if_changed()


def test_config_volume_invalid(
    tmp_path: Path, caplog: LogCaptureFixture
) -> None:
    """音量設定ファイルに不正な値がある場合の挙動を検証します。"""
    vol_file = tmp_path / "volume.txt"
    vol_file.write_text("1.0")

    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=tmp_path / "ng.txt",
        volume_path=vol_file,
    )

    # 音量設定ファイルに浮動小数点数として解析できない無効な値が
    # 書き込まれた場合に、音量設定が更新されず、警告ログが出力されることを
    # 検証します。
    vol_file.write_text("invalid_float")
    with caplog.at_level("WARNING"):
        config.reload_if_changed()
    assert config.volume_scale == 1.0
    assert any(
        "volume.txt の値が無効です" in record.message
        for record in caplog.records
    )
    caplog.clear()

    # 音量設定ファイルに許容範囲外（2.0超）の値が書き込まれた場合に、
    # 音量設定が更新されず、情報ログが出力されることを検証します。
    vol_file.write_text("2.5")
    with caplog.at_level("INFO"):
        config.reload_if_changed()
    assert config.volume_scale == 1.0
    assert any(
        "音量スケールが範囲外" in record.message
        for record in caplog.records
    )


def test_config_dictionary_invalid(tmp_path: Path) -> None:
    """辞書ファイルに無効な行が含まれる場合の挙動を検証します。"""
    dict_file = tmp_path / "dictionary.txt"
    dict_file.write_text(
        "apple = 林檎\ninvalid_line_no_equal\nbanana = バナナ", encoding="utf-8"
    )

    config = AppConfig(
        dictionary_path=dict_file,
        ng_words_path=tmp_path / "ng.txt",
        volume_path=tmp_path / "vol.txt",
    )

    # 辞書ファイルにイコールを含まない無効な行が含まれる場合に、
    # その行を無視して正常な行のみがロードされることを検証します。
    assert config.replacements == {"apple": "林檎", "banana": "バナナ"}


def test_config_ng_words_missing_and_empty_lines(tmp_path: Path) -> None:
    """NGワードファイルが不在、または空行を含む場合の挙動を検証します。"""
    # NGワードファイルが存在しない場合に、例外が発生せず、
    # 空の集合が設定されることを検証します。
    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=tmp_path / "non_existent_ng.txt",
        volume_path=tmp_path / "vol.txt",
    )
    assert config.ng_words == set()

    # NGワードファイルに空行や空白行が含まれる場合に、それらが無視されて
    # 有効な単語のみがロードされることを検証します。
    ng_file = tmp_path / "ng_words.txt"
    ng_file.write_text("\n   \nspam\n\n", encoding="utf-8")

    config = AppConfig(
        dictionary_path=tmp_path / "dict.txt",
        ng_words_path=ng_file,
        volume_path=tmp_path / "vol.txt",
    )
    assert config.ng_words == {"spam"}


def test_config_load_os_errors(
    tmp_path: Path, caplog: LogCaptureFixture
) -> None:
    """ファイル読み込み時にOSエラーが発生した場合の挙動を検証します。"""
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

    # タイムスタンプを更新して再ロードを促します。
    time.sleep(0.01)
    dict_file.touch()
    ng_file.touch()
    vol_file.touch()

    with patch("builtins.open", side_effect=OSError("Permission Denied")):
        with caplog.at_level("WARNING"):
            config.reload_if_changed()

    combined_output = "\n".join(record.message for record in caplog.records)

    assert (
        "辞書のロードに失敗しました: Permission Denied"
        in combined_output
    )
    assert (
        "NGワードのロードに失敗しました: Permission Denied"
        in combined_output
    )
    assert (
        "volume.txt の読み込みに失敗しました: Permission Denied"
        in combined_output
    )


def test_config_files_not_exists(tmp_path: Path) -> None:
    """設定ファイルが存在しない場合の挙動を検証します。"""
    config = AppConfig(
        dictionary_path=tmp_path / "non_existent_dict.txt",
        ng_words_path=tmp_path / "non_existent_ng.txt",
        volume_path=tmp_path / "non_existent_vol.txt",
    )
    # 初期状態で設定ファイルがいずれも存在しない場合に、タイムスタンプが
    # Noneのままとなり、空の設定情報が保持されることを検証します。
    assert config.replacements == {}
    assert config.ng_words == set()
    assert config.volume_scale == 1.0

    # ファイルが存在しない状態で再ロードを呼び出しても、設定が更新されず
    # エラーも発生しないことを検証します。
    config.reload_if_changed()
    assert config.volume_scale == 1.0
