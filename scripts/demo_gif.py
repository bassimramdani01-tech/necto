#!/usr/bin/env python3
"""Render a demo GIF of necto — no Playwright, no ffmpeg.

How it works:
  1. starts the demo pipeline as a child process (scripts/demo.py --delay ...) so events
     stream into a fresh run,
  2. drives the installed Microsoft Edge over the DevTools Protocol (a tiny stdlib
     WebSocket client, because headless Edge already works here),
  3. captures PNG frames while the run graph builds live, then re-captures the
     inspector view,
  4. assembles the frames into an animated GIF with Pillow.

Requirements: Microsoft Edge, Python 3.10+ with Pillow installed.
    pip install pillow
    python scripts/demo_gif.py                 # -> docs/assets/demo.gif
    python scripts/demo_gif.py --width 720 --fps 8 --out demo.gif

The server (uvicorn) and the web dev server (pnpm dev) must already be running.
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEFAULT_ENDPOINT = "http://127.0.0.1:8000"
DEFAULT_WEB = "http://localhost:5173"


# --------------------------------------------------------------------------- CDP
class WebSocket:
    """Just enough WebSocket to talk to the Chrome DevTools Protocol."""

    def __init__(self, url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        self.sock = socket.create_connection((host, port), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake.encode())
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("websocket handshake failed")
            buffer += chunk
        head, _, self._buffer = buffer.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError(f"websocket handshake rejected: {head[:120]!r}")

    def _read(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("websocket closed")
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data

    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])
        length = len(payload)
        mask = os.urandom(4)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        header += mask
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def receive(self) -> str:
        while True:
            first, second = self._read(2)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read(8))[0]
            data = self._read(length)
            if opcode == 0x8:
                raise ConnectionError("websocket closed by peer")
            if opcode in (0x9, 0xA):
                continue
            return data.decode()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class CDP:
    def __init__(self, ws_url: str) -> None:
        self.ws = WebSocket(ws_url)
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.receive())
            if message.get("id") == self._id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})

    def evaluate(self, expression: str):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return result.get("result", {}).get("value")

    def close(self) -> None:
        self.ws.close()


# ------------------------------------------------------------------ environment
def get_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def wait_for_target(port: int, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            targets = get_json(f"http://127.0.0.1:{port}/json/list")
            page = next((item for item in targets if item.get("type") == "page"), None)
            if page:
                return page["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("Edge never exposed a page target")


def wait_for_api(endpoint: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if get_json(f"{endpoint}/healthz").get("database") == "up":
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("necto API is not reachable")


def run_ids(endpoint: str) -> set[str]:
    return {run["id"] for run in get_json(f"{endpoint}/v1/runs?limit=50")}


# ------------------------------------------------------------------- GIF making
def assemble(frames: list[Path], out_path: Path, width: int, fps: int) -> int:
    from PIL import Image

    first = Image.open(frames[0]).convert("RGB")
    height = int(first.height * (width / first.width))
    images = [Image.open(frame).convert("RGB").resize((width, height)) for frame in frames]
    palette = [image.quantize(colors=128, method=Image.MEDIANCUT) for image in images]
    palette[0].save(
        out_path,
        save_all=True,
        append_images=palette[1:],
        duration=int(1000 / fps),
        loop=0,
        optimize=True,
        disposal=2,
    )
    return out_path.stat().st_size


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a necto demo GIF with Edge + Pillow.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--web", default=DEFAULT_WEB)
    parser.add_argument("--out", default=str(ROOT / "docs" / "assets" / "demo.gif"))
    parser.add_argument("--edge", default=DEFAULT_EDGE)
    parser.add_argument("--port", type=int, default=9333)
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument("--live-seconds", type=float, default=12.0)
    parser.add_argument("--event-delay", type=float, default=0.6)
    parser.add_argument("--inspector-seconds", type=float, default=1.6)
    parser.add_argument("--keep-frames", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wait_for_api(args.endpoint)

    frames_dir = Path(tempfile.mkdtemp(prefix="necto-gif-"))
    profile = Path(tempfile.mkdtemp(prefix="necto-edge-"))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Warm the dev server so the first real navigation is fast.
    warm = urllib.request.urlopen(f"{args.web}/", timeout=20)
    warm.read()

    browser = subprocess.Popen(
        [
            args.edge,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--disable-extensions",
            f"--remote-debugging-port={args.port}",
            f"--user-data-dir={profile}",
            "--window-size=1280,1150",
            "about:blank",
        ]
    )

    frame_paths: list[Path] = []
    try:
        cdp = CDP(wait_for_target(args.port))
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")

        # Navigate to the app first, so the page bundle is warm before the run appears.
        cdp.call("Page.navigate", {"url": f"{args.web}/"})
        time.sleep(2.0)

        # Warm the run-detail chunk too (Vite compiles routes on first use; otherwise the
        # first seconds of the live graph are lost to compilation).
        previous = get_json(f"{args.endpoint}/v1/runs?limit=1")
        if previous:
            cdp.call("Page.navigate", {"url": f"{args.web}/?run={previous[0]['id']}"})
            time.sleep(2.5)
            cdp.call("Page.navigate", {"url": f"{args.web}/"})
            time.sleep(0.5)

        before = run_ids(args.endpoint)
        child = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts" / "demo.py"),
                "--runs",
                "1",
                "--delay",
                str(args.event_delay),
                "--endpoint",
                args.endpoint,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for the new run, then open it.
        new_run: str | None = None
        deadline = time.time() + 30
        while time.time() < deadline and new_run is None:
            fresh = run_ids(args.endpoint) - before
            if fresh:
                new_run = fresh.pop()
            time.sleep(0.15)
        if new_run is None:
            raise RuntimeError("demo run never appeared")
        print(f"run: {new_run}")

        cdp.call("Page.navigate", {"url": f"{args.web}/?run={new_run}"})

        # Wait until the run view has actually rendered (the architecture panel).
        deadline = time.time() + 15
        while time.time() < deadline:
            if "Architecture" in (cdp.evaluate("document.body.innerText") or ""):
                break
            time.sleep(0.2)

        interval = 1.0 / args.fps
        total = int(args.live_seconds * args.fps)
        for index in range(total):
            result = cdp.call("Page.captureScreenshot", {"format": "png"})
            path = frames_dir / f"frame-{index:04d}.png"
            path.write_bytes(base64.b64decode(result["data"]))
            frame_paths.append(path)
            time.sleep(interval)
            if child.poll() is not None and index > args.fps * 2:
                break
        print(f"live frames: {len(frame_paths)}")

        child.wait(timeout=90)

        # Then the inspector: give it a moment to load and capture a short hold.
        cdp.call(
            "Page.navigate",
            {"url": f"{args.web}/?run={new_run}&at=18&node=agent%3Acritic"},
        )
        time.sleep(2.2)
        # The inspector panel sits below the graph; scroll it into frame for the hold.
        cdp.evaluate(
            "(document.querySelector('main') || document.documentElement).scrollTo(0, 340)"
        )
        time.sleep(0.4)
        for index in range(int(args.inspector_seconds * args.fps)):
            result = cdp.call("Page.captureScreenshot", {"format": "png"})
            path = frames_dir / f"frame-inspector-{index:04d}.png"
            path.write_bytes(base64.b64decode(result["data"]))
            frame_paths.append(path)
            time.sleep(interval)
        print(f"total frames: {len(frame_paths)}")

        cdp.close()
    finally:
        browser.terminate()
        try:
            browser.wait(timeout=10)
        except subprocess.TimeoutExpired:
            browser.kill()

    size = assemble(frame_paths, out_path, args.width, args.fps)
    print(f"gif: {out_path} ({size / 1024 / 1024:.2f} MB, {len(frame_paths)} frames)")
    if not args.keep_frames:
        for path in frame_paths:
            path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
