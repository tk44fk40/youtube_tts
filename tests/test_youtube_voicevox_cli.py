import pytest
import os
from unittest.mock import patch, MagicMock

# Import main function
#
# main 関数をインポート
from youtube_voicevox import main

@pytest.fixture(autouse=True)
def clean_environ():
    with patch.dict(os.environ, {"VOICEVOX_TTS_TEST": ""}):
        yield

@pytest.fixture(autouse=True)
def mock_voicevox_client_get_speakers():
    with patch(
        "youtube_voicevox.VoicevoxClient.get_speakers"
    ) as mock_get_speakers:
        yield mock_get_speakers

@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
@patch("sounddevice.query_devices")
def test_cli_device_option(
    mock_query, mock_audio_player_class, mock_app_class, mock_chat_client,
    mock_auth
):
    # Set up mocks
    #
    # モックをセットアップする
    mock_query.return_value = {"name": "test_device", "index": 6}
    
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance
    
    # Test with -d option specified
    #
    # -d オプションを指定してテスト
    with patch("sys.argv", ["youtube_voicevox.py", "-d", "6", "video123"]):
        main()
        
    # Verify that AudioPlayer was initialized with default_device=6
    #
    # AudioPlayer が default_device=6 で初期化されたことを検証
    mock_audio_player_class.assert_called_with(default_device=6)
    mock_chat_client_instance.extract_video_id.assert_called_with("video123")
    
    # Verify that YouTubeTtsApp was instantiated and run was called
    #
    # YouTubeTtsApp がインスタンス化され、run が呼び出されたことを検証
    mock_app_class.assert_called_once()
    mock_app_instance.run.assert_called_once()


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
@patch("sounddevice.query_devices")
def test_cli_device_env_var(
    mock_query, mock_audio_player_class, mock_app_class, mock_chat_client,
    mock_auth
):
    # Set up mocks
    #
    # モックをセットアップする
    mock_query.return_value = {"name": "test_device", "index": 6}
    
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance
    
    # Test with VOICEVOX_DEVICE environment variable
    #
    # VOICEVOX_DEVICE 環境変数を用いてテスト
    with patch.dict(os.environ, {"VOICEVOX_DEVICE": "6"}):
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
            
    # Verify that AudioPlayer was initialized with default_device=6
    #
    # AudioPlayer が default_device=6 で初期化されたことを検証
    mock_audio_player_class.assert_called_with(default_device=6)


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.get_project_id")
def test_cli_quota_options(
    mock_get_project_id, mock_app_class, mock_chat_client, mock_auth
):
    mock_get_project_id.return_value = "test-project-123"
    
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_creds = MagicMock()
    mock_auth_instance.get_credentials.return_value = mock_creds
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance
    
    from youtube_tts import QUOTA_SCOPES
    
    # Test with --quota-talk and custom intervals specified
    #
    # --quota-talk およびカスタムの間隔を指定してテスト
    with patch(
        "sys.argv",
        [
            "youtube_voicevox.py",
            "--quota-talk",
            "--chat-interval",
            "10",
            "--quota-interval",
            "30",
            "video123"
        ]
    ):
        main()
        
    # Verify that auth was called with QUOTA_SCOPES
    #
    # auth が QUOTA_SCOPES で呼び出されたことを検証
    mock_auth.assert_called_with(
        client_secret_path="client_secret.json",
        token_path="token.json",
        scopes=QUOTA_SCOPES
    )
    
    # Verify that get_project_id was called
    #
    # get_project_id が呼び出されたことを検証
    mock_get_project_id.assert_called_once()
    
    # Verify that app.run was called with correct parameters
    #
    # app.run が正しいパラメータで呼び出されたことを検証
    mock_app_instance.run.assert_called_with(
        mock_chat_client_instance,
        "video123",
        creds=mock_creds,
        quota_check=True,
        quota_talk=True,
        tts_test=None,
        chat_interval=10.0,
        quota_interval=30.0,
        stream_check_interval=180.0,
        project_id="test-project-123",
        verbose=False,
        backlog_seconds=10,
        backlog_counts=100
    )

    # Test with --verbose and custom --stream-check-interval specified
    #
    # --verbose およびカスタムの
    # --stream-check-interval を指定してテスト
    mock_app_instance.run.reset_mock()
    with patch(
        "sys.argv",
        [
            "youtube_voicevox.py",
            "--quota-talk",
            "--chat-interval",
            "10",
            "--quota-interval",
            "30",
            "--stream-check-interval",
            "120",
            "-v",
            "video123"
        ]
    ):
        main()

    mock_app_instance.run.assert_called_with(
        mock_chat_client_instance,
        "video123",
        creds=mock_creds,
        quota_check=True,
        quota_talk=True,
        tts_test=None,
        chat_interval=10.0,
        quota_interval=30.0,
        stream_check_interval=120.0,
        project_id="test-project-123",
        verbose=True,
        backlog_seconds=10,
        backlog_counts=100
    )


