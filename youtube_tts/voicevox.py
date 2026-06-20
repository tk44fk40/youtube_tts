import requests

class VoicevoxClient:
    def __init__(self, base_url="http://127.0.0.1:50021", speaker_id=3):
        self.base_url = base_url
        self.speaker_id = speaker_id

    def get_speakers(self) -> list:
        try:
            response = requests.get(f"{self.base_url}/speakers")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise RuntimeError(
                f"VOICEVOXサーバーへの接続に失敗しました: {e}\n"
                "VOICEVOXが起動しているか、ホストURLが正しいか確認してください。"
            ) from e

    def synthesize(self, text, volume_scale=1.0, target_sample_rate=None) -> bytes:
        # 1. 音声クエリを作成する
        query_response = requests.post(
            f"{self.base_url}/audio_query",
            params={"text": text, "speaker": self.speaker_id}
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        # サンプリングレートが指定されている場合は設定する
        if target_sample_rate:
            query_data["outputSamplingRate"] = target_sample_rate

        # 音量比を設定する
        query_data["volumeScale"] = volume_scale

        # 2. 音声合成を実行する
        synthesis_response = requests.post(
            f"{self.base_url}/synthesis",
            params={"speaker": self.speaker_id},
            json=query_data
        )
        synthesis_response.raise_for_status()
        return synthesis_response.content
