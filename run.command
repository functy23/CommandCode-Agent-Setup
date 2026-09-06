#!/bin/bash
# 双击运行：在终端中启动 CommandCode 多 Agent 配置脚本
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3：请先安装 Xcode Command Line Tools（xcode-select --install）"
  read -n 1 -s -r -p "按任意键关闭..."
  exit 1
fi
exec python3 setup.py "$@"
