import sys
from urllib.parse import parse_qs, urlparse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class YouTubeChatClient:
    def __init__(self, credentials):
        self.youtube = build("youtube", "v3", credentials=credentials)

    def extract_video_id(self, value):
        if "youtube.com" not in value and "youtu.be" not in value:
            return value

        parsed = urlparse(value)

        # youtu.be/<id>
        if parsed.netloc == "youtu.be":
            return parsed.path.lstrip("/")

        # youtube.com/watch?v=<id>
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            if "v" in query:
                return query["v"][0]

        # youtube.com/live/<id>
        if parsed.path.startswith("/live/"):
            parts = parsed.path.split("/")
            if len(parts) >= 3:
                return parts[2]

        raise RuntimeError("failed to extract video id")

    def get_live_chat_id(self, video_id):
        try:
            response = self.youtube.videos().list(part="liveStreamingDetails", id=video_id).execute()
        except HttpError as e:
            self._handle_quota_error(e)
            raise

        items = response.get("items", [])
        if not items:
            raise RuntimeError("video not found")

        details = items[0].get("liveStreamingDetails", {})
        live_chat_id = details.get("activeLiveChatId")
        if not live_chat_id:
            raise RuntimeError("activeLiveChatId not found")

        return live_chat_id

    def get_current_live_video_id(self):
        try:
            response = self.youtube.liveBroadcasts().list(part="id,status", mine=True).execute()
        except HttpError as e:
            self._handle_quota_error(e)
            raise

        items = response.get("items", [])
        for item in items:
            status = item.get("status", {}).get("lifeCycleStatus")
            if status == "live":
                vid = item.get("id")
                chat_url = f"https://www.youtube.com/live_chat?v={vid}&is_popout=1"
                return vid, chat_url

        raise RuntimeError(
            "No live broadcast found. "
            "Please start a live stream or pass VIDEO_ID as an argument."
        )

    def fetch_chat_messages(self, live_chat_id, page_token=None):
        try:
            response = (
                self.youtube.liveChatMessages()
                .list(
                    liveChatId=live_chat_id,
                    part="snippet,authorDetails",
                    pageToken=page_token,
                    maxResults=200,
                )
                .execute()
            )
        except HttpError as e:
            self._handle_quota_error(e)
            raise

        items = response.get("items", [])
        next_page_token = response.get("nextPageToken")
        polling_interval_min = 3000
        polling_interval = max(
            response.get("pollingIntervalMillis", polling_interval_min),
            polling_interval_min,
        )

        return items, next_page_token, polling_interval

    def check_stream_active(self, video_id) -> bool:
        try:
            vresp = (
                self.youtube.videos()
                .list(part="liveStreamingDetails", id=video_id)
                .execute()
            )
        except HttpError as e:
            self._handle_quota_error(e)
            print(f"[WARN] Error checking video status: {e}")
            return True
        
        items = vresp.get("items", [])
        if not items:
            print("[INFO] Video not found; assuming stream ended")
            return False

        details = items[0].get("liveStreamingDetails", {})
        active_chat = details.get("activeLiveChatId")
        if not active_chat:
            print("[INFO] activeLiveChatId missing; stream likely ended")
            return False

        return True

    def _handle_quota_error(self, e):
        if e.resp.status == 403 and "quotaExceeded" in str(e):
            print("\n[ERROR] YouTube API quota exceeded")
            print("        Please wait 24 hours before running again")
            print(f"        Error: {e}")
