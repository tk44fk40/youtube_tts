# TODO

懸案事項や、将来的にやりたいことのメモ

## 例外時の詳細なデバッグログなどで、ログ出力をインデントしてた箇所

- ほぼ、インデントを廃止したはずだが、残存してるものがあった
- まだ残ってるかもしれないので要チェック

## 例外ブロックの中で更に try してるコードがあった

- 例外処理ブロック内では、複雑な処理を実装するのはタブー
- 不特定の例外をキャッチして処理しなければならないなど、複雑な処理が必要な場合は
  ステータスなどを記録するだけにとどめて、別途判定処理を例外ブロックの外で行う
  ように改善が必要

## モジュール分割

全体的に複雑なコードになってないか、もっとスリムに書けないか検討すべき

- **優先度高：app.py (407行)**
  - アプリケーション全体の制御（スレッド管理、ライフサイクル等）を担っている。
  - Live制御とVideo制御、あるいはアプリケーション初期化部と実行管理部に分割可能か検討する。
- **優先度高：youtube_tts/workers/live.py (349行)**
  - ライブ配信のチャット取得や中継ロジックが詰まっている。
  - ポーリング制御、APIエラーハンドリング、キューイング処理をスリム化・分離できないか検討する。
- **優先度中：youtube_live_voicevox.py (322行)**
  - CLIのエントリーポイント。
  - コマンドライン引数解析（argparse）、シグナルハンドラ、メインループ前のセットアップ処理をユーティリティや別モジュールに逃がせないか検討する。

### 1. メインスクリプト (ルート直下)
| ファイル名 | 行数 | 概要 |
| :--- | :---: | :--- |
| youtube_live_voicevox.py | 322 | YouTube Live配信用エントリーポイント (CLI) |
| youtube_video_voicevox.py | 258 | YouTube アーカイブ動画用エントリーポイント (CLI) |
| get_quota_info.py | 98 | クォータ情報取得用ツールスクリプト |

### 2. アプリケーションおよびライブラリコード (youtube_tts/ 配下)
| ファイル名 | 行数 | 概要 |
| :--- | :---: | :--- |
| youtube_tts/__init__.py | 62 | パッケージ初期化モジュール |
| youtube_tts/app.py | 407 | アプリケーションコア制御モジュール |
| youtube_tts/audio.py | 244 | 音声再生およびデバイス制御モジュール |
| youtube_tts/auth.py | 113 | YouTube API 認証制御モジュール |
| youtube_tts/client.py | 163 | YouTube API クライアント共通モジュール |
| youtube_tts/config.py | 167 | 設定管理モジュール |
| youtube_tts/dictionary.py | 216 | 音声読み上げ用辞書・置換処理モジュール |
| youtube_tts/live.py | 185 | YouTube Live チャット取得クライアント |
| youtube_tts/logger.py | 108 | ロギング設定モジュール |
| youtube_tts/models.py | 255 | データモデル定義モジュール |
| youtube_tts/obs.py | 113 | OBS WebSocket連携制御モジュール |
| youtube_tts/quota.py | 177 | GCP クォータ API クライアントモジュール |
| youtube_tts/utils.py | 65 | 汎用ユーティリティ関数モジュール |
| youtube_tts/video.py | 111 | YouTube 動画コメント取得クライアント |
| youtube_tts/voicevox.py | 106 | VOICEVOX 連携クライアントモジュール |
| youtube_tts/workers/live.py | 349 | ライブコメント取得監視スレッドモジュール |
| youtube_tts/workers/playback.py | 75 | コメント音声再生スレッドモジュール |
| youtube_tts/workers/video.py | 184 | 動画コメント取得監視スレッドモジュール |

### 3. テストコード (tests/ 配下および個別検証用スクリプト)
| ファイル名 | 行数 |
| :--- | :---: |
| tests/conftest.py | 157 |
| tests/test_app_logging.py | 83 |
| tests/test_app_playback.py | 261 |
| tests/test_app_run.py | 252 |
| tests/test_audio_device.py | 188 |
| tests/test_audio_play.py | 205 |
| tests/test_audio_stop.py | 76 |
| tests/test_auth.py | 210 |
| tests/test_config.py | 211 |
| tests/test_dictionary.py | 240 |
| tests/test_get_quota_info.py | 138 |
| tests/test_integration.py | 86 |
| tests/test_live_cli.py | 410 |
| tests/test_live_worker_chat.py | 239 |
| tests/test_live_worker_error.py | 187 |
| tests/test_live_worker_quota.py | 306 |
| tests/test_live_worker_stream.py | 126 |
| tests/test_models.py | 170 |
| tests/test_oauth_test.py | 51 |
| tests/test_obs.py | 107 |
| tests/test_quota.py | 238 |
| tests/test_video_cli.py | 224 |
| tests/test_video_worker_backlog.py | 275 |
| tests/test_video_worker_polling.py | 227 |
| tests/test_voicevox.py | 135 |
| tests/test_voicevox_test.py | 163 |
| tests/test_youtube_live.py | 261 |
| tests/test_youtube_utils.py | 44 |
| tests/test_youtube_video.py | 240 |
| oauth_test.py | 44 |
| voicevox_test.py | 212 |

* **プロジェクト総行数**: 9,544行

## チャットメッセージの種類（Event/snippet.type）による制御

| snippet.type の値           | 意味・内容                         |
| :-------------------------- | :--------------------------------- |
| textMessageEvent            | 通常のテキストチャット             |
| superChatEvent              | スーパーチャット（投げ銭コメント） |
| newSponsorEvent             | 新規メンバーシップ登録             |
| memberMilestoneChatEvent    | メンバー継続マイルストーンチャット |
| giftMembershipReceivedEvent | メンバーシップギフトの受け取り     |
| membershipGiftingEvent      | メンバーシップギフトの贈与         |

例えば…
- メンバー登録イベントの時は読み上げる声を別のキャラクター（VOICEVOXの別のスタイル）に変えたい
- メンバー登録のときは「〇〇さん、メンバー登録ありがとう！」のように特別な定型文で読ませたい

## メンバーの記録（未対応）

- [ ] チャットしてくれたメンバーを記録して、そのメンバーが再度チャットしたときに「〇〇さん、またお話しに来てくれてありがとう！」のように読ませたい
- [ ] メンバーシップの継続日数を記録して、100日、200日…のように継続日数を読み上げたい
- [ ] ライブ、ライブアーカイブ限定

## ログの活用（未対応）

- [ ] 過去のログから頻繁に出てくる単語のランキングを表示
- [ ] 過去のログからよくコメントする人のランキングを表示
- [ ] 過去のログから面白い発言をピックアップ
