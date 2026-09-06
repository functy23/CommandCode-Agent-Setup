#!/bin/bash
# ============================================================================
# CommandCode-Agent-Setup 一键引导脚本（总脚本）
#
# 用法（推荐 curl | bash，零下载残留）：
#
#   curl -fsSL https://raw.githubusercontent.com/functy23/CommandCode-Agent-Setup/main/bootstrap.sh | bash
#   curl -fsSL .../bootstrap.sh | bash -s -- --agents codex --key user_xxx --yes
#
#   ./bootstrap.sh [setup参数]                                # 本地已下载仓库
#   COMMANDCODE_AGENT_SETUP_BASE=<RAW_BASE> ./bootstrap.sh    # 自定义脚本来源
#
# 行为：只下载运行所需的最小文件集合（setup.py + modules/）到临时目录，
# 运行结束后自动清理 —— 无需克隆/下载整个仓库。
# ============================================================================
set -euo pipefail

BASE_URL="${COMMANDCODE_AGENT_SETUP_BASE:-https://raw.githubusercontent.com/functy23/CommandCode-Agent-Setup/main}"

# ---- 解析参数：--base <url> / 直接给 URL；其余透传给 setup.py ----
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE_URL="$2"; shift 2 ;;
    http://*|https://*) BASE_URL="$1"; shift ;;
    *) args+=("$1"); shift ;;
  esac
done
BASE_URL="${BASE_URL%/}"

die() { echo "❌ $1" >&2; exit 1; }

[ "$(uname)" = "Darwin" ] || die "本脚本仅支持 macOS。"
command -v python3 >/dev/null 2>&1 || die "未找到 python3：请先安装 Xcode Command Line Tools（xcode-select --install）"
command -v curl >/dev/null 2>&1 || die "未找到 curl。"

FILES="setup.py modules/__init__.py modules/common.py modules/ccswitch.py modules/zcode.py modules/codex.py modules/claude_desktop.py"

# ---- 下载到临时目录（保持 modules/ 目录结构）----
TMP="$(mktemp -d /tmp/commandcode-agent-setup.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

echo "→ 从 ${BASE_URL} 下载脚本 …"
for f in $FILES; do
  curl -fsSL "${BASE_URL}/${f}" -o "${TMP}/${f}" \
    || die "下载 ${f} 失败：请检查 BASE_URL 是否正确（404 多为地址/分支写错）。"
done
[ "$(wc -c < "${TMP}/setup.py")" -gt 1000 ] || die "下载内容异常（文件过小），请检查 BASE_URL。"

echo "→ 启动配置脚本（结束后本临时目录会自动删除：${TMP}）…"
# curl|bash 时 stdin 是管道，交互输入改走 /dev/tty；
# 无控制终端（如 CI/沙盒）时回退 stdin（交互输入不可用，请用环境变量/参数提供 Key）
if [ -r /dev/tty ] && { true </dev/tty; } 2>/dev/null; then
  python3 "${TMP}/setup.py" ${args+"${args[@]}"} < /dev/tty
else
  python3 "${TMP}/setup.py" ${args+"${args[@]}"}
fi
