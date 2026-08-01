#!/bin/bash
export OBS_WEBSOCKET_PASSWORD=000000
uv run youtube_video_voicevox.py --quota-talk --tts-test --chat-interval 30 $@
