# PROJECT-detail.md — vibe-bug-hunting-trainer-agent

> **Full Technical & Product Specification**
> Version: 0.1.0 | Status: Planning

---

## 1. Project Overview

### Name
`vibe-bug-hunting-trainer-agent` — Covert Debug Skill Training System

### Problem Statement
Modern development practices — AI code completion, auto-fixing linters, intelligent IDEs —
are quietly eroding one of the most valuable developer skills: the ability to **independently
diagnose and fix bugs through systematic reasoning**.

Developers who always reach for Copilot or ChatGPT at the first sign of an error lose the
mental models that separate senior engineers from juniors. When these tools aren't available
(production outage at 2AM, air-gapped environment, critical security audit), the skill gap
becomes a liability.

**The gap**: No existing tool actively *trains* debugging intuition through realistic, adaptive,
deliberate practice. Existing tools (debugging courses, leetcode-style challenges) are artificial
and disconnected from a dev's real codebase.

### Solution
An agentic system that operates covertly within a developer's **local/sandbox environment**:
1. Analyzes the developer's actual code (AST-level understanding)
2. Secretly injects realistic, skill-appropriate bugs at runtime
3. Observes and hints (Socratically) during the hunting phase
4. Delivers rich educational debriefs after discovery
5. Adapts difficulty over time using an ELO-style skill scoring system
6. Grows smarter via weekly ingestion of new bug pattern research

### Who Benefits
- **Individual developers** (primary): Keeping debug skills sharp during AI-heavy workflows
- **Engineering teams** (secondary): Shared sessions, team leaderboards, onboarding ramp
- **Bootcamps & coding schools** (tertiary): Structured debug skill curriculum
- **Tech interviewers** (future): Generate realistic live-debugging interview scenarios

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DEVELOPER ENVIRONMENT                         │
│                    (Local / Sandbox — NEVER prod)                    │
│                                                                      │
│  ┌────────────────┐    ┌───────────────┐    ┌────────────────────┐  │
│  │  Source Code   │    │  Test Runner  │    │  Runtime Process   │  │
│  │  (git tracked) │    │  (pytest/jest)│    │  (node/python/go)  │  │
│  └───────┬────────┘    └───────┬───────┘    └────────┬───────────┘  │
│          │                     │                      │              │
│          └──────────┬──────────┘                      │              │
│                     │                                 │              │
│            ┌────────▼────────────────────────────────▼──────────┐   │
│            │              BUGHUNTER DAEMON                       │   │
│            │  (Background process, silent, env-gated)            │   │
│            └─────────────────────┬───────────────────────────────┘   │
└──────────────────────────────────│──────────────────────────────────┘
                                   │
          ┌────────────────────────┼──────────────────────────┐
          │                        │                           │
          ▼                        ▼                           ▼
┌─────────────────┐  ┌─────────────────────────┐  ┌─────────────────────┐
│   AST ANALYZER  │  │  MUTATION ENGINE         │  │  SANDBOX CONTROLLER │
│                 │  │                          │  │                     │
│ tree-sitter     │  │ Local SLM: Qwen-2.5-     │  │ Runtime monkey-     │
│ (multi-lang     │  │ Coder (Ollama)           │  │ patching + env var  │
│  AST parsing)   │  │                          │  │ injection           │
│                 │  │ External LLM (optional): │  │                     │
│ Candidate       │  │ Claude / GPT / Gemini    │  │ File system watcher │
│ scoring         │  │                          │  │ (watchdog)          │
└────────┬────────┘  └────────────┬────────────┘  └──────────┬──────────┘
         │                        │                            │
         └────────────┬───────────┘                            │
                      │                                        │
                      ▼                                        │
         ┌────────────────────────┐                            │
         │    KNOWLEDGE ENGINE    │◄───────────────────────────┘
         │                        │
         │  SECOND-KNOWLEDGE-     │
         │  BRAIN.md              │
         │                        │
         │  Bug Pattern Corpus    │
         │  (language-specific)   │
         │                        │
         │  Developer Profile DB  │
         │  (DSS, history, gaps)  │
         └────────────┬───────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │   SKILL PROFILER       │
         │                        │
         │  ELO Score Engine      │
         │  Spaced Repetition     │
         │  Anti-Cheat Monitor    │
         └────────────┬───────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │   SESSION REPORTER     │
         │                        │
         │  Debrief Generator     │
         │  Progress Dashboard    │
         │  Team Leaderboard      │
         └────────────────────────┘
