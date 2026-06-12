#!/usr/bin/env python3
# YouTube Live のチャットを VOICEVOX で読み上げる
import io
import os
import queue
import re
import sys
import threading
import time
import unicodedata
import wave

from collections import deque
from pathlib import Path
from urllib.parse import (
    parse_qs,
    urlparse
)

import numpy as np
import requests
import sounddevice as sd

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly"
]

TOKEN_FILE = "token.json"

VOICEVOX_URL = "http://127.0.0.1:50021"
SPEAKER_ID = 3

DICTIONARY_FILE = Path(
    "dictionary.txt"
)

NG_WORD_FILE = Path(
    "ng_words.txt"
)

# PipeWire の既定出力を使用
sd.default.device = "pipewire"

# ターゲットサンプリングレート
target_sample_rate = 24000

sd.default.samplerate = target_sample_rate

# コメント再生待ちキューの最大数
QUEUE_MAXSIZE = 50

# 処理済みメッセージIDの履歴長
# コメント再生キューより長い履歴を保持することで、APIのページングや重複取得を
# 避けつつ、再読み上げを防ぎます。
MAX_PROCESSED_MESSAGE_IDS = 1000

comment_queue = queue.Queue(
    maxsize=QUEUE_MAXSIZE
)

REPLACEMENTS = {}
NG_WORDS = set()

dictionary_mtime = None
ng_word_mtime = None


def normalize_text(text):
    return unicodedata.normalize(
        "NFKC",
        text
    )


