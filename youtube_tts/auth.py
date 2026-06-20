from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

class YouTubeAuthenticator:
    def __init__(self, client_secret_path="client_secret.json", token_path="token.json", scopes=None):
        self.client_secret_path = Path(client_secret_path)
        self.token_path = Path(token_path)
        self.scopes = scopes or ["https://www.googleapis.com/auth/youtube.readonly"]

    def get_credentials(self) -> Credentials:
        creds = None

        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
            except Exception:
                try:
                    self.token_path.unlink()
                except OSError:
                    pass

        # If token does not exist or is invalid
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None

            if not creds:
                if not self.client_secret_path.exists():
                    raise RuntimeError(
                        f"{self.client_secret_path.name} was not found. "
                        "Please download it from Google Cloud Console and place it in the workspace."
                    )
                # First time or token refreshed failed
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret_path), self.scopes
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials
            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        return creds
