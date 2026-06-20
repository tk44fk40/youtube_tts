import pytest
from unittest.mock import MagicMock
from youtube_tts import TextProcessor, AppConfig

@pytest.fixture
def mock_config():
    config = MagicMock(spec=AppConfig)
    config.replacements = {"apple": "りんご", "google": "グーグル"}
    config.ng_words = {"spam", "ad"}
    return config

def test_text_normalize(mock_config):
    processor = TextProcessor(mock_config)
    assert processor.normalize_text("ＡＢＣ") == "ABC"
    assert processor.normalize_text("ｱｲｳ") == "アイウ"

def test_replace_words(mock_config):
    processor = TextProcessor(mock_config)
    assert processor.replace_words("I like apple and google") == "I like りんご and グーグル"
    assert processor.replace_words("I like Apple") == "I like りんご"

def test_contains_ng_word(mock_config):
    processor = TextProcessor(mock_config)
    assert processor.contains_ng_word("this is spam email") is True
    assert processor.contains_ng_word("normal message") is False
    assert processor.contains_ng_word("This is SPAM") is True

def test_normalize_comment(mock_config):
    processor = TextProcessor(mock_config)
    
    # 投稿者の正規化（「さん」の付与）
    assert processor.normalize_author("Taro") == "Taroさん"
    assert processor.normalize_author("Taroさん") == "Taroさん"
    assert processor.normalize_author("@Taro") == "Taroさん"

    # メッセージの正規化
    msg = "こんにちは！ http://example.com/test 😄 wwwww youtubeでgoogleを見よう"
    # URLの除去、😄（絵文字）の除去、wwwwwを ' わら ' に変換、googleを 'グーグル' に変換
    # 「こんにちは！」は「こんにちは!」に正規化される
    expected = "こんにちは!    わら  youtubeでグーグルを見よう"
    assert processor.normalize_message(msg) == expected

def test_normalize_comment_invalid_input(mock_config):
    processor = TextProcessor(mock_config)
    
    # 空文字列のハンドリング
    assert processor.normalize_author("") == ""
    assert processor.normalize_author("   ") == ""
    
    assert processor.normalize_message("") == ""
    assert processor.normalize_message("   ") == ""
    
    # スペースを含む投稿者名
    assert processor.normalize_author(" @ ") == ""
    
    # 絵文字のみのメッセージは、正規化後に空文字列になること
    assert processor.normalize_message("😄👍") == ""

def test_normalize_author_custom_suffix(mock_config, monkeypatch):
    # ケース 1: カスタムサフィックス（「ちゃん」）
    monkeypatch.setenv("VOICEVOX_AUTHOR_SUFFIX", "ちゃん")
    processor = TextProcessor(mock_config)
    assert processor.normalize_author("Taro") == "Taroちゃん"
    assert processor.normalize_author("Taroちゃん") == "Taroちゃん"
    
    # ケース 2: サフィックスなし（空文字列）
    monkeypatch.setenv("VOICEVOX_AUTHOR_SUFFIX", "")
    processor2 = TextProcessor(mock_config)
    assert processor2.normalize_author("Taro") == "Taro"

