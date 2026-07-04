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
"""VOICEVOX エンジンと連携して音声合成を行うモジュールです。

このモジュールは、VOICEVOX エンジンの REST API を呼び出して
テキストから音声を合成し、WAV 形式のバイナリデータを
返す機能を提供します。
"""

from __future__ import annotations

import requests


class VoicevoxClient:
    """VOICEVOX エンジンの REST API クライアントクラスです。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:50021",
        speaker_id: int = 3,
    ):
        """VoicevoxClient クラスを初期化します。

        Args:
            base_url: VOICEVOX エンジンの REST API のベース URL。
            speaker_id: 音声合成に使用するスピーカー ID。
        """
        self.base_url = base_url
        self.speaker_id = speaker_id

    def get_speakers(self) -> list:
        """VOICEVOX エンジンから利用可能なスピーカー一覧を取得します。

        Returns:
            スピーカー情報のリスト。

        Raises:
            RuntimeError: VOICEVOX サーバーへの接続に失敗した場合。
        """
        try:
            response = requests.get(f"{self.base_url}/speakers")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise RuntimeError(
                f"VOICEVOXサーバーへの接続に失敗しました: {e}"
            ) from e

    def synthesize(
        self,
        text: str,
        volume_scale: float = 1.0,
        speed_scale: float = 1.0,
        target_sample_rate: int | None = None,
    ) -> bytes:
        """VOICEVOX エンジンでテキストを音声合成します。

        Args:
            text: 音声合成するテキスト。
            volume_scale: 音量のスケール係数。デフォルトは 1.0。
            speed_scale: 読上げスピードのスケール係数。デフォルトは 1.0。
            target_sample_rate: 出力サンプリングレート（Hz）。
                None の場合は VOICEVOX のデフォルト値を使用。

        Returns:
            WAV 形式の音声データのバイト列。
        """
        # 1. 音声クエリを作成します。
        query_response = requests.post(
            f"{self.base_url}/audio_query",
            params={"text": text, "speaker": self.speaker_id},
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        # サンプリングレートが指定されている場合は設定します。
        if target_sample_rate:
            query_data["outputSamplingRate"] = target_sample_rate

        # 音量比を設定します。
        query_data["volumeScale"] = volume_scale

        # 読上げスピードを設定します。
        query_data["speedScale"] = speed_scale

        # 2. 音声合成を実行します。
        synthesis_response = requests.post(
            f"{self.base_url}/synthesis",
            params={"speaker": self.speaker_id},
            json=query_data,
        )
        synthesis_response.raise_for_status()
        return synthesis_response.content
