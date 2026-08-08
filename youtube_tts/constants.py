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
"""アプリケーション全体で使用する定数およびデフォルト設定値を定義するモジュールです。"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. VOICEVOX 関連定数
# ---------------------------------------------------------------------------
# VOICEVOX Engine REST API のデフォルトベース URL
DEFAULT_VOICEVOX_URL: str = "http://127.0.0.1:50021"

# VOICEVOX Engine のデフォルトホストアドレス
DEFAULT_VOICEVOX_HOST: str = "127.0.0.1"

# VOICEVOX Engine のデフォルトポート番号
DEFAULT_VOICEVOX_PORT: int = 50021

# VOICEVOX Engine REST API のデフォルトベース URL (旧形式互換・エイリアス)
DEFAULT_VOICEVOX_BASE_URL: str = DEFAULT_VOICEVOX_URL

# デフォルトの VOICEVOX 話者 ID (ずんだもん ノーマル)
DEFAULT_SPEAKER_ID: int = 3

# デフォルトの音声読み上げ速度スケール (1.0倍)
DEFAULT_SPEED_SCALE: float = 1.0

# デフォルトの音声読み上げ音量スケール (1.0倍)
DEFAULT_VOLUME_SCALE: float = 1.0

# --max-speed オプション未指定時のデフォルト最大速度
DEFAULT_MAX_SPEED: float = 2.2

# VOICEVOX Engine コンテナのデフォルト名
DEFAULT_CONTAINER_NAME: str = "voicevox-engine"

# VOICEVOX Engine コンテナのデフォルトイメージ名
DEFAULT_CONTAINER_IMAGE: str = (
    "docker.io/voicevox/voicevox_engine:cpu-latest"
)

# VOICEVOX Engine コンテナのバインドポート番号
DEFAULT_CONTAINER_PORT: int = 50021

# VOICEVOX Engine コンテナのバインドホストアドレス
DEFAULT_CONTAINER_HOST: str = "127.0.0.1"

# コンテナ排他制御用ロックファイルパス
DEFAULT_LOCK_FILE_PATH: str = "/tmp/youtube_tts_voicevox_runners.lock"

# コンテナ状態管理用 JSON ファイルパス
DEFAULT_STATE_FILE_PATH: str = "/tmp/youtube_tts_voicevox_runners.json"

# コンテナ排他制御用ロックファイルパス (エイリアス)
DEFAULT_CONTAINER_LOCK_FILE: str = DEFAULT_LOCK_FILE_PATH

# コンテナ状態管理用 JSON ファイルパス (エイリアス)
DEFAULT_CONTAINER_STATE_FILE: str = DEFAULT_STATE_FILE_PATH


# ---------------------------------------------------------------------------
# 2. OBS 連携関連定数
# ---------------------------------------------------------------------------
# OBS Studio WebSocket サーバーのデフォルトホスト名
DEFAULT_OBS_HOST: str = "localhost"

# OBS Studio WebSocket サーバーのデフォルトポート番号
DEFAULT_OBS_PORT: int = 4455


# ---------------------------------------------------------------------------
# 3. インターバル・監視・バックログデフォルト値
# ---------------------------------------------------------------------------
# チャットコメント取得のデフォルト最短間隔（秒）
DEFAULT_CHAT_INTERVAL: float = 20.0

# クォータ消費量監視のデフォルト最短間隔（秒）
DEFAULT_QUOTA_INTERVAL: float = 600.0

# 配信アクティブ状態チェックのデフォルト最短間隔（秒）
DEFAULT_STREAM_CHECK_INTERVAL: float = 180.0

# Live配信起動時のデフォルト過去コメント遡り時間（秒）
DEFAULT_BACKLOG_SECONDS: int = 10

# 動画起動時のデフォルトバックログ読み込み件数（件）
DEFAULT_BACKLOG_COUNTS: int = 100

# VOICEVOX デフォルト出力サンプリングレート（Hz）
DEFAULT_SAMPLE_RATE: int = 24000

# VOICEVOX 設定可能サンプリング周波数リスト
SUPPORTED_SAMPLE_RATES: tuple[int, ...] = (
    24000,
    44100,
    48000,
    88200,
    96000,
)

# 取得失敗時のデフォルト1日あたりクォータ上限値
DEFAULT_QUOTA_LIMIT: int = 10000

# 音声再生キューのデフォルト最大保持件数
DEFAULT_QUEUE_MAXSIZE: int = 50

# 重複防止用に保持する処理済みメッセージ ID の最大数
DEFAULT_MAX_PROCESSED_MESSAGE_IDS: int = 1000


# ---------------------------------------------------------------------------
# 4. ガード値・下限値・上限値（バリデーション用定数）
# ---------------------------------------------------------------------------
# CLI指定 --chat-interval の下限値（秒）
MIN_CHAT_INTERVAL: float = 3.0

# API応答時の次回ポーリング最低待機時間（ミリ秒: 3000ms）
POLLING_INTERVAL_MIN_MS: int = int(MIN_CHAT_INTERVAL * 1000)

# CLI指定 --quota-interval の下限値（秒）
MIN_QUOTA_INTERVAL: float = 60.0

# CLI指定 --stream-check-interval の下限値（秒）
MIN_STREAM_CHECK_INTERVAL: float = 60.0

# 読上げスピードの下限値
MIN_SPEED_SCALE: float = 0.5

# 読上げスピードの全システム共通絶対上限値（システム制限）
MAX_SPEED_SCALE: float = 2.2

# 音量スケールの下限値
MIN_VOLUME_SCALE: float = 0.05

# 音量スケールの上限値
MAX_VOLUME_SCALE: float = 2.0

# 話者 ID の下限値
MIN_SPEAKER_ID: int = 0

# 現行エンジンの話者 ID 参照用上限値
MAX_SPEAKER_ID: int = 126

# 過去コメント遡り時間の下限値（秒, -1は全件無制限）
MIN_BACKLOG_SECONDS: int = -1

# 過去コメント遡り時間の上限値（秒: 1時間）
MAX_BACKLOG_SECONDS: int = 3600

# バックログ読み込み件数の下限値（件, 負数は全件無制限）
MIN_BACKLOG_COUNTS: int = -1

# バックログ読み込み件数の上限値（件: 1,000件）
MAX_BACKLOG_COUNTS: int = 1000


# ---------------------------------------------------------------------------
# 5. 設定ファイル・データファイル定数
# ---------------------------------------------------------------------------
# 単語変換辞書ファイルのデフォルトパス
DEFAULT_DICTIONARY_FILE: str = "dictionary.txt"

# 単語変換辞書ファイルのデフォルトパス (エイリアス)
DEFAULT_DICTIONARY_PATH: str = DEFAULT_DICTIONARY_FILE

# NGワード指定ファイルのデフォルトパス
DEFAULT_NG_WORDS_FILE: str = "ng_words.txt"

# NGワード指定ファイルのデフォルトパス (エイリアス)
DEFAULT_NG_WORDS_PATH: str = DEFAULT_NG_WORDS_FILE

# 音量設定ファイルのデフォルトパス
DEFAULT_VOLUME_FILE: str = "volume.txt"

# 音量設定ファイルのデフォルトパス (エイリアス)
DEFAULT_VOLUME_PATH: str = DEFAULT_VOLUME_FILE

# チャットログ出力ファイルのデフォルトパス
DEFAULT_CHAT_LOG_FILE: str = "chat_log.jsonl"

# チャットログ出力ファイルのデフォルトパス (エイリアス)
DEFAULT_CHAT_LOG_PATH: str = DEFAULT_CHAT_LOG_FILE

# Google OAuth 2.0 クライアントシークレットファイルのデフォルトパス
DEFAULT_CLIENT_SECRET_FILE: str = "client_secret.json"

# Google OAuth 認証トークン保存ファイルのデフォルトパス
DEFAULT_TOKEN_FILE: str = "token.json"

# デフォルトの投稿者名敬称
DEFAULT_AUTHOR_SUFFIX: str = "さん"


# ---------------------------------------------------------------------------
# 6. 環境変数名定数
# ---------------------------------------------------------------------------
# VOICEVOX REST API ベース URL 環境変数名
ENV_VOICEVOX_URL: str = "VOICEVOX_URL"

# 読上げ速度環境変数名
ENV_VOICEVOX_SPEED_SCALE: str = "VOICEVOX_SPEED_SCALE"

# 自動速度ブースト有効化環境変数名
ENV_VOICEVOX_AUTO_SPEED_BOOST: str = "VOICEVOX_AUTO_SPEED_BOOST"

# 自動ブースト時最大速度環境変数名
ENV_VOICEVOX_MAX_SPEED: str = "VOICEVOX_MAX_SPEED"

# 音量スケール環境変数名
ENV_VOICEVOX_VOLUME_SCALE: str = "VOICEVOX_VOLUME_SCALE"

# 話者 ID 環境変数名
ENV_VOICEVOX_SPEAKER_ID: str = "VOICEVOX_SPEAKER_ID"

# 出力オーディオデバイス環境変数名
ENV_VOICEVOX_DEVICE: str = "VOICEVOX_DEVICE"

# TTS テスト読み上げテキスト環境変数名
ENV_VOICEVOX_TTS_TEST: str = "VOICEVOX_TTS_TEST"

# コンテナ自動管理フラグ環境変数名
ENV_VOICEVOX_MANAGE_CONTAINER: str = "VOICEVOX_MANAGE_CONTAINER"

# 投稿者名敬称環境変数名
ENV_VOICEVOX_AUTHOR_SUFFIX: str = "VOICEVOX_AUTHOR_SUFFIX"

# コンテナ実行コマンド指定環境変数名
ENV_CONTAINER_CMD: str = "CONTAINER_CMD"

# OBS WebSocket ホスト環境変数名
ENV_OBS_WEBSOCKET_HOST: str = "OBS_WEBSOCKET_HOST"

# OBS WebSocket ポート環境変数名
ENV_OBS_WEBSOCKET_PORT: str = "OBS_WEBSOCKET_PORT"

# OBS WebSocket パスワード環境変数名
ENV_OBS_WEBSOCKET_PASSWORD: str = "OBS_WEBSOCKET_PASSWORD"


# ---------------------------------------------------------------------------
# 7. OAuth2 スコープ定数
# ---------------------------------------------------------------------------
# YouTube Data API 操作スコープ
YOUTUBE_SCOPE: str = "https://www.googleapis.com/auth/youtube.force-ssl"

# Google Cloud Monitoring API 閲覧スコープ
MONITORING_SCOPE: str = "https://www.googleapis.com/auth/monitoring.read"


# ---------------------------------------------------------------------------
# 8. メッセージ・再生スピード計算定数
# ---------------------------------------------------------------------------
# TTS テスト用デフォルトメッセージ
DEFAULT_TTS_TEST_MESSAGE: str = "ぴんぽーん！チャット読上げのテストなのだ"

# 基本スピード(1.0倍)時の1秒あたり概算読み上げ文字数
CHAR_RATE_PER_SECOND_BASE: float = 6.0

# 自動スピードブーストを開始するキュー推定残時間（秒）
BOOST_DURATION_MIN: float = 10.0

# 自動スピードブーストが最大速度に達するキュー推定残時間（秒）
BOOST_DURATION_MAX: float = 40.0


# ---------------------------------------------------------------------------
# 9. ログプリフィックス定数
# ---------------------------------------------------------------------------
# 設定ロード・更新ログのプリフィックス
LOG_PREFIX_CONFIG: str = "[CONFIG]"

# OBS Studio 連携処理ログのプリフィックス
LOG_PREFIX_OBS: str = "[OBS]"

# 音声再生・読み上げログのプリフィックス
LOG_PREFIX_TALK: str = "[TALK]"

# Live チャット取得ログのプリフィックス
LOG_PREFIX_CHAT: str = "[CHAT]"

# 動画コメント取得ログのプリフィックス
LOG_PREFIX_COMMENT: str = "[COMMENT]"

# クォータ消費量監視ログのプリフィックス
LOG_PREFIX_QUOTA: str = "[QUOTA]"

# TTS テスト読み上げログのプリフィックス
LOG_PREFIX_TTS_TEST: str = "[TTS-TEST]"

# 過去コメントスキップログのプリフィックス
LOG_PREFIX_SKIP_PAST: str = "[SKIP(過去コメント)]"

# NGワード検知スキップログのプリフィックス
LOG_PREFIX_SKIP_NG: str = "[SKIP(NG)]"

# キュー満杯時スキップログのプリフィックス
LOG_PREFIX_SKIP_QUEUE: str = "[SKIP(QUEUE)]"
