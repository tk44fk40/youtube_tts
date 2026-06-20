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

# グローバル状態・キュー
comment_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
stop_event = threading.Event()

# 設定とテキストプロセッサの初期化
config = AppConfig(
    dictionary_path="dictionary.txt",
    ng_words_path="ng_words.txt",
    volume_path="volume.txt"
)
# 環境変数の優先適用
if "VOICEVOX_VOLUME_SCALE" in os.environ:
    try:
        config.volume_scale = float(os.environ["VOICEVOX_VOLUME_SCALE"])
    except Exception:
        pass

text_processor = TextProcessor(config)
voicevox_client = VoicevoxClient(base_url=VOICEVOX_URL, speaker_id=SPEAKER_ID)
audio_player = AudioPlayer()


def speak(text):
    try:
        # 音声合成
        wav_bytes = voicevox_client.synthesize(
            text=text,
            volume_scale=config.volume_scale,
            target_sample_rate=audio_player.target_sample_rate
        )
        # 音声再生
        audio_player.play_wav(wav_bytes)
    except Exception as e:
        print(f"[ERROR] speak failed: {e}")


def playback_worker():
    while not stop_event.is_set():
        try:
            author, message = comment_queue.get(timeout=1)
        except queue.Empty:
            continue

        text = f"{author} {message}"
        print(f"[TALK] {text}")

        speak(text)
        comment_queue.task_done()


def youtube_worker(chat_client: YouTubeChatClient, video_id: str):
    live_chat_id = chat_client.get_live_chat_id(video_id)
    print(f"liveChatId: {live_chat_id}")

    next_page_token = None
    processed_message_ids = set()
    processed_message_queue = deque()
    max_processed_message_ids = MAX_PROCESSED_MESSAGE_IDS

    # 配信終了判定のためのカウンタ
    status_check_interval = 2
    status_check_counter = 0

    while not stop_event.is_set():
        # 設定の自動更新チェック
        config.reload_if_changed()

        try:
            items, next_page_token, polling_interval = chat_client.fetch_chat_messages(
                live_chat_id, page_token=next_page_token
            )
        except Exception as e:
            # クォータエラーなどの致命的なエラー時はスレッド終了
            print(f"[ERROR] Failed to fetch chat messages: {e}")
            stop_event.set()
            return

        for item in items:
            message_id = item["id"]

            if message_id in processed_message_ids:
                continue

            processed_message_ids.add(message_id)
            processed_message_queue.append(message_id)
            if len(processed_message_queue) > max_processed_message_ids:
                oldest_message_id = processed_message_queue.popleft()
                processed_message_ids.discard(oldest_message_id)

            author = item["authorDetails"]["displayName"]
            message = item["snippet"]["displayMessage"]

            if text_processor.contains_ng_word(message):
                print(f"[SKIP(NG)] {author}: {message}")
                continue

            print(f"[CHAT] {author}: {message}")

            author, message = text_processor.normalize_comment(author, message)

            if comment_queue.full():
                print(f"[SKIP(QUEUE)] {author}: {message}")
                continue

            comment_queue.put((author, message))

        # 定期的に配信ステータスをチェック
        status_check_counter += 1
        if status_check_counter % status_check_interval == 0:
            if not chat_client.check_stream_active(video_id):
                stop_event.set()
                return

        time.sleep(polling_interval / 1000)


def cleanup(playback_thread=None, wait_seconds=5):
    print("[INFO] Cleaning up...")
    stop_event.set()

    audio_player.stop()

    # キューの残りを処理するためのバッファ時間
    end_time = time.time() + wait_seconds
    while time.time() < end_time and not comment_queue.empty():
        time.sleep(0.1)

    # キューをクリアしてブロックを解除
    while True:
        try:
            comment_queue.get_nowait()
            comment_queue.task_done()
        except queue.Empty:
            break

    if playback_thread is not None:
        try:
            playback_thread.join(timeout=wait_seconds)
        except Exception:
            pass

    print("[INFO] Cleanup complete")


def main():
    parser = argparse.ArgumentParser(description="YouTube Live Chat TTS with VOICEVOX")
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
    args = parser.parse_args()

    config.reload_if_changed()

    # オーディオデバイスの適用
    device = args.device
    if device is not None:
        try:
            dev_id = int(device)
        except ValueError:
            dev_id = device

        try:
            import sounddevice as sd
            device_info = sd.query_devices(dev_id, 'output')
            print(f"[INFO] 出力デバイス: {device_info['name']} (ID: {device_info['index']})")
        except Exception as e:
            print(f"[WARN] デバイス情報の取得に失敗しました: {e}", file=sys.stderr)

        global audio_player
        audio_player = AudioPlayer(default_device=dev_id)

    # 認証情報の初期化
    authenticator = YouTubeAuthenticator(
        client_secret_path=CLIENT_SECRET_FILE,
        token_path=TOKEN_FILE
    )
    try:
        creds = authenticator.get_credentials()
    except Exception as e:
        print(f"[ERROR] Authentication failed: {e}")
        sys.exit(1)

    chat_client = YouTubeChatClient(creds)

    if args.video_url_or_id:
        video_id = chat_client.extract_video_id(args.video_url_or_id)
        chat_url = f"https://www.youtube.com/live_chat?v={video_id}&is_popout=1"
    else:
        try:
            video_id, chat_url = chat_client.get_current_live_video_id()
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)

        print(f"auto-detected current live video_id: {video_id}")
        print(f"chat URL: {chat_url}")

    print(f"video_id: {video_id}")

    # OBS連携
    obs_password = os.getenv("OBS_WEBSOCKET_PASSWORD")
    obs_host = os.getenv("OBS_WEBSOCKET_HOST", "localhost")
    obs_port = int(os.getenv("OBS_WEBSOCKET_PORT", "4455"))
    obs_source_name = os.getenv("OBS_BROWSER_SOURCE_NAME", "チャット")

    obs_client = ObsClient(host=obs_host, port=obs_port, password=obs_password)
    obs_client.update_chat_url(obs_source_name, chat_url)

    # シグナルハンドラ
    def handle_signal(signum, frame):
        print("[INFO] Signal received, shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    playback_thread = threading.Thread(target=playback_worker)
    playback_thread.start()

    try:
        youtube_worker(chat_client, video_id)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
    finally:
        cleanup(playback_thread=playback_thread, wait_seconds=5)


if __name__ == "__main__":
    main()