```

---

## 3. Module Specifications

### 3.1 AST Analyzer

**Purpose**: Parse source code into structured AST to identify realistic injection candidates

**Technology**: `tree-sitter` (universal, multi-language, incremental parsing)

**Supported languages (Phase 1)**: Python, JavaScript/TypeScript
**Phase 2**: Go, Java, Rust, Ruby

**Injection candidate scoring criteria**:
```python
@dataclass
class InjectionCandidate:
    file: str
    line_start: int
    line_end: int
    ast_node_type: str        # function_def, if_statement, assignment, etc.
    pattern_category: str     # boundary, type, async, security, state
    detectability_score: float  # 0.0 (too obvious) - 1.0 (virtually invisible)
    realism_score: float      # How plausible this bug is in real code
    difficulty_level: int     # BCT 1-5
    prerequisite_patterns: list[str]  # Patterns dev must have seen first
```

**Scoring algorithm**:
- Prefer functions with non-trivial logic (cyclomatic complexity > 3)
- Avoid: error handlers, logging functions, test files, migration files
- Prefer: data transformation, business logic, authentication flows, API handlers
- Weight heavily toward functions the dev recently modified (more contextually relevant)

---

### 3.2 Mutation Engine

**Purpose**: Generate semantically valid, realistic, plausible bugs

**Primary model**: `Qwen/Qwen2.5-Coder-7B-Instruct` via Ollama (local, privacy-preserving)
**Fallback/enhancement**: External LLM API (user-configured)

**Mutation Strategy Catalog**:

```
CATEGORY 1: Boundary & Off-by-One
  - Array index: i vs i+1 vs i-1
  - Loop bounds: < vs <= vs !=
  - Slice: [0:n] vs [0:n-1] vs [1:n]
  - String: include/exclude last character

CATEGORY 2: Type & Coercion
  - Implicit type conversion edge cases (JS: == vs ===)
  - Integer division vs float division
  - Null/None vs empty string vs 0 (falsy confusion)
  - String to int conversion without error handling

CATEGORY 3: Async & Concurrency
  - Missing await keyword
  - Race condition via shared state mutation
  - Promise chain missing .catch()
  - Thread-unsafe counter increment

CATEGORY 4: State & Mutation
  - Mutating input parameter instead of copy
  - Missing deep copy (shallow copy bug)
  - Global state pollution
  - Stale closure variable

CATEGORY 5: Security (OWASP-aligned, sandboxed)
  - SQL injection vector (in-memory SQLite only, no real DB)
  - Hardcoded credential in non-sensitive config
  - Missing input validation
  - Insecure randomness (Math.random() for token generation)
  - Path traversal in file operations (sandboxed VFS)

CATEGORY 6: Logic & Algorithm
  - Wrong operator: && vs || in conditionals
  - Wrong comparison: > vs >= in business rules
  - Missing edge case: empty list, zero, negative number
  - Incorrect short-circuit evaluation
```

**Mutation validation pipeline**:
```python
def validate_mutation(original: str, mutated: str, language: str) -> ValidationResult:
    checks = [
        syntax_valid(mutated, language),        # Must still parse
        linter_silent(mutated, language),        # flake8/eslint must not catch it
        type_checker_silent(mutated, language),  # mypy/tsc must not catch it
        not_identical(original, mutated),        # Actually changed something
        realism_check(mutated, language),        # LLM scores plausibility ≥ 0.7
        scope_safe(mutated),                     # No external I/O, no real credentials
    ]
    return ValidationResult(passed=all(checks), failures=[c for c in checks if not c])
