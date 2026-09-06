#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CommandCode-Agent-Setup —— 一键把 CommandCode 订阅配置进多个 AI Agent（仅限 macOS）。

支持目标（复选框多选）：
  • ZCode           —— 写 ~/.zcode/v2/config.json（openai-compatible provider）
  • Claude Desktop  —— 经 CC Switch 直连模式（Anthropic Messages 网关）
  • Codex CLI       —— 经 CC Switch 代理（responses→chat 转换）

Key 模式（单选）：
  • 共用 Key —— 所有选中 Agent 使用同一个 Key
  • 分别配置 —— 按顺序为每个选中 Agent 单独输入 Key

最低 GOAT 套餐（不支持 Go）。仅依赖 Python 3 标准库。

用法：
  python3 setup.py                          # 全交互
  python3 setup.py --agents zcode,codex --key-mode shared
  python3 setup.py --agents all --key-mode shared --key user_xxx --yes --verify
  python3 setup.py --dry-run --skip-probe   # 机器测试组合
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import common as C
from modules import zcode, codex, claude_desktop

# ---------------- Agent 注册表 ----------------

AGENTS = {
    "zcode": {
        "label": "ZCode",
        "desc": "写入 ~/.zcode/v2/config.json，模型选择器直接可见",
        "module": zcode,
    },
    "claude-desktop": {
        "label": "Claude Desktop",
        "desc": "CC Switch 直连模式（Anthropic Messages 网关；GOAT 不含 Claude，Pro+ 可用）",
        "module": claude_desktop,
    },
    "codex": {
        "label": "Codex CLI",
        "desc": "经 CC Switch 代理（responses→chat 转换），含思考档位标注",
        "module": codex,
    },
}
ORDER = ["zcode", "claude-desktop", "codex"]  # 显示与输入顺序

# ---------------- 终端复选框 / 单选（Inquirer 风格，方向键 + 空格） ----------------

ESC = "\x1b"
IS_TTY = sys.stdin.isatty() and sys.stdout.isatty()

def _read_key():
    """读取一个按键（含方向键/回车/空格），返回规范名。"""
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == ESC:
            seq = sys.stdin.read(2)
            return {"[A": "up", "[B": "down", "[C": "right", "[D": "left"}.get(seq, "other")
        if ch in ("\r", "\n"):
            return "enter"
        if ch == " ":
            return "space"
        if ch in ("\x03",):   # Ctrl-C
            raise KeyboardInterrupt
        return ch.lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def _render_choice(title, options, cursor, checked, multi, hint):
    out = [f"{title}（↑↓ 移动，{'空格 勾选，' if multi else ''}回车 确认）\n"]
    for i, (label, desc) in enumerate(options):
        mark = ("\x1b[36m❯\x1b[0m " if i == cursor else "  ")
        if multi:
            box = "\x1b[32m◉\x1b[0m" if i in checked else "◯"
            line = f"{mark}{box} {label}"
        else:
            line = f"{mark}\x1b[36m{label}\x1b[0m" if i == cursor else f"{mark}{label}"
        if desc:
            line += f"  \x1b[2m{desc}\x1b[0m"
        out.append(line + "\n")
    if hint:
        out.append(hint + "\n")
    # 回退光标到列表首行，下一帧原地重绘
    sys.stdout.write("\x1b[" + str(len(options) + (1 if hint else 0)) + "A\r")
    sys.stdout.write("\x1b[J".join(out) + "\x1b[J")
    sys.stdout.flush()

def checkbox(title, options, default=None):
    """多选复选框。options: [(label, desc)]，default: 勾选的下标集合。返回选中的下标列表（有序）。"""
    if not IS_TTY:
        raise RuntimeError("非交互终端，无法显示复选框")
    checked = set(default or set())
    cursor = 0
    print(title + "（↑↓ 移动，空格 勾选/取消，a 全选/反选，回车 确认）")
    _render_choice("", options, cursor, checked, True, "")
    while True:
        k = _read_key()
        hint = ""
        if k == "up":
            cursor = (cursor - 1) % len(options)
        elif k == "down":
            cursor = (cursor + 1) % len(options)
        elif k == "space":
            checked.symmetric_difference_update({cursor})
        elif k == "a":
            if len(checked) == len(options):
                checked.clear()
            else:
                checked = set(range(len(options)))
        elif k == "enter":
            if not checked:
                _render_choice("", options, cursor, checked, True, "\x1b[31m至少选择一项，空格勾选后回车\x1b[0m")
                continue
            break
        _render_choice("", options, cursor, checked, True, hint)
    result = sorted(checked)
    names = "、".join(options[i][0] for i in result)
    print(f"✔ 已选择：{names}")
    return result

def radiolist(title, options, default=0):
    """单选。返回选中下标。"""
    if not IS_TTY:
        raise RuntimeError("非交互终端，无法显示单选框")
    cursor = default
    print(title + "（↑↓ 移动，回车 确认）")
    _render_choice("", options, cursor, None, False, "")
    while True:
        k = _read_key()
        if k == "up":
            cursor = (cursor - 1) % len(options)
        elif k == "down":
            cursor = (cursor + 1) % len(options)
        elif k == "enter":
            break
        _render_choice("", options, cursor, None, False, "")
    print(f"✔ 已选择：{options[cursor][0]}")
    return cursor

# ---------------- 交互流程 ----------------

def ask_agents(args):
    """确定目标 Agent 列表。CLI --agents 优先，否则复选框。"""
    if args.agents:
        m = {"all": list(ORDER)}
        items = []
        for tok in args.agents.split(","):
            tok = tok.strip().lower()
            if not tok:
                continue
            items.extend(m.get(tok, [tok]))
        bad = [t for t in items if t not in AGENTS]
        if bad:
            C.die(f"未知目标：{','.join(bad)}（可选：all/{'/'.join(ORDER)}）")
        seen = list(dict.fromkeys(items))
        # 保持展示顺序
        return [a for a in ORDER if a in seen]
    if not IS_TTY:
        C.die("非交互环境请用 --agents zcode,codex,claude-desktop（或 all）指定目标。")
    idx = checkbox("选择要配置的 Agent", [(AGENTS[a]["label"], AGENTS[a]["desc"]) for a in ORDER],
                   default=set(range(len(ORDER))))
    return [ORDER[i] for i in idx]

def ask_keys(args, agents):
    """确定每个 Agent 的 Key。返回 {agent_slug: key}。"""
    keys = {}
    if args.key:
        for a in agents:
            keys[a] = args.key
        return keys
    env_key = os.environ.get("COMMANDCODE_API_KEY")
    mode = args.key_mode
    if mode is None:
        if not IS_TTY:
            if env_key:
                mode = "shared"
                C.log("使用环境变量 COMMANDCODE_API_KEY 作为共用 Key。")
            else:
                C.die("非交互环境请用 --key-mode shared|separate 与 --key（或环境变量）提供 Key。")
        else:
            idx = radiolist("Key 配置方式", [
                ("共用 Key", "所有选中的 Agent 使用同一个 Key"),
                ("分别配置", "按顺序为每个 Agent 单独输入 Key"),
            ])
            mode = "shared" if idx == 0 else "separate"
    if mode == "shared":
        key = env_key or args.key
        if not key:
            if not IS_TTY:
                C.die("非交互环境请用 --key 或环境变量 COMMANDCODE_API_KEY 提供 Key。")
            key = getpass.getpass(f"请输入共用的 CommandCode API Key（user_…，输入不回显）: ").strip()
        if not key:
            C.die("未提供 Key。")
        for a in agents:
            keys[a] = key
    else:  # separate
        for a in agents:
            key = getpass.getpass(f"请输入 {AGENTS[a]['label']} 使用的 CommandCode API Key（user_…，不回显）: ").strip() \
                if IS_TTY else None
            if not key:
                C.die(f"未提供 {AGENTS[a]['label']} 的 Key。")
            keys[a] = key
    for a, k in keys.items():
        if not k.startswith("user_"):
            C.warn(f"{AGENTS[a]['label']} 的 Key 不是 user_ 前缀，请确认这是 CommandCode 的 API Key。")
    return keys

# ---------------- 主流程 ----------------

def parse_args():
    ap = argparse.ArgumentParser(description="CommandCode → 多 Agent 一键配置（ZCode / Claude Desktop / Codex，仅限 macOS）")
    ap.add_argument("--agents", help="目标 Agent（逗号分隔：zcode,claude-desktop,codex 或 all）；缺省弹复选框")
    ap.add_argument("--key-mode", choices=["shared", "separate"], help="Key 模式；缺省弹单选框")
    ap.add_argument("-k", "--key", help="CommandCode API Key（共用模式下全部 Agent 使用；也可用环境变量 COMMANDCODE_API_KEY）")
    ap.add_argument("--plan", choices=["goat", "pro", "provider"], help="跳过订阅自动识别，强制按该套餐档位（闸门用）")
    ap.add_argument("-m", "--model", help=f"Codex 默认模型 slug（默认 {C.DEFAULT_MODEL}）")
    ap.add_argument("--name", default=C.DEFAULT_PROVIDER_NAME, help=f"提供商名称（默认 {C.DEFAULT_PROVIDER_NAME}）")
    ap.add_argument("--include", action="append", default=[], metavar="SLUG", help="额外强制收录的模型 slug（可重复）")
    ap.add_argument("--skip-probe", action="store_true", help="跳过探测，直接收录目录里除 Claude 外的全部模型")
    ap.add_argument("--db", help="CC Switch 数据库路径（默认 ~/.cc-switch/cc-switch.db；传其他路径用于演练，不触碰真实库）")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不做任何修改")
    ap.add_argument("--no-restart", action="store_true", help="写库后不重启 CC Switch")
    ap.add_argument("--verify", action="store_true", help="完成后跑冒烟测试（codex：PONG）")
    ap.add_argument("-y", "--yes", action="store_true", help="跳过所有确认提示")
    return ap.parse_args()


class Args:
    """把全局 args 映射成各模块期望的字段（zcode 模块用 args.dry_run/args.yes/args.name/args.include/args.skip_probe）。"""
    def __init__(self, global_args):
        self.__dict__.update(global_args.__dict__)
        self.db = global_args.db if hasattr(global_args, "db") else None


def main():
    args = parse_args()
    if sys.platform != "darwin":
        C.die("本脚本仅支持 macOS。")

    print("=" * 68)
    print(" CommandCode → 多 Agent 一键配置（ZCode / Claude Desktop / Codex）")
    print(" 最低 GOAT 套餐；Claude 系模型仅 Pro+ 套餐可用（会被自动跳过并说明原因）")
    print("=" * 68)

    agents = ask_agents(args)
    keys = ask_keys(args, agents)
    C.log(f"\n计划配置：{'、'.join(AGENTS[a]['label'] for a in agents)}")
    C.log(f"Key 模式：{'共用（1 个 Key）' if len(set(keys.values())) == 1 else '分别配置'}")

    if args.dry_run and args.skip_probe:
        # 零成本快速路径：不校验上游（无网络写操作），直接进模块预览
        pass

    # Key 校验：按 Key 去重校验（同 Key 只校验一次），拿到 upstream/plan
    validated = {}
    for a in agents:
        k = keys[a]
        if k not in validated:
            upstream, plan_id, account = C.validate_key(k)
            plan = args.plan or C.detect_plan(plan_id)
            if plan == "go":
                C.die("当前套餐为 Go：本脚本最低要求 GOAT 套餐，不支持 Go。请升级订阅后再试。")
            if plan is None:
                C.warn("无法识别订阅套餐（订阅接口失败或无数据）。")
                if not args.yes:
                    if not sys.stdin.isatty() or input("仍要继续（以探测结果为准）? [y/N] ").strip().lower() not in ("y", "yes"):
                        C.die("已取消。也可用 --plan goat 强制按 GOAT 处理。")
            C.log(f"✓ Key 有效（账户：{account or '未知'}），订阅 planId={plan_id or '未知'} → 套餐档位：{plan or '未知'}")
            validated[k] = {"upstream": upstream, "plan": plan}

    # 共享探测：同 Key 的 codex/zcode 目标复用同一份收录结果
    shared_probe = {}

    def get_shared(key, upstream):
        if key not in shared_probe:
            shared_probe[key] = C.build_entries(upstream, key, args.include, args.skip_probe)
        return shared_probe[key]

    class ModArgs:
        pass

    results = {}
    for a in agents:
        info = validated[keys[a]]
        ma = ModArgs()
        for f in ("dry_run", "yes", "name", "include", "skip_probe", "model", "verify", "no_restart", "plan", "db"):
            setattr(ma, f, getattr(args, f, None))
        if a == "codex":
            entries, excluded, notes = get_shared(keys[a], info["upstream"])
            ok = codex.run(keys[a], info["upstream"], ma, shared_entries=(entries, excluded, notes))
        elif a == "zcode":
            entries, excluded, notes = get_shared(keys[a], info["upstream"])
            ok = zcode.run(keys[a], info["upstream"], ma, shared_entries=(entries, excluded, notes))
        else:
            ok = claude_desktop.run(keys[a], info["upstream"], ma)
        results[a] = ok

    failed = [AGENTS[a]["label"] for a, ok in results.items() if not ok]
    print()
    if failed:
        C.warn(f"以下目标未全部通过：{'、'.join(failed)}（详见上方输出）")
        sys.exit(3)
    C.log("== 全部完成 ✅ ==  目标：" + "、".join(AGENTS[a]["label"] for a in agents))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中断，未保存任何修改。")
        sys.exit(130)
