#!/usr/bin/env python3
# OAuth 初回認証(トークンJSON保存)スクリプト

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"


def load_credentials():
    creds = None

    # token.json が存在する場合
    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # token が無い or 無効
    if not creds or not creds.valid:
        # refresh token で更新可能
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        # 初回OAuthログイン
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)

            creds = flow.run_local_server(port=0)

        # token.json 保存
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


def main():
    creds = load_credentials()

    print("認証成功")
    print(creds.token[:32] + "...")


if __name__ == "__main__":
    main()
