# Copyright 2026 tk44fk40
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""youtube_tts.constants モジュールの全定数を検証するユニットテストです。"""

from youtube_tts import constants


def test_voicevox_constants() -> None:
    """1. VOICEVOX 関連定数を検証します。"""
    assert constants.DEFAULT_VOICEVOX_URL == "http://127.0.0.1:50021"
    assert constants.DEFAULT_VOICEVOX_HOST == "127.0.0.1"
    assert constants.DEFAULT_VOICEVOX_PORT == 50021
    assert constants.DEFAULT_VOICEVOX_BASE_URL == "http://127.0.0.1:50021"
    assert constants.DEFAULT_SPEAKER_ID == 3
    assert constants.DEFAULT_SPEED_SCALE == 1.0
    assert constants.DEFAULT_VOLUME_SCALE == 1.0
    assert constants.DEFAULT_MAX_SPEED == 2.2
    assert constants.DEFAULT_CONTAINER_NAME == "voicevox-engine"
    assert (
        constants.DEFAULT_CONTAINER_IMAGE
        == "docker.io/voicevox/voicevox_engine:cpu-latest"
    )
    assert constants.DEFAULT_CONTAINER_PORT == 50021
    assert constants.DEFAULT_CONTAINER_HOST == "127.0.0.1"
    assert constants.DEFAULT_LOCK_FILE_PATH == "/tmp/youtube_tts_voicevox_runners.lock"
    assert constants.DEFAULT_STATE_FILE_PATH == "/tmp/youtube_tts_voicevox_runners.json"
    assert constants.DEFAULT_CONTAINER_LOCK_FILE == constants.DEFAULT_LOCK_FILE_PATH
    assert constants.DEFAULT_CONTAINER_STATE_FILE == constants.DEFAULT_STATE_FILE_PATH


def test_obs_constants() -> None:
    """2. OBS 連携関連定数を検証します。"""
    assert constants.DEFAULT_OBS_HOST == "localhost"
    assert constants.DEFAULT_OBS_PORT == 4455


def test_interval_and_backlog_constants() -> None:
    """3. インターバル・監視・バックログデフォルト値を検証します。"""
    assert constants.DEFAULT_CHAT_INTERVAL == 20.0
    assert constants.DEFAULT_QUOTA_INTERVAL == 600.0
    assert constants.DEFAULT_STREAM_CHECK_INTERVAL == 180.0
    assert constants.DEFAULT_BACKLOG_SECONDS == 10
    assert constants.DEFAULT_BACKLOG_COUNTS == 100
    assert constants.DEFAULT_SAMPLE_RATE == 24000
    assert constants.SUPPORTED_SAMPLE_RATES == (
        24000,
        44100,
        48000,
        88200,
        96000,
    )
    assert constants.DEFAULT_QUOTA_LIMIT == 10000
    assert constants.DEFAULT_QUEUE_MAXSIZE == 50
    assert constants.DEFAULT_MAX_PROCESSED_MESSAGE_IDS == 1000


def test_validation_guard_constants() -> None:
    """4. ガード値・下限値・上限値（バリデーション用定数）を検証します。"""
    assert constants.MIN_CHAT_INTERVAL == 3.0
    assert constants.POLLING_INTERVAL_MIN_MS == 3000
    assert constants.MIN_QUOTA_INTERVAL == 60.0
    assert constants.MIN_STREAM_CHECK_INTERVAL == 60.0
    assert constants.MIN_SPEED_SCALE == 0.5
    assert constants.MAX_SPEED_SCALE == 2.2
    assert constants.MIN_VOLUME_SCALE == 0.05
    assert constants.MAX_VOLUME_SCALE == 2.0
    assert constants.MIN_SPEAKER_ID == 0
    assert constants.MAX_SPEAKER_ID == 126
    assert constants.MIN_BACKLOG_SECONDS == -1
    assert constants.MAX_BACKLOG_SECONDS == 3600
    assert constants.MIN_BACKLOG_COUNTS == -1
    assert constants.MAX_BACKLOG_COUNTS == 1000


def test_file_path_constants() -> None:
    """5. 設定ファイル・データファイル定数を検証します。"""
    assert constants.DEFAULT_DICTIONARY_FILE == "dictionary.txt"
    assert constants.DEFAULT_DICTIONARY_PATH == "dictionary.txt"
    assert constants.DEFAULT_NG_WORDS_FILE == "ng_words.txt"
    assert constants.DEFAULT_NG_WORDS_PATH == "ng_words.txt"
    assert constants.DEFAULT_VOLUME_FILE == "volume.txt"
    assert constants.DEFAULT_VOLUME_PATH == "volume.txt"
    assert constants.DEFAULT_CHAT_LOG_FILE == "chat_log.jsonl"
    assert constants.DEFAULT_CHAT_LOG_PATH == "chat_log.jsonl"
    assert constants.DEFAULT_CLIENT_SECRET_FILE == "client_secret.json"
    assert constants.DEFAULT_TOKEN_FILE == "token.json"
    assert constants.DEFAULT_AUTHOR_SUFFIX == "さん"


def test_env_constants() -> None:
    """6. 環境変数名定数を検証します。"""
    assert constants.ENV_VOICEVOX_URL == "VOICEVOX_URL"
    assert constants.ENV_VOICEVOX_SPEED_SCALE == "VOICEVOX_SPEED_SCALE"
    assert constants.ENV_VOICEVOX_AUTO_SPEED_BOOST == "VOICEVOX_AUTO_SPEED_BOOST"
    assert constants.ENV_VOICEVOX_MAX_SPEED == "VOICEVOX_MAX_SPEED"
    assert constants.ENV_VOICEVOX_VOLUME_SCALE == "VOICEVOX_VOLUME_SCALE"
    assert constants.ENV_VOICEVOX_SPEAKER_ID == "VOICEVOX_SPEAKER_ID"
    assert constants.ENV_VOICEVOX_DEVICE == "VOICEVOX_DEVICE"
    assert constants.ENV_VOICEVOX_TTS_TEST == "VOICEVOX_TTS_TEST"
    assert constants.ENV_VOICEVOX_MANAGE_CONTAINER == "VOICEVOX_MANAGE_CONTAINER"
    assert constants.ENV_VOICEVOX_AUTHOR_SUFFIX == "VOICEVOX_AUTHOR_SUFFIX"
    assert constants.ENV_CONTAINER_CMD == "CONTAINER_CMD"
    assert constants.ENV_OBS_WEBSOCKET_HOST == "OBS_WEBSOCKET_HOST"
    assert constants.ENV_OBS_WEBSOCKET_PORT == "OBS_WEBSOCKET_PORT"
    assert constants.ENV_OBS_WEBSOCKET_PASSWORD == "OBS_WEBSOCKET_PASSWORD"


def test_oauth_scope_constants() -> None:
    """7. OAuth2 スコープ定数を検証します。"""
    assert (
        constants.YOUTUBE_SCOPE == "https://www.googleapis.com/auth/youtube.force-ssl"
    )
    assert (
        constants.MONITORING_SCOPE == "https://www.googleapis.com/auth/monitoring.read"
    )


def test_message_and_calculation_constants() -> None:
    """8. メッセージ・再生スピード計算定数を検証します。"""
    assert (
        constants.DEFAULT_TTS_TEST_MESSAGE == "ぴんぽーん！チャット読上げのテストなのだ"
    )
    assert constants.CHAR_RATE_PER_SECOND_BASE == 6.0
    assert constants.BOOST_DURATION_MIN == 10.0
    assert constants.BOOST_DURATION_MAX == 40.0


def test_log_prefix_constants() -> None:
    """9. ログプリフィックス定数 (全10種) を検証します。"""
    assert constants.LOG_PREFIX_CONFIG == "[CONFIG]"
    assert constants.LOG_PREFIX_OBS == "[OBS]"
    assert constants.LOG_PREFIX_TALK == "[TALK]"
    assert constants.LOG_PREFIX_CHAT == "[CHAT]"
    assert constants.LOG_PREFIX_COMMENT == "[COMMENT]"
    assert constants.LOG_PREFIX_QUOTA == "[QUOTA]"
    assert constants.LOG_PREFIX_TTS_TEST == "[TTS-TEST]"
    assert constants.LOG_PREFIX_SKIP_PAST == "[SKIP(過去コメント)]"
    assert constants.LOG_PREFIX_SKIP_NG == "[SKIP(NG)]"
    assert constants.LOG_PREFIX_SKIP_QUEUE == "[SKIP(QUEUE)]"
