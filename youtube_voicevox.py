#!/usr/bin/env python3
# YouTube Live のチャットを VOICEVOX で読み上げる

import argparse
import os
import queue
import signal
import sys
import threading
import time
from collections import deque
from pathlib import Path

from youtube_tts import (
    AppConfig,
    AudioPlayer,
    ObsClient,
    TextProcessor,
    VoicevoxClient,
    YouTubeAuthenticator,
    YouTubeChatClient,
    QUOTA_SCOPES,
    get_project_id,
    get_quota_info,
    setup_logger,
)

# 定数定義
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")
SPEAKER_ID = int(os.getenv("VOICEVOX_SPEAKER_ID", "3"))

# コメント再生待ちキューの最大数
QUEUE_MAXSIZE = 50

# 処理済みメッセージIDの履歴長
MAX_PROCESSED_MESSAGE_IDS = 1000


class YouTubeTtsApp:
    """YouTube Live チャット読み上げツール全体の実行状態・ライフサイクルを管理するクラス"""

    def __init__(
        self,
        config: AppConfig,
        voicevox_client: VoicevoxClient,
        audio_player: AudioPlayer,
        obs_client: ObsClient = None,
        logger = None,
    ):
        self.config = config
        self.text_processor = TextProcessor(config)
        self.voicevox_client = voicevox_client
        self.audio_player = audio_player
        self.obs_client = obs_client

        if logger is None:
            from youtube_tts import get_logger
            self.logger = get_logger()
        else:
            self.logger = logger

        # 実行時状態の初期化 (DI およびスレッド間共有用)
        self.comment_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
        self.stop_event = threading.Event()
        self.processed_message_ids = set()
        self.processed_message_queue = deque()
        self.max_processed_message_ids = MAX_PROCESSED_MESSAGE_IDS
        self.last_spoken_used = None

    def speak(self, text: str):
        """指定されたテキストを VOICEVOX で音声合成し再生する"""
        try:
            # 音声合成
            wav_bytes = self.voicevox_client.synthesize(
                text=text,
                volume_scale=self.config.volume_scale,
                speed_scale=self.config.speed_scale,
                target_sample_rate=self.audio_player.target_sample_rate
            )
            # 音声再生
            self.audio_player.play_wav(wav_bytes)
        except Exception as e:
            # VOICEVOX サーバーの未起動や、オーディオ出力デバイスの競合などが原因で失敗する可能性がある
            self.logger.error(f"speak failed: {e}")

    def playback_worker(self):
        """コメント再生キューを監視し、順次再生するスレッドワーカー"""
        while not self.stop_event.is_set():
            try:
                author, message = self.comment_queue.get(timeout=1)
            except queue.Empty:
                continue

            text = f"{author} {message}"
            self.logger.info(f"[TALK] {text}")

            self.speak(text)
            self.comment_queue.task_done()

    def youtube_worker(
        self,
        chat_client: YouTubeChatClient,
        video_id: str,
        creds=None,
        quota_check: bool = False,
        quota_talk: bool = False,
        chat_interval: float = 20.0,
        quota_interval: float = 180.0,
        stream_check_interval: float = 180.0,
        project_id: str = None,
        verbose: bool = False,
        backlog_seconds: int = 10,
    ):
        """YouTube チャットコメントの定期取得を行い、キューへ送るスレッドワーカー"""
        live_chat_id = chat_client.get_live_chat_id(video_id)
        self.logger.info(f"liveChatId: {live_chat_id}")

        # しきい値時刻の算出
        from datetime import datetime, timezone, timedelta
        if backlog_seconds >= 0:
            threshold_time = datetime.now(timezone.utc) - timedelta(seconds=backlog_seconds)
        else:
            threshold_time = None

        next_page_token = None
        last_quota_check_time = 0
        last_stream_check_time = time.time()

        while not self.stop_event.is_set():
            # 設定の自動更新チェック
            self.config.reload_if_changed()

            if verbose:
                self.logger.debug(f"Fetching chat messages (pageToken: {next_page_token})")

            try:
                items, next_page_token, polling_interval = chat_client.fetch_chat_messages(
                    live_chat_id, page_token=next_page_token
                )
            except Exception as e:
                # クォータエラーなどの致命的なエラー時はスレッド終了
                self.logger.error(f"Failed to fetch chat messages: {e}")
                self.stop_event.set()
                return

            if verbose:
                self.logger.debug(f"Fetched {len(items)} messages. next_page_token: {next_page_token}, polling_interval: {polling_interval}ms")

            for item in items:
                message_id = item["id"]

                if message_id in self.processed_message_ids:
                    continue

                self.processed_message_ids.add(message_id)
                self.processed_message_queue.append(message_id)
                if len(self.processed_message_queue) > self.max_processed_message_ids:
                    oldest_message_id = self.processed_message_queue.popleft()
                    self.processed_message_ids.discard(oldest_message_id)

                # 投稿時刻のチェックによる過去コメントの除外
                if threshold_time is not None:
                    published_at_str = item.get("snippet", {}).get("publishedAt")
                    if published_at_str:
                        try:
                            # タイムゾーン対応の比較のために Z を +00:00 に置換
                            published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
                            if published_at < threshold_time:
                                if verbose:
                                    self.logger.debug(f"[SKIP(PAST)] {item['authorDetails']['displayName']}: {item['snippet']['displayMessage']} (published at {published_at_str})")
                                continue
                        except ValueError as e:
                            self.logger.warning(f"Failed to parse publishedAt: {published_at_str}, error: {e}")

                author = item["authorDetails"]["displayName"]
                message = item["snippet"]["displayMessage"]

                if self.text_processor.contains_ng_word(message):
                    self.logger.info(f"[SKIP(NG)] {author}: {message}")
                    continue

                self.logger.info(f"[CHAT] {author}: {message}")

                author, message = self.text_processor.normalize_comment(author, message)

                if self.comment_queue.full():
                    self.logger.info(f"[SKIP(QUEUE)] {author}: {message}")
                    continue

                self.comment_queue.put((author, message))

            # 配信ステータスとクォータのチェックは共通のタイムスタンプで評価する
            now = time.time()

            # 定期的に配信ステータスをチェックする
            if now - last_stream_check_time >= stream_check_interval:
                if verbose:
                    self.logger.debug("Checking stream active status...")
                is_active = chat_client.check_stream_active(video_id)
                if verbose:
                    self.logger.debug(f"Stream active status: {is_active}")
                if not is_active:
                    self.stop_event.set()
                    return
                last_stream_check_time = now

            # クォータ使用量を定期的に取得しログ出力する
            if quota_check and creds and project_id and (now - last_quota_check_time >= quota_interval):
                if verbose:
                    self.logger.debug("Fetching quota info...")
                try:
                    used, limit = get_quota_info(creds, project_id)
                    remaining = max(0, limit - used)
                    usage_percent = (used / limit) * 100 if limit > 0 else 0
                    self.logger.info(f"[QUOTA] Used: {used:,} / {limit:,} ({usage_percent:.2f}%), Remaining: {remaining:,}")

                    if quota_talk and used != self.last_spoken_used:
                        if not self.comment_queue.full():
                            self.comment_queue.put(("", f"ぴんぽーん！クォータ使用量は {used} ユニットです。"))
                            self.last_spoken_used = used
                except Exception as e:
                    self.logger.warning(f"Failed to fetch quota info: {e}")
                last_quota_check_time = now

            time.sleep(max(polling_interval / 1000, chat_interval))

    def cleanup(self, playback_thread=None, wait_seconds=5):
        """スレッド停止、オーディオ停止、およびキュー内の残存コメント処理を行うクリーンアップ"""
        self.logger.info("Cleaning up...")
        self.stop_event.set()

        self.audio_player.stop()

        # 1. playback_worker がキューのアイテムを消化するのを最大 wait_seconds 秒待つ。
        #    stop_event がセットされていても、キューが空になるまで task_done を待ちたいため。
        end_time = time.time() + wait_seconds
        while time.time() < end_time and not self.comment_queue.empty():
            time.sleep(0.1)

        # 2. タイムアウト後も残っているアイテムを強制クリアする。
        #    get_nowait() + task_done() でキューの内部カウンタを 0 に戻し、
        #    join() のブロックを解除できる状態にする。
        while True:
            try:
                self.comment_queue.get_nowait()
                self.comment_queue.task_done()
            except queue.Empty:
                break

        if playback_thread is not None:
            try:
                playback_thread.join(timeout=wait_seconds)
            except Exception:
                pass

        self.logger.info("Cleanup complete")

    def run(
        self,
        chat_client: YouTubeChatClient,
        video_id: str,
        creds=None,
        quota_check: bool = False,
        quota_talk: bool = False,
        chat_interval: float = 20.0,
        quota_interval: float = 180.0,
        stream_check_interval: float = 180.0,
        project_id: str = None,
        verbose: bool = False,
        backlog_seconds: int = 10,
    ):
        """スレッドの起動、シグナルハンドラ設定、および実行中のエラー処理をハンドリングする"""
        def handle_signal(signum, frame):
            self.logger.info("Signal received, shutting down...")
            self.stop_event.set()

        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except ValueError:
            # メインスレッド以外から呼び出された場合はシグナル登録エラーを無視する
            pass

        playback_thread = threading.Thread(target=self.playback_worker)
        playback_thread.start()

        try:
            self.youtube_worker(
                chat_client,
                video_id,
                creds=creds,
                quota_check=quota_check,
                quota_talk=quota_talk,
                chat_interval=chat_interval,
                quota_interval=quota_interval,
                stream_check_interval=stream_check_interval,
                project_id=project_id,
                verbose=verbose,
                backlog_seconds=backlog_seconds,
            )
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
        finally:
            self.cleanup(playback_thread=playback_thread, wait_seconds=5)


