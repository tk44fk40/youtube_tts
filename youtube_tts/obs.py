import os

class ObsClient:
    def __init__(self, host="localhost", port=4455, password=None):
        self.host = host
        self.port = port
        self.password = password

    def update_chat_url(self, source_name: str, url: str) -> bool:
        if not source_name:
            return False

        if not self.password:
            print("[OBS] OBS_WEBSOCKET_PASSWORD is not set; skipping OBS update")
            return False

        try:
            from obswebsocket import obsws, requests as obs_requests
        except ImportError:
            print(
                "[OBS] obs-websocket library is not installed; install obs-websocket-py to enable OBS integration"
            )
            return False

        try:
            ws = obsws(self.host, self.port, self.password)
            ws.connect()
            ws.call(
                obs_requests.SetSourceSettings(
                    sourceName=source_name, sourceSettings={"url": url}
                )
            )
            ws.disconnect()
            print("[OBS] ✓ チャットURL設定成功")
            print(f"      URL: {url}")
            return True
        except Exception as e:
            print(f"[OBS] ✗ チャットURL設定失敗: {e}")
            return False
