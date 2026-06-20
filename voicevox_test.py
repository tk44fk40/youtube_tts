#!/usr/bin/env python3
import argparse
import io
import sys
import wave
import numpy as np
import requests
import sounddevice as sd

DEFAULT_HOST = "http://127.0.0.1:50021"
DEFAULT_SPEAKER = 3
DEFAULT_TEXT = "これは、ボイスボックスの発声テストです。"
DEFAULT_OUTPUT = "test.wav"
DEFAULT_VOLUME = 1.0

def get_speakers(host):
    try:
        response = requests.get(f"{host}/speakers")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[ERROR] VOICEVOXサーバーへの接続に失敗しました: {e}", file=sys.stderr)
        print("VOICEVOXが起動しているか、ホストURLが正しいか確認してください。", file=sys.stderr)
        sys.exit(1)

def list_speakers(host):
    speakers = get_speakers(host)
    print(f"{'ID':<6} | {'話者名':<15} | {'スタイル':<15}")
    print("-" * 45)
    for spk in speakers:
        name = spk.get("name", "Unknown")
        for style in spk.get("styles", []):
            style_name = style.get("name", "")
            style_id = style.get("id", "")
            print(f"{style_id:<6} | {name:<15} | {style_name:<15}")

def list_devices():
    print(sd.query_devices())

def synthesize_voice(text, speaker_id, host, target_sample_rate=None, volume_scale=None):
    print(f"[INFO] 音声合成中: 「{text}」 (話者ID: {speaker_id})")
    
    # 1. 音声クエリの作成
    try:
        query_response = requests.post(
            f"{host}/audio_query",
            params={"text": text, "speaker": speaker_id}
        )
        query_response.raise_for_status()
        query_data = query_response.json()
    except Exception as e:
        print(f"[ERROR] 音声クエリの作成に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)
        
    # 必要に応じてVOICEVOXに生成サンプリングレートを指定
    if target_sample_rate:
        print(f"[INFO] VOICEVOXでの生成サンプリングレートを指定: {target_sample_rate}Hz")
        query_data["outputSamplingRate"] = target_sample_rate

    # 音量比を指定
    if volume_scale is not None:
        print(f"[INFO] 音量比（volumeScale）を指定: {volume_scale}")
        query_data["volumeScale"] = volume_scale

    # 2. 音声合成の実行
    try:
        synthesis_response = requests.post(
            f"{host}/synthesis",
            params={"speaker": speaker_id},
            json=query_data
        )
        synthesis_response.raise_for_status()
        return synthesis_response.content
    except Exception as e:
        print(f"[ERROR] 音声合成の実行に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

def play_audio(wav_content, device=None):
    wav_io = io.BytesIO(wav_content)
    with wave.open(wav_io, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        pcm_data = wav_file.readframes(wav_file.getnframes())
    
    audio = np.frombuffer(pcm_data, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)
        
    # デバイスの設定
    dev_id = None
    if device is not None:
        try:
            dev_id = int(device)
        except ValueError:
            dev_id = device

    print(f"[INFO] 再生中... (サンプリングレート: {sample_rate}Hz, チャンネル数: {channels})")
    
    try:
        if dev_id is not None:
            sd.default.device = dev_id
            
        sd.play(audio, samplerate=sample_rate)
        sd.wait()
        print("[INFO] 再生完了")
    except Exception as e:
        print(f"[ERROR] 再生に失敗しました: {e}", file=sys.stderr)
        print("\n利用可能なオーディオデバイス一覧:", file=sys.stderr)
        list_devices()
        print("\nヒント: --device 引数で適切なデバイス名またはIDを指定して実行してください。", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="VOICEVOX 発声テストスクリプト")
    parser.add_argument("-t", "--text", default=DEFAULT_TEXT, help="発声させるテキスト")
    parser.add_argument("-s", "--speaker", type=int, default=DEFAULT_SPEAKER, help="話者スタイルID")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help="保存先WAVファイルパス")
    parser.add_argument("-H", "--host", default=DEFAULT_HOST, help="VOICEVOXのURL")
    parser.add_argument("-d", "--device", default=None, help="出力オーディオデバイス名またはID")
    parser.add_argument("-r", "--samplerate", type=int, default=None, help="生成サンプリングレート（未指定時はデバイスの既定値を使用）")
    parser.add_argument("-v", "--volume", type=float, default=DEFAULT_VOLUME, help="音量比（デフォルト: 1.0）")
    parser.add_argument("--list-speakers", action="store_true", help="利用可能な話者スタイル一覧を表示")
    parser.add_argument("--list-devices", action="store_true", help="オーディオデバイス一覧を表示")
    parser.add_argument("--no-play", action="store_true", help="再生をスキップしてファイル保存のみ行う")
    
    args = parser.parse_args()
    
    if args.list_speakers:
        list_speakers(args.host)
        return
        
    if args.list_devices:
        list_devices()
        return
        
    # 出力デバイスの規定サンプリングレートを調べる
    target_sample_rate = args.samplerate
    if target_sample_rate is None and not args.no_play:
        dev_id = None
        if args.device is not None:
            try:
                dev_id = int(args.device)
            except ValueError:
                dev_id = args.device
        try:
            device_info = sd.query_devices(dev_id, 'output')
            target_sample_rate = int(device_info['default_samplerate'])
            print(f"[INFO] 出力デバイス: {device_info['name']} (ID: {device_info['index']})")
        except Exception as e:
            print(f"[WARN] デバイスのサンプリングレート取得に失敗しました: {e}", file=sys.stderr)
            
    wav_content = synthesize_voice(args.text, args.speaker, args.host, target_sample_rate, args.volume)
    
    # WAVファイル保存
    try:
        with open(args.output, "wb") as f:
            f.write(wav_content)
        print(f"[INFO] 音声ファイルを保存しました: {args.output}")
    except Exception as e:
        print(f"[ERROR] ファイルの保存に失敗しました: {e}", file=sys.stderr)
        
    if not args.no_play:
        play_audio(wav_content, args.device)

if __name__ == "__main__":
    main()