```

---

### 3.3 Sandbox Controller

**Purpose**: Activate bugs at runtime without permanent source modification (Phase 1 uses
direct source patching with full rollback; Phase 2 explores runtime interception)

**Phase 1 — Source Patching**:
- Apply mutation directly to source file
- Record in encrypted local manifest (`~/.bughunter/sessions/{session_id}.enc`)
- Git branch isolation: always operate on a `bughunter/session-{id}` branch, never main
- Rollback: `git checkout` the original files from manifest

**Phase 2 — Runtime Interception** (advanced, optional):
- Python: `sys.settrace` + `importlib` hooks for monkey-patching at import time
- JavaScript: Node.js `--require` hook or Proxy objects for runtime interception
- Advantage: Zero source modification; harder to detect by dev inspecting git diff

**Environment gate** (hard requirement):
```python
def safety_gate():
    env = os.environ.get("BUGHUNTER_ENV", "")
    if env != "sandbox":
        raise SystemExit(
            "BugHunterAgent: Not in sandbox environment. "
            "Set BUGHUNTER_ENV=sandbox to activate. "
            "NEVER run in production."
        )
    if not is_local_environment():
        raise SystemExit("BugHunterAgent: Remote/CI environment detected. Aborting.")
```

---

### 3.4 Skill Profiler & ELO Engine

**Purpose**: Model developer's debugging skill accurately; drive adaptive difficulty

**Data schema**:
```json
{
  "developer_id": "sha256_of_git_email",
  "dss": 1247,
  "sessions_total": 23,
  "sessions_won": 18,
  "avg_time_to_find_seconds": 847,
  "hint_usage_rate": 0.22,
  "ai_assist_detected_count": 2,
  "pattern_mastery": {
    "boundary_off_by_one": 0.85,
    "type_coercion": 0.60,
    "async_race_condition": 0.30,
    "security_injection": 0.10
  },
  "spaced_repetition_queue": ["type_coercion", "async_race_condition"],
  "next_session_bct": 3
}
```

**ELO calculation**:
```python
def update_dss(current_dss: int, result: SessionResult) -> int:
    K = 32  # K-factor (sensitivity)
    expected = 1 / (1 + 10 ** ((result.bug_difficulty_elo - current_dss) / 400))
    actual = result.outcome_score  # 1.0=perfect, 0.5=hinted, 0.2=gave_up, 0.0=cheat
    delta = K * (actual - expected)
    return max(0, min(3000, current_dss + int(delta)))
```

**Spaced Repetition**: Implements SM-2 algorithm
- Patterns not seen in N days get re-queued (N determined by past performance on that pattern)
- Mastery threshold: 3 consecutive unaided finds → pattern marked "mastered"
- Mastered patterns still appear at low frequency (forgetting curve maintenance)

---

### 3.5 Anti-Cheat Monitor

**Purpose**: Detect AI-assisted bug discovery; turn detection into a coaching moment

**Detection signals**:
```python
class AntiCheatSignal(Enum):
    INSTANT_NAVIGATION = "Navigated directly to injected line within 60s"
    ZERO_EXPLORATION   = "Opened fewer than 3 files before fix"  
    SUSPICIOUSLY_FAST  = "Fixed in < 2min for BCT-3+ bug"
    PERFECT_FIX        = "Fix exactly matches expected correction verbatim"
    COMMIT_MSG_AI      = "Commit message matches LLM phrasing patterns"
