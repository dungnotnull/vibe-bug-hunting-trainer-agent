<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11%2B-green" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="License MIT">
  <img src="https://img.shields.io/badge/languages-python%20%7C%20javascript%20%7C%20typescript%20%7C%20go%20%7C%20rust-orange" alt="Languages">
</p>

<h1 align="center">🐛 BugHunterAgent</h1>
<p align="center"><strong>Covert Debug Skill Training System</strong></p>
<p align="center"><em>Secretly injects controlled bugs, then coaches you through finding them.</em></p>

---

## What is BugHunterAgent?

BugHunterAgent is an **AI-powered training system** that sharpens your debugging instincts by covertly injecting realistic, skill-appropriate bugs into your sandbox project, observing how you hunt them down, and delivering rich educational debriefs afterward. It adapts to your skill level using an ELO-based scoring system and spaced repetition.

> **The best debugging skill is earned through genuine struggle, not hand-holding.**

---

## Why BugHunterAgent?

Modern developer tools — AI code completion, auto-fixing linters, intelligent IDEs — are quietly eroding one of the most valuable skills: **independent diagnosis and repair through systematic reasoning**.

BugHunterAgent fights this decay. It simulates the kind of subtle, semantically-valid bugs that appear in real production code — bugs that pass linters, pass type checkers, and pass your test suite, yet produce wrong behavior. Finding them builds the mental models that separate senior engineers from juniors.

---

## Features

| Category | Capabilities |
|---|---|
| **Covert Injection** | Analyzes your AST, selects optimal injection sites, generates realistic mutations via LLM + template fallback, validates through 6-step pipeline |
| **5-Level Hint System** | Socratic, non-prescriptive — Category → File → Function → Line Range → Full Reveal |
| **ELO Skill Scoring (DSS)** | 0–3000 Developer Skill Score adapts to your performance. K=32 ELO engine with pattern mastery multipliers |
| **Spaced Repetition** | SM-2 algorithm (Anki-style) re-surfaces bug patterns you've struggled with at optimal intervals |
| **Full Rollback** | Git branch isolation + encrypted mutation manifest. One command restores everything. |
| **Session Reports** | Rich Markdown debriefs with bug anatomy, debug journey replay, skill analysis, and next-session preview |
| **Multi-Provider LLM** | Local Qwen2.5-Coder via Ollama (default) + Anthropic Claude, OpenAI GPT, Google Gemini (optional) |
| **5 Languages** | Python, JavaScript, TypeScript, Go, Rust — auto-detected |
| **6 Bug Categories** | Boundary/Off-by-One, Type/Coercion, Async/Concurrency, State/Mutation, Security (OWASP-aligned, sandboxed), Logic/Algorithm |
| **Team Mode** | WebSocket-based shared bug hunts with real-time leaderboard and shared hint pool |
| **Web Dashboard** | FastAPI + WebSocket backend with developer profile, session status, and report rendering |
| **VS Code Extension** | Status bar DSS indicator, tree views, inline hint display, one-click actions |
| **Community API** | Public REST API for bug pattern submissions, review workflow, instructor curricula |
| **Knowledge Self-Improvement** | Weekly crawl pipeline — arXiv, CVE/NVD, GitHub PRs, OWASP Top 10 → updates SECOND-KNOWLEDGE-BRAIN.md |
| **Anti-Cheat Monitor** | Detects AI-assisted shortcuts — logs for coaching, never punishes |
| **Safety Gate** | Hard env check (`BUGHUNTER_ENV=sandbox`), CI detection, production hostname block, root-user block |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     DEVELOPER SANDBOX                            │
│                                                                  │
│  Source Code ──→ AST Analyzer ──→ Mutation Engine ──→ Injection │
│       ▲              (tree-sitter)    (LLM + templates)   │     │
│       │                                                    │     │
│       └──────── Buggy Code ←───────────────────────────────┘     │
│                                                                  │
│  Dev Hunts Bug → Request Hints → Claim Solved → Rollback        │
│       │               │               │             │           │
│       ▼               ▼               ▼             ▼           │
│  File Watcher    Hint System    ELO Update    Session Report    │
│  (watchdog)     (5 levels)    (DSS ±32)    (Markdown debrief)  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Git** (required for safe rollback via branch isolation)
- **Ollama** (optional — for local LLM-powered mutation generation)

### Installation

```bash
# Clone the repository
git clone https://github.com/dungnotnull/vibe-bug-hunting-trainer-agent.git
cd vibe-bug-hunting-trainer-agent

# Install with all dependencies
pip install -e .

# (Optional) Pull the local LLM for better mutations
ollama pull qwen2.5-coder:7b
```

### First Session

