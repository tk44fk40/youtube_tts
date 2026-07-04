"""音声合成および再生ワーカー（playback_worker）のテストモジュール。"""

from unittest.mock import patch

from youtube_tts import CommentItem


def test_speak_success(app):
    """音声合成が正常に成功し、再生まで連動するか検証。"""
    app.voicevox_client.synthesize.return_value = b"mock_wav"
    app.speak("テストテキスト")

    app.voicevox_client.synthesize.assert_called_with(
        text="テストテキスト",
        volume_scale=0.5,
        speed_scale=1.0,
        target_sample_rate=app.audio_player.target_sample_rate,
    )
    app.audio_player.play_wav.assert_called_with(b"mock_wav")

    # 明示的な speed_scale を指定した発話
    app.speak("テストテキスト2", speed_scale=1.5)
    app.voicevox_client.synthesize.assert_called_with(
        text="テストテキスト2",
        volume_scale=0.5,
        speed_scale=1.5,
        target_sample_rate=app.audio_player.target_sample_rate,
    )


def test_speak_failure(app):
    """音声合成失敗時の例外テスト

    音声合成失敗時に例外をキャッチし、
    エラーログを出力してクラッシュしないか検証（verbose=False）。
    """
    app.voicevox_client.synthesize.side_effect = Exception("VOICEVOX Error")
    app.verbose = False

    with (
        patch.object(app.logger, "error") as mock_error,
        patch.object(app.logger, "debug") as mock_debug,
    ):
        app.speak("エラーテスト")
        app.audio_player.play_wav.assert_not_called()

        assert mock_error.call_count == 3
        mock_error.assert_any_call(
            "[ERROR] 音声の合成または再生に失敗しました。"
        )
        mock_debug.assert_not_called()


def test_speak_failure_verbose(app):
    """音声合成失敗時のデバッグログテスト

    音声合成失敗時に詳細なデバッグログが出力されるか検証（verbose=True）。
    """
    app.voicevox_client.synthesize.side_effect = Exception("VOICEVOX Error")
    app.verbose = True

    with (
        patch.object(app.logger, "error") as mock_error,
        patch.object(app.logger, "debug") as mock_debug,
    ):
        app.speak("エラーテスト")
        app.audio_player.play_wav.assert_not_called()

        assert mock_error.call_count == 3
        mock_debug.assert_called_once_with("  (エラー詳細: VOICEVOX Error)")


def test_playback_worker(app):
    """再生用文字列の整形テスト

    キューからコメントを取得し、正しく再生用文字列に整形されるか検証。
    """
    app.comment_queue.put(("User1", "こんにちは"))

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text, *args, **kwargs):
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()

        mock_speak.assert_called_once_with("User1 こんにちは", speed_scale=1.0)


def test_playback_worker_dynamic_speed_boost(app):
    """再生速度が自動ブーストのテスト

    キュー内の滞留文字数に応じて再生速度が自動ブーストされるか検証。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    app.comment_queue.put(CommentItem("User1", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 175, 180))
    app.queued_char_count = 191

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text, speed_scale=None):
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()

        assert app.queued_char_count == 180
        mock_speak.assert_called_once_with("User1 Hello", speed_scale=1.8)


def test_playback_worker_backward_compatibility(app):
    """キューの互換性テスト

    旧仕様の2要素タプルがキューに混在しても互換性を維持して処理できるか検証。
    """
    app.comment_queue.put(("UserOld", "HelloOld"))
    app.queued_char_count = 15

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text, speed_scale=None):
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()

        assert app.queued_char_count == 0
        mock_speak.assert_called_once_with("UserOld HelloOld", speed_scale=1.0)


def test_playback_worker_speed_boost_lower_limit(app):
    """自動ブースト時の通常速度が維持維持テスト

    自動ブースト発生の閾値未満では通常速度が維持されるか検証。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.2

    app.comment_queue.put(CommentItem("User", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 25, 30))
    app.queued_char_count = 41

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text, speed_scale=None):
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()
        mock_speak.assert_called_once_with("User Hello", speed_scale=1.0)


def test_playback_worker_speed_boost_upper_limit(app):
    """自動ブースト時の最大速度維持テスト

    大量の文字数が滞留しても設定された最大速度を超えないか検証。
    """
    app.config.auto_speed_boost = True
    app.config.speed_scale = 1.0
    app.config.max_speed = 2.0

    app.comment_queue.put(CommentItem("User", "Hello", 11))
    app.comment_queue.put(CommentItem("User2", "A" * 295, 300))
    app.queued_char_count = 311

    with patch.object(app, "speak") as mock_speak:

        def side_effect(text, speed_scale=None):
            app.stop_event.set()

        mock_speak.side_effect = side_effect
        app.playback_worker()
        mock_speak.assert_called_once_with("User Hello", speed_scale=2.0)