```

**Response protocol**: Never penalize harshly. Log signal. Generate coaching conversation:
> "Looks like you might have had some AI assistance on this one — totally valid in real work!
> But let's talk about *when* AI debugging assistance helps vs. when it creates blind spots..."

---

### 3.6 Knowledge Self-Improvement Pipeline

**Core differentiator: The agent gets measurably better at generating realistic bugs over time.**

```
Weekly Pipeline (Monday 3:00 AM local):
┌─────────────────────────────────────────────┐
│ 1. CRAWL                                    │
│    arXiv: cs.SE, cs.PL                      │
│    Queries:                                 │
│    - "mutation testing program repair"       │
│    - "software bug patterns empirical study" │
│    - "debugging cognitive strategies"        │
│    - "common programming errors analysis"   │
│                                             │
│    CVE Database: new common vulnerabilities  │
│    GitHub: trending bug fix PRs (sanitized) │
│    OWASP: updated top 10 patterns           │
│    ACM SIGPLAN / ISSTA proceedings          │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 2. EXTRACT KNOWLEDGE ATOMS                  │
│    - New bug pattern identified?            │
│      → Add to SECOND-KNOWLEDGE-BRAIN.md     │
│    - New language-specific pitfall?         │
│      → Add to language bug corpus           │
│    - New security vector (sandboxable)?     │
│      → Add to security injection catalog    │
│    - Mutation testing technique improvement?│
│      → Update mutation engine prompts       │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 3. QUALITY GATE                             │
│    - Relevance score ≥ 0.75                 │
│    - No duplicate (semantic dedup)          │
│    - Safety review: can it be sandboxed?    │
│    - Legal: no copyrighted code samples     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 4. VALIDATE NEW MUTATIONS                   │
│    Run new patterns through mutation        │
│    validator on synthetic codebase          │
│    Must pass all 6 validation checks        │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 5. UPDATE & REINDEX                         │
│    - SECOND-KNOWLEDGE-BRAIN.md updated      │
│    - Bug pattern corpus re-embedded         │
│    - Mutation prompt templates updated      │
│    - Run regression: quality of generated   │
│      bugs must not drop on test suite       │
└─────────────────────────────────────────────┘
```

---

### 3.7 Session Reporter

**Purpose**: Generate educational, motivating post-hunt debriefs

**Components**:
- **Bug anatomy report**: What was injected, why it was chosen, how realistic it is in production
- **Debug journey replay**: Timeline of files opened, time spent, hints used
- **Skill analysis**: What this session reveals about dev's strengths/gaps
- **Pattern lesson**: Educational content on the bug category (LLM-generated, knowledge-grounded)
- **Next session preview**: What pattern is queued next based on spaced repetition
- **Codebase scan** (optional): Find similar patterns in dev's real code that could be real bugs

---

## 4. ML/DL Components

### 4.1 Mutation Quality Classifier
**Task**: Score generated mutations for realism and detectability before injection
**Approach**: Fine-tuned `microsoft/codebert-base` on labeled mutation dataset
**Dataset**: 
- Positive: Real commits that introduced then fixed bugs (mined from GitHub)
- Negative: Random/syntactic mutations (poor quality)
**HuggingFace**: `bughunter/mutation-quality-classifier-v1`
**When**: Train in Phase 2; Phase 1 uses LLM scoring as proxy

### 4.2 Developer Behavior Embedder
**Task**: Embed developer's debug behavior (file navigation, time patterns) into vector
**Approach**: Lightweight transformer encoder on session action sequences
**Use**: Detect anomalous (AI-assisted) sessions; personalize difficulty
**Model base**: `sentence-transformers/all-MiniLM-L6-v2` (fast, local)

### 4.3 Bug Pattern Recommender
**Task**: Given developer profile, recommend next bug pattern (spaced repetition + novelty)
**Approach**: Collaborative filtering (Matrix Factorization) on developer × pattern matrix
**Library**: `surprise` or `implicit` (lightweight, CPU-friendly)
**Phase**: Phase 2

### 4.4 Code Context Embedder (RAG for Bug Patterns)
**Task**: Match developer's current code context to most relevant bug patterns
**Approach**: Code embedding + semantic search over bug pattern corpus
**Model**: `microsoft/unixcoder-base` or `BAAI/bge-code-v1` (HuggingFace)
**Use**: Ensure injected bugs are contextually plausible, not generic

---

## 5. Data Architecture

```
~/.bughunter/                  # Local, never synced without consent
├── profile.json               # Developer DSS, history, pattern mastery
├── sessions/
│   ├── {session_id}.enc       # Encrypted session manifest (rollback data)
│   └── {session_id}_report.md # Post-hunt debrief (human readable)
├── knowledge/
│   └── SECOND-KNOWLEDGE-BRAIN.md
└── models/                    # Local ML model cache
    ├── mutation_quality/
    └── code_embedder/

