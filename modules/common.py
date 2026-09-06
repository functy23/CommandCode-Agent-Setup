#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CommandCode-Agent-Setup 公共模块：HTTP、Key 校验、套餐闸门、探测、元数据权威表。

三个目标模块（zcode / codex / claude_desktop）共用这里的全部基础设施。
【实测】标注的事实见仓库 AGENTS.md；改探测/判定逻辑前先读它。
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE = "https://api.commandcode.ai"
UPSTREAM_BASE = API_BASE + "/provider/v1"
PATH_MODELS = "/provider/v1/models"
PATH_CHAT = "/provider/v1/chat/completions"
PATH_MESSAGES = "/provider/v1/messages"
PATH_SUBS = "/alpha/billing/subscriptions"
PATH_WHOAMI = "/alpha/whoami"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DEFAULT_PROVIDER_NAME = "CommandCode"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_LEVELS = ["low", "medium", "high"]  # 非 KNOWN_EFFORTS 模型的兜底档位（上游已验证通用接受）

PROVIDER_WEBSITE = "https://commandcode.ai"
PROVIDER_CATEGORY = "third_party"
PROVIDER_ICON_COLOR = "#4F46E5"

# ---------------- 模型元数据（来源：dsh-commandcode-provider/src/adapter.ts，command-code@1.37.0 同步；2026-08-29 实测核对） ----------------

# 模型列表不靠内嵌清单：拉取上游全量目录后逐模型探测套餐可用性（见 probe_model），
# 上游新增/下架模型自动跟随。以下两表只负责"元数据标注"（思考档位、图像输入）。

# KNOWN_EFFORTS：官方标注了可选思考档位的模型（档位升序；默认档取最高档，与实测目录一致）。
# 不在表内的模型一律用 DEFAULT_LEVELS（上游网关对 effort 参数通用接受，实测仅 deepseek 拒绝 "none"）。
KNOWN_EFFORTS = {
    "Qwen/Qwen3.8-Max": ["low", "medium", "xhigh"],
    "Qwen/Qwen3.8-27B": ["low", "medium", "xhigh"],
    "Qwen/Qwen3.8-Flash": ["low", "medium", "xhigh"],
    "deepseek/deepseek-v4-flash": ["high", "max"],
    "deepseek/deepseek-v4-flash-vision-exp": ["high", "max"],
    "deepseek/deepseek-v4-pro": ["high", "max"],
    "google/gemini-3.1-flash-lite": ["low", "medium", "high"],
    "google/gemini-3.5-flash": ["low", "medium", "high"],
    "google/gemini-3.5-flash-lite": ["low", "medium", "high"],
    "google/gemini-3.6-flash": ["low", "medium", "high"],
    "google/gemini-3.7-flash": ["low", "medium", "high"],
    "gpt-5.3-codex": ["low", "medium", "high", "xhigh"],
    "gpt-5.4": ["low", "medium", "high", "xhigh"],
    "gpt-5.4-mini": ["low", "medium", "high"],
    "gpt-5.5": ["low", "medium", "high", "xhigh"],
    "gpt-5.6-luna": ["low", "medium", "high", "xhigh", "max"],
    "gpt-5.6-sol": ["low", "medium", "high", "xhigh", "max"],
    "gpt-5.6-terra": ["low", "medium", "high", "xhigh", "max"],
    "xai/grok-4.5": ["low", "medium", "high"],
    "xai/grok-4.6": ["low", "medium", "high", "xhigh"],
    "z-ai/glm-5.3-flash": ["low", "high", "max"],
    "zai-org/GLM-5.2": ["high", "max"],
    "zai-org/GLM-5.3": ["low", "high", "max"],
}

# KNOWN_IMAGE_MODELS：支持图像输入（inputModalities 含 image）。
KNOWN_IMAGE_MODELS = {
    "MiniMaxAI/MiniMax-M3", "Qwen/Qwen3.6-Plus", "Qwen/Qwen3.7-Flash", "Qwen/Qwen3.7-Plus",
    "Qwen/Qwen3.8-27B", "Qwen/Qwen3.8-Flash", "Qwen/Qwen3.8-Max",
    "deepseek/deepseek-v4-flash-vision-exp", "google/gemini-3.1-flash-lite", "google/gemini-3.5-flash",
    "google/gemini-3.5-flash-lite", "google/gemini-3.6-flash", "google/gemini-3.7-flash",
    "gpt-5.3-codex", "gpt-5.4", "gpt-5.4-mini", "gpt-5.5", "gpt-5.6-luna", "gpt-5.6-sol",
    "meta/muse-spark-1.1", "meta/muse-spark-1.2", "meta/muse-spark-1.2-contributor",
    "minimax/minimax-m3-free", "moonshotai/Kimi-K2.5", "moonshotai/Kimi-K2.6",
    "moonshotai/Kimi-K2.7-Code", "moonshotai/Kimi-K2.7-Code-Highspeed", "moonshotai/Kimi-K3",
    "xiaomi/mimo-v2.5", "xiaomi/mimo-v2.5-pro", "z-ai/glm-5.3-flash", "xai/grok-4.5",
}

