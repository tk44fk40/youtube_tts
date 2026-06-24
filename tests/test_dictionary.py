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
    assert (
        processor.replace_words("I like apple and google")
        == "I like りんご and グーグル"
    )
    assert processor.replace_words("I like Apple") == "I like りんご"

def test_contains_ng_word(mock_config):
    processor = TextProcessor(mock_config)
    assert processor.contains_ng_word("this is spam email") is True
    assert processor.contains_ng_word("normal message") is False
    assert processor.contains_ng_word("This is SPAM") is True

def test_normalize_comment(mock_config):
    processor = TextProcessor(mock_config)
    
    # Normalize author name (appending suffix)
    #
    # 投稿者の正規化（「さん」の付与）
    assert processor.normalize_author("Taro") == "Taroさん"
    assert processor.normalize_author("Taroさん") == "Taroさん"
    assert processor.normalize_author("@Taro") == "Taroさん"

    # Normalize message
    #
    # メッセージの正規化
    msg = (
        "こんにちは！ http://example.com/test 😄 wwwww "
        "youtubeでgoogleを見よう"
    )
    # Remove URL, remove emoji 😄, convert wwwww to 'わら',
    # and convert google to 'グーグル'.
    # 'こんにちは！' is normalized to 'こんにちは!'.
    #
    # URLの除去、😄（絵文字）の除去、
    # wwwwwを ' わら ' に変換、
    # googleを 'グーグル' に変換
    # 「こんにちは！」は「こんにちは!」に正規化される
    expected = "こんにちは!    わら  youtubeでグーグルを見よう"
    assert processor.normalize_message(msg) == expected

def test_normalize_comment_invalid_input(mock_config):
    processor = TextProcessor(mock_config)
    
    # Handling of empty string
    #
    # 空文字列のハンドリング
    assert processor.normalize_author("") == ""
    assert processor.normalize_author("   ") == ""
    
    assert processor.normalize_message("") == ""
    assert processor.normalize_message("   ") == ""
    
    # Author name containing spaces
    #
    # スペースを含む投稿者名
    assert processor.normalize_author(" @ ") == ""
    
    # Emoji-only message becomes empty string after normalization
    #
    # 絵文字のみのメッセージは、
    # 正規化後に空文字列になること
    assert processor.normalize_message("😄👍") == ""

def test_normalize_author_custom_suffix(mock_config, monkeypatch):
    # Case 1: Custom suffix
    #
    # ケース 1: カスタムサフィックス（「ちゃん」）
    monkeypatch.setenv("VOICEVOX_AUTHOR_SUFFIX", "ちゃん")
    processor = TextProcessor(mock_config)
    assert processor.normalize_author("Taro") == "Taroちゃん"
    assert processor.normalize_author("Taroちゃん") == "Taroちゃん"
    
    # Case 2: No suffix (empty string)
    #
    # ケース 2: サフィックスなし（空文字列）
    monkeypatch.setenv("VOICEVOX_AUTHOR_SUFFIX", "")
    processor2 = TextProcessor(mock_config)
    assert processor2.normalize_author("Taro") == "Taro"


