#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode 目标模块：把 CommandCode 写入 ~/.zcode/v2/config.json（kind=openai-compatible）。

行为与原 ZCode-CommandCode-Setup 一致：探测收录 + 官网上下文 + 内嵌规则元数据，写入前备份。
"""

import json
import os
import re
import shutil
import subprocess
import time
import uuid

from . import common as C

CONFIG_PATH = os.path.expanduser("~/.zcode/v2/config.json")
MODELS_PAGE = "https://commandcode.ai/models"

# ---------------- ZCode 元数据规则表（官网无机器可读输出/档位，实测校准默认值） ----------------

DEFAULT_OUTPUT = 65536
OUTPUT_RULES = [
    (r"deepseek/deepseek-v4", 384000),
    (r"xai/grok", 500000),
    (r"Kimi-K2\.7-Code", 262144),
    (r"Kimi-K3", 131072),
    (r"Kimi-K2\.[56]", 65536),
    (r"GLM-5\.3", 128000),
    (r"GLM-5\.2", 131072),
    (r"zai-org/GLM-5(\.1)?$", 64000),
    (r"gpt-5\.6", 128000),
    (r"tencent/hy", 64000),
    (r"mimo-v2\.5", 128000),
    (r"MiniMax-M3|minimax-m3", 131072),
    (r"m2\.7|M2\.7", 131072),
    (r"MiniMax-M2\.5", 65536),
    (r"Qwen/Qwen3\.8", 131072),
]

# (variants..., defaultVariant) 打包成 tuple，最后一个元素是默认档位
_R_HM = ("off", "high", "max", "max")
_R_HM_OFF = ("off", "high", "max", "off")
_R_LHM = ("low", "high", "max", "max")
_R_ON = ("enabled", "off", "enabled")
_R_OH = ("off", "high", "high")
REASONING_RULES = [
    (r"deepseek/deepseek-v4", _R_HM),
    (r"glm-5\.3-flash", _R_HM_OFF),
    (r"GLM-5\.3", _R_LHM),
    (r"GLM-5\.2", _R_HM),
    (r"zai-org/GLM-5(\.1)?$", _R_ON),
    (r"Kimi-K3", _R_HM),
    (r"Kimi-K2\.[56]", _R_ON),
    (r"Qwen/", _R_ON),
    (r"MiniMax-M3|minimax-m3", _R_ON),
    (r"mimo-v2\.5", _R_ON),
    (r"tencent/hy", _R_OH),
    (r"xai/grok", _R_OH),
    (r"gpt-5\.6", _R_HM),
]

INPUT_RULES = [
    (r"flash-vision-exp", ("text", "image")),
    (r"moonshotai/", ("text", "image", "video")),
    (r"Qwen/", ("text", "image", "video")),
    (r"MiniMax-M3|minimax-m3", ("text", "image", "video")),
    (r"mimo-v2\.5$", ("text", "image", "audio", "video")),
    (r"xai/grok", ("text", "image")),
    (r"gpt-5\.6|google/gemini", ("text", "image", "pdf")),
]


def _first_match(rules, model_id):
    for pattern, value in rules:
        if re.search(pattern, model_id):
            return value
    return None


def _pretty_zcode_name(model_id):
    leaf = model_id.split("/")[-1]
    pretty = leaf.replace("-", " ")
    pretty = re.sub(r"\bV(\d)", r"V\1", pretty)
    for pat, rep in [
        (r"\bglm\b", "GLM"), (r"\bqwen\b", "Qwen"), (r"\bkimi\b", "Kimi"),
        (r"\bmimo\b", "MiMo"), (r"\bstep\b", "Step"), (r"\bgrok\b", "Grok"),
        (r"\bdeepseek\b", "DeepSeek"), (r"\bminimax\b", "MiniMax"),
        (r"\bgpt\b", "GPT"), (r"\bhy(\d)\b", r"Hy\1"),
        (r"\bcode\b", "Code"), (r"\bhighspeed\b", "HighSpeed"),
        (r"\bvision\b", "Vision"), (r"\bexp\b", "exp"),
        (r"\bfree\b", "Free"), (r"\bfast\b", "Fast"), (r"\bpro\b", "Pro"),
        (r"\bmax\b", "Max"), (r"\bplus\b", "Plus"), (r"\bflash\b", "Flash"),
        (r"\bpreview\b", "Preview"), (r"\bultra\b", "Ultra"),
    ]:
        pretty = re.sub(pat, rep, pretty, flags=re.I)
    pretty = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", pretty)
    return re.sub(r"\s+", " ", pretty).strip()


# ---------------- 上下文长度（官网 SSR 页） ----------------

def fetch_context_map():
    """从官网 models 页（SSR HTML）解析 显示名 → 上下文长度。失败返回 {}。"""
    status, html = C.http(MODELS_PAGE, timeout=30)
    try:
        if status != 200 or not isinstance(html, str):
            return {}
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", "|", text)
        text = re.sub(r"\|+", "|", text)
        result = {}
        tokens = [t.strip() for t in text.split("|") if t.strip()]
        for i, tok in enumerate(tokens):
            m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([MK])", tok)
            if not m or i == 0:
                continue
            name = None
            for back in range(1, 7):
                cand = tokens[i - back]
                if re.match(r"^(Free|Deals|All|\d)", cand):
                    break
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .()/&+-]{2,40}", cand) \
                        and not re.fullmatch(r"[a-z$]+", cand):
                    name = cand
                    break
            if name:
                mult = {"M": 1_000_000, "K": 1000}[m.group(2)]
                result.setdefault(name, int(float(m.group(1)) * mult))
        return result
    except Exception:
        return {}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def context_for(model_id, ctx_map):
    """显示名与目录 id 归一化匹配；找不到回退 1M（该目录绝大多数模型为 1M）。"""
    if not ctx_map:
        return 1_000_000
    cands = {_norm(model_id.split("/")[-1]), _norm(model_id.split("/")[-1] + " (latest)")}
    best, best_len = None, 0
    for name, ctx in ctx_map.items():
        n = _norm(name)
        for c in cands:
            if c == n or (len(c) >= 6 and (c in n or n in c)):
                if len(n) > best_len:
                    best, best_len = ctx, len(n)
    return best or 1_000_000


# ---------------- 写入 ----------------

def zcode_running():
    try:
        out = subprocess.run(["pgrep", "-f", r"ZCode\.app|zcode-cli"],
                             capture_output=True, text=True, timeout=10)
        return out.returncode == 0
    except Exception:
        return False


def find_provider(cfg, name):
    """优先按 baseURL 识别 CommandCode，其次按 name。返回 (pid, provider) 或 (None, None)。"""
    for pid, p in cfg["provider"].items():
        if isinstance(p, dict) and "commandcode.ai" in str(p.get("options", {}).get("baseURL", "")):
            return pid, p
    for pid, p in cfg["provider"].items():
        if isinstance(p, dict) and p.get("name") == name:
            return pid, p
    return None, None


def run(key, upstream, args, shared_entries=None):
    """ZCode 目标主流程。shared_entries 非空时复用已探测的收录结果（跳过重复探测）。"""
    C.log(f"\n===== 目标：ZCode（{CONFIG_PATH}） =====")
    if not os.path.isfile(CONFIG_PATH):
        C.die(f"未找到 ZCode 配置文件：{CONFIG_PATH}\n请先安装并启动一次 ZCode（生成配置后再运行本脚本）。")
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception as e:
        C.die(f"配置文件不是合法 JSON，中止（请手工检查，勿让脚本覆盖）：{e}")
    if not isinstance(cfg.get("provider"), dict):
        C.die("配置文件缺少 provider 段，结构异常，中止。")

    if zcode_running():
        C.warn("检测到 ZCode 正在运行。脚本仍会写入（改完需完全退出并重启 ZCode 才生效）；")
        C.warn("注意：之后不要在 ZCode 设置界面里改 provider，否则界面可能用旧配置覆盖本文件。")
        if not args.yes and not args.dry_run:
            if input("继续写入吗？[y/N] ").strip().lower() not in ("y", "yes"):
                C.die("已取消 ZCode 写入。", 0)

    # 收录结果：复用共享探测或独立探测
    if shared_entries is not None:
        entries, excluded, notes = shared_entries
    else:
        entries, excluded, notes = C.build_entries(upstream, key, args.include, args.skip_probe)
    if not entries:
        C.die("没有任何模型可用（可能 Key 或套餐异常），未写入任何配置。")

    # 组装 ZCode provider 模型表
    C.log("→ 组装 ZCode 模型元数据（上下文来自官网 models 页，输出/推理档位用内置规则）…")
    ctx_map = fetch_context_map()
    C.log(f"      官网上下文数据解析到 {len(ctx_map)} 个模型" if ctx_map
          else "      官网数据抓取失败，全部回退 1M 上下文")
    models = {}
    for e in entries:
        mid = e["model"]
        reason = _first_match(REASONING_RULES, mid)
        entry = {
            "name": _pretty_zcode_name(mid),
            "limit": {"context": context_for(mid, ctx_map),
                      "output": _first_match(OUTPUT_RULES, mid) or DEFAULT_OUTPUT},
            "modalities": {"input": list(_first_match(INPUT_RULES, mid) or ("text",)),
                           "output": ["text"]},
            "zcode": {"modalitiesConfigured": True},
        }
        if reason:
            entry["reasoning"] = {"enabled": True,
                                  "variants": list(reason[:-1]),
                                  "defaultVariant": reason[-1]}
        models[mid] = entry

    provider = {
        "name": args.name,
        "kind": "openai-compatible",
        "options": {"apiKey": key, "apiKeyRequired": True, "baseURL": C.UPSTREAM_BASE},
        "source": "custom",
        "models": models,
    }
    pid, existing = find_provider(cfg, args.name)
    if existing:
        cfg["provider"][pid] = provider
        action = f"更新已有 provider（id {pid[:8]}…）"
    else:
        pid = str(uuid.uuid4()).lower()
        cfg["provider"][pid] = provider
        action = f"新建 provider（id {pid[:8]}…）"

    C.log(f"→ ZCode：{action}，kind=openai-compatible，baseURL={C.UPSTREAM_BASE}，收录 {len(models)} 个模型")
    for slug, why in sorted(excluded):
        C.log(f"      未收录 · {slug:44} {why}")
    for n in notes:
        C.warn(n)

    if args.dry_run:
        C.log("== DRY-RUN：ZCode 未写盘 ==")
        return True
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = f"{CONFIG_PATH}.bak-{stamp}"
    shutil.copy2(CONFIG_PATH, backup)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    with open(CONFIG_PATH) as f:                          # 回读校验
        json.load(f)
    C.log(f"✅ 已写入 {CONFIG_PATH}（备份：{backup}）")
    C.log("   后续：完全退出并重启 ZCode（⌘Q）后，模型选择器即可见 CommandCode 的模型。")
    return True
