#!/usr/bin/env python3
# OAuth 初回認証(トークンJSON保存)スクリプト

import sys
from youtube_tts import YouTubeAuthenticator

TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"


def main():
    try:
        authenticator = YouTubeAuthenticator(
            client_secret_path=CLIENT_SECRET_FILE,
            token_path=TOKEN_FILE
        )
        creds = authenticator.get_credentials()
        print("認証成功")
        print(creds.token[:32] + "...")
    except Exception as e:
        print(f"[ERROR] 認証に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
