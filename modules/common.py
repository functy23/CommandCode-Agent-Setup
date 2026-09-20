#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CommandCode-Agent-Setup 公共模块：HTTP、Key 校验、套餐闸门、公开模型目录、元数据权威表。

zcode / codex 共用这里的全部基础设施。
【实测】标注的事实见仓库 AGENTS.md；改目录/判定逻辑前先读它。
"""

import json
import re
import sys
import urllib.error
import urllib.request

API_BASE = "https://api.commandcode.ai"
UPSTREAM_BASE = API_BASE + "/provider/v1"
PATH_MODELS = "/provider/v1/models"
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

# 模型列表不靠内嵌清单：GET 公开目录 /provider/v1/models（与 dsh-commandcode-provider 同源），
# 上游新增/下架模型自动跟随。不再逐模型 POST chat/completions 探测。
# 以下两表只负责"元数据标注"（思考档位、图像输入）。

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

def _parse_models(resp):
    if not isinstance(resp, dict) or not isinstance(resp.get("data"), list):
        return None
    return {m["id"]: m for m in resp["data"] if isinstance(m, dict) and m.get("id")}

def fetch_catalog(key=None):
    """拉模型目录。先走公开 GET（dsh-commandcode-provider 同源，不带 Key）；
    失败且提供了 Key 时再带鉴权重试。返回 (upstream_map, err)。"""
    status, resp = http(API_BASE + PATH_MODELS, timeout=30)
    models = _parse_models(resp) if status == 200 else None
    if models:
        return models, None
    if key:
        status, resp = http(API_BASE + PATH_MODELS, key=key, timeout=30)
        if status in (401, 403):
            return None, f"Key 无效或无权限（HTTP {status}）"
        models = _parse_models(resp) if status == 200 else None
        if models:
            return models, None
        return None, f"模型目录返回异常（HTTP {status}）：{str(resp)[:200]}"
    return None, f"公开模型目录返回异常（HTTP {status}）：{str(resp)[:200]}"

def fetch_upstream(key):
    """带 Key 拉目录（用于校验 Key）。返回 (upstream_map, err)。"""
    status, resp = http(API_BASE + PATH_MODELS, key=key, timeout=30)
    if status in (401, 403):
        return None, f"Key 无效或无权限（HTTP {status}）"
    models = _parse_models(resp) if status == 200 else None
    if models is None:
        return None, f"模型目录返回异常（HTTP {status}）：{str(resp)[:200]}"
    return models, None

def validate_key(key):
    """校验 Key 并返回 (upstream_map, plan_id, account_label)。任一失败抛 SystemExit。

    Key 有效性以带鉴权的 /models 或 /whoami 为准；模型清单优先用公开目录
    （与 dsh-commandcode-provider 一致，不消耗 token、不逐模型探测）。"""
    log("→ 校验 API Key …")
    auth_upstream, err = fetch_upstream(key)
    if auth_upstream is None:
        # 公开目录可访问时，带 Key 的 /models 仍可能 401——那才是 Key 无效
        who_status, _ = http(API_BASE + PATH_WHOAMI, key=key, timeout=30)
        if who_status in (401, 403) or (err and "无效或无权限" in err):
            die(err or f"Key 无效或无权限（HTTP {who_status}）")
        warn(err or "带 Key 的模型目录不可用，改走公开目录")
    public, pub_err = fetch_catalog()
    upstream = public or auth_upstream
    if not upstream:
        die(pub_err or err or "无法访问 CommandCode 模型目录")
    if public:
        log(f"  公开目录 {len(public)} 个模型")
    elif auth_upstream:
        log(f"  鉴权目录 {len(auth_upstream)} 个模型（公开目录不可用）")
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
    """CC Switch modelCatalog 条目（codex 元数据口径）。"""
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

def build_entries(upstream, key=None, extra_includes=(), skip_probe=False, quiet_header=False):
    """从公开目录构建收录列表，返回 (entries, excluded, notes)。

    不再逐模型 POST 探测。Claude 系一律剔除（只能走 Anthropic 路由）。
    key / skip_probe 保留仅为兼容旧调用（skip_probe 现为无操作）。"""
    notes, excluded = [], []
    if not quiet_header:
        log(f"\n→ 按公开目录收录模型（{len(upstream)} 个，Claude 系跳过）…")
    entries = []
    for slug in upstream:
        if slug.startswith("claude"):
            excluded.append((slug, "Claude 系只能走 Anthropic Messages 端点，无法经 chat/completions 使用"))
        else:
            entries.append(codex_entry(slug, upstream))
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
