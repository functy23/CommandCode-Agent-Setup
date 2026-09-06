#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CC Switch 共享设施：进程控制、数据库写入、双核验。

codex 与 claude_desktop 两个目标模块共用。
"""

import glob
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime

from . import common as C

APP_NAME = "CC Switch"
APP_PATH = "/Applications/CC Switch.app"
PROC_NAME = "cc-switch"
HOME = os.path.expanduser("~")
DB_PATH = os.path.join(HOME, ".cc-switch", "cc-switch.db")
LOG_PATH = os.path.join(HOME, ".cc-switch", "logs", "cc-switch.log")
CODEX_DIR = os.path.join(HOME, ".codex")
CODEX_CONFIG = os.path.join(CODEX_DIR, "config.toml")
CODEX_CATALOG = os.path.join(CODEX_DIR, "cc-switch-model-catalog.json")
PROXY_HOST, PROXY_PORT = "127.0.0.1", 15721

COMPACT = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))

# ---------------- 进程控制 ----------------

def app_running():
    return subprocess.run(["pgrep", "-x", PROC_NAME], capture_output=True).returncode == 0

def quit_app():
    if not app_running():
        return
    C.log("→ 退出 CC Switch …")
    subprocess.run(["osascript", "-e", f'tell application "{APP_NAME}" to quit'], capture_output=True, timeout=10)
    for _ in range(20):
        if not app_running():
            break
        time.sleep(0.5)
    if app_running():
        subprocess.run(["pkill", "-TERM", "-x", PROC_NAME], capture_output=True)
        for _ in range(10):
            if not app_running():
                break
            time.sleep(0.5)
    if app_running():
        C.die("CC Switch 未能退出，为避免数据库写入冲突已中止。请手动退出后重试。", 2)
    C.log("  已退出。")

def launch_app():
    C.log("→ 启动 CC Switch …")
    subprocess.run(["open", "-a", APP_PATH], check=True)
    deadline = time.time() + 40
    while time.time() < deadline:
        try:
            with socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=0.5):
                C.log(f"  代理已监听 {PROXY_HOST}:{PROXY_PORT}")
                return True
        except OSError:
            time.sleep(1)
    C.warn(f"等待 {PROXY_PORT} 端口超时，请手动打开 CC Switch 检查。")
    return False

# ---------------- 备份与写库 ----------------

def backup_files(db, include_codex=True):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backups = []
    if os.path.exists(db):
        b = f"{db}.bak-{ts}"
        src = sqlite3.connect(db)
        dst = sqlite3.connect(b)
        src.backup(dst)
        dst.close(); src.close()
        backups.append(b)
    if include_codex:
        for f in (CODEX_CONFIG, CODEX_DIR + "/auth.json", CODEX_CATALOG):
            if os.path.exists(f):
                b = f + f".bak-{ts}"
                shutil.copy2(f, b)
                backups.append(b)
    return backups

def write_provider(db, app_type, name, sc_json, meta_json, upstream_url, make_current=True):
    """幂等写入：指定 app_type 下同名提供商存在则原地更新，否则新建。返回 (provider_id, action)。"""
    conn = sqlite3.connect(db, timeout=15)
    conn.execute("PRAGMA busy_timeout=10000")
    now_ms = int(time.time() * 1000)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM providers WHERE app_type=? AND name=? ORDER BY created_at LIMIT 1", (app_type, name)
        ).fetchone()
        if row:
            pid = row[0]
            conn.execute("UPDATE providers SET settings_config=?, meta=? WHERE id=? AND app_type=?",
                         (sc_json, meta_json, pid, app_type))
            action = "updated"
        else:
            pid = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO providers
                   (id, app_type, name, settings_config, website_url, category, created_at,
                    icon, icon_color, meta, is_current, in_failover_queue, cost_multiplier)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 0, '1.0')""",
                (pid, app_type, name, sc_json, C.PROVIDER_WEBSITE, C.PROVIDER_CATEGORY, now_ms,
                 C.PROVIDER_ICON_COLOR, meta_json, 0),
            )
            action = "created"
        conn.execute("DELETE FROM provider_endpoints WHERE provider_id=? AND app_type=?", (pid, app_type))
        conn.execute("INSERT INTO provider_endpoints (provider_id, app_type, url, added_at) VALUES (?, ?, ?, ?)",
                     (pid, app_type, upstream_url, now_ms))
        if make_current:
            conn.execute("UPDATE providers SET is_current=0 WHERE app_type=?", (app_type,))
            conn.execute("UPDATE providers SET is_current=1 WHERE id=? AND app_type=?", (pid, app_type))
        if app_type == "codex":
            # codex 需要 proxy_config 开启接管；claude-desktop 是 direct 模式，不走代理
            conn.execute(
                """INSERT INTO proxy_config (app_type, proxy_enabled, enabled) VALUES ('codex', 1, 1)
                   ON CONFLICT(app_type) DO UPDATE SET proxy_enabled=1, enabled=1, updated_at=datetime('now')"""
            )
        conn.commit()
        return pid, action
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def prepare_write(db, live, no_restart, args_yes_label=""):
    """备份 → （退出应用）。返回是否需要手动重启提示。"""
    backups = backup_files(db, include_codex=live)
    if backups:
        C.log("→ 已备份：")
        for b in backups:
            C.log(f"    {b}")
    if live:
        if no_restart:
            if app_running():
                C.warn("CC Switch 正在运行中写库，可能有内存态覆盖风险；建议写完手动重启。")
        else:
            quit_app()
    else:
        if app_running():
            C.warn("演练模式：不触碰正在运行的 CC Switch。")