```bash
# Set sandbox mode (REQUIRED — agent refuses to run otherwise)
export BUGHUNTER_ENV=sandbox

# Navigate to a git-tracked project
cd my-sandbox-project

# Initialize BugHunterAgent in the project
bughunter init

# Start a bug hunt — agent injects bugs silently
bughunter hunt --start

# Your project now has hidden bugs. Debug as normal.
# When stuck, request a Socratic hint:
bughunter hint

# Check session status:
bughunter status

# When you think you've found and fixed it:
bughunter solved

# Or give up and see the solution:
bughunter surrender

# View your skill profile:
bughunter profile
```

---

## CLI Commands

| Command | Description |
|---|---|
| `bughunter init` | Initialize agent in a git-tracked project |
| `bughunter hunt --start` | Start a new bug hunt session (analyze → mutate → inject) |
| `bughunter hint` | Request next Socratic hint (Level 1–5) |
| `bughunter status` | View current session — phase, mutations, hints used |
| `bughunter solved` | Claim victory — verification + rollback + session report |
| `bughunter surrender` | Give up — rollback + coaching report |
| `bughunter profile` | View DSS score, pattern mastery, session history |
| `bughunter rollback --all` | Emergency recovery — force rollback all injections |
| `bughunter history` | View past session reports |
| `bughunter knowledge` | Manage the knowledge brain (status / update) |
| `bughunter version` | Show version |

---

## Bug Categories & Difficulty Tiers

### 6 Categories

| Category | Examples | BCT Range |
|---|---|---|
| **Boundary & Off-by-One** | Wrong loop bound, incorrect slice endpoint | BCT 1–2 |
| **Type & Coercion** | `==` vs `===`, integer division surprise, falsy chains | BCT 1–3 |
| **Async & Concurrency** | Missing `await`, race conditions, stale closures | BCT 3–4 |
| **State & Mutation** | Mutable default args, shallow copy bugs | BCT 2–3 |
| **Security (sandboxed)** | SQL injection vector, insecure randomness, path traversal | BCT 3–4 |
| **Logic & Algorithm** | AND/OR confusion, wrong comparison operator | BCT 1–3 |

### 5 Difficulty Tiers (ELO-scaled)

| Tier | DSS Range | Description |
|---|---|---|
| BCT-1 | 0–800 | Obvious logic errors, wrong return values |
| BCT-2 | 800–1400 | Off-by-one, boundary conditions, type coercion |
| BCT-3 | 1400–1800 | Race conditions, async pitfalls, subtle state mutation |
| BCT-4 | 1800–2200 | Security vulnerabilities, concurrent data corruption |
| BCT-5 | 2200+ | Heisenbugs, platform-specific edge cases, compiler quirks |

---

## Hint System

Hints are **Socratic** — they guide reasoning without giving answers. Each level costs DSS points.

| Level | Reveals | DSS Penalty |
|---|---|---|
| 1 — Category | "The bug is in the data transformation layer" | -15 |
| 2 — File | "Look at `src/utils/parser.js`" | -20 |
| 3 — Function | "Focus on the `processItems()` function" | -25 |
| 4 — Line Range | "Lines 42–67 contain the issue" | -30 |
| 5 — Full Reveal | Complete explanation of the bug | -40 |

---

## ELO Scoring (DSS)

The **Developer Skill Score** starts at **1200** and ranges from **0–3000**.

| Outcome | Score Multiplier | DSS Impact |
|---|---|---|
| Found independently, fast | 1.0 | +50 to +200 |
| Found independently, moderate | 1.0 | +10 to +50 |
| Found with 1–2 hints | 0.5 | Minor gain or neutral |
| Used 3+ hints | 0.5 minus hint penalties | -10 to -30 |
| Surrendered / time out | 0.1–0.2 | -10 to -30 |
| **First-time pattern** | ×1.5 | Bonus |
| **Security bug** | ×1.3 | Bonus |

Base formula: `Δ = 32 × (actual_score − expected_score)` where expected uses the standard ELO formula.

---

## Safety — Non-Negotiable

| Rule | Enforcement |
|---|---|
| **Sandbox only** | Hard crash if `BUGHUNTER_ENV != sandbox` |
| **Never in CI/CD** | Detects GitHub Actions, GitLab CI, Jenkins, CircleCI, Travis, Bamboo, TeamCity |
| **Never on production hostnames** | Blocks hostnames containing `prod`, `production`, `live`, `deploy` |
| **Never as root** | Blocks UID 0 on Unix systems |
| **Never in home/root dir** | Blocks CWD matching home or `/` |
| **No external side effects** | 6-step validation blocks network calls, real DB access, subprocess execution |
| **Instant rollback** | One command restores all injections + git branch |

---

## Project Structure

