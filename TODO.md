# TODO

懸案事項や、将来的にやりたいことのメモ

## VOICEBOX コンテナでの運用

> **対応完了**: 本ツールの起動時に Podman / Docker を使用して `voicevox-engine` コンテナが自動で作成・起動・管理されるようになりました（最後のツール終了時に自動停止）。
> 手動で管理したい場合や外部サーバーを利用する場合は `--no-manage-container` オプションまたは環境変数 `VOICEVOX_MANAGE_CONTAINER=false` を指定してください。

```bash
# 手動操作時のコマンド参考 (Podman)
# VOICEBOX コンテナの作成
podman pull docker.io/voicevox/voicevox_engine:cpu-latest
podman run -d \
  --name voicevox-engine \
  --restart unless-stopped \
  -p 127.0.0.1:50021:50021 \
  docker.io/voicevox/voicevox_engine:cpu-latest

# VOICEBOXの起動
podman start voicevox-engine

# VOICEBOXの停止
podman stop voicevox-engine

# VOICEBOXの削除
podman rm voicevox-engine
```

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