def finish_write(db, live, no_restart, targets):
    """启动应用 + 按 targets 依次核验。targets: [("codex", entries) / ("claude-desktop", None)]"""
    if not live or no_restart:
        C.log("\n== 完成（未重启 CC Switch）。请手动重启 CC Switch 使配置生效。==")
        return True
    if not launch_app():
        return False
    failed = []
    for kind, payload in targets:
        if kind == "codex":
            if not codex_post_verify(payload):
                failed.append("codex")
        elif kind == "claude-desktop":
            if not claude_desktop_verify():
                failed.append("claude-desktop")
    if failed:
        C.warn("接管核验未通过：" + "、".join(failed) +
               "。请按上方提示操作；配置本身已写入，回滚可用上方 .bak 文件。")
        return False
    return True

# ---------------- codex 核验 ----------------

def codex_post_verify(entries):
    ok = True
    C.log("→ 核验 codex 接管结果 …")
    if os.path.exists(CODEX_CONFIG):
        content = open(CODEX_CONFIG, encoding="utf-8").read()
        if f"{PROXY_HOST}:{PROXY_PORT}" in content:
            C.log(f"  ✓ {CODEX_CONFIG} 已指向本机代理")
        else:
            C.warn(f"{CODEX_CONFIG} 未指向 {PROXY_HOST}:{PROXY_PORT} —— 接管可能未生效，请在 CC Switch 中手动开启 Codex 代理。")
            ok = False
    else:
        C.warn(f"未找到 {CODEX_CONFIG}")
        ok = False
    if os.path.exists(CODEX_CATALOG):
        try:
            cat = json.load(open(CODEX_CATALOG, encoding="utf-8"))
            models = cat.get("models", [])
            empty = [m["slug"] for m in models if not m.get("supported_reasoning_levels")]
            if len(models) == len(entries) and not empty:
                C.log(f"  ✓ 模型目录已生成：{len(models)} 个模型，档位完整")
            else:
                C.warn(f"模型目录异常：{len(models)}/{len(entries)} 个模型" + (f"，空档位：{empty}" if empty else ""))
                ok = False
        except json.JSONDecodeError as e:
            C.warn(f"模型目录 JSON 解析失败：{e}")
            ok = False
    else:
        C.warn(f"未找到 {CODEX_CATALOG}")
        ok = False
    return ok

# ---------------- claude-desktop 核验 ----------------

