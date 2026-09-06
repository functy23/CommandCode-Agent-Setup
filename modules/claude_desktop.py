#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Desktop 目标模块：CC Switch 两种模式可选。

proxy 模式（默认，推荐）—— 等同 Codex 的接入方式：
  请求链路：Claude Desktop → 本机 15721 代理 /claude-desktop/v1/messages
            → Anthropic→OpenAI 转换 → CommandCode chat/completions
  模型菜单完全由配置决定：meta.claudeDesktopModelRoutes 把 Claude Desktop 认可的
  claude-safe 角色 id（sonnet/opus/haiku/fable 档）映射到 CommandCode 真实模型，
  CC Switch 接管时把映射结果写进 3P profile 的 inferenceModels——官方模型清单
  彻底消失（也消掉了官方模型探测 403 MODEL_NOT_IN_PLAN 的启动报错）。
  settings_config.modelCatalog 同时写入映射后模型，供 CC Switch 用量/上下文统计。
  前提：CC Switch 代理开启（脚本自动开）+ Claude Desktop 部署模式 3p。

direct 模式（旧行为）：
  直连上游 Anthropic Messages 端点，模型由 Claude Desktop 端自动清单决定。
  GOAT 套餐下 Claude Desktop 会报「Gateway rejected the configured credential
  (HTTP 403)」——这是官方模型探测 403 MODEL_NOT_IN_PLAN 所致（GOAT 无 Claude），
  非 Key 问题。direct 模式仅适合含 Claude 的套餐（Pro+）。

【实测 2026-09-06，cc-switch 源码 claude_desktop_config.rs/provider.rs 为准】
- meta.claudeDesktopModelRoutes: {route_id: {model, labelOverride?, supports1m?}}
  route_id 必须 claude-* 或 anthropic/claude-*；proxy 模式下 model 可为任意上游模型；
  direct 模式禁止映射（model 只能等于 route_id）。
- proxy 模式 profile：inferenceGatewayBaseUrl=http://127.0.0.1:15721/claude-desktop、
  apiKey=CC Switch 生成的 ccs-* 网关 token、inferenceModels=映射后列表。
- proxy 模式请求：/v1/models 返回映射列表；messages 里 model 按路由表换成上游模型
  （含角色关键词回落与 [1m] 后缀剥离），再按 apiFormat 转换转发。
"""

from . import common as C
from . import ccswitch as CC

CLAUDE_DESKTOP_BASE = "https://api.commandcode.ai/provider"   # direct 模式用（Desktop 拼 /v1/messages）

# proxy 模式默认映射：Claude Desktop 的四个角色档 → 四个不同的 CommandCode 模型。
# 分档逻辑（能力从高到低，全部在 GOAT 套餐内、经探测收录）：
#   opus   = gpt-5.6-sol                最强综合推理（GPT 顶配）
#   sonnet = deepseek/deepseek-v4-flash 均衡主力（1M 上下文、推理档位完整）
#   haiku  = z-ai/glm-5.3-flash         快速响应（GLM Flash）
#   fable  = moonshotai/Kimi-K3         创意/长文（Kimi）
# 用户可用 --cd-model 角色=slug 覆盖；映射目标必须是探测收录的模型。
DEFAULT_ROLE_MAP = {
    "opus": "gpt-5.6-sol",
    "sonnet": "deepseek/deepseek-v4-flash",
    "haiku": "z-ai/glm-5.3-flash",
    "fable": "moonshotai/Kimi-K3",
}
ROLE_ROUTE_ID = {          # CC Switch 认可的 claude-safe route id（DEFAULT_PROXY_ROUTES）
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5",
    "fable": "claude-fable-5",
}
# 各角色显示名（labelOverride 写进 3P profile，即 Claude Desktop 菜单里看到的名字）：
# 直接用底层模型名，让菜单像原生模型列表一样清晰。
ROLE_LABEL = {
    "opus": "GPT-5.6 Sol",
    "sonnet": "DeepSeek V4 Flash",
    "haiku": "GLM-5.3 Flash",
    "fable": "Kimi K3",
}

def parse_role_overrides(pairs):
    """解析 --cd-model opus=slug 形式的覆盖项。返回 {role: slug}。"""
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            C.die(f"--cd-model 格式应为 角色=模型slug（如 opus=zai-org/GLM-5.3），收到：{pair}")
        role, slug = pair.split("=", 1)
        role = role.strip().lower()
        slug = slug.strip()
        if role not in ROLE_ROUTE_ID:
            C.die(f"--cd-model 角色只能是 {'/'.join(ROLE_ROUTE_ID)}，收到：{role}")
        if not slug:
            C.die(f"--cd-model {role}= 后面缺少模型 slug")
        out[role] = slug
    return out


def build_role_map(overrides, entries):
    """合并默认映射与用户覆盖，并校验目标在收录清单内。返回 {role: slug}。"""
    included = {e["model"] for e in entries}
    merged = dict(DEFAULT_ROLE_MAP)
    merged.update(overrides)
    for role, slug in merged.items():
        if slug not in included:
            C.die(f"映射目标 {role}={slug} 不在探测收录的模型清单内（收录 {len(included)} 个）。"
                  "请改用已收录模型，或去掉 --skip-probe 重新探测。")
    return merged


def proxy_settings_config(key, entries, role_map):
    """proxy 模式的 settings_config：env 两键（同 direct）+ modelCatalog（映射后四档）。"""
    by_slug = {e["model"]: e for e in entries}
    catalog = []
    for role, slug in role_map.items():
        src = by_slug[slug]
        catalog.append({
            "model": ROLE_ROUTE_ID[role],
            "displayName": ROLE_LABEL[role],
            "contextWindow": src["contextWindow"],
            "reasoningLevels": src["reasoningLevels"],
            "defaultReasoningLevel": src["defaultReasoningLevel"],
            "inputModalities": src["inputModalities"],
        })
    env = {"ANTHROPIC_BASE_URL": C.UPSTREAM_BASE, "ANTHROPIC_AUTH_TOKEN": key}
    return {"env": env, "modelCatalog": {"models": catalog}}


def proxy_meta(role_map):
    routes = {}
    for role, slug in role_map.items():
        routes[ROLE_ROUTE_ID[role]] = {
            "model": slug,
            "labelOverride": ROLE_LABEL[role],
            "supports1m": True,
        }
    return {
        "claudeDesktopMode": "proxy",
        "apiFormat": "openai_chat",       # 上游 CommandCode 只有 chat/completions
        "claudeDesktopModelRoutes": routes,
    }


def _label_for(slug):
    return C.display_name(slug)


def run(key, upstream, args, shared_entries=None):
    """Claude Desktop 目标主流程。proxy 模式需要探测收录（映射目标校验）。"""
    mode = getattr(args, "cd_mode", "proxy") or "proxy"
    C.log(f"\n===== 目标：Claude Desktop（CC Switch {mode} 模式） =====")

    if mode == "direct":
        return _run_direct(key, args)

    # ---- proxy 模式 ----
    if shared_entries is None:
        entries, excluded, notes = C.build_entries(upstream, key, args.include, args.skip_probe)
    else:
        entries, excluded, notes = shared_entries
    if not entries:
        C.die("没有任何模型可用（可能 Key 或套餐异常），未写入任何配置。")

    role_map = build_role_map(parse_role_overrides(getattr(args, "cd_model", None)), entries)
    meta = proxy_meta(role_map)
    sc = proxy_settings_config(key, entries, role_map)

    C.log("模型映射（Claude Desktop 菜单 ← CommandCode 真实模型）：")
    for role, slug in role_map.items():
        C.log(f"  {ROLE_ROUTE_ID[role]:20} → {slug:44} 菜单显示「{ROLE_LABEL[role]}」")
    C.log("模型菜单将只显示以上映射项（官方模型清单不再出现，启动探测 403 报错随之消除）。")
    C.log(f"上游 API 格式：{meta['apiFormat']}（CC Switch 做 Anthropic→OpenAI 转换）")
    for n in notes:
        C.warn(n)

    if args.dry_run:
        C.log("\n将写入（CC Switch DB claude-desktop 行，proxy 模式）：")
        C.log(f"  settings_config.env.ANTHROPIC_BASE_URL = {C.UPSTREAM_BASE}")
        C.log(f"  settings_config.env.ANTHROPIC_AUTH_TOKEN = <Key，len={len(key)}>")
        C.log(f"  settings_config.modelCatalog = {len(sc['modelCatalog']['models'])} 个映射档")
        C.log(f"  meta.claudeDesktopModelRoutes = {meta['claudeDesktopModelRoutes']}")
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
    pid, action = CC.write_provider(db, "claude-desktop", args.name,
                                    CC.COMPACT(sc), CC.COMPACT(meta), C.UPSTREAM_BASE)
    C.log(f"→ claude-desktop 提供商已{'新建' if action == 'created' else '原地更新'}（id={pid[:8]}…，proxy 模式，已设为当前提供商）")

    if not CC.finish_write(db, live=not getattr(args, "db", None), no_restart=args.no_restart,
                           targets=[("claude-desktop", None)]):
        return False

    C.log("Claude Desktop：重启 Claude Desktop 后即可在模型菜单看到映射档位"
          "（如「Opus 档 · DeepSeek V4 Flash」），官方模型不再出现。")
    return True


def _run_direct(key, args):
    """direct 模式（旧行为）：直连上游，模型由 Claude Desktop 端清单决定。"""
    C.log(f"  上游：{CLAUDE_DESKTOP_BASE}（Claude Desktop 请求 {{base}}/v1/messages，bearer 鉴权）")
    C.log("  模型由 Claude Desktop 端选择（不经过 CC Switch 目录）。")
    C.log("  ⚠️  GOAT 套餐不含 Claude：Claude Desktop 启动探测官方模型会报 403 MODEL_NOT_IN_PLAN"
          "（非 Key 问题）。想消除报错请用 proxy 模式（--cd-mode proxy，默认）；"
          "direct 模式适合含 Claude 的套餐（Pro+）。")

    if args.dry_run:
        C.log("\n将写入（CC Switch DB claude-desktop 行，direct 模式）：")
        C.log(f"  settings_config.env.ANTHROPIC_BASE_URL = {CLAUDE_DESKTOP_BASE}")
        C.log(f"  settings_config.env.ANTHROPIC_AUTH_TOKEN = <你输入的 Key，len={len(key)}>")
        C.log(f"  meta = {{'claudeDesktopMode': 'direct', 'apiFormat': 'anthropic'}}")
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
                                    CC.COMPACT(sc), CC.COMPACT({"claudeDesktopMode": "direct", "apiFormat": "anthropic"}),
                                    CLAUDE_DESKTOP_BASE)
    C.log(f"→ claude-desktop 提供商已{'新建' if action == 'created' else '原地更新'}（id={pid[:8]}…，direct 模式，已设为当前提供商）")

    if not CC.finish_write(db, live=not getattr(args, "db", None), no_restart=args.no_restart,
                           targets=[("claude-desktop", None)]):
        return False

    C.log("Claude Desktop：重启 Claude Desktop 后，在设置中确认部署模式为第三方（3p）即可经 CommandCode 直连。")
    return True