# ==============================================================================
# Test CLI exception handling and fallback processing
#
# CLI 例外ハンドリング・フォールバック処理のテスト
# ==============================================================================
@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
@patch("sounddevice.query_devices")
def test_cli_device_option_string_name(
    mock_query, mock_audio_player_class, mock_app_class, mock_chat_client,
    mock_auth
):
    mock_query.return_value = {"name": "MyDevice", "index": 3}
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    with patch(
        "sys.argv", ["youtube_voicevox.py", "-d", "MyDevice", "video123"]
    ):
        main()
    mock_audio_player_class.assert_called_with(default_device="MyDevice")


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
@patch("sounddevice.query_devices")
def test_cli_device_option_query_failure(
    mock_query, mock_audio_player_class, mock_app_class, mock_chat_client,
    mock_auth
):
    mock_query.side_effect = Exception("Sounddevice Error")
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    # Monitor logger warning messages
    #
    # ロガーの warning メッセージを監視
    with patch("youtube_voicevox.setup_logger") as mock_setup_logger:
        mock_logger = MagicMock()
        mock_setup_logger.return_value = mock_logger
        with patch("sys.argv", ["youtube_voicevox.py", "-d", "6", "video123"]):
            main()
        mock_logger.warning.assert_called_with(
            "デバイス情報の取得に失敗しました: "
            "Sounddevice Error"
        )


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
def test_cli_auth_failure(mock_app_class, mock_chat_client, mock_auth):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.side_effect = Exception("Auth Failure")

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
    assert exc_info.value.code == 1


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
def test_cli_video_id_auto_detection_success(
    mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.get_current_live_video_id.return_value = (
        "live_vid", "live_url"
    )

    with patch("sys.argv", ["youtube_voicevox.py"]):
        main()
    mock_chat_client_instance.get_current_live_video_id.assert_called_once()


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
def test_cli_video_id_auto_detection_failure(
    mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.get_current_live_video_id.side_effect = (
        RuntimeError("No live stream found")
    )

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["youtube_voicevox.py"]):
            main()
    assert exc_info.value.code == 1


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.get_project_id")
def test_cli_project_id_load_failure(
    mock_get_project_id, mock_app_class, mock_chat_client, mock_auth
):
    mock_get_project_id.side_effect = Exception("File not found")
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    with patch(
        "sys.argv", ["youtube_voicevox.py", "--quota-check", "video123"]
    ):
        main()
    
    args, kwargs = mock_app_instance.run.call_args
    assert kwargs["quota_check"] is False


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
def test_cli_unexpected_error_in_worker(
    mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance
    
    # Raise exception in run
    #
    # run で例外を投げる
    mock_app_instance.run.side_effect = Exception("Worker Unexpected Crash")

    with patch("youtube_voicevox.setup_logger") as mock_setup_logger:
        mock_logger = MagicMock()
        mock_setup_logger.return_value = mock_logger
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
        mock_logger.exception.assert_called_with("Unexpected error")


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_speed_option(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    # Specify speed argument
    #
    # speed 引数を指定
    with patch(
        "sys.argv", ["youtube_voicevox.py", "--speed", "1.5", "video123"]
    ):
        main()
        
    # Verify config.speed_scale is 1.5 when app is initialized
    #
    # app が初期化された際、その config.speed_scale が
    # 1.5 であることを確認する
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].speed_scale == 1.5


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_speed_env_var(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    # Specify VOICEVOX_SPEED_SCALE env var
    #
    # 環境変数 VOICEVOX_SPEED_SCALE を指定
    with patch.dict(os.environ, {"VOICEVOX_SPEED_SCALE": "1.8"}):
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
            
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].speed_scale == 1.8


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_speed_env_var_invalid(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    # Specify invalid VOICEVOX_SPEED_SCALE env var (fallback to 1.0)
    #
    # 無効な環境変数 VOICEVOX_SPEED_SCALE を指定
    # （フォールバックしてデフォルト1.0になること）
    with patch.dict(os.environ, {"VOICEVOX_SPEED_SCALE": "invalid"}):
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
            
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].speed_scale == 1.0


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_speed_boost_options(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    # Specify argument
    #
    # 引数を指定
    with patch(
        "sys.argv",
        [
            "youtube_voicevox.py",
            "--auto-speed-boost",
            "--max-speed",
            "1.8",
            "video123"
        ]
    ):
        main()
        
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].auto_speed_boost is True
    assert kwargs["config"].max_speed == 1.8


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_speed_boost_env_vars(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    # Specify environment variable
    #
    # 環境変数を指定
    with patch.dict(
        os.environ,
        {"VOICEVOX_AUTO_SPEED_BOOST": "true", "VOICEVOX_MAX_SPEED": "2.0"}
    ):
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
            
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].auto_speed_boost is True
    assert kwargs["config"].max_speed == 2.0


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_max_speed_clip(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    # Specify value exceeding limits
    #
    # 限界値を超える値を指定
    with patch(
        "sys.argv", ["youtube_voicevox.py", "--max-speed", "3.0", "video123"]
    ):
        main()
        
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].max_speed == 2.2


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_max_speed_env_var_invalid(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    with patch.dict(os.environ, {"VOICEVOX_MAX_SPEED": "invalid_speed"}):
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
            
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].max_speed == 2.2


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_volume_scale_env_var_invalid(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    with patch.dict(os.environ, {"VOICEVOX_VOLUME_SCALE": "invalid_volume"}):
        with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
            main()
            
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].volume_scale is not None


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_chat_log_option(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"

    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    with patch(
        "sys.argv",
        ["youtube_voicevox.py", "--chat-log", "custom_path.jsonl", "video123"]
    ):
        main()
        
    args, kwargs = mock_app_class.call_args
    assert kwargs["config"].chat_log_path == "custom_path.jsonl"


# ==============================================================================
# Coverage completion tests
# 
# カバレッジ補完テスト
# ==============================================================================
@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_voicevox_connection_failure_warning(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    """If VOICEVOX connection check fails: warning is output (L805-809)
    
    VOICEVOX接続確認に失敗した場合:
    warning が出力される（L805-809）
    """
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    with patch(
        "youtube_voicevox.VoicevoxClient.get_speakers",
        side_effect=Exception("Connection refused")
    ):
        with patch("youtube_voicevox.setup_logger") as mock_setup_logger:
            mock_logger = MagicMock()
            mock_setup_logger.return_value = mock_logger
            with patch("sys.argv", ["youtube_voicevox.py", "video123"]):
                main()

    mock_logger.warning.assert_any_call(
        "VOICEVOX サーバーへの接続確認に失敗しました。"
    )


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
@patch("youtube_voicevox.AudioPlayer")
def test_cli_voicevox_connection_failure_verbose(
    mock_audio_player, mock_app_class, mock_chat_client, mock_auth
):
    """If VOICEVOX connection check fails with verbose mode:
    debug log is output (L808-809)
    
    VOICEVOX接続確認に失敗した場合 verbose 時:
    debug ログが出力される（L808-809）
    """
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.return_value = MagicMock()
    mock_chat_client_instance = MagicMock()
    mock_chat_client.return_value = mock_chat_client_instance
    mock_chat_client_instance.extract_video_id.return_value = "video123"
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance

    with patch(
        "youtube_voicevox.VoicevoxClient.get_speakers",
        side_effect=Exception("Connection refused")
    ):
        with patch("youtube_voicevox.setup_logger") as mock_setup_logger:
            mock_logger = MagicMock()
            mock_setup_logger.return_value = mock_logger
            with patch("sys.argv", ["youtube_voicevox.py", "-v", "video123"]):
                main()

    mock_logger.debug.assert_any_call("  (エラー詳細: Connection refused)")


@patch("youtube_voicevox.YouTubeAuthenticator")
@patch("youtube_voicevox.YouTubeChatClient")
@patch("youtube_voicevox.YouTubeTtsApp")
def test_cli_auth_failure_verbose(mock_app_class, mock_chat_client, mock_auth):
    """If authentication fails with verbose mode:
    debug log is output (L823)
    
    認証失敗かつ verbose 時: debug ログが出力される（L823）
    """
    mock_auth_instance = MagicMock()
    mock_auth.return_value = mock_auth_instance
    mock_auth_instance.get_credentials.side_effect = Exception(
        "Auth Verbose Failure"
    )

    with patch("youtube_voicevox.setup_logger") as mock_setup_logger:
        mock_logger = MagicMock()
        mock_setup_logger.return_value = mock_logger
        with pytest.raises(SystemExit):
            with patch("sys.argv", ["youtube_voicevox.py", "-v", "video123"]):
                main()

    mock_logger.debug.assert_any_call(
        "  (エラー詳細: Auth Verbose Failure)"
    )
