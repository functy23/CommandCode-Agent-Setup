<div align="center">

# 🔧 CommandCode Agent Setup

**一键把 CommandCode 订阅配置进 ZCode 与 Codex CLI —— 仅限 macOS。**

[![CommandCode-Agent-Setup](https://img.shields.io/badge/CommandCode-Agent-Setup-CCAS-orange.svg)](https://github.com/functy23/CommandCode-Agent-Setup)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Top Language](https://img.shields.io/github/languages/top/functy23/CommandCode-Agent-Setup?style=flat)](https://github.com/functy23/CommandCode-Agent-Setup)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg?logo=apple&logoColor=white)](https://github.com/functy23/CommandCode-Agent-Setup)

[![Stars](https://img.shields.io/github/stars/functy23/CommandCode-Agent-Setup?style=flat&logo=github)](https://github.com/functy23/CommandCode-Agent-Setup/stargazers)
[![Repo Size](https://img.shields.io/github/repo-size/functy23/CommandCode-Agent-Setup?style=flat&logo=github)](https://github.com/functy23/CommandCode-Agent-Setup)
[![Contributors](https://img.shields.io/github/contributors/functy23/CommandCode-Agent-Setup?color=ee8449&logo=githubsponsors)](https://github.com/functy23/CommandCode-Agent-Setup/graphs/contributors)

[Issues](https://github.com/functy23/CommandCode-Agent-Setup/issues) • [AGENTS.md](AGENTS.md)

[English](../README.md) | **简体中文**
</div>

---
## 概述

一键把 **CommandCode 订阅**配置进你的 AI Agent：**ZCode**、**Codex CLI**。仅限 **macOS**，最低 **GOAT 套餐**（不支持 Go）。

> 本仓库由 [`ZCode-CommandCode-Setup`](https://github.com/functy23/ZCode-CommandCode-Setup) 与 [`ccswitch-commandcode-setup`](https://github.com/functy23/ccswitch-commandcode-setup) 合并而成，那两个仓库已归档、不再维护——请一律改用本仓库。

## 快速开始（一键运行，推荐）

脚本类项目经典用法：`curl` 一个总脚本下来，它会自动拉取其余文件到临时目录运行，**结束后自动清理——无需下载整个仓库再手动删除**。

```bash
# 全交互：复选框选 Agent → 选凭证来源（网页登录 / 贴 Key / 本机凭证）
curl -fsSL https://raw.githubusercontent.com/functy23/CommandCode-Agent-Setup/main/bootstrap.sh | bash

# 带参数（参数原样透传给 setup.py）
curl -fsSL https://raw.githubusercontent.com/functy23/CommandCode-Agent-Setup/main/bootstrap.sh | bash -s -- --agents codex --login
```

说明：`bootstrap.sh` 只下载运行所需的最小文件集合（`setup.py` + `modules/`）到 `/tmp` 临时目录，运行结束自动删除；交互输入自动改走 `/dev/tty`，所以在 `curl | bash` 下照常可以输入 Key / 完成网页登录。`curl | bash` 模式下传参要用 `bash -s --` 分隔。

## 本地运行

仓库已在本地时，无需任何下载：

- **双击 `run.command`**（Finder 里双击会自动打开终端运行）；或
- `python3 setup.py`

## 交互流程

1. **选择 Agent**（复选框，↑↓ 移动 + 空格勾选，`a` 全选/反选，回车确认）：

   ```
   ◉ ZCode            写入 ~/.zcode/v2/config.json，模型选择器直接可见
   ◉ Codex CLI        经 CC Switch 代理（responses→chat 转换），含思考档位标注
   ```

2. **选择凭证来源**（单选）：
   - **网页登录** —— 打开 CommandCode Studio，登录后自动把 Key 回填到脚本（并写入 `~/.commandcode/auth.json`）
   - **手动输入** —— 粘贴 `user_` 开头的 API Key（多个 Agent 时可再选共用 / 分别配置）
   - **本机已有凭证** —— 读取 `~/.commandcode/auth.json`、`~/.pi/agent/auth.json`、`~/.omp/agent/auth.json`

3. 脚本校验 Key、识别套餐（最低 GOAT）、拉取公开模型目录，然后按选择写入。

## 命令行参数（可完全跳过交互）

| 参数 | 说明 |
|---|---|
| `--agents zcode,codex`（或 `all`） | 目标 Agent，逗号分隔；缺省弹复选框 |
| `--login` | 网页登录：打开 CommandCode Studio，登录后自动回填 Key |
| `--auth-file` | 使用本机已有凭证（`~/.commandcode/auth.json` 等） |
| `--key-mode shared\|separate` | 手动输入时的 Key 模式；缺省弹单选框 |
| `-k, --key` | CommandCode API Key（共用模式直接使用；也可用环境变量 `COMMANDCODE_API_KEY`） |
| `--plan goat\|pro\|provider` | 跳过订阅自动识别，强制按该套餐档位（仅作闸门用） |
| `-m, --model SLUG` | Codex 默认模型（默认 `deepseek/deepseek-v4-flash`） |
| `--name NAME` | 提供商名称（默认 `CommandCode`） |
| `--include SLUG` | 额外强制收录的模型 slug，可重复 |
| `--db PATH` | 指定 CC Switch 数据库路径（演练用，不触碰真实库、不重启应用） |
| `--dry-run` | 只预览模型目录与写入内容 |
| `--no-restart` | 写库后不重启 CC Switch（需手动重启生效） |
| `--verify` | 完成后跑冒烟测试（Codex：PONG 端到端） |
| `-y, --yes` | 跳过所有确认提示 |

非交互示例：

```bash
python3 setup.py --agents all --login --yes --verify
python3 setup.py --agents all --key-mode shared --key user_xxx --yes --verify
python3 setup.py --agents codex --auth-file --yes
```

`separate` 模式下 Key 也可以用环境变量按 Agent 提供：`ZCODE_COMMANDCODE_KEY` / `CODEX_COMMANDCODE_KEY`。

## 两个目标分别做什么

| Agent | 写入位置 | 模型列表 | 备注 |
|---|---|---|---|
| **ZCode** | `~/.zcode/v2/config.json`（`openai-compatible` provider） | 公开目录（剔 Claude），内嵌输出/推理档位规则 | 写前备份；改完需完全重启 ZCode |
| **Codex CLI** | CC Switch DB（`codex` 行）+ 代理接管 | 公开目录（剔 Claude），思考档位按权威表 | `~/.codex/config.toml` 由 CC Switch 接管指向本机代理（15721），responses→chat 自动转换 |

> **关键机制**：CC Switch 会在接管/重启时**从数据库重新生成** `~/.codex/cc-switch-model-catalog.json`，任何对磁盘 catalog 的手工修改都会丢——必须改数据库。本脚本直接写数据库，因此天然不会被覆盖。

## 重要说明

由于上游模型更新频繁，可能会出现模型失效或被下架的情况，导致无法使用。**重跑本脚本即可刷新目录**。Claude 系模型无法经 chat/completions 使用，目录里会自动跳过。

## 模型目录与元数据

- 与 [dsh-commandcode-provider](https://github.com/Victor-770/dsh-commandcode-provider) 相同：`GET https://api.commandcode.ai/provider/v1/models`（公开，不带 Key；失败再带 Key 重试）。**不再**对每个模型发 1-token 探测请求。
- Claude 系（`claude*`）一律剔除（只能走 Anthropic Messages 端点）。
- 思考档位用内嵌 `KNOWN_EFFORTS` 权威表，表外模型统一 `low/medium/high`、默认最高档；图像输入由 `KNOWN_IMAGE_MODELS` 决定。

## 网页登录

协议对齐 Command Code Studio 的 CLI 回调（与 opencode-commandcode / 旧版 dsh-commandcode-provider 同源）：

1. 本机 `127.0.0.1:5959+` 起临时 HTTP 服务
2. 打开 `https://commandcode.ai/studio/auth/cli?callback=…&state=…`
3. Studio 登录后把 `{apiKey, userId, userName, keyName, state}` POST 回 `/callback`
4. 成功后写入 `~/.commandcode/auth.json`，下次可直接选「本机已有凭证」

浏览器未自动打开时，终端会打印完整 URL。最多等待 12 分钟，Ctrl-C 取消。

## 备份与回滚

每次实际写入前，脚本自动备份（时间戳后缀 `.bak-YYYYmmdd-HHMMSS`）：

- `~/.cc-switch/cc-switch.db`（选中 CC Switch 目标时）
- `~/.codex/config.toml`、`~/.codex/auth.json`、`~/.codex/cc-switch-model-catalog.json`（选中 Codex 时）
- `~/.zcode/v2/config.json`（选中 ZCode 时）

回滚：先退出 CC Switch / ZCode，再用对应 `.bak` 文件覆盖回去。

## 项目文件

| 文件 | 用途 |
|---|---|
| `bootstrap.sh` | 总脚本（curl \| bash 入口）：下载最小文件集到临时目录、运行、自动清理 |
| `setup.py` | 主入口：Agent 复选框 → 凭证来源 → 分发到各目标模块 |
| `modules/common.py` | 公共设施：HTTP（防 Cloudflare 1010）、Key 校验、套餐闸门、公开模型目录、元数据权威表 |
| `modules/login.py` | 网页登录（Studio CLI 回调）+ 本机 auth.json 读写 |
| `modules/ccswitch.py` | CC Switch 共享设施：进程控制、数据库写入、codex 核验、PONG 冒烟 |
| `modules/zcode.py` | ZCode 目标：写 `~/.zcode/v2/config.json` |
| `modules/codex.py` | Codex 目标：写 CC Switch DB codex 行 + 代理接管 |
| `run.command` | macOS 双击启动器 |

（AI agent 接手开发请读 [AGENTS.md](../AGENTS.md)。）