def main():
    env_speed = 1.0
    if "VOICEVOX_SPEED_SCALE" in os.environ:
        try:
            env_speed = float(os.environ["VOICEVOX_SPEED_SCALE"])
        except ValueError:
            pass

    parser = argparse.ArgumentParser(description="YouTube Live Chat TTS with VOICEVOX")
    parser.add_argument(
        "--speed",
        type=float,
        default=env_speed,
        help="読み上げスピード（デフォルト: 1.0）。環境変数 VOICEVOX_SPEED_SCALE でも指定可能です。"
    )
    parser.add_argument(
        "video_url_or_id",
        nargs="?",
        default=None,
        help="YouTube Live配信のURLまたは動画ID"
    )
    parser.add_argument(
        "-d",
        "--device",
        default=os.getenv("VOICEVOX_DEVICE"),
        help="出力オーディオデバイス名またはID"
    )
    parser.add_argument(
        "-q",
        "--quota-check",
        action="store_true",
        help="デバッグ用のクォータ情報確認機能を有効にする"
    )
    parser.add_argument(
        "--quota-talk",
        action="store_true",
        help="クォータ使用量の読上げ機能を有効にする"
    )
    parser.add_argument(
        "--chat-interval",
        type=float,
        default=20.0,
        help="コメント取得の最短時間（秒）。デフォルトは20秒。"
    )
    parser.add_argument(
        "--backlog-seconds",
        type=int,
        default=10,
        help="起動時に読み上げる過去コメントの遡り時間（秒）。-1を指定した場合は過去コメントをすべて読み上げます。デフォルトは10秒。"
    )
    parser.add_argument(
        "--quota-interval",
        type=float,
        default=180.0,
        help="使用量の取得の最短時間（秒）。デフォルトは180秒。"
    )
    parser.add_argument(
        "--stream-check-interval",
        type=float,
        default=180.0,
        help="配信アクティブ状態チェックの最短時間（秒）。デフォルトは180秒。"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="詳細ログ（DEBUGタグ）を出力する"
    )
    args = parser.parse_args()

    if args.quota_talk:
        args.quota_check = True

    # ロギング設定の初期化
    logger = setup_logger(verbose=args.verbose)

    # 設定・クライアントの初期化
    config = AppConfig(
        dictionary_path="dictionary.txt",
        ng_words_path="ng_words.txt",
        volume_path="volume.txt"
    )
    # 環境変数 VOICEVOX_VOLUME_SCALE が設定されている場合はファイル設定より優先する
    if "VOICEVOX_VOLUME_SCALE" in os.environ:
        try:
            config.volume_scale = float(os.environ["VOICEVOX_VOLUME_SCALE"])
        except Exception:
            pass

    config.reload_if_changed()
    config.speed_scale = args.speed

    # オーディオデバイスの適用
    dev_id = None
    device = args.device
    if device is not None:
        try:
            dev_id = int(device)
        except ValueError:
            dev_id = device

        try:
            import sounddevice as sd
            device_info = sd.query_devices(dev_id, 'output')
            logger.info(f"出力デバイス: {device_info['name']} (ID: {device_info['index']})")
        except Exception as e:
            logger.warning(f"デバイス情報の取得に失敗しました: {e}")

    audio_player = AudioPlayer(default_device=dev_id)
    voicevox_client = VoicevoxClient(base_url=VOICEVOX_URL, speaker_id=SPEAKER_ID)

    # 認証情報の初期化
    scopes = QUOTA_SCOPES if args.quota_check else None
    authenticator = YouTubeAuthenticator(
        client_secret_path=CLIENT_SECRET_FILE,
        token_path=TOKEN_FILE,
        scopes=scopes
    )
    try:
        creds = authenticator.get_credentials()
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)

    chat_client = YouTubeChatClient(creds)

    if args.video_url_or_id:
        video_id = chat_client.extract_video_id(args.video_url_or_id)
        chat_url = f"https://www.youtube.com/live_chat?v={video_id}&is_popout=1"
    else:
        try:
            video_id, chat_url = chat_client.get_current_live_video_id()
        except RuntimeError as e:
            logger.error(e)
            sys.exit(1)

        logger.info(f"auto-detected current live video_id: {video_id}")
        logger.info(f"chat URL: {chat_url}")

    logger.info(f"video_id: {video_id}")

    # OBS連携
    obs_password = os.getenv("OBS_WEBSOCKET_PASSWORD")
    obs_host = os.getenv("OBS_WEBSOCKET_HOST", "localhost")
    obs_port = int(os.getenv("OBS_WEBSOCKET_PORT", "4455"))
    obs_source_name = os.getenv("OBS_BROWSER_SOURCE_NAME", "チャット")

    obs_client = ObsClient(host=obs_host, port=obs_port, password=obs_password)
    obs_client.update_chat_url(obs_source_name, chat_url)

    # クォータチェックに必要な情報を準備
    project_id = None
    if args.quota_check:
        try:
            project_id = get_project_id()
        except Exception as e:
            logger.warning(f"クォータチェックを有効にできませんでした (project_id 取得失敗): {e}")
            args.quota_check = False
            args.quota_talk = False

    app = YouTubeTtsApp(
        config=config,
        voicevox_client=voicevox_client,
        audio_player=audio_player,
        obs_client=obs_client,
        logger=logger,
    )

    try:
        app.run(
            chat_client,
            video_id,
            creds=creds,
            quota_check=args.quota_check,
            quota_talk=args.quota_talk,
            chat_interval=args.chat_interval,
            quota_interval=args.quota_interval,
            stream_check_interval=args.stream_check_interval,
            project_id=project_id,
            verbose=args.verbose,
            backlog_seconds=args.backlog_seconds,
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
