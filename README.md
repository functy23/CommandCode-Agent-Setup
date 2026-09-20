<div align="center">

# 🔧 CommandCode Agent Setup

**One-liner setup that wires your CommandCode subscription into ZCode and Codex CLI — macOS only.**

[![CommandCode-Agent-Setup](https://img.shields.io/badge/CommandCode-Agent-Setup-CCAS-orange.svg)](https://github.com/functy23/CommandCode-Agent-Setup)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Top Language](https://img.shields.io/github/languages/top/functy23/CommandCode-Agent-Setup?style=flat)](https://github.com/functy23/CommandCode-Agent-Setup)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg?logo=apple&logoColor=white)](https://github.com/functy23/CommandCode-Agent-Setup)

[![Stars](https://img.shields.io/github/stars/functy23/CommandCode-Agent-Setup?style=flat&logo=github)](https://github.com/functy23/CommandCode-Agent-Setup/stargazers)
[![Repo Size](https://img.shields.io/github/repo-size/functy23/CommandCode-Agent-Setup?style=flat&logo=github)](https://github.com/functy23/CommandCode-Agent-Setup)
[![Contributors](https://img.shields.io/github/contributors/functy23/CommandCode-Agent-Setup?color=ee8449&logo=githubsponsors)](https://github.com/functy23/CommandCode-Agent-Setup/graphs/contributors)

[Issues](https://github.com/functy23/CommandCode-Agent-Setup/issues) • [AGENTS.md](AGENTS.md)

**English** | [简体中文](doc/README_zh-CN.md)
</div>

---
## Overview

One-liner scripts that wire your **CommandCode subscription** into your AI agents: **ZCode** and **Codex CLI**. **macOS only**, **GOAT plan minimum** (Go is not supported).

> This repository is a merge of [`ZCode-CommandCode-Setup`](https://github.com/functy23/ZCode-CommandCode-Setup) and [`ccswitch-commandcode-setup`](https://github.com/functy23/ccswitch-commandcode-setup). Both of those repositories are archived and no longer maintained — use this repository for everything instead.

## Quick Start (One-Liner, Recommended)

The classic usage pattern for script projects: `curl` a single top-level script, and it automatically pulls the remaining files into a temporary directory to run them — **and cleans up after itself when it finishes, so there is no need to download the whole repository and delete it by hand**.

```bash
# Fully interactive: pick agents with checkboxes → pick a credential source (web login / paste a key / local credentials)
curl -fsSL https://raw.githubusercontent.com/functy23/CommandCode-Agent-Setup/main/bootstrap.sh | bash

# With arguments (passed through to setup.py verbatim)
curl -fsSL https://raw.githubusercontent.com/functy23/CommandCode-Agent-Setup/main/bootstrap.sh | bash -s -- --agents codex --login
```

Notes: `bootstrap.sh` downloads only the minimal set of files needed to run (`setup.py` + `modules/`) into a temporary directory under `/tmp`, and deletes it automatically when the run finishes; interactive input is automatically rerouted through `/dev/tty`, so typing a key or completing a web login still works under `curl | bash`. In `curl | bash` mode, separate arguments with `bash -s --`.

## Running Locally

When the repository is already on your machine, no download is needed:

- **Double-click `run.command`** (double-clicking it in Finder opens a terminal and runs it); or
- `python3 setup.py`

## Interactive Flow

1. **Select agents** (checkboxes: move with ↑↓, toggle with space, `a` to select/deselect all, Enter to confirm):

   ```
   ◉ ZCode            writes ~/.zcode/v2/config.json, directly visible in the model picker
   ◉ Codex CLI        proxied through CC Switch (responses→chat conversion), with reasoning-effort labels
   ```

2. **Select a credential source** (single choice):
   - **Web login** — opens CommandCode Studio; after you log in, the key is filled back into the script automatically (and written to `~/.commandcode/auth.json`)
   - **Manual input** — paste an API key that starts with `user_` (with multiple agents you can then choose to share one or configure them separately)
   - **Existing local credentials** — reads `~/.commandcode/auth.json`, `~/.pi/agent/auth.json`, `~/.omp/agent/auth.json`

3. The script validates the key, identifies the plan (GOAT minimum), pulls the public model catalog, and then writes according to your choices.

## Command-Line Arguments (Skip the Interactive Flow Entirely)

| Argument | Description |
|---|---|
| `--agents zcode,codex` (or `all`) | Target agents, comma-separated; shows a checkbox list if omitted |
| `--login` | Web login: opens CommandCode Studio and fills the key back in after you log in |
| `--auth-file` | Use existing local credentials (`~/.commandcode/auth.json`, etc.) |
| `--key-mode shared\|separate` | Key mode for manual input; shows a radio list if omitted |
| `-k, --key` | CommandCode API key (used directly in shared mode; the environment variable `COMMANDCODE_API_KEY` also works) |
| `--plan goat\|pro\|provider` | Skip subscription auto-detection and force this plan tier (used as a gate only) |
| `-m, --model SLUG` | Codex default model (default `deepseek/deepseek-v4-flash`) |
| `--name NAME` | Provider name (default `CommandCode`) |
| `--include SLUG` | Additional model slug to force into the catalog; may be repeated |
| `--db PATH` | Specify the CC Switch database path (for dry runs; the real database is untouched and the app is not restarted) |
| `--dry-run` | Preview the model catalog and the content to be written only |
| `--no-restart` | Do not restart CC Switch after writing to the database (restart it manually for the change to take effect) |
| `--verify` | Run a smoke test when done (Codex: end-to-end PONG) |
| `-y, --yes` | Skip all confirmation prompts |

Non-interactive examples:

```bash
python3 setup.py --agents all --login --yes --verify
python3 setup.py --agents all --key-mode shared --key user_xxx --yes --verify
python3 setup.py --agents codex --auth-file --yes
```

In `separate` mode, keys can also be supplied per agent through environment variables: `ZCODE_COMMANDCODE_KEY` / `CODEX_COMMANDCODE_KEY`.

## What the Two Targets Do

| Agent | Written to | Model list | Notes |
|---|---|---|---|
| **ZCode** | `~/.zcode/v2/config.json` (an `openai-compatible` provider) | Public catalog (Claude excluded), with embedded output/reasoning-effort rules | Backed up before writing; ZCode must be fully restarted after the change |
| **Codex CLI** | CC Switch DB (the `codex` row) + proxy takeover | Public catalog (Claude excluded), reasoning effort from the authoritative table | `~/.codex/config.toml` is taken over by CC Switch and pointed at the local proxy (15721); responses→chat is converted automatically |

> **Key mechanism**: when taking over or restarting, CC Switch **regenerates** `~/.codex/cc-switch-model-catalog.json` from the database, so any manual edit to the on-disk catalog is lost — the database must be changed. This script writes the database directly, so it is inherently immune to being overwritten.

## Important Notes

Because upstream models are updated frequently, a model may stop working or be delisted, which makes it unusable. **Re-running this script refreshes the catalog.** Claude-family models cannot be used through chat/completions and are skipped automatically in the catalog.

## Model Catalog and Metadata

- Same as [dsh-commandcode-provider](https://github.com/Victor-770/dsh-commandcode-provider): `GET https://api.commandcode.ai/provider/v1/models` (public, no key required; retried with the key on failure). It **no longer** sends a 1-token probe request for every model.
- Claude-family models (`claude*`) are always excluded (they can only go through the Anthropic Messages endpoint).
- Reasoning effort uses the embedded authoritative `KNOWN_EFFORTS` table; models outside the table fall back uniformly to `low/medium/high` with the highest tier as default; image input is decided by `KNOWN_IMAGE_MODELS`.

## Web Login

The protocol matches Command Code Studio's CLI callback (same lineage as opencode-commandcode / the older dsh-commandcode-provider):

1. Start a temporary HTTP server on `127.0.0.1:5959+` locally
2. Open `https://commandcode.ai/studio/auth/cli?callback=…&state=…`
3. After logging in to Studio, it POSTs `{apiKey, userId, userName, keyName, state}` back to `/callback`
4. On success it writes `~/.commandcode/auth.json`, so next time you can pick "existing local credentials" directly

If the browser does not open automatically, the terminal prints the full URL. It waits up to 12 minutes; Ctrl-C cancels.

## Backup and Rollback

Before every actual write, the script backs up automatically (timestamp suffix `.bak-YYYYmmdd-HHMMSS`):

- `~/.cc-switch/cc-switch.db` (when a CC Switch target is selected)
- `~/.codex/config.toml`, `~/.codex/auth.json`, `~/.codex/cc-switch-model-catalog.json` (when Codex is selected)
- `~/.zcode/v2/config.json` (when ZCode is selected)

Rollback: quit CC Switch / ZCode first, then copy the corresponding `.bak` file back over.

## Project Files

| File | Purpose |
|---|---|
| `bootstrap.sh` | Top-level script (the `curl \| bash` entry point): downloads the minimal file set into a temporary directory, runs it, and cleans up automatically |
| `setup.py` | Main entry point: agent checkboxes → credential source → dispatch to each target module |
| `modules/common.py` | Shared infrastructure: HTTP (Cloudflare 1010 avoidance), key validation, plan gate, public model catalog, authoritative metadata tables |
| `modules/login.py` | Web login (Studio CLI callback) + reading and writing the local auth.json |
| `modules/ccswitch.py` | CC Switch shared infrastructure: process control, database writes, codex verification, PONG smoke test |
| `modules/zcode.py` | ZCode target: writes `~/.zcode/v2/config.json` |
| `modules/codex.py` | Codex target: writes the codex row in the CC Switch DB + proxy takeover |
| `run.command` | macOS double-click launcher |

(For AI agents taking over development, read [AGENTS.md](AGENTS.md).)
