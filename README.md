# YouTube Live Chat TTS with VOICEVOX

**[English]** | **[日本語 (Japanese)](README.ja.md)**

---

"Meet Yucha-pon! It reads out YouTube Live chat in real-time, making streaming way more fun."

---

## Table of Contents

- [Background](#background)
- [1. Overview and Usage](#1-overview-and-usage)
  - [Overview](#overview)
  - [Prerequisites](#prerequisites)
  - [Setup Instructions](#setup-instructions)
  - [Execution / Usage](#execution--usage)
  - [Differences in Stream Modes & Backlog Handling](#differences-in-stream-modes--backlog-handling)
  - [Helper Scripts and Options](#helper-scripts-and-options)
  - [Console Output Prefixes](#console-output-prefixes)
  - [Environment Variables](#environment-variables)
  - [Checking and Specifying Audio Devices](#checking-and-specifying-audio-devices)
  - [Configuration Files](#configuration-files)
  - [Credentials & Token Files (client_secret.json / token.json)](#credentials--token-files-client_secretjson--tokenjson)
- [2. Library Overview](#2-library-overview)
  - [Module Structure](#module-structure)
  - [Key Classes and Functions](#key-classes-and-functions)
- [3. Testing](#3-testing)
  - [Running Tests](#running-tests)
- [4. License](#4-license)

---

## Background

When switching to Linux environment, comment read-aloud tools used in Windows became unavailable. Thus, this tool was created from scratch using VOICEVOX. While utilizing it in actual live streaming, features like dictionary replacement, NG words filter, and OBS integration were gradually added to form the current project.

---

## 1. Overview and Usage

### Overview
This tool retrieves comments from YouTube Live chat in real-time and reads them aloud using the VOICEVOX speech synthesis engine.
It supports dynamic configuration reloading and automatic URL updates for OBS browser sources.

> [!WARNING]
> **Important Security Notice Regarding Credentials (`client_secret.json` / `token.json`)**
> This tool saves Google API (YouTube Data API v3) credentials in local files. Because these files contain sensitive credentials, they must NEVER be committed or publicly exposed to GitHub or other public repositories. (They are pre-configured to be excluded in the project's `.gitignore` file).
> For setup instructions, please refer to [Placing Google OAuth Credentials](#4-placing-google-oauth-credentials).

### Prerequisites

To use this tool, the following environment and services must be prepared:

1. **Python 3.12 or higher**
   - This tool runs on Python 3.12 or higher (the standard Python for Ubuntu 24.04 is 3.12).
   - We use `uv` for package management. Python itself can be installed from your OS packages or [python.org](https://www.python.org/).
1. **Linux Environment & System Audio Playback Commands**
   - This tool is **Linux-exclusive**. Windows and macOS are not supported.
   - For audio playback, one of the following commands must be installed
     on your system: `pw-play` (PipeWire), `aplay` (ALSA), or `paplay` (PulseAudio).
     (These are usually pre-installed on most Linux distributions.)
   - To easily identify numerical IDs and detailed names with the device
     list feature (`--list-devices`), it is recommended to have `pactl`
     installed on your system (falls back to `aplay` for a simplified list
     if `pactl` is not available; see [Checking and Specifying Audio Devices](#checking-and-specifying-audio-devices) for details).
2. **VOICEVOX**
   - VOICEVOX (Desktop or Docker version) must be running beforehand, with its API accessible on the default port `50021`.
3. **OBS (Open Broadcaster Software) & Browser Source** *(Required only for OBS integration)*
   - To display chat on the streaming screen, a browser source must be set up in OBS.
   - Add a "Browser Source" in your OBS scene.
   - The tool automatically retrieves the live chat URL (`https://www.youtube.com/live_chat?v=...`) generated at the start of the stream, and automatically updates the specified browser source URL via OBS WebSocket.
   - If you do not want to use OBS integration, leave the `OBS_WEBSOCKET_PASSWORD` environment variable unset, and this feature will be skipped.
4. **Google Cloud Console & YouTube Data API v3**
   - To retrieve YouTube Live chat details via the API, you must create a Google Cloud project, enable "YouTube Data API v3", and create an OAuth 2.0 Client credentials file (`client_secret.json`).
   - For detailed steps, refer to [Setup Step 4: Placing Google OAuth Credentials](#4-placing-google-oauth-credentials).

> [!IMPORTANT]
> This tool is designed for Linux environments only. Operating on Windows or macOS is not supported.

### Setup Instructions

#### 1. Obtain the Repository

**Download from GitHub:**
Go to the [GitHub Releases page](https://github.com/tk44fk40/youtube_tts/releases) or the [repository main page](https://github.com/tk44fk40/youtube_tts) and download the ZIP file via "Code" -> "Download ZIP", then extract it to any directory.

**Clone with Git:**
```bash
git clone https://github.com/tk44fk40/youtube_tts.git
cd youtube_tts
```

#### 2. Install uv

This project uses `uv` (a fast Python package and project manager) to manage dependencies. If you haven't installed it yet, install it using the following command:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, restart your terminal or run `source ~/.local/bin/env` to apply the path changes.  
For other installation methods, refer to the [uv Official Documentation](https://docs.astral.sh/uv/getting-started/installation/).

#### 3. Install Dependencies

Run the following command inside the project directory. The dependent packages will be installed into a virtual environment (if your system's default Python is 3.12+, it will be used directly):
```bash
uv sync
```

#### 4. Placing Google OAuth Credentials

To use the YouTube Data API v3, retrieve the credentials file (`client_secret.json`) from the Google Cloud Console and place it in the project root.

<details>
<summary><b>Detailed Steps (Click to expand)</b></summary>

##### 1. Create a Google Cloud Project
1. Access [Google Cloud Console](https://console.cloud.google.com/) and log in with your Google account.
2. Click the project selection menu at the top-left, and create a **"New Project"** (name it as you like).

##### 2. Enable YouTube Data API v3
1. Verify that your newly created project is selected.
2. From the top-left menu, choose **"APIs & Services"** > **"Library"**.
3. Enter `YouTube Data API v3` in the search bar, select it, and click **"Enable"**.

##### 3. Configure OAuth Consent Screen (If creating for the first time)
1. Select **"OAuth consent screen"** from the left menu.
2. Select **"External"** for User Type, and click **"Create"**.
3. Fill in the **"App information"** (App name, User support email) and **"Developer contact information"** (Email address), then click **"Save and Continue"**.
4. Skip the "Scopes" screen by clicking **"Save and Continue"**.
5. On the "Test users" screen, click **"+ ADD USERS"** and add the Google account you intend to use for streaming, then click **"Save and Continue"**.
6. Finally, click **"Back to Dashboard"**.

##### 4. Create and Download OAuth Client ID
1. Select **"Credentials"** from the left menu.
2. Click **"+ Create Credentials"** at the top, and select **"OAuth client ID"**.
3. Select **"Desktop app"** for Application type.
4. Enter a name (e.g., `YouTube TTS`) and click **"Create"**.
5. Your created item will appear under "OAuth 2.0 Client IDs". Click the **Download icon (Download JSON)** on the far right to save the file.

##### 5. Place the File
1. Rename the downloaded JSON file to **`client_secret.json`**.
2. Place it in the root directory of this project (where `youtube_voicevox.py` is located).

</details>

#### 5. Execute Initial Authentication
Run the following script and log in via your browser to complete authentication. Upon completion, `token.json` will be generated in the root directory.
```bash
uv run python3 oauth_test.py
```

#### 6. Start VOICEVOX
Ensure VOICEVOX is running and its API is accessible at the default port `50021`.

### Execution / Usage

#### Direct Video URL or Video ID Specification
```bash
uv run python3 youtube_voicevox.py https://www.youtube.com/watch?v=YOUR_VIDEO_ID
# OR
uv run python3 youtube_voicevox.py YOUR_VIDEO_ID
```

#### Auto-Detection of Current Stream (For your own channel)
If the channel configured in `client_secret.json` / `token.json` is currently live, you can start the application without arguments to auto-detect the stream.
```bash
uv run python3 youtube_voicevox.py
```

#### Specifying the Audio Device
You can specify a specific sound output device (e.g., Device ID 6) to play audio.
```bash
uv run python3 youtube_voicevox.py -d 6
```

#### Command Line Options (`youtube_voicevox.py`)

| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--device` | `-d` | Index or name of the audio output device. | (System default device) |
| `--quota-check` | `-q` | Enables the quota info checking feature for debugging (prints to console periodically). | `False` |
| `--quota-talk` | (None) | Enables speaking the quota usage (only when value changes). After playing a chime, it announces the quota value. Enabling this automatically enables `--quota-check`. If the YouTube API quota is exceeded, it also announces the reset time before exiting. | `False` |
| `--tts-test [TEXT]` | (None) | Speaks the specified text at startup if it's your own stream. If text is omitted, uses "Ding-dong! Testing chat read-aloud". Can also be specified via the env var `VOICEVOX_TTS_TEST`. | `None` (Disabled) |
| `--chat-interval` | (None) | Minimum interval (in seconds) between comment fetches. | `20.0` |
| `--chat-log` | (None) | File path to save chat logs. | `"chat_log.jsonl"` |
| `--backlog-seconds` | (None) | Time window (in seconds) to backtrack past comments at startup. If `-1` is specified, all past comments in the rolling buffer (up to 200) are read. *Only valid in Live Stream Mode.* | `10` |
| `--backlog-counts` | (None) | Maximum number of past comments to fetch and read at startup in Archive/Video mode. If `-1` is specified, all past comments are read. *Only valid in Comment Mode.* | `100` |
| `--quota-interval` | (None) | Minimum interval (in seconds) between quota checks. | `180.0` |
| `--stream-check-interval` | (None) | Interval (in seconds) to check stream active status. | `180.0` |
| `--speed` | (None) | Read-aloud speed scale. Larger values are faster. Can also be set via env var `VOICEVOX_SPEED_SCALE`. | `1.0` |
| `--auto-speed-boost` | (None) | Auto-boosts speaking speed when comments pile up in the queue. Can also be set via env var `VOICEVOX_AUTO_SPEED_BOOST`. | `False` |
| `--max-speed` | (None) | Maximum speed limit during auto speed boost (hard limit: `2.2`). Can also be set via env var `VOICEVOX_MAX_SPEED`. | `2.2` |
| `--verbose` | `-v` | Outputs detailed (DEBUG) logs to the console. | `False` |

### Differences in Stream Modes & Backlog Handling

This tool automatically detects the video status and operates in either "Live Stream Mode" or "Comment Mode".

| Item | Live Stream Mode (Active live stream / waiting room) | Comment Mode (Archived streams / uploaded videos) |
| :--- | :--- | :--- |
| **Target Video Status** | Live streams currently broadcasting or waiting | Completed streams, regular video uploads |
| **Effective Backlog Options** | **`--backlog-seconds`** (how many seconds to look back) | **`--backlog-counts`** (how many comments to read at start) |
| **Ignored Options** | `--backlog-counts` | `--backlog-seconds` |
| **API Limit Behavior** | Due to YouTube API (`liveChatMessages`) limitations, filtering by timestamp is not supported. The tool fetches all comments in the rolling buffer (up to 200) and filters out older ones on the client-side based on `--backlog-seconds`. | Fetch count can be specified in the YouTube API (`commentThreads`). The tool fetches only the number specified in `--backlog-counts` (default 100). If `-1` is set, all comments are fetched using pagination. |
| **End of Stream Monitoring** | Enabled (stops the tool automatically when stream ends) | Disabled (skipped since it's a pre-recorded video) |

### Helper Scripts and Options

#### 1. OAuth Initial Authentication (`oauth_test.py`)
- **Description**: Performs initial authentication for YouTube API and generates/saves the access token to `token.json`.
- **Usage**:
  ```bash
  uv run python3 oauth_test.py
  ```

#### 2. YouTube API Quota Check (`get_quota_info.py`)
- **Description**: Displays the YouTube Data API quota consumption over the last 24 hours and the remaining quota for today.
- **Usage**:
  ```bash
  uv run python3 get_quota_info.py
  ```
  *(Requires billing setup in your GCP project as it queries Cloud Monitoring API)*

#### 3. VOICEVOX Speech Test (`voicevox_test.py`)
- **Description**: Performs a standalone test using VOICEVOX. Verifies audio synthesis, WAV saving, and playback.
- **Usage**:
  ```bash
  uv run python3 voicevox_test.py [options]
  ```
- **Options**:
  | Option | Short | Description | Default |
  | :--- | :--- | :--- | :--- |
  | `--text` | `-t` | Japanese text to speak. | `"これは、ボイスボックスの発声テストです。"` |
  | `--speaker` | `-s` | VOICEVOX Speaker Style ID. | `3` (Zundamon Normal) |
  | `--volume` | `-v` | Volume scale factor (`0.0` - `2.0`). | `1.0` |
  | `--speed` | (None) | Speaking speed scale. Can also be set via env var `VOICEVOX_SPEED_SCALE`. | `1.0` |
  | `--output` | `-o` | Output file path for the synthesized WAV. | `"test.wav"` |
  | `--host` | `-H` | VOICEVOX server URL. | `"http://127.0.0.1:50021"` |
  | `--device` | `-d` | Audio output device index or name. | (System default device) |
  | `--samplerate` | `-r` | Audio sampling rate (Hz) for playback. | (Device default value) |
  | `--list-speakers` | (None) | Prints available speakers and style IDs, then exits. | (None) |
  | `--list-devices` | (None) | Prints recognized audio output devices, then exits. | (None) |
  | `--no-play` | (None) | Disables speaker playback, saves WAV file only. | (None) |

### Console Output Prefixes

- **`[CONFIG]`**: Printed when settings files (volume, dictionary, NG words) are loaded or reloaded dynamically.
  - Example: `[CONFIG] volume scale updated: 0.5`
- **`[CHAT]`**: Printed when a new chat comment is received.
  - Example: `[CHAT] Taro: こんにちは`
- **`[TALK]`**: Printed when VOICEVOX speech playback starts (after adding honorifics and dictionary replacements).
  - Example: `[TALK] Taroさん こんにちは`
- **`[SKIP(NG)]`**: Printed when a comment is skipped due to NG words.
- **`[SKIP(QUEUE)]`**: Printed when a comment is skipped because the queue size limit (50) is reached.
- **`[OBS]`**: Results of updating the browser source chat URL via OBS WebSocket.
  - Example: `[OBS] ✓ チャットURL設定成功`
- **`[QUOTA]`**: Printed when quota checking is active.
  - Example: `[QUOTA] Used: 963 / 10,000 (9.63%), Remaining: 9,037`
- **`[TTS-TEST]`**: Printed when test reading is executed at startup.
- **`[INFO] / [WARN] / [ERROR]`**: System logs indicating startup info, warning on delete/disconnects, or API errors.

### Environment Variables

| Variable | Description | Default | Example / Note |
| :--- | :--- | :--- | :--- |
| `VOICEVOX_AUTHOR_SUFFIX` | Honorific suffix added to author's name. Set to empty to disable. | `さん` | `ちゃん`, `様`, `""` |
| `VOICEVOX_URL` | VOICEVOX server URL. | `http://127.0.0.1:50021` | `http://localhost:50021` |
| `VOICEVOX_SPEAKER_ID` | Speaker Style ID for VOICEVOX synthesis. | `3` (Zundamon) | `2` (Metan), `8` (Tsumugi) |
| `VOICEVOX_VOLUME_SCALE` | Initial volume if `volume.txt` does not exist or this variable is set. | `1.0` | `0.5` (50% volume) |
| `VOICEVOX_SPEED_SCALE` | Initial read-aloud speed scale. | `1.0` | `1.5` |
| `VOICEVOX_AUTO_SPEED_BOOST` | Enables speed boosting when comments pile up. | `false` | `true` |
| `VOICEVOX_MAX_SPEED` | Maximum speed limit during speed boost. | `2.2` | `2.0` |
| `VOICEVOX_DEVICE` | Audio device index or name. | (System default) | `6` or `pipewire` |
| `VOICEVOX_TTS_TEST` | Text to read aloud at startup if it's your own stream. | (None) | `ぴんぽーん！チャット読上げのテストです` |
| `OBS_WEBSOCKET_PASSWORD` | OBS WebSocket authentication password. | (None) | `your_obs_websocket_password` |
| `OBS_WEBSOCKET_HOST` | OBS WebSocket host name. | `localhost` | `127.0.0.1` |
| `OBS_WEBSOCKET_PORT` | OBS WebSocket port. | `4455` | `4455` |
| `OBS_BROWSER_SOURCE_NAME` | Browser source name in OBS for chat URL update. | `チャット` | `LiveChatUrl` |

### Checking and Specifying Audio Devices

To change the audio output destination, use the `--list-devices` option to
get a list of available devices on your system, and specify it with the
`--device` argument or the `VOICEVOX_DEVICE` environment variable.

#### 1. When pactl is installed (Recommended)
If the `pactl` command is available, the IDs and names of the PipeWire/
PulseAudio "sinks" are listed clearly as follows:

```text
利用可能なオーディオ出力デバイス (pactl):
  ID: 7 -> alsa_output.pci-0000_00_1f.3.analog-stereo
  ID: 12 -> alsa_output.pci-0000_00_1f.3.hdmi-stereo
```

**Examples**:
* Specifying by numerical ID:
  ```bash
  uv run voicevox_test.py --device 7
  ```
* Specifying by device name:
  ```bash
  uv run voicevox_test.py --device alsa_output.pci-0000_00_1f.3.analog-stereo
  ```

#### 2. When falling back to aplay (pactl not available)
If `pactl` is not available, the physical/logical device names of ALSA
are displayed as a simplified list:

```text
利用可能なオーディオ出力デバイス (aplay):
  default
  sysdefault:CARD=PCH
  hdmi:CARD=PCH,DEV=0
```

**Example**:
* Specifying by connection identifier:
  ```bash
  uv run voicevox_test.py --device sysdefault:CARD=PCH
  ```

### Configuration Files

These files are reloaded in real-time when changes are detected:

#### Volume Configuration File (`volume.txt`)
- **Format**: A single float value between `0.0` and `2.0`.
- **Example**: `0.5` (Sets volume to 50%)

#### Pronunciation Dictionary File (`dictionary.txt`)
- **Format**: `WordBefore = WordAfter` per line.
- **Example**:
  ```text
  google = グーグル
  w = わら
  初見 = しょけん
  ```

#### NG Words File (`ng_words.txt`)
- **Format**: One word per line to skip reading.
- **Example**:
  ```text
  spamword
  ad
  ```

### Credentials & Token Files (`client_secret.json` / `token.json`)

These files contain sensitive information. **Never commit them to a public repository.** (They are excluded via `.gitignore`).

#### OAuth Client Info (`client_secret.json`)
Contains client credentials for YouTube API. Download from Google Cloud Console.

#### Access Token File (`token.json`)
Automatically generated after initial authentication. Automatically refreshed using `client_secret.json`. Re-authorization may be needed if new permissions (e.g. `monitoring.read` scope) are requested.

---

## 2. Library Overview

Modules and classes inside `youtube_tts` package:

### Module Structure
```text
youtube_tts/
├── __init__.py           # Package entry point
├── app.py                # Application execution control
├── audio.py              # Audio data decoding, resampling, and playback
├── auth.py               # Google API authentication management
├── client.py             # Common base client for YouTube API
├── config.py             # Dynamic configuration loading and watching
├── dictionary.py         # Comment normalization, translation, and NG word filtering
├── live.py               # YouTube Live chat acquisition
├── logger.py             # Package-wide logger configuration
├── models.py             # Data model definitions
├── obs.py                # OBS WebSocket integration
├── quota.py              # YouTube API quota information retrieval
├── utils.py              # Common utility functions
├── video.py              # YouTube video comment acquisition
├── voicevox.py           # VOICEVOX API integration
└── workers/              # Background processing threads
    ├── live.py           # Live chat monitoring worker
    ├── playback.py       # Audio playback processing worker
    └── video.py          # Video comment monitoring worker
```

### Key Classes and Functions
- **`YouTubeTtsApp`** (Module: `youtube_tts/app.py`):
  Manages the comment receive/playback queue, and the overall program lifecycle and execution state.
- **`AudioPlayer`** (Module: `youtube_tts/audio.py`):
  Decodes synthesized WAV data, manages audio devices, performs resampling for different sample rates, and controls audio playback.
- **`YouTubeAuthenticator`** (Module: `youtube_tts/auth.py`):
  Manages Google API credential lifecycle including loading `token.json`, refreshing expired tokens, and executing new OAuth flow.
- **`BaseYouTubeClient`** (Module: `youtube_tts/client.py`):
  Base class that provides common communication and error handling processes with YouTube API.
- **`AppConfig`** (Module: `youtube_tts/config.py`):
  Monitors settings files (`volume.txt`, `dictionary.txt`, `ng_words.txt`) and automatically reloads them upon detecting timestamp changes.
- **`TextProcessor`** (Module: `youtube_tts/dictionary.py`):
  Normalizes and filters comments by adding honorific suffixes to author names, removing URLs and emojis, replacing text, and checking NG words.
- **`YouTubeLiveChatClient`** (Module: `youtube_tts/live.py`):
  Detects YouTube Live streams, retrieves chat comments, and monitors stream active status.
- **`CommentItem`** (Module: `youtube_tts/models.py`):
  A data model class that holds YouTube comments and metadata.
- **`ObsClient`** (Module: `youtube_tts/obs.py`):
  Communicates with OBS via OBS WebSocket (port 4455) to automatically update browser source URLs.
- **`YouTubeVideoClient`** (Module: `youtube_tts/video.py`):
  Retrieves comment threads for past stream archives and regular video uploads.
- **`VoicevoxClient`** (Module: `youtube_tts/voicevox.py`):
  Calls VOICEVOX API (`/audio_query`, `/synthesis`) to synthesize audio for a specified speaker style.
- **`live_worker` / `video_worker` / `playback_worker`** (Module: `youtube_tts/workers/` subpackage):
  Background workers for processing stream monitoring, video comment monitoring, and audio playback asynchronously in separate threads.

---

## 3. Testing

The repository contains mock-based unit tests for each module and simplified integration tests verifying the data pipeline in the `tests/` directory.

### Running Tests
Execute unit tests and measure coverage:
```bash
uv run pytest --cov=youtube_tts --cov=youtube_live_voicevox --cov-report=term-missing
```

---

## 4. License

This project is licensed under the [Apache License 2.0](LICENSE).
