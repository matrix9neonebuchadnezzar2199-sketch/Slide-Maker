"""llama-server 子プロセスバックエンド（Glaux process.rs + extractor.rs 準拠）."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import schema

logger = logging.getLogger(__name__)

_CREATE_NO_WINDOW = 0x08000000
_HEALTH_TIMEOUT_SEC = 2
_STARTUP_TIMEOUT_SEC = 600
_HEALTH_POLL_SEC = 0.5
_BUNDLE_ZIP_NAME = "runtime-bundle.zip"
_BUNDLE_SHA_NAME = "runtime-bundle.sha256"
_RUNTIME_MARKER = ".pdf2pptx_runtime_ok"
_THINK_BLOCK_RE = re.compile(r"<\|think\|>.*?<\|/think\|>", re.DOTALL)




def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _data_dir() -> Path:
    """Glaux data_dir 相当 — 展開先ルート。"""
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "PDF2PPTX" / "data"
    return Path.home() / ".pdf2pptx" / "data"


def _dev_runtime_dir() -> Path:
    return _app_base_dir() / "runtime"


def _bundled_asset_path(name: str) -> Path | None:
    """PyInstaller 同梱 or 開発時 assets/ のファイルを返す。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidate = Path(meipass) / name
            if candidate.is_file():
                return candidate
    candidate = _app_base_dir() / "assets" / name
    if candidate.is_file():
        return candidate
    return None


def _read_bundle_sha256() -> str | None:
    sha_path = _bundled_asset_path(_BUNDLE_SHA_NAME)
    if sha_path is None:
        return None
    try:
        return sha_path.read_text(encoding="ascii").strip().lower()
    except OSError:
        return None


def _embedded_runtime_dir(bundle_sha: str) -> Path:
    return _data_dir() / "runtime" / bundle_sha


def _extract_runtime_bundle(zip_path: Path, dest: Path, bundle_sha: str) -> Path:
    """内蔵 ZIP を LOCALAPPDATA に展開する（Glaux ensure_embedded_runtime 相当）。"""
    marker = dest / _RUNTIME_MARKER
    server = dest / "llama-server.exe"

    if (
        server.is_file()
        and marker.is_file()
        and marker.read_text(encoding="ascii").strip().lower() == bundle_sha
    ):
        
        return dest

    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    

    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(dest)

    if not server.is_file():
        raise FileNotFoundError(f"llama-server.exe missing after extract: {dest}")

    marker.write_text(bundle_sha, encoding="ascii")
    logger.info("Embedded runtime extracted to %s", dest)
    return dest


def ensure_runtime_dir() -> Path | None:
    """llama-server 実行に必要なランタイムディレクトリを返す。"""
    # 開発時のみリポジトリ直下 runtime/ を使う（配布 EXE は内蔵 ZIP 展開）
    if not getattr(sys, "frozen", False):
        dev_dir = _dev_runtime_dir()
        if dev_dir.joinpath("llama-server.exe").is_file():
            return dev_dir

    bundle_sha = _read_bundle_sha256()
    zip_path = _bundled_asset_path(_BUNDLE_ZIP_NAME)
    if bundle_sha is None or zip_path is None:
        return None

    dest = _embedded_runtime_dir(bundle_sha)
    return _extract_runtime_bundle(zip_path, dest, bundle_sha)


def resolve_server_exe() -> Path | None:
    """llama-server.exe を解決する（開発 runtime / EXE 内蔵展開）。"""
    runtime_dir = ensure_runtime_dir()
    candidate = runtime_dir / "llama-server.exe" if runtime_dir else None
    exists = candidate is not None and candidate.is_file()
    
    if exists and candidate is not None:
        return candidate
    return None


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _probe_server(server_exe: Path) -> tuple[int, str]:
    """llama-server --version で MSVC 欠落等を事前検出する。"""
    runtime_dir = server_exe.parent
    result = subprocess.run(
        [str(server_exe), "--version"],
        cwd=str(runtime_dir),
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW,
        check=False,
    )
    text = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()
    return result.returncode, text


def _format_windows_exit(code: int) -> str:
    if code == -1073741819:
        return "0xc0000005 (ACCESS_VIOLATION)"
    if code == -1073741515:
        return "0xc0000135 (DLL_NOT_FOUND)"
    return str(code)


def _runtime_preflight(server_exe: Path) -> None:
    code, output = _probe_server(server_exe)
    inventory = sorted(p.name for p in server_exe.parent.iterdir() if p.is_file())
    has_vc = any(name.lower() == "vcruntime140.dll" for name in inventory)
    
    if code == 0:
        return
    raise RuntimeError(
        f"llama-server preflight failed ({_format_windows_exit(code)}): "
        f"{output or 'no output — likely missing MSVC runtime'}"
    )


def _read_stderr_tail(path: Path, max_bytes: int = 16384) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) <= max_bytes:
        return data.decode("utf-8", errors="replace")
    return data[-max_bytes:].decode("utf-8", errors="replace")


def _http_get(url: str, timeout: int) -> int:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status)


