# AGENTS.md — CommandCode-Agent-Setup（AI 接手说明）

> 本文件面向 AI agent（ZCode / Claude Code / Codex / 其他），是项目的完整事实库与开发规程。
> 人类用户请读 [README.md](README.md)。
> 标注【实测】的事实分别于 **2026-08-29**（codex 链路）、**2026-09-06**（claude-desktop 链路与本仓库整合）在用户本机（macOS arm64，HOME=/Users/functy）验证过；
> 修改代码前先读完本文，不要凭记忆改动已验证的行为。怀疑过期时按 §8 重新验证。

---

## 1. 项目定位

一键把 **CommandCode 订阅**配置进三个 AI Agent（三合一）：

| 目标 | 接入方式 | 数据落点 |
|---|---|---|
| **ZCode** | 直写配置（`kind=openai-compatible`） | `~/.zcode/v2/config.json` |
| **Claude Desktop** | CC Switch **直连模式**（direct） | `~/.cc-switch/cc-switch.db` 的 `claude-desktop` 行 → CC Switch 写 `Claude-3p` 网关配置 |
| **Codex CLI** | CC Switch **代理模式**（responses→chat 转换） | `~/.cc-switch/cc-switch.db` 的 `codex` 行 + 代理接管 15721 |

- 入口 `setup.py`：终端复选框（Inquirer 风格：↑↓ + 空格 + 回车，`a` 全选/反选）选 Agent → 单选 Key 模式（共用/分别配置）→ 分发到模块。
- 仅限 **macOS**，最低 **GOAT 套餐**（Go 直接中止）。仅依赖 Python 3 标准库。
- 本仓库由旧仓库 [`ZCode-CommandCode-Setup`](https://github.com/functy23/ZCode-CommandCode-Setup)（ZCode 目标）与 [`ccswitch-commandcode-setup`](https://github.com/functy23/ccswitch-commandcode-setup)（Codex + Claude Desktop 目标）合并而来，两个旧仓库已归档、README 已标注指向本仓库。
- **不做**的事：不支持 Claude 模型经 chat/completions（只能走 Anthropic 路由）；GOAT 套餐 Claude Desktop 打开会报 403 MODEL_NOT_IN_PLAN（非凭据问题，Pro+ 才含 Claude；配置本身正确，升级套餐即用）。

线上仓库：<https://github.com/functy23/CommandCode-Agent-Setup>（public，分支 main）

## 2. 文件清单

| 文件 | 职责 |
|---|---|
| `setup.py` | 主入口：Agent 注册表、终端复选框/单选（raw-mode 自绘）、Key 模式、按 Key 去重校验、共享探测分发 |
| `modules/common.py` | 公共设施：UA/HTTP（防 Cloudflare 1010）、Key 校验、套餐闸门、1-token 探测、目录构建、`KNOWN_EFFORTS`/`KNOWN_IMAGE_MODELS` 元数据表 |
| `modules/ccswitch.py` | CC Switch 共享：进程控制（osascript→pkill -x）、备份、幂等写库、codex/claude-desktop 核验、PONG 冒烟 |
| `modules/zcode.py` | ZCode 目标：官网上下文抓取 + ZCode 元数据规则表 + 写 `~/.zcode/v2/config.json` |
| `modules/codex.py` | Codex 目标：预览 + 写 codex 行 + 接管核验 + 可选 PONG |
| `modules/claude_desktop.py` | Claude Desktop 目标：写 claude-desktop 行（direct），无需探测 |
| `bootstrap.sh` | curl\|bash 总引导：下载 setup.py + modules/（保持目录结构）到 mktemp → 运行 → trap 清理 |
| `run.command` | macOS 双击启动器 |

## 3. 交互设计（setup.py）

- `ask_agents()`：CLI `--agents zcode,claude-desktop,codex|all` 优先；否则 `checkbox()`。复选框自绘实现要点：raw mode 读键（`termios/tty`）、每帧 `\x1b[N A` 回退重绘、空格 toggle、`a` 全选/反选、空选回车给提示不放行。
- `ask_keys()`：`--key-mode shared|separate`；shared 用 `--key` 或 `COMMANDCODE_API_KEY` 或提示输入一次；separate 按显示顺序（ZCode → Claude Desktop → Codex）逐个 `getpass`。
- **Key 校验按 Key 值去重**（同 Key 只调一次 `/models`+`/subscriptions`+`/whoami`）；`--skip-probe` 时探测也按 Key 去重共享（`shared_probe` 缓存），三目标只探测一次。
- Claude Desktop 模块**不消费探测结果**（模型由 Claude Desktop 端选择），只写 env 两键。

## 4. 端到端链路【实测】

### 4.1 ZCode【实测 2026-08-29】

`~/.zcode/v2/config.json` 的 `provider` 字典加一条 `kind=openai-compatible`、`baseURL=https://api.commandcode.ai/provider/v1` 的 provider；ZCode 请求时自动追加 `/chat/completions`。写前备份、回读校验。ZCode 运行中也可写，但改完必须 ⌘Q 完全重启；**之后不要在 ZCode 设置 UI 里改 provider**（UI 会用内存旧配置整体回写覆盖）。

### 4.2 Codex【实测 2026-08-29】

```
Codex CLI（vendor 二进制，不在 PATH；wire_api=responses）
  → POST http://127.0.0.1:15721/v1/responses
  → CC Switch（meta.apiFormat=openai_chat 时做 responses→chat 转换）
  → POST https://api.commandcode.ai/provider/v1/chat/completions
```

- Codex 二进制用 glob 定位（版本会升级，勿硬编码）：`~/Library/Application Support/deepseek-harness-desktop/node-runtime/packages/node_modules/.pnpm/@openai+codex@*/node_modules/@openai/codex/vendor/*/bin/codex`
- `~/.codex/config.toml` 由 CC Switch 接管改写（base_url→代理、token→PROXY_MANAGED、`model_catalog_json`）；`auth.json` 写当前接管提供商的 key
- **【关键】CC Switch 重启/接管时从 DB 重新生成磁盘 catalog** —— 改磁盘文件无效，必须写 DB
- **【实测 2026-09-06】`~/.codex/auth.json` 的 key 可能是其他平台的**（xpl_ 前缀：`/models` 200 但 `/chat/completions` 401）。真 CommandCode key 以 CC Switch DB 为准：
  `sqlite3 ~/.cc-switch/cc-switch.db "SELECT settings_config FROM providers WHERE app_type='codex' AND name='CommandCode'"` → `auth.OPENAI_API_KEY`（`user_` 前缀）

### 4.3 Claude Desktop【实测 2026-09-06】

两种模式（`--cd-mode`，**默认 proxy**）：

**proxy 本地路由模式（默认，推荐）**——模型清单写进配置文件，等同 Codex 思路：

```
Claude Desktop（deploymentMode=3p，模型菜单来自 profile.inferenceModels）
  → POST http://127.0.0.1:15721/claude-desktop/v1/messages（bearer，token=CC Switch 生成的 ccs-*）
  → map_proxy_request_model：claude-* route_id 映射为真实上游模型（角色回落 + [1m] 剥离）
  → apiFormat=openai_chat：Anthropic→OpenAI 转换
  → POST https://api.commandcode.ai/provider/v1/chat/completions
```

- DB 行 `meta`：`{"claudeDesktopMode":"proxy","apiFormat":"openai_chat","claudeDesktopModelRoutes":{route_id:{model,labelOverride?,supports1m?}}}`
  - `route_id` 必须 claude-* 或 anthropic/claude-*（CC Switch `DEFAULT_PROXY_ROUTES`：claude-sonnet-5/claude-opus-5/claude-haiku-4-5/claude-fable-5）；proxy 模式 `model` 可为任意上游模型（direct 模式禁止映射）
  - `settings_config` = `env`（同 direct）+ `modelCatalog`（映射后四档，供用量统计）
  - **默认角色映射（四档 → 四个不同 GOAT 模型，菜单像原生列表）**：opus→`gpt-5.6-sol`、sonnet→`deepseek/deepseek-v4-flash`、haiku→`z-ai/glm-5.3-flash`、fable→`moonshotai/Kimi-K3`；`labelOverride` 直接用底层模型名（GPT-5.6 Sol / DeepSeek V4 Flash / GLM-5.3 Flash / Kimi K3）。`--cd-model 角色=slug` 可覆盖，映射目标必须在探测收录内
- CC Switch 接管后写 3P profile：`inferenceGatewayBaseUrl=http://127.0.0.1:15721/claude-desktop`、`inferenceGatewayApiKey=ccs-*`（存 DB settings 表）、`inferenceModels`=映射列表
- `/claude-desktop/v1/models` 只返回映射项 → **模型菜单由配置决定，官方模型清单消失**，官方模型启动探测 403 报错消除；GOAT 可用
- 【实测端到端】`claude-opus-5` 请求 → 上游 `deepseek/deepseek-v4-flash`（chat/completions）→ 正常返回

**direct 直连模式（`--cd-mode direct`，适合含 Claude 的套餐 Pro+）**：

```
Claude Desktop（deploymentMode=3p）
  → 读 ~/Library/Application Support/Claude-3p/configLibrary/<appliedId>.json
  → POST {inferenceGatewayBaseUrl}/v1/messages（bearer）
  → https://api.commandcode.ai/provider/v1/messages
```

- direct 模式映射：DB 行 `env.ANTHROPIC_BASE_URL` → `inferenceGatewayBaseUrl`；`env.ANTHROPIC_AUTH_TOKEN` → `inferenceGatewayApiKey`；外加固定字段 `inferenceProvider=gateway`、`inferenceGatewayAuthScheme=bearer`、`coworkEgressAllowedHosts=["*"]`、`disableDeploymentModeChooser=true`
- **baseURL 必须不含端点路径**（`https://api.commandcode.ai/provider`，网关自己拼 `/v1/messages`）；上游 `/v1/messages` 接受 Bearer 与 x-api-key（用 OSS 模型名探测返回 400 model-not-supported 而非 401，即鉴权通过）
- GOAT 下 Claude 全系 403 `MODEL_NOT_IN_PLAN`（haiku/sonnet→Pro+，opus/fable→Provider+）。用户可见症状：Claude Desktop 启动提示「Couldn't sign in to 网关 … Gateway rejected the configured credential (HTTP 403) … probedModel: claude-haiku-4-5-20251001」——**这不是 Key 错误**；proxy 模式可消除

**【关键坑】3P profile 只在 UI 切换提供商时写出**：CC Switch 源码（`proxy_config` 表 CHECK 约束 + `supports_local_proxy()` 不含 claude-desktop）决定 claude-desktop **不参与代理启动恢复**，也无 CLI/deeplink 触发 switch（deeplink app 白名单不含 claude-desktop；is_current 翻转重启无效、删 profile 重启也不重建）。脚本写完 DB 后 profile 可能仍是旧内容——核验检测到不一致时给出一次性手动步骤：「打开 CC Switch → Claude Desktop 页 → 点一下 CommandCode 卡片（重新切换）」；官方文案同义「重新切换当前供应商可修复」。`claude_desktop_config.json` 的 `deploymentMode` 必须为 `"3p"`（用户在 Claude Desktop 设置里切）

## 5. CC Switch 数据库写入规范（最关键的坑）

- 库 `~/.cc-switch/cc-switch.db`（SQLite）；进程名 `cc-switch`（必须 `pkill -x`，`pkill -f` 会误杀自身 shell）
- 涉及三张表：
  - `providers`：PK `(id, app_type)`。codex 行 id=`f4a0013a-37aa-41f5-828b-b8fe50aa16b9`，claude-desktop 行 id=`ca83eb27-8b15-4b8e-a802-0ef3ba74c9ca`（更新路径保留原 id）；写入用 `BEGIN IMMEDIATE` 单事务
  - `provider_endpoints`：codex=`…/provider/v1`，claude-desktop=`…/provider`
  - `proxy_config`：仅 codex 需 `proxy_enabled=1, enabled=1`；claude-desktop（direct）不动
- `settings_config`：
  - codex 行：`auth.OPENAI_API_KEY` + `config`（TOML 片段，存**上游直连**地址，接管时 CC Switch 自动换代理并注入）+ `modelCatalog.models[]`（`{model, displayName, contextWindow, reasoningLevels[], defaultReasoningLevel, inputModalities}`）
  - claude-desktop 行：`env.ANTHROPIC_BASE_URL` + `env.ANTHROPIC_AUTH_TOKEN`
- `meta`（逐字使用）：
  - codex：`{"commonConfigEnabled":false,"endpointAutoSelect":true,"apiFormat":"openai_chat","codexChatReasoning":{...}}`（openai_chat 是 responses→chat 转换前提；写成 openai_responses 会透传 /responses → 404）
  - claude-desktop：`{"claudeDesktopMode":"direct","apiFormat":"anthropic"}`
- `is_current` 同 app_type 内唯一；写库流程：备份 → 退应用（osascript→pkill -TERM -x，最多 15s，退不掉中止）→ 写库 → 启动 → 等 15721（40s）→ 核验
- 幂等：同 app_type 同名 UPDATE（保留 id/created_at），否则 INSERT（uuid4）

## 6. 探测式模型列表（设计决策，勿回退成内嵌清单）

上游增删频繁，探测式自动跟随（2026-09-06 目录 67 个、收录 44；此前 62→43 时 M2.7 上游故障被自动剔除）。

- `GET /provider/v1/models` → `{data:[{id, name, context_length, …}]}`（id 带厂商前缀）
- 每模型 POST `chat/completions`：`{"model", "messages":[hi], "max_tokens":1}`，8 并发、0.2s 限速
- 判定：`200`→OK 收录；`403 MODEL_NOT_IN_PLAN`→剔除；`429/503`→退避 3 次后 TRANSIENT **保留**；`400`→含 `">= 16"` 自动升级 max_tokens 重试，否则剔除；其他→ERROR 剔除；`claude-*` 一律剔除（只能走 Anthropic 路由）
- 成本每模型 1~16 token；`--skip-probe` 跳过（收录全部非 Claude 模型）
- 套餐闸门：`/alpha/billing/subscriptions` 的 `data.planId`；goat/pro/provider 放行，**go 中止**；识别失败交互确认或 `--yes` 继续；`--plan` 可强制

## 7. 元数据权威表（内嵌）

- `KNOWN_EFFORTS`（adapter.ts，command-code@1.37.0 同步）：deepseek [high,max]、GLM-5.2 [high,max]、GLM-5.3/glm-5.3-flash [low,high,max]、Qwen3.8 [low,medium,xhigh]、gpt-5.6 [low..max]、grok-4.6 [low,medium,high,xhigh]…；**默认档取最高档**。
- 表外统一 `[low,medium,high]` + 默认 high（上游网关对 `reasoning_effort` 通用接受，实测仅 deepseek 拒绝 `none`）。
- `KNOWN_IMAGE_MODELS` 决定 inputModalities 含 image；易漏三个：`moonshotai/Kimi-K2.5`、`moonshotai/Kimi-K2.6`、`xai/grok-4.5`。
- ZCode 目标另有自己的规则表（`OUTPUT_RULES`/`REASONING_RULES`/`INPUT_RULES`，正则首条命中）与官网 SSR 页上下文抓取——这是旧仓库原逻辑，与 CC Switch 目录的口径**有意不同**（ZCode 元数据 schema 不同），勿合并。
- CC Switch 重新生成磁盘 catalog 时自动补全其余字段（truncation_policy 等），脚本不管。

### 7.1 【实测 2026-09-06】Codex /model UI 的档位显示策略（勿误判为数据缺失）

用户曾报告「GLM-5.3 Flash 在 Codex 中思考等级没有最高选项，但 ZCode/DSH 有 max」。实测结论：**max 档一直存在且生效，只是 Codex TUI 从不显示 max 原名**。Codex 0.147 `/model` 界面的显示规则：

- 任何模型的 `max` 档一律显示为 **「More reasoning…」**，副标题 `Max consumes usage limits faster`（OpenAI 把 max 定位成"隐藏彩蛋档"的 UI 设计，与 catalog 数据无关）；
- `xhigh` 显示为 **「Extra high」**；
- 当前选中的档位后缀 `(current)`。

实际抓屏（100 列 pty）：

```
Select Reasoning Level for z-ai/glm-5.3-flash        ← catalog [low,high,max]
  1. Low                        Fast responses with lighter reasoning
  2. High                       Greater reasoning depth for complex problems
› 3. More reasoning… (current)  Max consumes usage limits faster   ← 这就是 max

Select Reasoning Level for gpt-5.6-sol               ← catalog [low..max] 5 档
  1. Low / 2. Medium / 3. High
  4. Extra high                  Extra high reasoning depth…
› 5. More reasoning… (current)  Max consumes usage limits faster   ← max
```

与 ZCode/DSH 的差异本质：ZCode/DSH 的 UI 直接显示 variants 字面量（如 off/high/max），Codex TUI 做了展示层改名。数据链路（CC Switch DB → `~/.codex/cc-switch-model-catalog.json` → codex）与实际请求（`model_reasoning_effort = "max"` → 上游 200，`codex exec` 输出 `reasoning effort: max`）都已实测正确，**不要因此去改 catalog 档位数据**。

## 8. 测试规程（改代码后必做，按成本从低到高）

```bash
cd ~/Desktop/CommandCode-Agent-Setup

# 0. 语法
python3 -m py_compile setup.py modules/*.py && bash -n bootstrap.sh && bash -n run.command

# 1. 零成本机械测试（不探测不写库；三种 agents 组合都过一遍更稳）
COMMANDCODE_API_KEY=<key> python3 setup.py --agents all --skip-probe --dry-run
COMMANDCODE_API_KEY=<key> python3 setup.py --agents codex --skip-probe --dry-run

# 2. 真探测预览（每模型 1~16 token，约 1~3 分钟；不写库）
COMMANDCODE_API_KEY=<key> python3 setup.py --agents all --dry-run

# 3. 写库演练（--db 副本库；ZCode 仍写真实 config.json——它不走 CC Switch，注意）
sqlite3 ~/.cc-switch/cc-switch.db ".backup '/tmp/cc-tri.db'"
COMMANDCODE_API_KEY=<key> python3 setup.py --agents all --skip-probe --yes --db /tmp/cc-tri.db

# 4. 实机全流程（重启 CC Switch + 写真实库两行 + ZCode 配置）
COMMANDCODE_API_KEY=<key> python3 setup.py --agents all --skip-probe --yes --verify
```

- **真 key 来源**（勿用 `~/.codex/auth.json`，可能是其他平台 key）：
  `sqlite3 ~/.cc-switch/cc-switch.db "SELECT settings_config FROM providers WHERE app_type='codex' AND name='CommandCode'" | python3 -c "import json,sys;print(json.loads(sys.stdin.read())['auth']['OPENAI_API_KEY'])"`
- **交互测试**（复选框按键流）用 pty：`pty.fork()` + 每键间隔 ≥0.3s（发送太快会被丢帧）；序列示例：`down space down space down up space up space up enter`（复原全选）→ `enter`（共用 Key）→ key+回车。断言输出含 `计划配置：ZCode、Claude Desktop、Codex CLI`、`共用`、`全部完成`。
- bootstrap 测试：`python3 -m http.server 8123` 模拟托管，`curl -fsSL http://127.0.0.1:8123/bootstrap.sh | bash -s -- --base http://127.0.0.1:8123 --agents codex --skip-probe --dry-run`；跑完 `/tmp/commandcode-agent-setup.*` 无残留。
- claude-desktop 核验点：`Claude-3p/configLibrary/_meta.json` 的 appliedId 对应文件 `inferenceGatewayBaseUrl` 指向 `https://api.commandcode.ai/provider`、key 前缀 `user_`；`claude_desktop_config.json` 的 `deploymentMode=="3p"`。
- 推送后 raw CDN 缓存最长约 5 分钟；急验证用 `gh api repos/.../contents/<file>`。

## 9. 发布流程

1. 跑 §8 的 0→4
2. `git add -A && git commit && git push`（main）
3. README 一键命令 URL 恒定（指向 main）

## 10. 已知坑清单（都是踩过的）

- **catalog 覆盖**：CC Switch 重启从 DB 重新生成磁盘 catalog —— 必须写 DB
- **3P profile 异步**：CC Switch 启动后 ~10s 才写，核验必须带重试窗口
- **auth.json key 不可信**：可能是其他平台 key（/models 200 但 /chat 401）；真 key 以 CC Switch DB 为准
- **pkill -f 误杀**：必须 `pkill -x cc-switch`
- **pty 按键节流**：复选框逐帧重绘，自动化测试按键间隔 ≥0.3s 否则丢帧
- **bash 多字节变量名**：`$VAR` 紧跟全角字符会被并进变量名 → 一律 `${VAR}`
- **/dev/tty 误判**：`[ -r /dev/tty ]` 在 CI/沙盒误通过；bootstrap 已改为真实试开 `{ true </dev/tty; } 2>/dev/null`
- **curl|bash stdin 是管道**：交互输入必须走 /dev/tty（bootstrap 处理）
- **ZCode 设置 UI 回写**：写入后不要在 UI 里改 provider，否则整文件被旧内存配置覆盖
- **备份先行**：写库前 `sqlite3 ".backup"`；codex 三文件与 zcode config.json 同批备份（时间戳后缀）
- **额度**：探测与冒烟消耗 CommandCode 额度（很小但非零）；机械测试一律 `--skip-probe`
- **敏感信息**：key 只在用户输入/环境变量/CC Switch DB/auth.json/3P profile，绝不进仓库文件、README、commit、终端回显

## 11. 变更历史

| 日期 | 变更 |
|---|---|
| 2026-08-29 | ZCode-CommandCode-Setup 诞生（ZCode 目标，探测式 + 官网上下文）；同日手工打通 Codex→CC Switch→CommandCode 链路并项目化为 ccswitch-commandcode-setup |
| 2026-09-06（上午） | ccswitch-commandcode-setup 增加 Claude Desktop 支持（--app，direct 模式实测）；发现 auth.json key 不可信问题 |
| 2026-09-06 | **三合一为本仓库 CommandCode-Agent-Setup**：common/ccswitch/zcode/codex/claude_desktop 模块化 + Inquirer 风格复选框/单选交互 + 共用/分别 Key 模式 + 探测共享（同 Key 只探一次）+ bootstrap 下载 modules/ 目录结构；pty 交互测试、副本库演练、实机三目标全通过；旧两仓库归档并在 README 标注指向本仓库 |
| 2026-09-06 | **claude-desktop 改默认 proxy 本地路由模式**（官方模型清单消失、GOAT 可用）：角色档映射 opus→gpt-5.6-sol / sonnet→deepseek-v4-flash / haiku→glm-5.3-flash / fable→Kimi-K3，labelOverride=模型名；实证 profile 仅 UI switch 时写出（is_current 翻转/删 profile 重启均不重建），核验给一次性手动步骤；端到端 haiku→GLM、opus→Sol 路由 PONG 全通 |
| 2026-09-06 | 新增 §7.1：实证 Codex /model UI 把 max 档显示为「More reasoning…」（非缺失）；max 在 catalog 中存在且实测生效，勿改档位数据 |
