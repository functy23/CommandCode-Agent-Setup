#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CommandCode 凭证：网页登录（Studio CLI 回调）、本机 auth.json 读取。

网页登录协议对齐 Command Code Studio 的 CLI-compatible callback
（opencode-commandcode / 旧版 dsh-commandcode-provider 同源）：

  1. 本机 127.0.0.1:5959+ 起临时 HTTP 服务
  2. 打开 https://commandcode.ai/studio/auth/cli?callback=…&state=…
  3. Studio 登录后 POST {apiKey, userId, userName, keyName, state} 到 /callback
  4. CORS + Access-Control-Allow-Private-Network（Chrome PNA）

仅标准库：http.server / webbrowser / secrets。
"""

import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode

from . import common as C

STUDIO_BASE = "https://commandcode.ai"
AUTH_START_PORT = 5959
AUTH_MAX_PORT_ATTEMPTS = 10
AUTH_TIMEOUT_S = 12 * 60
ALLOWED_CORS = (
    "http://localhost:3000",
    "https://staging.commandcode.ai",
    "https://commandcode.ai",
    "https://www.commandcode.ai",
)
AUTH_FILE = os.path.expanduser("~/.commandcode/auth.json")
AUTH_CANDIDATES = (
    AUTH_FILE,
    os.path.expanduser("~/.pi/agent/auth.json"),
    os.path.expanduser("~/.omp/agent/auth.json"),
)


def _key_from_record(value):
    if not isinstance(value, dict):
        return None
    t = value.get("type")
    if t == "api" and isinstance(value.get("key"), str):
        return value["key"]
    if t == "oauth" and isinstance(value.get("access"), str):
        return value["access"]
    for field in ("key", "access"):
        if isinstance(value.get(field), str) and value[field]:
            return value[field]
    return None


def read_existing_key():
    """从本机已有 CommandCode 凭证文件解析 Key。返回 (key, path) 或 (None, None)。"""
    for path in AUTH_CANDIDATES:
        try:
            with open(path, encoding="utf-8") as f:
                parsed = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        if isinstance(parsed.get("apiKey"), str) and parsed["apiKey"]:
            return parsed["apiKey"], path
        if isinstance(parsed.get("commandcode"), str) and parsed["commandcode"]:
            return parsed["commandcode"], path
        for field in ("commandcode", "command-code"):
            key = _key_from_record(parsed.get(field))
            if key:
                return key, path
    return None, None


def save_auth(key, user_id=None, user_name=None, key_name=None):
    """把网页登录拿到的 Key 写入 ~/.commandcode/auth.json（官方 CLI 形状），下次可走本机凭证。"""
    data = {}
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}
    rec = {"type": "api", "key": key}
    if user_id:
        rec["userId"] = user_id
    if user_name:
        rec["userName"] = user_name
    if key_name:
        rec["keyName"] = key_name
    data["command-code"] = rec
    os.makedirs(os.path.dirname(AUTH_FILE), mode=0o700, exist_ok=True)
    tmp = AUTH_FILE + f".{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, AUTH_FILE)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return AUTH_FILE


def _cors_origin(origin):
    if isinstance(origin, str) and origin in ALLOWED_CORS:
        return origin
    if isinstance(origin, str) and origin.endswith("commandcode.ai"):
        return origin
    return "https://commandcode.ai"


class _LoginServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _make_handler(state, box):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _set_cors(self):
            origin = _cors_origin(self.headers.get("Origin"))
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")

        def _json(self, code, obj):
            raw = json.dumps(obj).encode()
            self.send_response(code)
            self._set_cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self):
            self.send_response(204)
            self._set_cors()
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path != "/callback":
                self._json(404, {"success": False, "error": "Not found"})
                return
            body = ("<!doctype html><meta charset=utf-8><title>CommandCode</title>"
                    "<p>登录回调已就绪。请回到终端；本页可关闭。</p>").encode("utf-8")
            self.send_response(200)
            self._set_cors()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path != "/callback":
                self._json(404, {"success": False, "error": "Not found"})
                return
            try:
                n = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                n = 0
            if n < 0 or n > 10_000:
                self._json(400, {"success": False, "error": "Invalid body"})
                return
            raw = self.rfile.read(n) if n else b"{}"
            try:
                parsed = json.loads(raw.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                self._json(400, {"success": False, "error": "Invalid JSON"})
                return
            if not isinstance(parsed, dict):
                self._json(400, {"success": False, "error": "Invalid JSON"})
                return
            if "error" in parsed:
                self._json(200, {"success": True})
                msg = parsed.get("error_description") or parsed.get("error") or "Authorization denied"
                box["error"] = str(msg)
                box["event"].set()
                return
            for field in ("apiKey", "state", "userId", "userName", "keyName"):
                if not isinstance(parsed.get(field), str) or not parsed[field]:
                    self._json(400, {"success": False, "error": "Missing required fields"})
                    return
            if parsed["state"] != state:
                self._json(403, {"success": False, "error": "Invalid state token"})
                return
            self._json(200, {"success": True})
            box["payload"] = parsed
            box["event"].set()

    return Handler


def browser_login(timeout=AUTH_TIMEOUT_S):
    """打开浏览器完成 CommandCode Studio 登录，返回 apiKey。失败抛 SystemExit。"""
    state = secrets.token_urlsafe(32)
    box = {"event": threading.Event(), "payload": None, "error": None}
    httpd = None
    port = None
    last_err = None
    for i in range(AUTH_MAX_PORT_ATTEMPTS):
        candidate = AUTH_START_PORT + i
        try:
            httpd = _LoginServer(("127.0.0.1", candidate), _make_handler(state, box))
            port = candidate
            break
        except OSError as e:
            last_err = e
            httpd = None
    if httpd is None or port is None:
        C.die(f"无法绑定网页登录回调端口（从 {AUTH_START_PORT} 起试了 {AUTH_MAX_PORT_ATTEMPTS} 个）：{last_err}")

    callback = f"http://localhost:{port}/callback"
    url = f"{STUDIO_BASE}/studio/auth/cli?{urlencode({'callback': callback, 'state': state})}"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    C.log("→ 网页登录：已启动本机回调，正在打开 CommandCode Studio …")
    C.log(f"  若浏览器未自动打开，请访问：\n  {url}")
    C.log(f"  登录成功后会自动回到终端（最多等待 {timeout // 60} 分钟，Ctrl-C 取消）")
    try:
        webbrowser.open(url, new=1, autoraise=True)
    except Exception as e:
        C.warn(f"无法自动打开浏览器（{e}），请手动打开上方链接。")
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if box["event"].wait(timeout=1.0):
                break
        else:
            C.die("网页登录超时。可改用手动输入 Key，或重跑后再次选择网页登录。")
        if box["error"]:
            C.die(f"网页登录被拒绝或失败：{box['error']}")
        payload = box["payload"] or {}
        key = payload.get("apiKey") or ""
        if not key:
            C.die("网页登录未返回 API Key。")
        who = payload.get("userName") or payload.get("userId") or ""
        kname = payload.get("keyName") or ""
        extra = "，".join(x for x in (who, kname) if x)
        C.log(f"✓ 网页登录成功" + (f"（{extra}）" if extra else ""))
        try:
            saved = save_auth(key, payload.get("userId"), payload.get("userName"), payload.get("keyName"))
            C.log(f"  已写入 {saved}，下次可直接选「本机已有凭证」。")
        except OSError as e:
            C.warn(f"登录成功但未能写入 {AUTH_FILE}：{e}")
        return key
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass
