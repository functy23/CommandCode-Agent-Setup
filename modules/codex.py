#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Codex CLI 目标模块：经 CC Switch 代理接入（写 DB codex 行 + 接管 + 可选 PONG）。"""

import json
import os
import time

from . import common as C
from . import ccswitch as CC

# meta：openai_chat 让 CC Switch 做 responses→chat 转换（上游只有 chat/completions，无 /responses）。
# codexChatReasoning 各字段为 CC Switch 认可的转换参数，勿随意改动。
PROVIDER_META = {
    "commonConfigEnabled": False,
    "endpointAutoSelect": True,
    "apiFormat": "openai_chat",
    "codexChatReasoning": {
        "supportsThinking": True,
        "supportsEffort": True,
        "thinkingParam": "none",
        "effortParam": "reasoning_effort",
        "effortValueMode": "zen",
        "outputFormat": "reasoning_content",
    },
}

CONFIG_TOML_TEMPLATE = """model_provider = "custom"
model = "{model}"
model_reasoning_effort = "{effort}"
disable_response_storage = true

[model_providers.custom]
name = "custom"
wire_api = "responses"
requires_openai_auth = true
base_url = "{base_url}"
"""


def build_settings_config(key, entries, model, effort):
    toml = CONFIG_TOML_TEMPLATE.format(model=model, effort=effort, base_url=C.UPSTREAM_BASE)
    return {"auth": {"OPENAI_API_KEY": key}, "config": toml, "modelCatalog": {"models": entries}}


def run(key, upstream, args, shared_entries=None):
    """Codex 目标主流程。shared_entries 非空时复用已探测的收录结果。"""
    C.log(f"\n===== 目标：Codex CLI（经 CC Switch 代理） =====")
    if shared_entries is not None:
        entries, excluded, notes = shared_entries
    else:
        entries, excluded, notes = C.build_entries(upstream, key, args.include, args.skip_probe)
    if not entries:
        C.die("没有任何模型可用（可能 Key 或套餐异常），未写入任何配置。")

    default_model = args.model or (C.DEFAULT_MODEL if any(e["model"] == C.DEFAULT_MODEL for e in entries) else entries[0]["model"])
    if not any(e["model"] == default_model for e in entries):
        C.die(f"--model 指定的 {default_model} 不在套餐可用模型内。")
    effort = C.default_level(default_model)

    # ---- 预览 ----
    C.log(f"将写入模型目录（{len(entries)} 个）：")
    C.log(f"  {'#':>3}  {'slug':44} {'显示名':26} {'上下文':>9}  档位 / 图像")
    for i, e in enumerate(entries, 1):
        img = "🖼" if "image" in e["inputModalities"] else ""
        lv = "/".join(e["reasoningLevels"])
        C.log(f"  {i:>3}  {e['model']:44} {e['displayName']:26} {e['contextWindow']:>9}  {lv} {img}")
    for slug, why in sorted(excluded):
        C.log(f"  未收录 · {slug:44} {why}")
    for n in notes:
        C.warn(n)
    C.log(f"\n默认模型：{default_model}（effort={effort}）")
    C.log(f"提供商名称：{args.name} ｜ 数据库：{CC.DB_PATH}")

    if args.dry_run:
        C.log("\n== DRY-RUN：未做任何修改 ==")
        return True

    if not args.yes:
        import sys
        if not sys.stdin.isatty():
            C.die("非交互环境请加 --yes 确认写入。")
        if input("\n确认写入 CC Switch 数据库并重启应用? [y/N] ").strip().lower() not in ("y", "yes"):
            C.die("已取消，未做任何修改。")

    CC.prepare_write(CC.DB_PATH, live=not getattr(args, "db", None), no_restart=args.no_restart)
    db = getattr(args, "db", None) or CC.DB_PATH
    sc = build_settings_config(key, entries, default_model, effort)
    pid, action = CC.write_provider(db, "codex", args.name,
                                    CC.COMPACT(sc), CC.COMPACT(PROVIDER_META), C.UPSTREAM_BASE)
    C.log(f"→ codex 提供商已{'新建' if action == 'created' else '原地更新'}（id={pid[:8]}…，已设为当前提供商，代理接管已启用）")

    if not CC.finish_write(db, live=not getattr(args, "db", None), no_restart=args.no_restart,
                           targets=[("codex", entries)]):
        return False

    if args.verify:
        codex_bin = CC.find_codex()
        if not codex_bin:
            C.warn("未找到 codex 可执行文件，跳过冒烟测试。")
        else:
            deadline = time.time() + 20
            while time.time() < deadline:  # 等接管完成、目录文件生成
                if os.path.exists(CC.CODEX_CATALOG):
                    try:
                        if len(json.load(open(CC.CODEX_CATALOG))["models"]) == len(entries):
                            break
                    except Exception:
                        pass
                time.sleep(1)
            if not CC.e2e_verify(codex_bin, default_model, effort):
                C.warn("冒烟测试未通过，请检查 ~/.cc-switch/logs/cc-switch.log。")
                return False
    return True
