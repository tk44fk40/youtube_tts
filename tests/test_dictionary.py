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


def test_normalize_message_grass(mock_config):
    processor = TextProcessor(mock_config)
    
    # --- 変換されるパターン ---
    # 文章全体が w または ww のみ（大文字・小文字、全角・半角問わず）
    assert processor.normalize_message("w") == "わら"
    assert processor.normalize_message("ww") == "わら"
    assert processor.normalize_message("W") == "わら"
    assert processor.normalize_message("WW") == "わら"
    assert processor.normalize_message("ｗ") == "わら"
    assert processor.normalize_message("ｗｗ") == "わら"
    assert processor.normalize_message("Ww") == "わら"
    
    # 日本語の直後
    assert processor.normalize_message("こんにちはw") == "こんにちは わら"
    assert processor.normalize_message("こんにちはww") == "こんにちは わら"
    
    # 句読点・感嘆符・疑問符の直後
    assert processor.normalize_message("おーい！w") == "おーい! わら"
    assert processor.normalize_message("どうした？ww") == "どうした? わら"
    assert processor.normalize_message("はい、w") == "はい、 わら"
    assert processor.normalize_message("そうです。ww") == "そうです。 わら"
    
    # 閉じ括弧の直後
    assert processor.normalize_message("(笑)w") == "(笑) わら"
    assert processor.normalize_message("「テスト」w") == "「テスト」 わら"

    # ホワイトリスト指定の直前文字種（全種類）の網羅テスト
    # 1. 日本語文字: ぁ-ん, ァ-ヶ, 一-龠々
    assert processor.normalize_message("あw") == "あ わら"
    assert processor.normalize_message("アw") == "ア わら"
    assert processor.normalize_message("漢w") == "漢 わら"
    assert processor.normalize_message("々w") == "々 わら"
    # 2. 句読点・記号: 、。，．・
    assert processor.normalize_message("、w") == "、 わら"
    assert processor.normalize_message("。w") == "。 わら"
    assert processor.normalize_message("，w") == ", わら"  # ， は NFKC で , になる
    assert processor.normalize_message("．w") == ". わら"  # ． は NFKC で . になる
    assert processor.normalize_message("・w") == "・ わら"
    # 3. 感嘆符・疑問符: !！?？
    assert processor.normalize_message("!w") == "! わら"
    assert processor.normalize_message("！w") == "! わら"
    assert processor.normalize_message("?w") == "? わら"
    assert processor.normalize_message("？w") == "? わら"
    # 4. 閉じ括弧類: ) ） ] ］ } ｝ > ＞ 」 』
    assert processor.normalize_message(")w") == ") わら"
    assert processor.normalize_message("）w") == ") わら"
    assert processor.normalize_message("]w") == "] わら"
    assert processor.normalize_message("］w") == "] わら"
    assert processor.normalize_message("}w") == "} わら"
    assert processor.normalize_message("｝w") == "} わら"
    assert processor.normalize_message(">w") == "> わら"
    assert processor.normalize_message("＞w") == "> わら"
    assert processor.normalize_message("」w") == "」 わら"
    assert processor.normalize_message("』w") == "』 わら"
    # 5. 長音記号・波ダッシュ: ー〜～~
    assert processor.normalize_message("そっかーw") == "そっかー わら"
    assert processor.normalize_message("はぃーーww") == "はぃーー わら"
    assert processor.normalize_message("〜w") == "〜 わら"  # 〜 は NFKC で変換されずそのまま
    assert processor.normalize_message("～w") == "~ わら"  # ～ は NFKC で ~ になる
    assert processor.normalize_message("~w") == "~ わら"
    
    # --- 変換されない（安全な）パターン ---
    # 英単語の一部
    assert processor.normalize_message("show") == "show"
    assert processor.normalize_message("now") == "now"
    
    # 数字＋w
    assert processor.normalize_message("10w") == "10w"
    assert processor.normalize_message("50W") == "50W"
    
    # 開き括弧の直後（単一の文字としてのwの言及など）
    assert processor.normalize_message("「w」") == "「w」"
    assert processor.normalize_message("(w)") == "(w)"
    
    # 文字列の先頭（ただし複数語ある場合）
    assert processor.normalize_message("w hello") == "w hello"