# ---------------- 输出辅助 ----------------

def log(msg=""):
    print(msg, flush=True)

def warn(msg):
    print(f"⚠️  {msg}", flush=True)

def die(msg, code=1):
    print(f"❌ {msg}", file=sys.stderr, flush=True)
    raise SystemExit(code)

# ---------------- HTTP ----------------

def _headers(key=None, extra=None):
    h = {"Content-Type": "application/json", "User-Agent": UA, "Accept": "application/json"}
    if key:
        h["Authorization"] = f"Bearer {key}"
        h["x-api-key"] = key
        h["anthropic-version"] = "2023-06-01"
    if extra:
        h.update(extra)
    return h

def _try_json(raw):
    try:
        return json.loads(raw)
    except Exception:
        return raw

def http(url, key=None, body=None, method=None, timeout=60, extra_headers=None):
    """带浏览器 UA 的 HTTP 请求（该站会用 Cloudflare 1010 拦截非浏览器 UA）。
    返回 (status, 解析后的dict或原始str)。"""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(key, extra_headers),
                                 method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _try_json(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, _try_json(e.read().decode("utf-8", "replace"))
    except Exception as e:
        return 0, f"网络异常: {e}"

# ---------------- 探测 ----------------

PROBE_MARKS = {"OK": "✅", "NOT_IN_PLAN": "🚫", "UNSUPPORTED": "❌", "TRANSIENT": "⏳", "ERROR": "❌"}

def probe_model(model_id, key, attempts=3):
    """1-token 最小请求探测。返回 (类别, 说明)：
    OK=可用；NOT_IN_PLAN=套餐不含；UNSUPPORTED=上游拒绝；
    TRANSIENT=429/503 临时问题（保留收录）；ERROR=其他失败（剔除）。"""
    body = {"model": model_id, "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}]}
    detail = ""
    for attempt in range(attempts):
        status, resp = http(API_BASE + PATH_CHAT, key=key, body=body)
        if status == 200:
            return "OK", ""
        if status == 403:
            s = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
            return ("NOT_IN_PLAN", "套餐不含（MODEL_NOT_IN_PLAN）"
                    if "MODEL_NOT_IN_PLAN" in s else f"403: {s[:140]}")
        if status in (429, 503):
            detail = f"{status} 上游暂时不可用"
            time.sleep(3 * (attempt + 1))
            continue
        if status == 400:
            s = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
            if ">= 16" in s and body["max_tokens"] < 16:
                body["max_tokens"] = 16      # 部分模型要求 max_tokens >= 16
                continue
            return "UNSUPPORTED", s[:140]
        detail = f"{status}: {resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)}"[:140]
        time.sleep(2)
    if detail.startswith("429") or detail.startswith("503"):
        return ("TRANSIENT", detail)
    return ("ERROR", detail or "多次重试失败")

def probe_all(model_ids, key, workers=8):
    results, done = {}, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(probe_model, mid, key): mid for mid in model_ids}
        for fut in as_completed(futs):
            mid = futs[fut]
            try:
                results[mid] = fut.result()
            except Exception as e:                       # 网络层异常
                results[mid] = ("ERROR", str(e)[:140])
            done += 1
            cls, note = results[mid]
            print(f"  [{done:>2}/{len(model_ids)}] {PROBE_MARKS.get(cls, '❌')} {mid:44} {note}", flush=True)
            time.sleep(0.2)                              # 温和限速
    return results

# ---------------- Key 校验与套餐闸门 ----------------

def detect_plan(plan_id):
    p = (plan_id or "").lower()
    if "goat" in p:
        return "goat"
    if re.search(r"(^|[^a-z])go([^a-z]|$)", p):
        return "go"
    if "pro" in p:
        return "pro"
    if p:
        return "provider"
    return None

def fetch_plan_id(key):
    status, resp = http(API_BASE + PATH_SUBS, key=key, timeout=30)
    if status == 200 and isinstance(resp, dict):
        return (resp.get("data") or {}).get("planId") or "", None
    return None, f"HTTP {status} {str(resp)[:120]}"

def fetch_account(key):
    status, resp = http(API_BASE + PATH_WHOAMI, key=key, timeout=30)
    if status == 200 and isinstance(resp, dict):
        u = resp.get("user") or {}
        return u.get("email") or u.get("name") or u.get("id") or ""
    return ""

def fetch_upstream(key):
    """返回 (upstream_map, err)。upstream_map: {id: {name, context_length, ...}}"""
    status, resp = http(API_BASE + PATH_MODELS, key=key, timeout=30)
    if status in (401, 403):
        return None, f"Key 无效或无权限（HTTP {status}）"
    if status != 200 or not isinstance(resp, dict) or not isinstance(resp.get("data"), list):
        return None, f"模型目录返回异常（HTTP {status}）：{str(resp)[:200]}"
    return {m["id"]: m for m in resp["data"] if isinstance(m, dict) and m.get("id")}, None

def validate_key(key):
    """校验 Key 并返回 (upstream_map, plan_id, account_label)。任一失败抛 SystemExit。"""
    log("→ 校验 API Key …")
    upstream, err = fetch_upstream(key)
    if upstream is None:
        die(err or "无法访问 CommandCode API")
    if not upstream:
        die("上游 /models 返回为空，接口结构可能已变化。")
    plan_id, sub_err = fetch_plan_id(key)
    if sub_err:
        warn(f"订阅信息获取失败（不影响继续）：{sub_err}")
    return upstream, plan_id or "", fetch_account(key)

# ---------------- 目录构建 ----------------

def display_name(name):
    """去掉上游 (latest)/(exp) 后缀，得到干净显示名。"""
    return re.sub(r"\s*\((latest|exp)\)\s*$", "", name or "").strip()

def levels_for(slug):
    """写入 codex catalog 的档位集。

    【实测 2026-09-06】ChatGPT.app（原 Codex 桌面版 GUI）的推理强度菜单不认识
    max（TUI 源码 is_advanced_reasoning_effort 把 Max/Ultra 归入『More reasoning…』
    高级弹窗，GUI 前端则直接不渲染），只认识 none/minimal/low/medium/high/xhigh。
    因此权威表中的 max 统一映射为 xhigh（GUI 显示『极高』）——上游网关对两者
    均返回 200，xhigh 即为 GUI 可选的最高档；CLI 侧 /model 的『More reasoning…』
    行为不变。"""
    raw = KNOWN_EFFORTS.get(slug, DEFAULT_LEVELS)
    return ["xhigh" if lv == "max" else lv for lv in raw]

def default_level(slug):
    return levels_for(slug)[-1]

def codex_entry(slug, upstream, ctx_fallback=128000):
    """CC Switch modelCatalog 条目（codex / claude-desktop 共用元数据口径）。"""
    u = upstream.get(slug) or {}
    ctx = int(u.get("context_length") or 0)
    if ctx <= 0:
        warn(f"{slug}: 上游未提供 context_length，回退为 {ctx_fallback}")
        ctx = ctx_fallback
    return {
        "model": slug,
        "displayName": display_name(u.get("name")) or slug,
        "contextWindow": ctx,
        "reasoningLevels": levels_for(slug),
        "defaultReasoningLevel": default_level(slug),
        "inputModalities": ["text", "image"] if slug in KNOWN_IMAGE_MODELS else ["text"],
    }

def build_entries(upstream, key, extra_includes=(), skip_probe=False, quiet_header=False):
    """探测上游全量模型的套餐可用性，返回 (entries, excluded, notes)。
    判定与参考实现一致：OK/TRANSIENT 收录（429/503 属临时问题），
    NOT_IN_PLAN/UNSUPPORTED/ERROR 剔除；Claude 系一律剔除（只能走 Anthropic 路由）。"""
    notes, excluded = [], []
    if skip_probe:
        warn("已跳过探测（--skip-probe）：直接收录除 Claude 外的全部模型，其中失效模型在调用时会报错。")
        results = {m: ("OK", "跳过探测") for m in upstream}
    else:
        if not quiet_header:
            log("\n→ 探测各模型在当前套餐下的可用性（每模型 1~16 token，8 并发，约 1~3 分钟）…")
        results = probe_all(list(upstream), key)
    entries = []
    for slug, (cls, note) in results.items():
        if slug.startswith("claude"):
            excluded.append((slug, "Claude 系只能走 Anthropic Messages 端点，无法经 chat/completions 使用"))
        elif cls in ("OK", "TRANSIENT"):
            entries.append(codex_entry(slug, upstream))
            if cls == "TRANSIENT":
                notes.append(f"{slug}: 上游暂时不可用（{note}），已保留收录，请留意")
        else:
            excluded.append((slug, note))
    for slug in extra_includes:                       # --include 强制收录
        if slug not in upstream:
            notes.append(f"--include {slug}: 上游目录中不存在，忽略")
        elif slug.startswith("claude"):
            notes.append(f"--include {slug}: Claude 系无法经 chat/completions 使用，忽略")
        elif all(e["model"] != slug for e in entries):
            entries.append(codex_entry(slug, upstream))
            notes.append(f"{slug}: 经 --include 强制收录")
    order = {m: i for i, m in enumerate(upstream)}    # 按上游目录顺序稳定排序
    entries.sort(key=lambda e: order.get(e["model"], 10 ** 9))
    return entries, excluded, notes
