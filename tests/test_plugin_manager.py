"""PluginManager およびプラグイントランスポートのテストモジュールです。"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest
from httpx import Response
from pytest_mock import MockerFixture

from youtube_tts.plugins.manager import (
    DEFAULT_MANIFEST_FILENAME,
    PluginManager,
)
from youtube_tts.plugins.models import (
    TRANSPORT_HTTP,
    TRANSPORT_STDIO,
    PluginManifest,
    PluginMessage,
)
from youtube_tts.plugins.transports import HttpTransport, StdioTransport

# テスト用定数
DEFAULT_TEST_TIMEOUT = 2.0
SHORT_TEST_TIMEOUT = 0.2
DEFAULT_TEST_VERSION = "1.0.0"
DEFAULT_TEST_PLUGIN_TYPE = "test"


@pytest.mark.asyncio
async def test_plugin_manager_scan_empty(tmp_path: Path) -> None:
    """空または存在しないディレクトリをスキャンした場合のテストです。

    Args:
        tmp_path: Pytest 一時ディレクトリパス。
    """
    # [検証目的]: ディレクトリ未存在時に空リストを返すか検証
    # [実施内容]: 存在しないパスを指定し scan_plugins() を実行
    pm = PluginManager(tmp_path / "non_existent")
    pm.scan_plugins()
    assert pm.get_plugin_names() == []

    # [検証目的]: 非プラグイン要素がスキップされるか検証
    # [実施内容]: マニフェストなしのファイル・フォルダを作成して検証
    (tmp_path / "some_file.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "dir_no_manifest").mkdir()

    pm_empty = PluginManager(tmp_path)
    pm_empty.scan_plugins()
    assert pm_empty.get_plugin_names() == []


@pytest.mark.asyncio
async def test_plugin_manager_scan_invalid_manifest(tmp_path: Path) -> None:
    """不正なマニフェスト等の読み込みハンドリングのテストです。

    Args:
        tmp_path: Pytest 一時ディレクトリパス。
    """
    # [検証目的]: 構文エラー manifest.json がスキップされるか検証
    # [実施内容]: 不正 JSON ファイルを作成しスキャンする
    plugin_dir = tmp_path / "bad_plugin"
    plugin_dir.mkdir()
    manifest_file = plugin_dir / DEFAULT_MANIFEST_FILENAME
    manifest_file.write_text('{"invalid_json":', encoding="utf-8")

    pm = PluginManager(tmp_path)
    pm.scan_plugins()
    assert pm.get_plugin_names() == []

    # [検証目的]: マニフェストが非辞書型 JSON の場合に ValueError となるか検証
    manifest_file.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(
        ValueError, match="マニフェストは JSON 辞書である必要があります"
    ):
        pm._load_plugin(manifest_file)

    # [検証目的]: 未対応トランスポートで例外発生するか検証
    # [実施内容]: transport に "unknown" を設定し読み込ませる
    manifest_file.write_text(
        json.dumps(
            {
                "name": "unsupported",
                "version": DEFAULT_TEST_VERSION,
                "type": DEFAULT_TEST_PLUGIN_TYPE,
                "transport": "unknown",
            }
        ),
        encoding="utf-8",
    )
    pm.scan_plugins()
    assert pm.get_plugin_names() == []
    with pytest.raises(Exception):
        pm._load_plugin(manifest_file)


@pytest.mark.asyncio
async def test_stdio_plugin_success(tmp_path: Path) -> None:
    """Python エコースクリプトを用いた STDIO プラグインのテスト。

    Args:
        tmp_path: Pytest 一時ディレクトリパス。
    """
    # [検証目的]: stdio 通信経由で応答を取得できるか検証
    # [実施内容]: エコースクリプトを作成し execute() で呼び出す
    plugin_dir = tmp_path / "stdio_plugin"
    plugin_dir.mkdir()

    script_path = plugin_dir / "echo.py"
    script_content = (
        "import sys, json\n"
        "line = sys.stdin.readline()\n"
        "req = json.loads(line)\n"
        "sys.stderr.write('Test stderr log\\n')\n"
        "sys.stderr.flush()\n"
        "res = {'status': 'ok', 'echo_action': req['action']}\n"
        "print(json.dumps(res))\n"
        "sys.stdout.flush()\n"
    )
    script_path.write_text(script_content, encoding="utf-8")

    manifest = {
        "name": "stdio_test",
        "version": DEFAULT_TEST_VERSION,
        "type": DEFAULT_TEST_PLUGIN_TYPE,
        "transport": TRANSPORT_STDIO,
        "command": [sys.executable, str(script_path)],
        "timeout_seconds": DEFAULT_TEST_TIMEOUT,
    }
    (plugin_dir / DEFAULT_MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    pm = PluginManager(tmp_path)
    pm.scan_plugins()
    assert pm.get_plugin_names() == ["stdio_test"]

    res = await pm.execute("stdio_test", "ping", {"foo": "bar"})
    assert res == {"status": "ok", "echo_action": "ping"}

    await pm.close()


@pytest.mark.asyncio
async def test_stdio_plugin_invalid_json_response(tmp_path: Path) -> None:
    """STDIO プラグインが非 JSON 文字列を返した場合のテストです。"""
    # [検証目的]: 非 JSON 出力がエラーへ変換されるか検証
    # [実施内容]: 非 JSON 文字列を出力するスクリプトで検証する
    plugin_dir = tmp_path / "bad_output_plugin"
    plugin_dir.mkdir()

    script_path = plugin_dir / "bad.py"
    script_path.write_text("print('not json')\n", encoding="utf-8")

    manifest = {
        "name": "bad_output",
        "version": DEFAULT_TEST_VERSION,
        "type": DEFAULT_TEST_PLUGIN_TYPE,
        "transport": TRANSPORT_STDIO,
        "command": [sys.executable, str(script_path)],
    }
    (plugin_dir / DEFAULT_MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    pm = PluginManager(tmp_path)
    pm.scan_plugins()
    res = await pm.execute("bad_output", "test")
    assert res["status"] == "error"

    await pm.close()


@pytest.mark.asyncio
async def test_stdio_plugin_non_dict_json_response(tmp_path: Path) -> None:
    """STDIO プラグインが辞書型以外の JSON を返した場合のテスト。"""
    # [検証目的]: JSON がリスト構造の場合にエラーとなるか検証
    # [実施内容]: リスト型 JSON を出力するスクリプトで検証する
    plugin_dir = tmp_path / "list_json_plugin"
    plugin_dir.mkdir()

    script_path = plugin_dir / "list_json.py"
    script_path.write_text("print('[1, 2, 3]')\n", encoding="utf-8")

    manifest = {
        "name": "list_json",
        "version": DEFAULT_TEST_VERSION,
        "type": DEFAULT_TEST_PLUGIN_TYPE,
        "transport": TRANSPORT_STDIO,
        "command": [sys.executable, str(script_path)],
    }
    (plugin_dir / DEFAULT_MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    pm = PluginManager(tmp_path)
    pm.scan_plugins()
    res = await pm.execute("list_json", "test")
    assert res["status"] == "error"

    await pm.close()


@pytest.mark.asyncio
async def test_stdio_plugin_unexpected_stdout_close(tmp_path: Path) -> None:
    """STDIO プラグインが予期せず stdout をクローズしたかのテスト。"""
    # [検証目的]: 応答前終了時にエラー検知されるか検証
    # [実施内容]: 即座に終了するスクリプトを実行し検証する
    plugin_dir = tmp_path / "close_plugin"
    plugin_dir.mkdir()

    script_path = plugin_dir / "close.py"
    script_path.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    manifest = {
        "name": "close_test",
        "version": DEFAULT_TEST_VERSION,
        "type": DEFAULT_TEST_PLUGIN_TYPE,
        "transport": TRANSPORT_STDIO,
        "command": [sys.executable, str(script_path)],
    }
    (plugin_dir / DEFAULT_MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    pm = PluginManager(tmp_path)
    pm.scan_plugins()
    res = await pm.execute("close_test", "test")
    assert res["status"] == "error"

    await pm.close()


@pytest.mark.asyncio
async def test_stdio_plugin_process_kill_on_terminate_timeout(
    mocker: MockerFixture,
) -> None:
    """Terminate タイムアウト時に kill が呼ばれるかのテスト。"""
    # [検証目的]: タイムアウト時に kill() が呼ばれるか検証
    # [実施内容]: wait() で TimeoutError を発生させ検証
    manifest = PluginManifest(
        name="stub",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_STDIO,
        command=["echo", "hi"],
    )
    transport = StdioTransport(manifest)
    mock_process = mocker.MagicMock()
    mock_process.wait = mocker.AsyncMock(side_effect=asyncio.TimeoutError())
    type(mock_process).returncode = mocker.PropertyMock(return_value=None)

    transport._process = mock_process

    await transport.close()
    mock_process.kill.assert_called_once()
    assert transport._process is None


@pytest.mark.asyncio
async def test_stdio_plugin_process_kill_not_called_if_returncode_set(
    mocker: MockerFixture,
) -> None:
    """Terminate 後に returncode 設定済みの場合 kill が呼ばれないテスト。"""
    # [検証目的]: プロセス自律停止時に kill() がスキップされるか検証
    # [実施内容]: returncode が設定されたモックで検証する
    manifest = PluginManifest(
        name="stub",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_STDIO,
        command=["echo", "hi"],
    )
    transport = StdioTransport(manifest)
    mock_process = mocker.MagicMock()
    mock_process.wait = mocker.AsyncMock(side_effect=asyncio.TimeoutError())
    type(mock_process).returncode = mocker.PropertyMock(side_effect=[None, 0])

    transport._process = mock_process

    await transport.close()
    mock_process.kill.assert_not_called()
    assert transport._process is None


@pytest.mark.asyncio
async def test_stdio_plugin_process_lookup_error(mocker: MockerFixture) -> None:
    """ProcessLookupError 時の close ハンドリングのテストです。"""
    # [検証目的]: ProcessLookupError 発生時のハンドリング検証
    # [実施内容]: ProcessLookupError を設定し close() を呼ぶ
    manifest = PluginManifest(
        name="stub",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_STDIO,
        command=["echo", "hi"],
    )
    transport = StdioTransport(manifest)
    mock_process = mocker.MagicMock()
    mock_process.returncode = None
    mock_process.terminate.side_effect = ProcessLookupError()
    transport._process = mock_process

    await transport.close()
    assert transport._process is None


@pytest.mark.asyncio
async def test_stdio_plugin_timeout_and_errors(tmp_path: Path) -> None:
    """STDIO トランスポートのタイムアウトおよびエラー処理のテスト。

    Args:
        tmp_path: Pytest 一時ディレクトリパス。
    """
    # [検証目的 1]: コマンド空で ValueError が送出されるか検証
    manifest = PluginManifest(
        name="timeout_plugin",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_STDIO,
        command=[],
    )
    transport = StdioTransport(manifest)
    msg = PluginMessage(request_id="1", action="test")

    with pytest.raises(
        ValueError, match="マニフェストのコマンドリストが空です"
    ):
        await transport.send_and_receive(msg, DEFAULT_TEST_TIMEOUT)

    # [検証目的 2]: 無応答で TimeoutError になるか検証
    plugin_dir = tmp_path / "hang_plugin"
    plugin_dir.mkdir()
    script_path = plugin_dir / "hang.py"
    script_path.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")

    manifest_hang = PluginManifest(
        name="hang",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_STDIO,
        command=[sys.executable, str(script_path)],
    )
    hang_transport = StdioTransport(manifest_hang)
    with pytest.raises(TimeoutError):
        await hang_transport.send_and_receive(msg, SHORT_TEST_TIMEOUT)

    await hang_transport.close()


@pytest.mark.asyncio
async def test_http_plugin_execution(mocker: MockerFixture) -> None:
    """HTTP プラグイン実行およびエラー処理のテストです。

    Args:
        mocker: Pytest-mocker フィクスチャインスタンス。
    """
    # [検証目的]: HTTP POST 経由で正常応答を取得できるか検証
    # [実施内容]: post() をモックし 200 OK で応答させて検証
    manifest = PluginManifest(
        name="http_test",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_HTTP,
        url="http://localhost:8000/api",
    )
    transport = HttpTransport(manifest)
    msg = PluginMessage(
        request_id="req-123", action="greet", data={"name": "Alice"}
    )

    mock_post = mocker.patch("httpx.AsyncClient.post")
    request = httpx.Request("POST", "http://localhost:8000/api")
    mock_post.return_value = Response(
        200, json={"status": "success", "reply": "Hello Alice"}, request=request
    )

    res = await transport.send_and_receive(msg, DEFAULT_TEST_TIMEOUT)
    assert res == {"status": "success", "reply": "Hello Alice"}

    await transport.close()


@pytest.mark.asyncio
async def test_http_plugin_non_dict_response(mocker: MockerFixture) -> None:
    """HTTP プラグインがリスト型 JSON を返した場合のテスト。"""
    # [検証目的]: レスポンスが非辞書型の場合にエラーになるか検証
    # [実施内容]: リスト型 JSON を返すモックで検証
    manifest = PluginManifest(
        name="http_list",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_HTTP,
        url="http://localhost:8000/api",
    )
    transport = HttpTransport(manifest)
    msg = PluginMessage(request_id="req-123", action="greet")

    mock_post = mocker.patch("httpx.AsyncClient.post")
    request = httpx.Request("POST", "http://localhost:8000/api")
    mock_post.return_value = Response(
        200, json=[1, 2, 3], request=request
    )

    with pytest.raises(ValueError, match="JSON 辞書である必要があります"):
        await transport.send_and_receive(msg, DEFAULT_TEST_TIMEOUT)

    await transport.close()


@pytest.mark.asyncio
async def test_http_plugin_timeout(mocker: MockerFixture) -> None:
    """HTTP プラグインのタイムアウト処理のテストです。"""
    # [検証目的]: タイムアウト時に TimeoutError となるか検証
    # [実施内容]: post() で TimeoutException を発生させて検証
    manifest = PluginManifest(
        name="http_timeout",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_HTTP,
        url="http://localhost:8000/api",
    )
    transport = HttpTransport(manifest)
    msg = PluginMessage(request_id="req-123", action="greet")

    mocker.patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.TimeoutException("Timeout"),
    )

    with pytest.raises(TimeoutError, match="タイムアウトしました"):
        await transport.send_and_receive(msg, DEFAULT_TEST_TIMEOUT)

    await transport.close()


@pytest.mark.asyncio
async def test_http_plugin_errors(mocker: MockerFixture) -> None:
    """HTTP トランスポートのエラー処理のテストです。

    Args:
        mocker: Pytest-mocker フィクスチャインスタンス。
    """
    # [検証目的 1]: URL 未設定で ValueError となるか検証
    manifest_no_url = PluginManifest(
        name="no_url",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_HTTP,
        url=None,
    )
    transport_no_url = HttpTransport(manifest_no_url)
    msg = PluginMessage(request_id="1", action="test")

    with pytest.raises(ValueError, match="URL が未設定です"):
        await transport_no_url.send_and_receive(msg, DEFAULT_TEST_TIMEOUT)

    # [検証目的 2]: リクエスト失敗時に RuntimeError になるか検証
    manifest = PluginManifest(
        name="http_err",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_HTTP,
        url="http://localhost:8000/fail",
    )
    transport = HttpTransport(manifest)

    mocker.patch(
        "httpx.AsyncClient.post",
        side_effect=RuntimeError("Connection refused"),
    )
    with pytest.raises(RuntimeError):
        await transport.send_and_receive(msg, DEFAULT_TEST_TIMEOUT)

    await transport.close()


@pytest.mark.asyncio
async def test_execute_unregistered_plugin(tmp_path: Path) -> None:
    """未登録プラグインの実行を試みた場合のテストです。

    Args:
        tmp_path: Pytest 一時ディレクトリパス。
    """
    # [検証目的]: 未登録名指定で KeyError となるか検証
    # [実施内容]: 空の PluginManager に execute() を呼ぶ
    pm = PluginManager(tmp_path)
    with pytest.raises(KeyError, match="は登録されていません"):
        await pm.execute("unknown", "action")


@pytest.mark.asyncio
async def test_plugin_manager_close_exception(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """トランスポート終了時の例外ハンドリングのテストです。"""
    # [検証目的]: close() 例外時も全体処理が継続されるか検証
    # [実施内容]: close() で例外を出すモックで pm.close() を呼ぶ
    plugin_dir = tmp_path / "mock_plugin"
    plugin_dir.mkdir()
    manifest = {
        "name": "mock_err",
        "version": DEFAULT_TEST_VERSION,
        "type": DEFAULT_TEST_PLUGIN_TYPE,
        "transport": TRANSPORT_HTTP,
        "url": "http://localhost",
    }
    (plugin_dir / DEFAULT_MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    pm = PluginManager(tmp_path)
    pm.scan_plugins()

    mocker.patch.object(
        pm._plugins["mock_err"][1],
        "close",
        side_effect=Exception("Close error"),
    )
    await pm.close()
    assert pm.get_plugin_names() == []


@pytest.mark.asyncio
async def test_stdio_plugin_reuse_process_and_no_pipes(
    mocker: MockerFixture,
) -> None:
    """プロセス再利用やパイプ未設定等のテストです。"""
    # [検証目的 1]: _process が None 時の早期リターン検証
    manifest = PluginManifest(
        name="stub",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_STDIO,
        command=["echo", "hi"],
    )
    transport = StdioTransport(manifest)
    transport._process = None
    await transport._read_stderr()

    # [検証目的 2]: パイプ未設定 (None) で RuntimeError となるか検証
    mock_process = mocker.MagicMock()
    mock_process.returncode = None
    mock_process.stdin = None
    mock_process.stdout = None
    transport._process = mock_process

    msg = PluginMessage(request_id="1", action="test")
    with pytest.raises(
        RuntimeError, match="サブプロセスのパイプが利用できません"
    ):
        await transport.send_and_receive(msg, DEFAULT_TEST_TIMEOUT)


@pytest.mark.asyncio
async def test_plugin_manager_unsupported_transport_branch(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """PluginManager における未知のトランスポート分岐のテストです。"""
    # [検証目的]: 未対応 transport 値で ValueError となるか検証
    # [実施内容]: モックの transport を変更して読み込ませる
    plugin_dir = tmp_path / "custom_plugin"
    plugin_dir.mkdir()
    manifest_path = plugin_dir / DEFAULT_MANIFEST_FILENAME
    manifest_path.write_text(
        '{"name": "a", "version": "1", "type": "t", "transport": "stdio"}',
        encoding="utf-8",
    )

    pm = PluginManager(tmp_path)
    mock_manifest = PluginManifest(
        name="stub",
        version=DEFAULT_TEST_VERSION,
        type=DEFAULT_TEST_PLUGIN_TYPE,
        transport=TRANSPORT_STDIO,
    )
    mock_manifest.transport = "invalid_transport"  # type: ignore[assignment]
    mocker.patch(
        "youtube_tts.plugins.manager.PluginManifest",
        return_value=mock_manifest,
    )

    with pytest.raises(ValueError, match="未対応トランスポート種別"):
        pm._load_plugin(manifest_path)
