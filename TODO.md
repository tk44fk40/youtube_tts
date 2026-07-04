# TODO

懸案事項や、将来的にやりたいことのメモ


## ログに関するテストコードの改善

- ログが出ること、ログ出力部分のカバレッジが重要であって、ログ内容はあまり重要じゃない
- ログ内容まで検証しない


## モジュール分割

全体的に複雑なコードになってないか、もっとスリムに書けないか検討すべき

- テストコード肥大化、要分割
  - test_app_video_worker.py 太り過ぎ
  - test_app_live_worker.py 太り過ぎ
  - test_audio.py おデブちゃん
  - test_live_cli.py もうちょっとがんばりましょう
  - tests/test_youtube_video.py が複数のモジュールのテストを含んでる？
- app.py をモジュール分割したがまだ巨大
- youtube_live_voicevox.py もうちょっとがんばりましょう
- youtube_tts/workers/live.py もうちょっとがんばりましょう

### 1. メインスクリプト (ルート直下)
| ファイル名 | 行数 | 概要 |
| :--- | :---: | :--- |
| youtube_live_voicevox.py | 322 | YouTube Live配信用エントリーポイント (CLI) |
| youtube_video_voicevox.py | 258 | YouTube アーカイブ動画用エントリーポイント (CLI) |
| get_quota_info.py | 103 | クォータ情報取得用ツールスクリプト |

### 2. アプリケーションおよびライブラリコード (youtube_tts/ 配下)
| ファイル名 | 行数 | 概要 |
| :--- | :---: | :--- |
| youtube_tts/__init__.py | 51 | パッケージ初期化モジュール |
| youtube_tts/app.py | 430 | アプリケーションコア制御モジュール |
| youtube_tts/audio.py | 245 | 音声再生およびデバイス制御モジュール |
| youtube_tts/auth.py | 113 | YouTube API 認証制御モジュール |
| youtube_tts/client.py | 157 | YouTube API クライアント共通モジュール |
| youtube_tts/config.py | 167 | 設定管理モジュール |
| youtube_tts/dictionary.py | 218 | 音声読み上げ用辞書・置換処理モジュール |
| youtube_tts/live.py | 188 | YouTube Live チャット取得クライアント |
| youtube_tts/logger.py | 108 | ロギング設定モジュール |
| youtube_tts/models.py | 51 | データモデル定義モジュール |
| youtube_tts/obs.py | 113 | OBS WebSocket連携制御モジュール |
| youtube_tts/quota.py | 169 | GCP クォータ API クライアントモジュール |
| youtube_tts/utils.py | 65 | 汎用ユーティリティ関数モジュール |
| youtube_tts/video.py | 111 | YouTube 動画コメント取得クライアント |
| youtube_tts/voicevox.py | 106 | VOICEVOX 連携クライアントモジュール |
| youtube_tts/workers/live.py | 341 | ライブコメント取得監視スレッドモジュール |
| youtube_tts/workers/playback.py | 75 | コメント音声再生スレッドモジュール |
| youtube_tts/workers/video.py | 184 | 動画コメント取得監視スレッドモジュール |

### 3. テストコード (tests/ 配下および個別検証用スクリプト)
| ファイル名 | 行数 |
| :--- | :---: |
| tests/conftest.py | 104 |
| tests/test_app_live_worker.py | 1,059 |
| tests/test_app_logging.py | 83 |
| tests/test_app_playback.py | 286 |
| tests/test_app_run.py | 251 |
| tests/test_app_video_worker.py | 824 |
| tests/test_audio.py | 596 |
| tests/test_auth.py | 212 |
| tests/test_config.py | 216 |
| tests/test_dictionary.py | 241 |
| tests/test_get_quota_info.py | 168 |
| tests/test_integration.py | 86 |
| tests/test_live_cli.py | 359 |
| tests/test_models.py | 35 |
| tests/test_obs.py | 113 |
| tests/test_quota.py | 236 |
| tests/test_video_cli.py | 224 |
| tests/test_voicevox.py | 135 |
| tests/test_youtube_live.py | 262 |
| tests/test_youtube_utils.py | 46 |
| tests/test_youtube_video.py | 240 |
| oauth_test.py | 44 |
| voicevox_test.py | 212 |

* **プロジェクト総行数**: 9,607行


## models.py の存在意義
- class CommentItem(tuple) しかない
- ほかにもクラスにしたほうがいいもの（レスポンスとか）があるはず


## READMEの改善

- ライブラリのディレクトリ構成、クラス説明が更新できてない
- テスト環境の構成は冗長。使い方だけでいい


## テストコードにもライセンス表記？

- いまんとこ一部を除きテストコードにはライセンス表記してない
- 多分いらない


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

