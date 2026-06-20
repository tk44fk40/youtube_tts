
class ObsClient:
    def __init__(self, host="localhost", port=4455, password=None):
        self.host = host
        self.port = port
        self.password = password

        # obs-websocket-py のインポートを一度だけ試みてキャッシュする
        try:
            from obswebsocket import obsws, requests as obs_requests
            self._obsws = obsws
            self._obs_requests = obs_requests
            self._available = True
        except ImportError:
            self._obsws = None
            self._obs_requests = None
            self._available = False

    def update_chat_url(self, source_name: str, url: str) -> bool:
        if not source_name:
            return False

        if not self.password:
            print("[OBS] OBS_WEBSOCKET_PASSWORD is not set; skipping OBS update")
            return False

        if not self._available:
            print(
                "[OBS] obs-websocket library is not installed; install obs-websocket-py to enable OBS integration"
            )
            return False

        try:
            ws = self._obsws(self.host, self.port, self.password)
            ws.connect()
            ws.call(
                self._obs_requests.SetInputSettings(
                    inputName=source_name, inputSettings={"url": url}
                )
            )
            ws.disconnect()
            print("[OBS] ✓ チャットURL設定成功")
            print(f"      URL: {url}")
            return True
        except Exception as e:
            print(f"[OBS] ✗ チャットURL設定失敗: {e}")
            return False
