#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Desktop 目标模块：CC Switch 直连模式（写 DB claude-desktop 行）。

【实测】CC Switch 的 direct 模式：DB 行 settings_config.env 两键会被原样写进
~/Library/Application Support/Claude-3p/configLibrary/<appliedId>.json：
  ANTHROPIC_BASE_URL   → inferenceGatewayBaseUrl（Claude Desktop 请求 {base}/v1/messages）
  ANTHROPIC_AUTH_TOKEN → inferenceGatewayApiKey（AuthScheme=bearer，上游 /v1/messages 实测接受 Bearer）
因此 baseURL 必须是不含端点路径的 Anthropic 形态前缀。

重要限制：Claude Desktop 只走 Anthropic Messages 端点（Claude 系模型）；
GOAT 套餐不含任何 Claude 模型（Pro 及以上才含）——配置照常写入，升级套餐即自动可用。
"""

from . import common as C
from . import ccswitch as CC

CLAUDE_DESKTOP_BASE = "https://api.commandcode.ai/provider"   # Claude Desktop 会请求 {base}/v1/messages
CLAUDE_DESKTOP_META = {"claudeDesktopMode": "direct", "apiFormat": "anthropic"}


def run(key, upstream, args, shared_entries=None):
    """Claude Desktop 目标主流程。无需探测结果（不读模型目录），仅写直连配置。"""
    C.log(f"\n===== 目标：Claude Desktop（CC Switch 直连模式） =====")
    C.log(f"  上游：{CLAUDE_DESKTOP_BASE}（Claude Desktop 请求 {{base}}/v1/messages，bearer 鉴权）")
    C.log("  模型由 Claude Desktop 端选择（不经过 CC Switch 目录）。")
    C.log("  ⚠️  Claude 模型能否调用取决于订阅套餐：GOAT 不含 Claude（Pro 及以上可用）；"
          "配置照常写入，升级套餐后即可用，无需重跑。")

    if args.dry_run:
        C.log("\n将写入（CC Switch DB claude-desktop 行）：")
        C.log(f"  settings_config.env.ANTHROPIC_BASE_URL = {CLAUDE_DESKTOP_BASE}")
        C.log(f"  settings_config.env.ANTHROPIC_AUTH_TOKEN = <你输入的 Key，len={len(key)}>")
        C.log(f"  meta = {CLAUDE_DESKTOP_META}")
        C.log("  is_current=1（Claude Desktop 分组内）")
        C.log("\n== DRY-RUN：未做任何修改 ==")
        return True

    import sys
    if not args.yes:
        if not sys.stdin.isatty():
            C.die("非交互环境请加 --yes 确认写入。")
        if input("\n确认写入 CC Switch 数据库并重启应用? [y/N] ").strip().lower() not in ("y", "yes"):
            C.die("已取消，未做任何修改。")

    CC.prepare_write(CC.DB_PATH, live=not getattr(args, "db", None), no_restart=args.no_restart)
    db = getattr(args, "db", None) or CC.DB_PATH
    sc = {"env": {"ANTHROPIC_BASE_URL": CLAUDE_DESKTOP_BASE, "ANTHROPIC_AUTH_TOKEN": key}}
    pid, action = CC.write_provider(db, "claude-desktop", args.name,
                                    CC.COMPACT(sc), CC.COMPACT(CLAUDE_DESKTOP_META), CLAUDE_DESKTOP_BASE)
    C.log(f"→ claude-desktop 提供商已{'新建' if action == 'created' else '原地更新'}（id={pid[:8]}…，direct 模式，已设为当前提供商）")

    if not CC.finish_write(db, live=not getattr(args, "db", None), no_restart=args.no_restart,
                           targets=[("claude-desktop", None)]):
        return False

    C.log("Claude Desktop：重启 Claude Desktop 后，在设置中确认部署模式为第三方（3p）即可经 CommandCode 直连。")
    return True
