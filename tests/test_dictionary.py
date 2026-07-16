"""TextProcessor クラスの単体テストを行うモジュールです。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from youtube_tts import AppConfig, TextProcessor


@pytest.fixture
def mock_config() -> MagicMock:
    """テスト用のモック設定オブジェクトを生成します。

    Returns:
        MagicMock: モック化された AppConfig インスタンス。
    """
    config = MagicMock(spec=AppConfig)
    config.replacements = {"apple": "りんご", "google": "グーグル"}
    config.ng_words = {"spam", "ad"}
    return config


def test_text_normalize(mock_config: MagicMock) -> None:
    """全角英数字や半角カナが正しく Unicode 正規化 (NFKC) されるか
    検証します。
    """
    processor = TextProcessor(mock_config)
    assert processor.normalize_text("ＡＢＣ") == "ABC"
    assert processor.normalize_text("ｱｲｳ") == "アイウ"


def test_replace_words(mock_config: MagicMock) -> None:
    """設定された単語置換（辞書置換）が正しく適用されるか検証します。"""
    processor = TextProcessor(mock_config)
    assert (
        processor.replace_words("I like apple and google")
        == "I like りんご and グーグル"
    )
    assert processor.replace_words("I like Apple") == "I like りんご"


def test_contains_ng_word(mock_config: MagicMock) -> None:
    """メッセージに NG ワードが含まれるかどうかの判定を検証します。"""
    processor = TextProcessor(mock_config)
    assert processor.contains_ng_word("this is spam email") is True
    assert processor.contains_ng_word("normal message") is False
    assert processor.contains_ng_word("This is SPAM") is True


def test_normalize_comment(mock_config: MagicMock) -> None:
    """投稿者名とメッセージの正規化処理が正しく連動するか検証します。"""
    processor = TextProcessor(mock_config)

    # 投稿者の正規化（「さん」の付与）を検証します。
    assert processor.normalize_author("Taro") == "Taroさん"
    assert processor.normalize_author("Taroさん") == "Taroさん"
    assert processor.normalize_author("@Taro") == "Taroさん"

    # メッセージの正規化を検証します。
    msg = (
        "こんにちは！ http://example.com/test 😄 wwwww youtubeでgoogleを見よう"
    )
    # URLの除去、😄（絵文字）の除去、
    # wwwwwを ' わら ' に変換、
    # googleを 'グーグル' に変換
    # 「こんにちは！」は「こんにちは!」に正規化されます。
    expected = "こんにちは!    わら  youtubeでグーグルを見よう"
    assert processor.normalize_message(msg) == expected

    # 一括正規化メソッドの検証を行います。
    assert processor.normalize_comment("Taro", "hello") == (
        "Taroさん",
        "hello",
    )


def test_normalize_comment_invalid_input(mock_config: MagicMock) -> None:
    """空文字列やスペース、絵文字のみの無効な入力の挙動を検証します。"""
    processor = TextProcessor(mock_config)

    # 空文字列のハンドリングを検証します。
    assert processor.normalize_author("") == ""
    assert processor.normalize_author("   ") == ""

    assert processor.normalize_message("") == ""
    assert processor.normalize_message("   ") == ""

    # スペースを含む投稿者名を検証します。
    assert processor.normalize_author(" @ ") == ""

    # 絵文字のみのメッセージは、正規化後に空文字列になることを検証します。
    assert processor.normalize_message("😄👍") == ""


def test_normalize_author_custom_suffix(
    mock_config: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """環境変数で指定されたカスタムサフィックスの動作を検証します。"""
    # ケース 1: カスタムサフィックス（「ちゃん」）
    monkeypatch.setenv("VOICEVOX_AUTHOR_SUFFIX", "ちゃん")
    processor = TextProcessor(mock_config)
    assert processor.normalize_author("Taro") == "Taroちゃん"
    assert processor.normalize_author("Taroちゃん") == "Taroちゃん"

    # ケース 2: サフィックスなし（空文字列）
    monkeypatch.setenv("VOICEVOX_AUTHOR_SUFFIX", "")
    processor2 = TextProcessor(mock_config)
    assert processor2.normalize_author("Taro") == "Taro"


def test_normalize_message_grass(mock_config: MagicMock) -> None:
    """文末などの『w』（草）の読み上げテキスト変換ルールを検証します。"""
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

    # 日本語の直後を検証します。
    assert processor.normalize_message("こんにちはw") == "こんにちは わら"
    assert processor.normalize_message("こんにちはww") == "こんにちは わら"

    # 句読点・感嘆符・疑問符の直後を検証します。
    assert processor.normalize_message("おーい！w") == "おーい! わら"
    assert processor.normalize_message("どうした？ww") == "どうした? わら"
    assert processor.normalize_message("はい、w") == "はい、 わら"
    assert processor.normalize_message("そうです。ww") == "そうです。 わら"

    # 閉じ括弧の直後を検証します。
    assert processor.normalize_message("(笑)w") == "(笑) わら"
    assert processor.normalize_message("「テスト」w") == "「テスト」 わら"

    # ホワイトリスト指定の直前文字種（全種類）の網羅テストを行います。

    # 1. 日本語文字: ぁ-ん, ァ-ヶ, 一-龠々
    assert processor.normalize_message("あw") == "あ わら"
    assert processor.normalize_message("アw") == "ア わら"
    assert processor.normalize_message("漢w") == "漢 わら"
    assert processor.normalize_message("々w") == "々 わら"
    # 2. 句読点・記号: 、。，．・
    assert processor.normalize_message("、w") == "、 わら"
    assert processor.normalize_message("。w") == "。 わら"
    # '，' は NFKC で , になります。
    assert processor.normalize_message("，w") == ", わら"
    # ． は NFKC で . になります。
    assert processor.normalize_message("．w") == ". わら"
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
    # 〜 は NFKC で変換されずそのまま残ります。
    assert processor.normalize_message("〜w") == "〜 わら"
    # ～ は NFKC で ~ になります。
    assert processor.normalize_message("～w") == "~ わら"
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


def test_normalize_message_stamps_and_kaomoji(mock_config: MagicMock) -> None:
    """YouTube スタンプや顔文字・絵文字が正しく除去されるか検証します。"""
    processor = TextProcessor(mock_config)

    assert processor.normalize_message(":face-purple-crying:") == ""
    assert (
        processor.normalize_message("こんにちは！:custom_stamp:")
        == "こんにちは!"
    )
    assert processor.normalize_message(":emoji-1: 元気？ :emoji-2:") == "元気?"

    # 括弧付き顔文字の除去を行います。
    assert processor.normalize_message("よろしく！(^-^)") == "よろしく!"
    assert processor.normalize_message("(´・ω・｀) つかれた") == "つかれた"
    assert processor.normalize_message("どうしたの？(>_<)") == "どうしたの?"
    assert processor.normalize_message("おめでとう(*^-^*)") == "おめでとう"

    # 通常の括弧表記は残ります。
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

    # 括弧なしの顔文字の除去を行います。
    assert processor.normalize_message("すみませんm(_ _)m") == "すみません"
    assert processor.normalize_message("ごめんm(__)m") == "ごめん"
    assert processor.normalize_message("悲しいT_T") == "悲しい"
    assert processor.normalize_message("もう駄目だorz") == "もう駄目だ"

    # BMP 領域の絵文字・記号の除去を行います。
    assert processor.normalize_message("星空✨きれい⭐") == "星空きれい"