def _wait_until_healthy(base_url: str, process: subprocess.Popen[Any], stderr_log: Path) -> None:
    health_urls = [f"{base_url}/health", f"{base_url}/v1/models"]
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = _read_stderr_tail(stderr_log)
            
            raise RuntimeError(
                f"llama-server exited early (code={process.returncode})\n{tail}"
            )
        for url in health_urls:
            try:
                status = _http_get(url, _HEALTH_TIMEOUT_SEC)
                if 200 <= status < 300:
                    return
            except (urllib.error.URLError, TimeoutError):
                continue
        time.sleep(_HEALTH_POLL_SEC)
    raise TimeoutError(f"llama-server health timeout ({_STARTUP_TIMEOUT_SEC}s)")


def _gemma_prompt(messages: list[dict[str, str]]) -> str:
    """Glaux api/chat.rs と同じ Gemma 4 プロンプト形式。"""
    prompt = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        if role == "assistant":
            turn_role = "model"
        elif role == "system":
            turn_role = "system"
        else:
            turn_role = "user"
        prompt += f"<|turn>{turn_role}\n{content}<turn|>\n"
    prompt += "<|turn>model\n"
    return prompt


def _strip_gemma_thinking(text: str) -> str:
    """Gemma 4 の thinking ブロックを除去する。"""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    if "<|think|>" in cleaned:
        cleaned = cleaned.split("<|think|>", 1)[0]
    return cleaned.strip()


class LlamaServerClient:
    """llama-server HTTP クライアント（create_chat_completion 互換）。"""

    def __init__(
        self,
        *,
        base_url: str,
        process: subprocess.Popen[Any],
        stderr_log: Path,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._process = process
        self._stderr_log = stderr_log
        parsed = urlparse(self._base_url)
        self._http_host = parsed.hostname or "127.0.0.1"
        self._http_port = parsed.port or 80
        self._http: HTTPConnection | None = None

    def _get_http(self) -> HTTPConnection:
        if self._http is None:
            self._http = HTTPConnection(
                self._http_host,
                self._http_port,
                timeout=schema.LLM_TIMEOUT_SEC + 30,
            )
        return self._http

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        conn = self._get_http()
        conn.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"HTTP {response.status}: {raw[:500]}")
        return json.loads(raw)

    def create_chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = schema.LLM_MAX_TOKENS,
        temperature: float = schema.LLM_TEMPERATURE,
        top_p: float = 0.9,
        stop: list[str] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Glaux 同等の /completion API（Gemma テンプレート）で推論する。"""
        stop_tokens = ["<turn|>"]
        if stop:
            stop_tokens.extend(stop)
        payload: dict[str, Any] = {
            "prompt": _gemma_prompt(messages),
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
            "n_predict": max_tokens,
            "stop": stop_tokens,
        }
        t0 = time.perf_counter()
        data = self._post_json("/completion", payload)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        content = _strip_gemma_thinking(str(data.get("content", "")))
        timings = data.get("timings") if isinstance(data.get("timings"), dict) else {}
        
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ]
        }

    def close(self) -> None:
        """子プロセスを停止する。"""
        if self._http is not None:
            try:
                self._http.close()
            except OSError:
                pass
            self._http = None
        if self._process.poll() is None:
            self._process.kill()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def start_server(model_path: Path) -> LlamaServerClient:
    """Glaux 同等フラグで llama-server を起動する。"""
    server_exe = resolve_server_exe()
    if server_exe is None:
        raise FileNotFoundError(
            "llama-server runtime not available (embedded bundle missing or extract failed)"
        )

    _runtime_preflight(server_exe)
    runtime_dir = server_exe.parent
    port = _pick_free_port()
    host = f"127.0.0.1:{port}"
    base_url = f"http://{host}"
    stderr_log = _data_dir() / "llama-server-last.stderr.log"
    stderr_log.parent.mkdir(parents=True, exist_ok=True)

    args = [
        str(server_exe),
        "-m",
        str(model_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "-c",
        str(schema.LLM_N_CTX),
        "-np",
        "1",
        "-t",
        str(schema.LLM_N_THREADS),
        "-b",
        str(schema.LLM_N_BATCH),
        "-ub",
        str(schema.LLM_N_UBATCH),
        "-ctk",
        schema.LLM_KV_CACHE_TYPE,
        "-ctv",
        schema.LLM_KV_CACHE_TYPE,
        "-ngl",
        "0",
        "--no-op-offload",
        "--device",
        "none",
        "--cache-ram",
        "0",
    ]

    stderr_handle = stderr_log.open("w", encoding="utf-8")
    process = subprocess.Popen(
        args,
        cwd=str(runtime_dir),
        stdout=subprocess.DEVNULL,
        stderr=stderr_handle,
        creationflags=_CREATE_NO_WINDOW,
    )
    stderr_handle.close()

    

    try:
        _wait_until_healthy(base_url, process, stderr_log)
    except Exception:
        if process.poll() is None:
            process.kill()
        raise

    
    logger.info("llama-server ready at %s", base_url)
    return LlamaServerClient(base_url=base_url, process=process, stderr_log=stderr_log)
