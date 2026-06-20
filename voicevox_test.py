#!/usr/bin/env python3
import argparse
import sys
from youtube_tts import VoicevoxClient, AudioPlayer

DEFAULT_HOST = "http://127.0.0.1:50021"
DEFAULT_SPEAKER = 3
DEFAULT_TEXT = "これは、ボイスボックスの発声テストです。"
DEFAULT_OUTPUT = "test.wav"
DEFAULT_VOLUME = 1.0


def list_speakers(client: VoicevoxClient):
    try:
        speakers = client.get_speakers()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"{'ID':<6} | {'話者名':<15} | {'スタイル':<15}")
    print("-" * 45)
    for spk in speakers:
        name = spk.get("name", "Unknown")
        for style in spk.get("styles", []):
            style_name = style.get("name", "")
            style_id = style.get("id", "")
            print(f"{style_id:<6} | {name:<15} | {style_name:<15}")


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
    
    client = VoicevoxClient(base_url=args.host, speaker_id=args.speaker)
    player = AudioPlayer(default_device=args.device)

    if args.list_speakers:
        list_speakers(client)
        return
        
    if args.list_devices:
        print(player.query_devices())
        return
        
    # 出力デバイスの規定サンプリングレートを調べる
    target_sample_rate = args.samplerate
    if target_sample_rate is None and not args.no_play:
        try:
            device_info = player.query_devices(args.device, 'output')
            target_sample_rate = int(device_info['default_samplerate'])
            print(f"[INFO] 出力デバイス: {device_info['name']} (ID: {device_info['index']})")
        except Exception as e:
            print(f"[WARN] デバイスのサンプリングレート取得に失敗しました: {e}", file=sys.stderr)
            
    try:
        print(f"[INFO] 音声合成中: 「{args.text}」 (話者ID: {args.speaker})")
        wav_content = client.synthesize(
            text=args.text,
            volume_scale=args.volume,
            target_sample_rate=target_sample_rate
        )
    except Exception as e:
        print(f"[ERROR] 音声合成に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)
    
    # WAVファイル保存
    try:
        with open(args.output, "wb") as f:
            f.write(wav_content)
        print(f"[INFO] 音声ファイルを保存しました: {args.output}")
    except Exception as e:
        print(f"[ERROR] ファイルの保存に失敗しました: {e}", file=sys.stderr)
        
    if not args.no_play:
        print(f"[INFO] 再生中... (サンプリングレート: {target_sample_rate or player.target_sample_rate}Hz)")
        try:
            player.play_wav(wav_content, device=args.device, target_sample_rate=target_sample_rate)
            print("[INFO] 再生完了")
        except Exception as e:
            print(f"[ERROR] 再生に失敗しました: {e}", file=sys.stderr)
            print("\n利用可能なオーディオデバイス一覧:", file=sys.stderr)
            print(player.query_devices())
            print("\nヒント: --device 引数で適切なデバイス名またはIDを指定して実行してください。", file=sys.stderr)


if __name__ == "__main__":
    main()
