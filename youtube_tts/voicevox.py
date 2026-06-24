# Copyright 2026 tk44fk40
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
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
                f"VOICEVOXサーバーへの接続に失敗しました: {e}"
            ) from e

    def synthesize(
        self, text, volume_scale=1.0, speed_scale=1.0, target_sample_rate=None
    ) -> bytes:
        # 1. Create an audio query
        #
        # 1. 音声クエリを作成する
        query_response = requests.post(
            f"{self.base_url}/audio_query",
            params={"text": text, "speaker": self.speaker_id}
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        # Set sampling rate if target_sample_rate is specified
        #
        # サンプリングレートが指定されている場合は設定する
        if target_sample_rate:
            query_data["outputSamplingRate"] = target_sample_rate

        # Set volume scale
        #
        # 音量比を設定する
        query_data["volumeScale"] = volume_scale

        # Set speaking speed scale
        #
        # 読上げスピードを設定する
        query_data["speedScale"] = speed_scale

        # 2. Perform speech synthesis
        #
        # 2. 音声合成を実行する
        synthesis_response = requests.post(
            f"{self.base_url}/synthesis",
            params={"speaker": self.speaker_id},
            json=query_data
        )
        synthesis_response.raise_for_status()
        return synthesis_response.content