```
vibe-bug-hunting-trainer-agent/
├── bughunter/
│   ├── schemas/
│   │   └── models.py              # Pydantic schemas (15+ models/enums)
│   ├── core/
│   │   ├── agent_loop.py          # Hunt session state machine
│   │   ├── ast_analyzer.py        # Multi-language tree-sitter analyzer
│   │   ├── mutation_engine.py     # LLM + template mutation generation
│   │   ├── validators.py          # 6-step validation pipeline
│   │   ├── llm_client.py          # Ollama/Claude/GPT/Gemini router
│   │   ├── skill_profiler.py      # ELO scoring + pattern mastery
│   │   ├── session_reporter.py    # Markdown debrief generator
│   │   ├── spaced_repetition.py   # SM-2 algorithm + anti-cheat
│   │   ├── knowledge_crawler.py   # arXiv/CVE/GitHub/OWASP pipeline
│   │   ├── ml_classifier.py       # CodeBERT realism classifier
│   │   ├── team_mode.py           # WebSocket team sessions
│   │   ├── git_isolation.py       # GitPython branch management
│   │   ├── safety_gate.py         # Environment validation
│   │   ├── manifest.py            # Fernet-encrypted sessions
│   │   ├── config.py              # .env configuration
│   │   └── logging.py             # Loguru silent-by-default
│   ├── cli/
│   │   └── main.py                # Typer CLI (11 commands)
│   ├── web/
│   │   └── app.py                 # FastAPI dashboard backend
│   └── api/
│       └── community.py           # Public REST API + curricula
├── vscode-extension/
│   ├── package.json               # VS Code extension manifest
│   ├── tsconfig.json
│   └── src/
│       └── extension.ts           # Extension entry point
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── CLAUDE.md                      # Behavioral specification
├── PROJECT-detail.md              # Technical specification
├── PROJECT-DEVELOPMENT-PHASE-TRACKING.md
├── SECOND-KNOWLEDGE-BRAIN.md      # Seeded bug knowledge base
└── README.md
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.11+ |
| **AST Parsing** | tree-sitter (Python, JavaScript, TypeScript, Go, Rust) |
| **Local LLM** | Qwen2.5-Coder-7B via Ollama |
| **External LLMs** | Anthropic Claude, OpenAI GPT, Google Gemini |
| **ML** | CodeBERT (mutation quality), sentence-transformers (behavior embedder) |
| **Vector Store** | ChromaDB (bug pattern corpus) |
| **CLI** | Typer + Rich |
| **Web** | FastAPI + WebSocket |
| **Encryption** | cryptography (Fernet) |
| **File Watching** | watchdog |
| **Scheduling** | APScheduler |
| **Git** | GitPython |
| **Logging** | Loguru |
| **VS Code Extension** | TypeScript + VS Code API |

---

## Team Mode

Start a shared session where multiple developers hunt the same bugs simultaneously:

```bash
# Create a team session
bughunter team --create --name "Wednesday Hunt"

# Join with the session code
bughunter team --join ABC12345
```

Features: shared hint pool, real-time leaderboard via WebSocket, relative performance scoring.

---

## Web Dashboard

Start the dashboard server:

```bash
python -m bughunter.web.app
# → http://localhost:8000
```

Endpoints: `/api/profile`, `/api/hunt/status`, `/api/sessions`, `/api/leaderboard`, `/api/llm/config`, `/api/knowledge`, WebSocket at `/ws/session/{id}`.

---

## Community API

Start the community server:

```bash
python -m bughunter.api.community
# → http://localhost:8001
```

Features: pattern submission, review workflow, 5-star rating, download tracking, instructor curriculum builder.

---

## Configuration

Copy `.env.example` to `.env` and customize:

```env
BUGHUNTER_ENV=sandbox          # REQUIRED
BUGHUNTER_SESSION_TIMEOUT=240  # 4 hours
BUGHUNTER_MAX_BUGS=3           # Max concurrent injections
BUGHUNTER_MUTATION_RETRIES=5
BUGHUNTER_REALISM_THRESHOLD=0.7

# Optional: External LLM for better mutation quality
# BUGHUNTER_EXTERNAL_LLM=claude
# BUGHUNTER_EXTERNAL_MODEL=claude-sonnet-4-6
# BUGHUNTER_EXTERNAL_API_KEY=your-api-key
```

---

## Development

```bash
# Install dev dependencies
pip install -e .

# Run type checking
mypy bughunter/

# Run the CLI
bughunter --help

# Start the web dashboard
python -m bughunter.web.app

# Start the community API
python -m bughunter.api.community
```

---

## License

MIT License © 2026 Claude

See [LICENSE](LICENSE) for details.

---

## Status

**v0.1.0** — All 4 phases complete. Production-grade core engine, intelligence layer, team mode, web dashboard, VS Code extension, and public API. Ready for go-live and community contributions.

---

<p align="center">
  <sub>Built with ❤️ by Claude · <a href="https://github.com/dungnotnull/vibe-bug-hunting-trainer-agent">GitHub</a></sub>
</p>
