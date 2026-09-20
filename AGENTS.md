# AGENTS.md — CommandCode-Agent-Setup（AI 接手说明）

> 本文件面向 AI agent（ZCode / Claude Code / Codex / 其他），是项目的完整事实库与开发规程。
> 人类用户请读 [README.md](README.md)。
> 标注【实测】的事实分别于 **2026-08-29**（codex 链路）、**2026-09-06**（本仓库整合）在用户本机（macOS arm64，HOME=/Users/functy）验证过；
> 修改代码前先读完本文，不要凭记忆改动已验证的行为。怀疑过期时按 §8 重新验证。

---

## 文档约定（双语 + 徽章）

README 为**英文主文档**（`README.md`）+ **中文全量翻译**（`doc/README_zh-CN.md`），
两份内容一一对应，**改一边必须同步另一边**。两份文件顶部是同一组 shields.io 徽章
（语言/平台/CI/License/Release/Downloads/Stars/Repo Size/Contributors 按仓库实际能力裁剪，
没有的能力不放，避免死链），徽章下面一行语言切换：
`README.md` 用 `**English** | [简体中文](doc/README_zh-CN.md)`，
中文版用 `[English](../README.md) | **简体中文**`。增删徽章时两份一起改。

---

## 1. 项目定位

一键把 **CommandCode 订阅**配置进两个 AI Agent：

| 目标 | 接入方式 | 数据落点 |
|---|---|---|
| **ZCode** | 直写配置（`kind=openai-compatible`） | `~/.zcode/v2/config.json` |
| **Codex CLI** | CC Switch **代理模式**（responses→chat 转换） | `~/.cc-switch/cc-switch.db` 的 `codex` 行 + 代理接管 15721 |