def test_normalize_message_grass(mock_config):
    processor = TextProcessor(mock_config)
    
    # --- Patterns to be converted ---
    # The entire text consists only of 'w' or 'ww'
    # (Case-insensitive, full-width/half-width insensitive)
    #
    # --- 変換されるパターン ---
    # 文章全体が w または ww のみ
    # （大文字・小文字、全角・半角問わず）
    assert processor.normalize_message("w") == "わら"
    assert processor.normalize_message("ww") == "わら"
    assert processor.normalize_message("W") == "わら"
    assert processor.normalize_message("WW") == "わら"
    assert processor.normalize_message("ｗ") == "わら"
    assert processor.normalize_message("ｗｗ") == "わら"
    assert processor.normalize_message("Ww") == "わら"
    
    # Immediately after Japanese characters
    #
    # 日本語の直後
    assert (
        processor.normalize_message("こんにちはw") == "こんにちは わら"
    )
    assert (
        processor.normalize_message("こんにちはww") == "こんにちは わら"
    )
    
    # Immediately after punctuation, exclamation, or question marks
    #
    # 句読点・感嘆符・疑問符の直後
    assert processor.normalize_message("おーい！w") == "おーい! わら"
    assert (
        processor.normalize_message("どうした？ww") == "どうした? わら"
    )
    assert processor.normalize_message("はい、w") == "はい、 わら"
    assert (
        processor.normalize_message("そうです。ww") == "そうです。 わら"
    )
    
    # Immediately after closing brackets
    #
    # 閉じ括弧の直後
    assert processor.normalize_message("(笑)w") == "(笑) わら"
    assert (
        processor.normalize_message("「テスト」w") == "「テスト」 わら"
    )

    # Coverage test of all preceding character types for the whitelist
    #
    # ホワイトリスト指定の直前文字種（全種類）の網羅テスト

    # 1. Japanese characters: ひらがな, カタカナ, CJK Unified Ideographs,
    # Iteration marks (ぁ-ん, ァ-ヶ, 一-龠々)
    #
    # 1. 日本語文字: ぁ-ん, ァ-ヶ, 一-龠々
    assert processor.normalize_message("あw") == "あ わら"
    assert processor.normalize_message("アw") == "ア わら"
    assert processor.normalize_message("漢w") == "漢 わら"
    assert processor.normalize_message("々w") == "々 わら"
    # 2. Punctuation/Symbols
    #
    # 2. 句読点・記号: 、。，．・
    assert processor.normalize_message("、w") == "、 わら"
    assert processor.normalize_message("。w") == "。 わら"
    # ',' (full-width) normalizes to ',' (half-width) via NFKC
    #
    # '，' は NFKC で , になる
    assert processor.normalize_message("，w") == ", わら"
    # '.' (full-width) normalizes to '.' (half-width) via NFKC
    #
    # ． は NFKC で . になる
    assert processor.normalize_message("．w") == ". わら"
    assert processor.normalize_message("・w") == "・ わら"
    # 3. Exclamation/Question marks
    #
    # 3. 感嘆符・疑問符: !！?？
    assert processor.normalize_message("!w") == "! わら"
    assert processor.normalize_message("！w") == "! わら"
    assert processor.normalize_message("?w") == "? わら"
    assert processor.normalize_message("？w") == "? わら"
    # 4. Closing brackets
    #
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
    # 5. Prolonged sound marks/Wave dashes
    #
    # 5. 長音記号・波ダッシュ: ー〜～~
    assert processor.normalize_message("そっかーw") == "そっかー わら"
    assert (
        processor.normalize_message("はぃーーww") == "はぃーー わら"
    )
    # '〜' (wave dash) remains unchanged after NFKC normalization
    #
    # 〜 は NFKC で変換されずそのまま
    assert processor.normalize_message("〜w") == "〜 わら"
    # '～' (full-width tilde) normalizes to '~' (half-width tilde) via NFKC
    #
    # ～ は NFKC で ~ になる
    assert processor.normalize_message("～w") == "~ わら"
    assert processor.normalize_message("~w") == "~ わら"
    
    # --- Patterns not to be converted (safe patterns) ---
    # Part of an English word
    #
    # --- 変換されない（安全な）パターン ---
    # 英単語の一部
    assert processor.normalize_message("show") == "show"
    assert processor.normalize_message("now") == "now"
    
    # Number followed by 'w'
    #
    # 数字＋w
    assert processor.normalize_message("10w") == "10w"
    assert processor.normalize_message("50W") == "50W"
    
    # Immediately after opening brackets
    #
    # 開き括弧の直後（単一の文字としてのwの言及など）
    assert processor.normalize_message("「w」") == "「w」"
    assert processor.normalize_message("(w)") == "(w)"
    
    # Beginning of string with multiple words
    #
    # 文字列の先頭（ただし複数語ある場合）
    assert processor.normalize_message("w hello") == "w hello"


def test_normalize_message_stamps_and_kaomoji(mock_config):
    processor = TextProcessor(mock_config)
    
    # Removal of YouTube custom emojis (colon notation)
    #
    # YouTubeスタンプ (コロン表記) の除去
    assert processor.normalize_message(":face-purple-crying:") == ""
    assert (
        processor.normalize_message("こんにちは！:custom_stamp:")
        == "こんにちは!"
    )
    assert (
        processor.normalize_message(":emoji-1: 元気？ :emoji-2:")
        == "元気?"
    )
    
    # Removal of parenthesized emoticons
    #
    # 括弧付き顔文字の除去
    assert (
        processor.normalize_message("よろしく！(^-^)") == "よろしく!"
    )
    assert (
        processor.normalize_message("(´・ω・｀) つかれた") == "つかれた"
    )
    assert (
        processor.normalize_message("どうしたの？(>_<)") == "どうしたの?"
    )
    assert (
        processor.normalize_message("おめでとう(*^-^*)") == "おめでとう"
    )
    
    # Normal parentheses remain
    #
    # 通常の括弧表記は残る
    assert (
        processor.normalize_message("りんご(林檎)を食べる")
        == "りんご(林檎)を食べる"
    )
    assert (
        processor.normalize_message("会議は水曜日(水)です")
        == "会議は水曜日(水)です"
    )
    assert (
        processor.normalize_message("これはテストです(笑)")
        == "これはテストです(笑)"
    )
    assert (
        processor.normalize_message("通常コメント(Taro)")
        == "通常コメント(Taro)"
    )
    
    # Removal of emoticons without parentheses
    #
    # 括弧なしの顔文字の除去
    assert (
        processor.normalize_message("すみませんm(_ _)m") == "すみません"
    )
    assert processor.normalize_message("ごめんm(__)m") == "ごめん"
    assert processor.normalize_message("悲しいT_T") == "悲しい"
    assert (
        processor.normalize_message("もう駄目だorz") == "もう駄目だ"
    )
    
    # Removal of BMP range emojis and symbols
    #
    # BMP領域の絵文字・記号の除去
    assert (
        processor.normalize_message("星空✨きれい⭐") == "星空きれい"
    )