def claude_desktop_verify(wait_secs=30, expect_mode="proxy"):
    """claude-desktop 核验：CC Switch 仅在 UI 切换提供商时写 3P profile（【实测】无 CLI/deeplink/
    启动自动补跑；官方文案即"重新切换当前供应商可修复"）。脚本写库后 profile 可能仍是旧内容——
    轮询一小段时间，若未生效则给出明确的一次性手动步骤，不判失败。"""
    C.log("→ 核验 Claude Desktop 接管结果 …")
    lib = os.path.join(HOME, "Library", "Application Support", "Claude-3p", "configLibrary")
    meta_p = os.path.join(lib, "_meta.json")
    profile_p = os.path.join(lib, "00000000-0000-4000-8000-000000157210.json")

    def _read_profile():
        try:
            return json.load(open(profile_p, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    data = None
    deadline = time.time() + wait_secs
    while time.time() < deadline:  # 兜底轮询（万一应用侧异步写入）
        data = _read_profile()
        if data and _profile_matches(data, expect_mode):
            break
        time.sleep(2)
    data = data or _read_profile()

    if data is None:
        C.warn(f"未见 3P profile（{profile_p}）。请在 CC Switch 里切换一次 Claude Desktop 提供商以写出。")
        return False

    base = data.get("inferenceGatewayBaseUrl", "")
    if _profile_matches(data, expect_mode):
        C.log(f"  ✓ 3P profile 已应用：inferenceGatewayBaseUrl={base}")
        if data.get("inferenceModels"):
            names = [m if isinstance(m, str) else m.get("name", "?") for m in data["inferenceModels"]]
            C.log(f"  ✓ 模型菜单（inferenceModels）：{', '.join(names)}")
    else:
        if expect_mode == "proxy":
            C.warn(f"3P profile 仍是旧内容（base={base}）。CC Switch 仅在 UI 切换提供商时重写 profile："
                   "请打开 CC Switch → Claude Desktop 页 → 点一下 CommandCode 卡片（重新切换），"
                   "profile 会立即变为本机代理地址并只含映射模型。")
        else:
            C.warn(f"3P profile 仍是旧内容（base={base}）。请打开 CC Switch → Claude Desktop 页 →"
                   "点一下 CommandCode 卡片（重新切换）。")
        return False

    cfg = os.path.join(HOME, "Library", "Application Support", "Claude", "claude_desktop_config.json")
    if os.path.exists(cfg):
        try:
            mode = json.load(open(cfg, encoding="utf-8")).get("deploymentMode")
            if mode != "3p":
                C.warn(f"claude_desktop_config.json 的 deploymentMode={mode}（应为 3p）—— 请在 Claude Desktop 设置里切换到第三方部署模式。")
        except (json.JSONDecodeError, OSError) as e:
            C.warn(f"{cfg} 读取失败：{e}")
    return True


def _profile_matches(data, expect_mode):
    base = data.get("inferenceGatewayBaseUrl", "")
    if expect_mode == "proxy":
        return base.rstrip("/").endswith("/claude-desktop")
    return "commandcode.ai" in base

# ---------------- codex 冒烟测试 ----------------

def find_codex():
    p = shutil.which("codex")
    if p:
        return p
    pnpm = os.path.join(HOME, "Library/Application Support/deepseek-harness-desktop/node-runtime/packages/node_modules/.pnpm")
    hits = sorted(glob.glob(pnpm + "/@openai+codex@*/node_modules/@openai/codex/vendor/*/bin/codex"))
    return hits[-1] if hits else None

def e2e_verify(codex_bin, model, effort):
    import tempfile
    C.log(f"\n→ Codex 冒烟测试（{model}，effort={effort}）…")
    tmp = tempfile.mkdtemp(prefix="codex-verify-")
    shutil.copy2(CODEX_CATALOG, os.path.join(tmp, "cc-switch-model-catalog.json"))
    with open(os.path.join(tmp, "config.toml"), "w", encoding="utf-8") as f:
        f.write(f'''model_provider = "custom"
model = "{model}"
model_reasoning_effort = "{effort}"
model_catalog_json = "cc-switch-model-catalog.json"
disable_response_storage = true

[model_providers.custom]
name = "custom"
wire_api = "responses"
requires_openai_auth = true
base_url = "http://{PROXY_HOST}:{PROXY_PORT}/v1"
experimental_bearer_token = "PROXY_MANAGED"
''')
    with open(os.path.join(tmp, "auth.json"), "w", encoding="utf-8") as f:
        json.dump({"OPENAI_API_KEY": "PROXY_MANAGED"}, f)
    env = dict(os.environ, CODEX_HOME=tmp)
    try:
        r = subprocess.run(
            [codex_bin, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "Reply with exactly: PONG"],
            env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        C.warn("codex exec 超时（120s）")
        return False
    out = (r.stdout or "") + (r.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-6:])
    if "PONG" in out:
        if "metadata not found" in out.lower():
            C.warn("输出含 Model metadata not found 警告")
        C.log("  ✓ 端到端打通，输出尾部：")
        C.log("  " + tail.replace("\n", "\n  "))
        return True
    C.warn("未看到 PONG，输出尾部：")
    C.log("  " + tail.replace("\n", "\n  "))
    return False