project-local/ (per project):
├── .bughunter/
│   ├── config.yaml            # Project-specific settings
│   └── corpus/                # Project AST cache
└── .env                       # Must contain BUGHUNTER_ENV=sandbox
```

---

## 6. CLI Interface (Phase 1)

```bash
# Initialize BugHunterAgent in a project
bughunter init

# Start a new bug hunt session (agent decides when/what to inject)
bughunter hunt --start

# Request a hint during active session
bughunter hint

# View current session status
bughunter status

# Declare victory (triggers verification + debrief)
bughunter solved

# Give up (triggers rollback + coaching report)
bughunter surrender

# View developer profile and DSS score
bughunter profile

# Force rollback all injections (emergency)
bughunter rollback --all

# View past session reports
bughunter history

# Manually trigger knowledge update
bughunter knowledge update

# Team mode: start shared session
bughunter team --create --name "Wednesday Hunt"
bughunter team --join {session_code}
```

---

## 7. Team Mode (Phase 3)

**Shared Bug Hunt**:
- One session, one injected bug set, multiple devs racing to find it
- Real-time leaderboard (who found what first)
- Same hint pool (if one dev requests hint, all devs see it)
- Session report aggregates all participants' journeys

**Team DSS**: Individual scores updated based on relative performance within team session

---

## 8. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Best ecosystem for AI/ML + code analysis |
| Local SLM | Qwen2.5-Coder-7B via Ollama | Best open-source code model, local privacy |
| External LLM | Claude / GPT / Gemini (user config) | Enhanced mutation quality |
| AST Parsing | tree-sitter (py-tree-sitter) | Universal, incremental, multi-language |
| Code Embeddings | BAAI/bge-code-v1 | SOTA code semantic search |
| Mutation QA | CodeBERT fine-tuned | Realism scoring |
| Spaced Repetition | SM-2 algorithm (anki-style) | Proven memory retention |
| ELO Engine | Custom Python | Elo + K-factor tuning |
| File Watching | watchdog | Monitor dev's file activity |
| Vector Store | ChromaDB (local) | Lightweight, local-first |
| CLI | Typer + Rich | Beautiful terminal output |
| Encryption | cryptography (Fernet) | Session manifest protection |
| Scheduling | APScheduler | Weekly knowledge crawl |
| Web UI (Ph 3) | Next.js + Tailwind | Team mode dashboard |

---

## 9. Improvements vs Original Concept

| Original | Enhancement | Rationale |
|---|---|---|
| Local SLM only | Local SLM + External LLM router | Better mutation quality; user choice |
| Random injection | ELO-adaptive difficulty + spaced repetition | Scientifically proven learning optimization |
| Binary find/not-find | 5-level Socratic hint system | Graduated support preserves learning |
| No anti-cheat | Anti-cheat monitor + coaching | Addresses the core threat to the learning goal |
| Single developer | Team mode + leaderboard | Viral growth + social learning |
| Static bug patterns | Weekly crawl → SECOND-KNOWLEDGE-BRAIN | Self-improving, ever-growing pattern library |
| Code-only bugs | Security vulnerability scenarios (OWASP) | Highest-value skill gap in industry |
| Terminal only | Web UI for team sessions | Better UX for collaborative use |
| No ML | Mutation quality classifier + behavior embedder | Quantifiable improvement over time |

---

## 10. Constraints & Risks

| Risk | Mitigation |
|---|---|
| Production environment activation | Hard env gate; CI detection; multiple safety checks |
| Bug breaks dev's entire project | Validation pipeline + instant rollback command |
| Developer frustration (too hard) | ELO ensures 70% success rate target; hint system |
| Privacy (code sent to cloud LLM) | Default local-only; explicit opt-in for cloud LLM |
| Copyright of mined bug patterns | Only use commit-level diffs, no full code reproduction |
| Agent itself has bugs | Extensive test suite on mutation engine; rollback is always safe |

---

*Document version: 0.1.0 | Created: Project initialization*
