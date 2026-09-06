# CommandCode-Agent-Setup

一键把 **CommandCode 订阅**配置进你的 AI Agent（三合一）：**ZCode**、**Claude Desktop**、**Codex CLI**。仅限 **macOS**，最低 **GOAT 套餐**（不支持 Go）。

> 本仓库由 [`ZCode-CommandCode-Setup`](https://github.com/functy23/ZCode-CommandCode-Setup) 与 [`ccswitch-commandcode-setup`](https://github.com/functy23/ccswitch-commandcode-setup) 合并而成，那两个仓库已归档、不再维护——请一律改用本仓库。

## 快速开始（一键运行，推荐）

脚本类项目经典用法：`curl` 一个总脚本下来，它会自动拉取其余文件到临时目录运行，**结束后自动清理——无需下载整个仓库再手动删除**。

```bash
# 全交互：复选框选 Agent → 选 Key 模式 → 输入 Key
curl -fsSL https://raw.githubusercontent.com/functy23/CommandCode-Agent-Setup/main/bootstrap.sh | bash

# 带参数（参数原样透传给 setup.py）
curl -fsSL https://raw.githubusercontent.com/functy23/CommandCode-Agent-Setup/main/bootstrap.sh | bash -s -- --agents codex --key-mode shared
```

说明：`bootstrap.sh` 只下载运行所需的最小文件集合（`setup.py` + `modules/`）到 `/tmp` 临时目录，运行结束自动删除；交互输入自动改走 `/dev/tty`，所以在 `curl | bash` 下照常可以输入 Key。`curl | bash` 模式下传参要用 `bash -s --` 分隔。

## 本地运行

仓库已在本地时，无需任何下载：

- **双击 `run.command`**（Finder 里双击会自动打开终端运行）；或
- `python3 setup.py`

## 交互流程

1. **选择 Agent**（复选框，↑↓ 移动 + 空格勾选，`a` 全选/反选，回车确认）：

   ```
   ◉ ZCode            写入 ~/.zcode/v2/config.json，模型选择器直接可见
   ◉ Claude Desktop   CC Switch 直连模式（Anthropic Messages 网关；GOAT 不含 Claude，Pro+ 可用）
   ◉ Codex CLI        经 CC Switch 代理（responses→chat 转换），含思考档位标注
   ```

2. **选择 Key 模式**（单选）：
   - **共用 Key** —— 所有选中的 Agent 用同一个 Key（只输一次）
   - **分别配置** —— 按顺序为每个选中的 Agent 单独输入 Key

3. 脚本校验 Key、识别套餐（最低 GOAT）、探测可用模型，然后按选择写入。

## 命令行参数（可完全跳过交互）

| 参数 | 说明 |
|---|---|
| `--agents zcode,claude-desktop,codex`（或 `all`） | 目标 Agent，逗号分隔；缺省弹复选框 |
| `--key-mode shared\|separate` | Key 模式；缺省弹单选框 |
| `-k, --key` | CommandCode API Key（共用模式直接使用；也可用环境变量 `COMMANDCODE_API_KEY`） |
| `--plan goat\|pro\|provider` | 跳过订阅自动识别，强制按该套餐档位（仅作闸门用） |
| `-m, --model SLUG` | Codex 默认模型（默认 `deepseek/deepseek-v4-flash`） |
| `--name NAME` | 提供商名称（默认 `CommandCode`） |
| `--include SLUG` | 额外强制收录的模型 slug，可重复 |
| `--skip-probe` | 跳过探测，直接收录目录里除 Claude 外的全部模型 |
| `--cd-mode proxy\|direct` | Claude Desktop 接入模式：proxy（默认，模型映射进配置）/ direct（直连，GOAT 会报 403） |
| `--cd-model ROLE=SLUG` | proxy 模式角色映射覆盖（角色：opus/sonnet/haiku/fable，可重复） |
| `--db PATH` | 指定 CC Switch 数据库路径（演练用，不触碰真实库、不重启应用） |
| `--dry-run` | 只预览模型目录与写入内容 |
| `--no-restart` | 写库后不重启 CC Switch（需手动重启生效） |
| `--verify` | 完成后跑冒烟测试（Codex：PONG 端到端） |
| `-y, --yes` | 跳过所有确认提示 |

非交互示例：

```bash
python3 setup.py --agents all --key-mode shared --key user_xxx --yes --verify
python3 setup.py --agents codex,claude-desktop --key-mode separate --skip-probe --yes
```

`separate` 模式下 Key 也可以用环境变量按 Agent 提供：`ZCODE_COMMANDCODE_KEY` / `CLAUDE_DESKTOP_COMMANDCODE_KEY` / `CODEX_COMMANDCODE_KEY`。

## 三个目标分别做什么

| Agent | 写入位置 | 模型列表 | 备注 |
|---|---|---|---|
| **ZCode** | `~/.zcode/v2/config.json`（`openai-compatible` provider） | 探测收录，内嵌输出/推理档位规则 | 写前备份；改完需完全重启 ZCode |
| **Claude Desktop** | CC Switch DB（`claude-desktop` 行，**proxy 本地路由模式**） | **配置文件里的映射表决定**（四档角色 → CommandCode 模型） | CC Switch 接管时自动写 `Claude-3p` 网关配置；Claude Desktop 需切到第三方（3p）部署模式 |
| **Codex CLI** | CC Switch DB（`codex` 行）+ 代理接管 | 探测收录，思考档位按权威表 | `~/.codex/config.toml` 由 CC Switch 接管指向本机代理（15721），responses→chat 自动转换 |

## Claude Desktop 的模型映射（proxy 模式，默认）

与 Codex 同样的思路：**模型清单不再由 Claude Desktop 自动抓取，而是写进配置文件**。脚本把四个角色档映射到四个不同的 CommandCode 模型（写入 CC Switch DB 的 `claudeDesktopModelRoutes` + `modelCatalog`），菜单看起来就像原生模型列表：

| Claude Desktop 菜单项 | 实际调用 | 定位 |
|---|---|---|
| GPT-5.6 Sol | `gpt-5.6-sol` | Opus 档 · 最强综合推理 |
| DeepSeek V4 Flash | `deepseek/deepseek-v4-flash` | Sonnet 档 · 均衡主力（1M 上下文） |
| GLM-5.3 Flash | `z-ai/glm-5.3-flash` | Haiku 档 · 快速响应 |
| Kimi K3 | `moonshotai/Kimi-K3` | Fable 档 · 创意/长文 |

- 请求链路：Claude Desktop → 本机代理 `127.0.0.1:15721/claude-desktop`（Anthropic→OpenAI 转换）→ CommandCode
- **模型菜单只显示映射项，官方模型清单彻底消失**——官方模型启动探测 403 MODEL_NOT_IN_PLAN 的报错随之消除；GOAT 套餐即可用
- 默认映射可用 `--cd-model` 覆盖（角色：opus/sonnet/haiku/fable），例如把 Opus 档换成 GLM-5.3：
  `python3 setup.py --agents claude-desktop --cd-model opus=zai-org/GLM-5.3`
- 映射目标必须是探测收录的模型；`supports1m=true` 使 Claude Desktop 按 1M 上下文对待

**一次性手动步骤**：CC Switch 的 3P profile 只在 UI 切换提供商时写出（官方设计，无 CLI 触发）。脚本写完库后会检测并在需要时提示：打开 CC Switch → Claude Desktop 页 → 点一下 CommandCode 卡片（重新切换）即可生效。

> **关键机制**：CC Switch 会在接管/重启时**从数据库重新生成** `~/.codex/cc-switch-model-catalog.json`，任何对磁盘 catalog 的手工修改都会丢——必须改数据库。本脚本直接写数据库，因此天然不会被覆盖。

## 重要说明

由于上游模型更新频繁，可能会出现模型失效或被下架的情况，导致无法使用。如果出现 Claude 模型无法使用的情况，暂时是没法修复的，因为作者没有 Claude 的 API。

- **Claude Desktop 默认走 proxy 映射模式**：模型菜单来自配置文件映射，与订阅套餐里的 Claude 无关，GOAT 可正常使用（实际调用的是映射到的 CommandCode 模型）。旧的直连模式（`--cd-mode direct`）仅适合含 Claude 的套餐（Pro+）：GOAT 下 Claude Desktop 启动会用官方模型探测网关并报「Couldn't sign in to 网关 / Gateway rejected the configured credential (HTTP 403)」——那是 `MODEL_NOT_IN_PLAN`，不是 Key 错误。
- 探测式模型列表会自动跟随上游增删：模型失效或被下架时**重跑本脚本刷新**即可。

## 模型探测与元数据

- 拉取上游全量目录后，对每个模型发送 `max_tokens=1` 的最小请求（8 并发，每模型 1~16 token 额度）：
  `200` 收录；`403 MODEL_NOT_IN_PLAN` 剔除；`429/503` 视为临时问题保留；`400` 剔除（`max_tokens>=16` 要求自动重试）；Claude 系一律剔除（只能走 Anthropic Messages 端点）。
- 思考档位用内嵌 `KNOWN_EFFORTS` 权威表（来自 `dsh-commandcode-provider/src/adapter.ts`），表外模型统一 `low/medium/high`、默认最高档；图像输入由 `KNOWN_IMAGE_MODELS` 决定。

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
| `setup.py` | 主入口：Agent 复选框 → Key 模式单选 → 分发到各目标模块 |
| `modules/common.py` | 公共设施：HTTP（防 Cloudflare 1010）、Key 校验、套餐闸门、模型探测、元数据权威表 |
| `modules/ccswitch.py` | CC Switch 共享设施：进程控制、数据库写入、codex/claude-desktop 核验、PONG 冒烟 |
| `modules/zcode.py` | ZCode 目标：写 `~/.zcode/v2/config.json` |
| `modules/codex.py` | Codex 目标：写 CC Switch DB codex 行 + 代理接管 |
| `modules/claude_desktop.py` | Claude Desktop 目标：写 CC Switch DB claude-desktop 行（直连模式） |
| `run.command` | macOS 双击启动器 |

（AI agent 接手开发请读 [AGENTS.md](AGENTS.md)。）
