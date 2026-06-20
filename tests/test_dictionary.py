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
    
    # Author normalization (san appending)
    assert processor.normalize_author("Taro") == "Taroさん"
    assert processor.normalize_author("Taroさん") == "Taroさん"
    assert processor.normalize_author("@Taro") == "Taroさん"

    # Message normalization
    msg = "こんにちは！ http://example.com/test 😄 wwwww youtubeでgoogleを見よう"
    # URLs removed, 😄 removed, wwwww replaced with ' わら ', google replaced with 'グーグル'
    # 'こんにちは！' is normalized to 'こんにちは!'
    expected = "こんにちは!    わら  youtubeでグーグルを見よう"
    assert processor.normalize_message(msg) == expected

def test_normalize_comment_invalid_input(mock_config):
    processor = TextProcessor(mock_config)
    
    # Empty string handling
    assert processor.normalize_author("") == ""
    assert processor.normalize_author("   ") == ""
    
    assert processor.normalize_message("") == ""
    assert processor.normalize_message("   ") == ""
    
    # Author with spaces
    assert processor.normalize_author(" @ ") == ""
    
    # Emoji-only messages should become empty strings after normalization
    assert processor.normalize_message("😄👍") == ""

def test_normalize_author_custom_suffix(mock_config, monkeypatch):
    # Case 1: Custom suffix ("ちゃん")
    monkeypatch.setenv("VOICEVOX_AUTHOR_SUFFIX", "ちゃん")
    processor = TextProcessor(mock_config)
    assert processor.normalize_author("Taro") == "Taroちゃん"
    assert processor.normalize_author("Taroちゃん") == "Taroちゃん"
    
    # Case 2: No suffix (empty string)
    monkeypatch.setenv("VOICEVOX_AUTHOR_SUFFIX", "")
    processor2 = TextProcessor(mock_config)
    assert processor2.normalize_author("Taro") == "Taro"