- 入口 `setup.py`：终端复选框（Inquirer 风格：↑↓ + 空格 + 回车，`a` 全选/反选）选 Agent → 凭证来源（网页登录 / 贴 Key / 本机 auth.json）→ 分发到模块。
- 仅限 **macOS**，最低 **GOAT 套餐**（Go 直接中止）。仅依赖 Python 3 标准库。
- 本仓库由旧仓库 [`ZCode-CommandCode-Setup`](https://github.com/functy23/ZCode-CommandCode-Setup)（ZCode 目标）与 [`ccswitch-commandcode-setup`](https://github.com/functy23/ccswitch-commandcode-setup)（Codex + 曾含 Claude Desktop）合并而来，两个旧仓库已归档、README 已标注指向本仓库。
- **不做**的事：不支持 Claude 模型经 chat/completions（只能走 Anthropic 路由，目录里直接剔除）；**不再支持 Claude Desktop**（模块已删除）。

线上仓库：<https://github.com/functy23/CommandCode-Agent-Setup>（public，分支 main）

## 2. 文件清单

| 文件 | 职责 |
|---|---|
| `setup.py` | 主入口：Agent 注册表、终端复选框/单选（raw-mode 自绘）、凭证来源、按 Key 去重校验、共享目录分发 |
| `modules/common.py` | 公共设施：UA/HTTP（防 Cloudflare 1010）、Key 校验、套餐闸门、公开 `/models` 目录、`KNOWN_EFFORTS`/`KNOWN_IMAGE_MODELS` 元数据表 |
| `modules/login.py` | 网页登录（Studio CLI 回调 + CORS/PNA）与本机 `auth.json` 读写 |
| `modules/ccswitch.py` | CC Switch 共享：进程控制（osascript→pkill -x）、备份、幂等写库、codex 核验、PONG 冒烟 |
| `modules/zcode.py` | ZCode 目标：官网上下文抓取 + ZCode 元数据规则表 + 写 `~/.zcode/v2/config.json` |
| `modules/codex.py` | Codex 目标：预览 + 写 codex 行 + 接管核验 + 可选 PONG |
| `bootstrap.sh` | curl\|bash 总引导：下载 setup.py + modules/（保持目录结构）到 mktemp → 运行 → trap 清理 |
| `run.command` | macOS 双击启动器 |

## 3. 交互设计（setup.py）

- `ask_agents()`：CLI `--agents zcode,codex|all` 优先；否则 `checkbox()`。复选框自绘实现要点：raw mode 读键（`termios/tty`）、每帧 `\x1b[nA` 回退重绘、空格 toggle、`a` 全选/反选、空选回车给提示不放行。
- **【关键】光标回退必须是 `drawn-1`**：末行无换行，光标已在第 drawn 行上；用 `drawn` 会多退一行，再 `\x1b[J` 就把标题/横幅随着每次 ↑↓ **一行行吞掉**。`CSI 0A` 在部分终端等于 `1A`，`drawn==1` 时只发 `\r\x1b[J`。首绘前 `_enter_raw()`，避免第一帧 cooked、后续 raw。`_restore_termios` 必须自己 `import termios`（函数内 import 不会漏到恢复函数）。
- `ask_keys()`：`--key` / `COMMANDCODE_API_KEY` 优先；否则 `--login` 网页登录、`--auth-file` 读本机凭证；交互则单选「网页登录 / 手动输入 / 本机已有凭证」。手动输入时再问共用/分别（`--key-mode shared|separate`）。网页登录与本机凭证一律共用一个 Key。
- **Key 校验按 Key 值去重**（同 Key 只调一次鉴权 `/models`+`/subscriptions`+`/whoami`）；目录按 Key 缓存（`shared_probe`），两目标只拉一次。
- `--skip-probe` 已无效果（保留以免旧命令行报错）。

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

## 5. CC Switch 数据库写入规范（最关键的坑）

- 库 `~/.cc-switch/cc-switch.db`（SQLite）；进程名 `cc-switch`（必须 `pkill -x`，`pkill -f` 会误杀自身 shell）
- 涉及三张表：
  - `providers`：PK `(id, app_type)`。codex 行 id=`f4a0013a-37aa-41f5-828b-b8fe50aa16b9`（更新路径保留原 id）；写入用 `BEGIN IMMEDIATE` 单事务
  - `provider_endpoints`：codex=`…/provider/v1`
  - `proxy_config`：codex 需 `proxy_enabled=1, enabled=1`
- `settings_config`：
  - codex 行：`auth.OPENAI_API_KEY` + `config`（TOML 片段，存**上游直连**地址，接管时 CC Switch 自动换代理并注入）+ `modelCatalog.models[]`（`{model, displayName, contextWindow, reasoningLevels[], defaultReasoningLevel, inputModalities}`）
- `meta`（逐字使用）：
  - codex：`{"commonConfigEnabled":false,"endpointAutoSelect":true,"apiFormat":"openai_chat","codexChatReasoning":{...}}`（openai_chat 是 responses→chat 转换前提；写成 openai_responses 会透传 /responses → 404）
- `is_current` 同 app_type 内唯一；写库流程：备份 → 退应用（osascript→pkill -TERM -x，最多 15s，退不掉中止）→ 写库 → 启动 → 等 15721（40s）→ 核验
- 幂等：同 app_type 同名 UPDATE（保留 id/created_at），否则 INSERT（uuid4）

## 6. 公开模型目录（设计决策，勿回退成内嵌清单，也勿回退成逐模型探测）

上游增删频繁，公开目录自动跟随。方法对齐 dsh-commandcode-provider `src/models.ts`：

- `GET /provider/v1/models` **不带 Key**（公开）；失败再带 Key 重试
- 返回 `{object:"list", data:[{id, name, context_length, …}]}`（id 带厂商前缀）
- **不再**对每个模型 POST `chat/completions` 做 1-token 探测（耗额度、慢、且不是可用性的权威来源）
- `claude-*` 一律剔除（只能走 Anthropic 路由）
- `--skip-probe` 保留为无操作（旧命令行兼容）
- `--include SLUG` 仍可强制收录（Claude 除外）
- 套餐闸门：`/alpha/billing/subscriptions` 的 `data.planId`；goat/pro/provider 放行，**go 中止**；识别失败交互确认或 `--yes` 继续；`--plan` 可强制
- Key 有效性另走带鉴权的 `/models` 或 `/whoami`（401/403 才判无效），与公开目录解耦

## 6.1 网页登录

协议对齐 Command Code Studio CLI 回调（opencode-commandcode `src/auth-login.ts` / 旧版 dsh-commandcode-provider `/commandcode-login`，现行 dsh 插件 0.1.2 已删）：

- 本机 `127.0.0.1:5959` 起最多试 10 个端口
- URL：`https://commandcode.ai/studio/auth/cli?callback=http://localhost:PORT/callback&state=STATE`
- Studio POST `{apiKey, userId, userName, keyName, state}`；`state` 必须匹配，否则 403
- CORS：`Access-Control-Allow-Origin` 校验 `commandcode.ai`；必须回 `Access-Control-Allow-Private-Network: true`（Chrome PNA）
- 超时 12 分钟；成功写入 `~/.commandcode/auth.json` 的 `command-code: {type:api, key}`
- 本机凭证读取顺序：`COMMANDCODE_API_KEY` → `~/.commandcode/auth.json` → `~/.pi/agent/auth.json` → `~/.omp/agent/auth.json`（形状兼容 `apiKey` / `commandcode` 字符串 / `{type:api,key}` / `{type:oauth,access}`）

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

与 ZCode/DSH 的差异本质：ZCode/DSH 的 UI 直接显示 variants 字面量（如 off/high/max），Codex TUI 做了展示层改名。

**【实测 2026-09-06 续】ChatGPT.app（原 Codex 桌面版 GUI，bundle `com.openai.codex`，内嵌 codex 0.151.0-alpha）的行为不同且更严**：GUI 读取同一套 `~/.codex/config.toml` + `model_catalog_json`（左下角显示 provider 名与「模型 档位」），但其推理强度子菜单**不渲染 max 档**——catalog `[low,high,max]` 的 GLM-5.3 Flash 只显示「轻度/高」两项，max 被静默丢弃（GUI i18n 里有 max{Max} 映射，但菜单构建按白名单过滤；TUI 的 max/Ultra→More reasoning… 归档逻辑与 GUI 前端不一致）。GUI 认识 `xhigh`（显示「极高」）。

**修复（已实现于 common.levels_for）**：写 codex catalog 时把档位集里的 `max` 统一替换为 `xhigh`（default 同步取末位）——GUI 显示「极高」作为可选最高档；上游网关对 xhigh 与 max 均返回 200（实测），推理深度等效。ZCode 侧不受影响（仍用 off/high/max 等原字面量）。实验过程：把 catalog 档位手工改为 [low,high,xhigh] 并重启 ChatGPT.app → 子菜单立即出现「极高」；改回后消失。

## 8. 测试规程（改代码后必做，按成本从低到高）

```bash
cd ~/Desktop/CommandCode-Agent-Setup

# 0. 语法
python3 -m py_compile setup.py modules/*.py && bash -n bootstrap.sh && bash -n run.command

# 1. 零成本机械测试（不写库；两种 agents 组合都过一遍更稳）
COMMANDCODE_API_KEY=<key> python3 setup.py --agents all --dry-run
COMMANDCODE_API_KEY=<key> python3 setup.py --agents codex --dry-run

# 2. 拉目录预览（公开 /models，不消耗 token；不写库）
COMMANDCODE_API_KEY=<key> python3 setup.py --agents all --dry-run

# 3. 写库演练（--db 副本库；ZCode 仍写真实 config.json——它不走 CC Switch，注意）
sqlite3 ~/.cc-switch/cc-switch.db ".backup '/tmp/cc-tri.db'"
COMMANDCODE_API_KEY=<key> python3 setup.py --agents all --yes --db /tmp/cc-tri.db

# 4. 实机全流程（重启 CC Switch + 写真实库 + ZCode 配置）
COMMANDCODE_API_KEY=<key> python3 setup.py --agents all --yes --verify
```

- **真 key 来源**（勿用 `~/.codex/auth.json`，可能是其他平台 key）：
  `sqlite3 ~/.cc-switch/cc-switch.db "SELECT settings_config FROM providers WHERE app_type='codex' AND name='CommandCode'" | python3 -c "import json,sys;print(json.loads(sys.stdin.read())['auth']['OPENAI_API_KEY'])"`
- **交互测试**（复选框按键流）用 pty：`pty.fork()` + 每键间隔 ≥0.3s（发送太快会被丢帧）；序列示例：`down space down space up space up space enter`（复原全选）→ `enter`（网页登录或贴 Key）→ 断言输出含 `计划配置：ZCode、Codex CLI`、`全部完成`。**断言标题「选择要配置的 Agent」在 ↑↓ 之后仍在屏幕上**（回归吞行 bug）。
- bootstrap 测试：`python3 -m http.server 8123` 模拟托管，`curl -fsSL http://127.0.0.1:8123/bootstrap.sh | bash -s -- --base http://127.0.0.1:8123 --agents codex --dry-run`；跑完 `/tmp/commandcode-agent-setup.*` 无残留。
- 推送后 raw CDN 缓存最长约 5 分钟；急验证用 `gh api repos/.../contents/<file>`。

## 9. 发布流程

1. 跑 §8 的 0→4
2. `git add -A && git commit && git push`（main）
3. README 一键命令 URL 恒定（指向 main）

## 10. 已知坑清单（都是踩过的）

- **catalog 覆盖**：CC Switch 重启从 DB 重新生成磁盘 catalog —— 必须写 DB
- **auth.json key 不可信**：可能是其他平台 key（/models 200 但 /chat 401）；真 key 以 CC Switch DB 为准
- **pkill -f 误杀**：必须 `pkill -x cc-switch`
- **pty 按键节流**：复选框逐帧重绘，自动化测试按键间隔 ≥0.3s 否则丢帧
- **复选框吞行**：`\x1b[drawn A` 多退一行会把标题/横幅按键吞掉；必须 `drawn-1`，且 CSI 0A 当 1A
- **bash 多字节变量名**：`$VAR` 紧跟全角字符会被并进变量名 → 一律 `${VAR}`
- **/dev/tty 误判**：`[ -r /dev/tty ]` 在 CI/沙盒误通过；bootstrap 已改为真实试开 `{ true </dev/tty; } 2>/dev/null`
- **curl|bash stdin 是管道**：交互输入必须走 /dev/tty（bootstrap 处理）
- **ZCode 设置 UI 回写**：写入后不要在 UI 里改 provider，否则整文件被旧内存配置覆盖
- **备份先行**：写库前 `sqlite3 ".backup"`；codex 三文件与 zcode config.json 同批备份（时间戳后缀）
- **额度**：冒烟消耗 CommandCode 额度（很小但非零）；机械测试用 `--dry-run`
- **敏感信息**：key 只在用户输入/环境变量/CC Switch DB/auth.json，绝不进仓库文件、README、commit、终端回显
- **网页登录 PNA**：Chrome 从 commandcode.ai POST 到 localhost 必须回 `Access-Control-Allow-Private-Network: true`，且 `shutdown()` 不要在请求处理线程里调用（Python HTTPServer 会死锁）

## 11. 变更历史

| 日期 | 变更 |
|---|---|
| 2026-08-29 | ZCode-CommandCode-Setup 诞生（ZCode 目标，探测式 + 官网上下文）；同日手工打通 Codex→CC Switch→CommandCode 链路并项目化为 ccswitch-commandcode-setup |
| 2026-09-06（上午） | ccswitch-commandcode-setup 增加 Claude Desktop 支持（--app，direct 模式实测）；发现 auth.json key 不可信问题 |
| 2026-09-06 | **两目标合并为本仓库 CommandCode-Agent-Setup**：common/ccswitch/zcode/codex 模块化 + Inquirer 风格复选框/单选交互 + 共用/分别 Key 模式 + 目录共享 + bootstrap 下载 modules/ 目录结构；pty 交互测试、副本库演练、实机目标全通过；旧两仓库归档并在 README 标注指向本仓库 |
| 2026-09-06 | 新增 §7.1：实证 Codex /model UI 把 max 档显示为「More reasoning…」（非缺失）；max 在 catalog 中存在且实测生效，勿改档位数据 |
| 2026-09-10 | **删除 Claude Desktop 支持**；模型列表改为公开 GET `/provider/v1/models`（对齐 dsh-commandcode-provider，不再逐模型 1-token 探测）；新增网页登录 / 本机 auth.json；修复复选框 ↑↓ 多退一行把标题吞掉 |
