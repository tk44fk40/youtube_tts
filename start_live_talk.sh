#!/bin/bash
export OBS_WEBSOCKET_PASSWORD=000000
uv run youtube_live_voicevox.py \
--tts-test ライブ配信が開始されました。これは読上げ音声のテストです。 \
--quota-talk --backlog-seconds -1 $@