def load_replacements():
    replacements = {}

    if not DICTIONARY_FILE.exists():
        return replacements

    with open(
        DICTIONARY_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:
            line = line.strip()

            if not line:
                continue

            if "=" not in line:
                continue

            src, dst = line.split(
                "=",
                1
            )

            normalized_src = normalize_text(
                src.strip()
            ).lower()

            replacements[
                normalized_src
            ] = dst.strip()

    return replacements


def load_ng_words():
    ng_words = set()

    if not NG_WORD_FILE.exists():
        return ng_words

    with open(
        NG_WORD_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:
            word = line.strip()

            if not word:
                continue

            normalized_word = normalize_text(
                word
            ).lower()

            ng_words.add(
                normalized_word
            )

    return ng_words


def reload_config():
    global REPLACEMENTS
    global NG_WORDS

    global dictionary_mtime
    global ng_word_mtime

    # dictionary.txt
    if DICTIONARY_FILE.exists():
        current_mtime = os.path.getmtime(
            DICTIONARY_FILE
        )

        if current_mtime != dictionary_mtime:
            dictionary_mtime = current_mtime

            REPLACEMENTS = (
                load_replacements()
            )

            print(
                "[CONFIG] dictionary reloaded"
            )

    # ng_words.txt
    if NG_WORD_FILE.exists():
        current_mtime = os.path.getmtime(
            NG_WORD_FILE
        )

        if current_mtime != ng_word_mtime:
            ng_word_mtime = current_mtime

            NG_WORDS = (
                load_ng_words()
            )

            print(
                "[CONFIG] ng words reloaded"
            )


def load_credentials():
    if not Path(TOKEN_FILE).exists():
        raise RuntimeError(
            "token.json was not found. "
            "Run oauth_test.py to create OAuth credentials."
        )

    try:
        creds = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )
    except Exception as e:
        try:
            os.remove(TOKEN_FILE)
        except OSError:
            pass

        raise RuntimeError(
            "Failed to load token.json because it is invalid or corrupted. "
            "Deleted token.json. Run oauth_test.py to recreate credentials."
        ) from e

    if creds.expired:
        if creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                raise RuntimeError(
                    "OAuth token refresh failed. "
                    "Delete token.json and reauthenticate with oauth_test.py."
                ) from e

            with open(
                TOKEN_FILE,
                "w",
                encoding="utf-8"
            ) as token:
                token.write(
                    creds.to_json()
                )
        else:
            raise RuntimeError(
                "OAuth credentials are expired and no refresh token is available. "
                "Delete token.json and run oauth_test.py to recreate credentials."
            )

    return creds


def extract_video_id(value):
    # URLでない場合は
    # そのまま video_id とみなす
    if "youtube.com" not in value \
    and "youtu.be" not in value:
        return value

    parsed = urlparse(value)

    # youtu.be/<id>
    if parsed.netloc == "youtu.be":
        return parsed.path.lstrip("/")

    # youtube.com/watch?v=<id>
    if parsed.path == "/watch":
        query = parse_qs(parsed.query)

        if "v" in query:
            return query["v"][0]

    # youtube.com/live/<id>
    if parsed.path.startswith("/live/"):
        parts = parsed.path.split("/")

        if len(parts) >= 3:
            return parts[2]

    raise RuntimeError(
        "failed to extract video id"
    )


def get_live_chat_id(
    youtube,
    video_id
):
    response = youtube.videos().list(
        part="liveStreamingDetails",
        id=video_id
    ).execute()

    items = response.get(
        "items",
        []
    )

    if not items:
        raise RuntimeError(
            "video not found"
        )

    details = items[0].get(
        "liveStreamingDetails",
        {}
    )

    live_chat_id = details.get(
        "activeLiveChatId"
    )

    if not live_chat_id:
        raise RuntimeError(
            "activeLiveChatId not found"
        )

    return live_chat_id


def get_current_live_video_id(
    youtube
):
    # Fetch own channel's live broadcasts via authenticated API
    try:
        response = youtube.liveBroadcasts().list(
            part="id,status",
            mine=True,
            broadcastStatus="active"
        ).execute()
    except HttpError as e:
        if e.resp.status == 403 and "quotaExceeded" in str(e):
            print("\n[ERROR] YouTube API quota exceeded")
            print("        Please wait 24 hours before running again")
            print(f"        Error: {e}")
            sys.exit(1)
        raise

    items = response.get(
        "items",
        []
    )

    for item in items:
        status = item.get(
            "status",
            {}
        ).get(
            "lifeCycleStatus"
        )

        if status == "live":
            vid = item.get("id")
            chat_url = f"https://www.youtube.com/live_chat?v={vid}&is_popout=1"
            return vid, chat_url

    raise RuntimeError(
        "No live broadcast found. "
        "Please start a live stream or pass VIDEO_ID as an argument."
    )


def update_obs_browser_source(
    chat_url
):
    source_name = os.getenv(
        "OBS_BROWSER_SOURCE_NAME"
        ,"チャット"
    )

    if not source_name:
        return

    obs_password = os.getenv(
        "OBS_WEBSOCKET_PASSWORD"
    )

    if not obs_password:
        print(
            "[OBS] OBS_WEBSOCKET_PASSWORD is not set; skipping OBS update"
        )
        return

    obs_host = os.getenv(
        "OBS_WEBSOCKET_HOST",
        "localhost"
    )

    obs_port = int(
        os.getenv(
            "OBS_WEBSOCKET_PORT",
            "4455"
        )
    )

    try:
        from obswebsocket import obsws, requests as obs_requests
    except ImportError:
        print(
            "[OBS] obs-websocket library is not installed; install obs-websocket-py to enable OBS integration"
        )
        return

    try:
        ws = obsws(
            obs_host,
            obs_port,
            obs_password
        )
        ws.connect()
        ws.call(
            obs_requests.SetSourceSettings(
                sourceName=source_name,
                sourceSettings={"url": chat_url}
            )
        )
        ws.disconnect()
        print(
            "[OBS] ✓ チャットURL設定成功"
        )
        print(
            f"      URL: {chat_url}"
        )
    except Exception as e:
        print(
            f"[OBS] ✗ チャットURL設定失敗: {e}"
        )


def synthesize_voice(text):
    audio_query = requests.post(
        f"{VOICEVOX_URL}/audio_query",
        params={
            "text": text,
            "speaker": SPEAKER_ID
        }
    )

    audio_query.raise_for_status()

    synthesis = requests.post(
        f"{VOICEVOX_URL}/synthesis",
        params={
            "speaker": SPEAKER_ID
        },
        data=audio_query.text,
        headers={
            "Content-Type": "application/json"
        }
    )

    synthesis.raise_for_status()

    wav_io = io.BytesIO(
        synthesis.content
    )

    with wave.open(
        wav_io,
        "rb"
    ) as wav_file:

        sample_rate = (
            wav_file.getframerate()
        )

        channels = (
            wav_file.getnchannels()
        )

        pcm_data = wav_file.readframes(
            wav_file.getnframes()
        )

    audio = np.frombuffer(
        pcm_data,
        dtype=np.int16
    )

    if channels > 1:
        audio = audio.reshape(
            -1,
            channels
        )

    return (
        audio,
        sample_rate
    )


def resample_audio(
    audio,
    source_sample_rate,
    target_sample_rate
):
    if source_sample_rate == target_sample_rate:
        return audio

    duration = (
        len(audio)
        / source_sample_rate
    )

    old_time = np.linspace(
        0,
        duration,
        num=len(audio)
    )

    new_length = int(
        duration
        * target_sample_rate
    )

    new_time = np.linspace(
        0,
        duration,
        num=new_length
    )

    resampled_audio = np.interp(
        new_time,
        old_time,
        audio
    ).astype(np.int16)

    return resampled_audio


def normalize_author(author):
    # 全角半角正規化
    author = normalize_text(
        author
    )

    # 先頭の @ を除去
    author = author.lstrip("@")

    # 前後空白除去
    author = author.strip()

    if not author:
        return author

    if author.endswith("さん"):
        return author

    return f"{author}さん"


def replace_words(message):
    normalized_message = normalize_text(
        message
    )

    for src, dst in REPLACEMENTS.items():
        pattern = re.compile(
            re.escape(src),
            re.IGNORECASE
        )

        normalized_message = pattern.sub(
            dst,
            normalized_message
        )

    return normalized_message


def contains_ng_word(message):
    normalized_message = normalize_text(
        message
    ).lower()

    for word in NG_WORDS:
        if word in normalized_message:
            return True

    return False


def normalize_message(message):
    # 全角半角正規化
    message = normalize_text(
        message
    )

    # URL除去
    message = re.sub(
        r"https?:\S+",
        "",
        message
    )

    # 草を圧縮
    message = re.sub(
        r"[wｗ]{3,}",
        " わら ",
        message,
        flags=re.IGNORECASE
    )

    # ! を圧縮
    message = re.sub(
        r"[!！]{2,}",
        "！",
        message
    )

    # ? を圧縮
    message = re.sub(
        r"[?？]{2,}",
        "？",
        message
    )

    # 絵文字除去
    message = re.sub(
        r"[\U00010000-\U0010ffff]",
        "",
        message
    )

    # 読み上げ辞書
    message = replace_words(
        message
    )

    # 前後空白除去
    message = message.strip()

    return message


def normalize_comment(
    author,
    message
):
    normalized_author = (
        normalize_author(author)
    )

    normalized_message = (
        normalize_message(message)
    )

    return (
        normalized_author,
        normalized_message
    )


def speak(text):
    audio, source_sample_rate = (
        synthesize_voice(text)
    )

    audio = resample_audio(
        audio,
        source_sample_rate,
        target_sample_rate
    )

    sd.play(
        audio,
        samplerate=target_sample_rate
    )

    sd.wait()


def playback_worker():
    while True:
        author, message = (
            comment_queue.get()
        )

        text = f"{author} {message}"

        print(
            f"[READ] {text}"
        )

        try:
            speak(text)

        except Exception as e:
            print(e)

        comment_queue.task_done()


def youtube_worker(video_id):
    creds = load_credentials()

    youtube = build(
        "youtube",
        "v3",
        credentials=creds
    )

    live_chat_id = get_live_chat_id(
        youtube,
        video_id
    )

    print(
        f"liveChatId: {live_chat_id}"
    )

    next_page_token = None

    processed_message_ids = set()
    processed_message_queue = deque()
    max_processed_message_ids = MAX_PROCESSED_MESSAGE_IDS

    while True:
        reload_config()

        try:
            response = youtube.liveChatMessages().list(
                liveChatId=live_chat_id,
                part="snippet,authorDetails",
                pageToken=next_page_token,
                maxResults=200
            ).execute()
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print("\n[ERROR] YouTube API quota exceeded")
                print("        Please wait 24 hours before running again")
                print(f"        Error: {e}")
                return
            raise

        for item in response.get(
            "items",
            []
        ):
            message_id = item["id"]

            if message_id in processed_message_ids:
                continue

            processed_message_ids.add(
                message_id
            )
            processed_message_queue.append(
                message_id
            )
            if len(processed_message_queue) > max_processed_message_ids:
                oldest_message_id = processed_message_queue.popleft()
                processed_message_ids.discard(
                    oldest_message_id
                )

            author = item[
                "authorDetails"
            ]["displayName"]

            message = item[
                "snippet"
            ]["displayMessage"]

            if contains_ng_word(
                message
            ):
                print(
                    f"[SKIP(NG)] "
                    f"{author}: {message}"
                )

                continue

            print(
                f"[CHAT] "
                f"{author}: {message}"
            )

            author, message = (
                normalize_comment(
                    author,
                    message
                )
            )

            if comment_queue.full():
                print(
                    f"[SKIP(QUEUE)] "
                    f"{author}: {message}"
                )

                continue

            comment_queue.put(
                (
                    author,
                    message
                )
            )

        next_page_token = response.get(
            "nextPageToken"
        )

        # YouTube API の推奨するポーリング間隔を尊重しつつ、
        # 最低3秒は空けるようにする
        polling_interval_min = 3000
        polling_interval = max(
            response.get(
                "pollingIntervalMillis",
                polling_interval_min
            ),
            polling_interval_min
        )

        time.sleep(
            polling_interval / 1000
        )


def main():
    reload_config()

    if len(sys.argv) >= 2:
        video_id = extract_video_id(
            sys.argv[1]
        )
        chat_url = (
            f"https://www.youtube.com/live_chat?v={video_id}&is_popout=1"
        )

    else:
        creds = load_credentials()
        youtube = build(
            "youtube",
            "v3",
            credentials=creds
        )

        try:
            video_id, chat_url = get_current_live_video_id(
                youtube
            )
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)

        print(
            f"auto-detected current live video_id: {video_id}"
        )
        print(
            f"chat URL: {chat_url}"
        )

    print(
        f"video_id: {video_id}"
    )

    update_obs_browser_source(
        chat_url
    )

    playback_thread = threading.Thread(
        target=playback_worker,
        daemon=True
    )

    playback_thread.start()

    youtube_worker(video_id)



if __name__ == "__main__":
    main()
