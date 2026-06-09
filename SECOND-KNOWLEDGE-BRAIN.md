# SECOND-KNOWLEDGE-BRAIN.md

> **BugHunterAgent Living Knowledge Base**
> The agent's accumulated intelligence on bug patterns, debugging psychology, and mutation techniques.
> Auto-updated weekly by crawl pipeline. Manually curated by maintainers.
> Every agent session loads this as core context — the agent grows smarter over time.
>
> **Labels**:
> - `[VERIFIED]` — peer-reviewed paper or official specification
> - `[EMPIRICAL]` — mining study from real codebases (GitHub, StackOverflow, etc.)
> - `[COMMUNITY]` — expert community source (OWASP, iFixit-equivalent for bugs)
> - `[INFERRED]` — derived by LLM; treat with lower confidence, flag for review
>
> `confidence: 0.0–1.0` | `last_updated: date`

---

## TABLE OF CONTENTS

1. [Bug Pattern Library — Boundary & Off-by-One](#1-bug-pattern-library--boundary--off-by-one)
2. [Bug Pattern Library — Type & Coercion](#2-bug-pattern-library--type--coercion)
3. [Bug Pattern Library — Async & Concurrency](#3-bug-pattern-library--async--concurrency)
4. [Bug Pattern Library — State & Mutation](#4-bug-pattern-library--state--mutation)
5. [Bug Pattern Library — Security (OWASP-aligned)](#5-bug-pattern-library--security-owasp-aligned)
6. [Bug Pattern Library — Logic & Algorithm](#6-bug-pattern-library--logic--algorithm)
7. [Debugging Psychology & Pedagogy](#7-debugging-psychology--pedagogy)
8. [Mutation Testing Research](#8-mutation-testing-research)
9. [Language-Specific Pitfalls](#9-language-specific-pitfalls)
10. [Crawl Log](#10-crawl-log)

---

## 1. Bug Pattern Library — Boundary & Off-by-One

### BP-001 | Classic Off-by-One in Loop Bounds
**Tags**: `boundary`, `loop`, `python`, `javascript`, `universal`
**Status**: [EMPIRICAL] **Confidence**: 0.97
**Source**: "An Empirical Study of Software Bugs" — Zhivich & Cunningham, IEEE S&P
**Last Updated**: Project Init

**Pattern**: Using `<` vs `<=` (or `>` vs `>=`) in loop termination conditions.

```python
# CORRECT
for i in range(len(items)):
    process(items[i])

# INJECTED BUG (off-by-one, skips last element):
for i in range(len(items) - 1):
    process(items[i])
```

**Why realistic**: Fence-post errors account for ~25% of all logic bugs in production code.
Especially dangerous in pagination, batch processing, and array slicing.

**Detectability**: Medium — manifests only when processing the boundary element.
Logs may show correct count minus 1 (subtle).

**Best injection contexts**: Pagination logic, data batch processing, string iteration,
array accumulation functions.

**DSS range**: BCT-2 (DSS 800–1400)

**Teaching point**: Always test with: empty collection, 1 element, exactly N elements, N+1 elements.
Name variables clearly: `limit` vs `count` vs `index`.

---

### BP-002 | Slice Boundary Error
**Tags**: `boundary`, `slice`, `python`, `javascript`
**Status**: [EMPIRICAL] **Confidence**: 0.92
**Source**: GitHub bug-fix commit mining study (internal)
**Last Updated**: Project Init

**Pattern**: Incorrect slice endpoint causing silent data truncation.

```python
# CORRECT (returns first `limit` items):
results = items[0:limit]

# INJECTED BUG (returns limit-1 items):
results = items[0:limit - 1]
```

**JavaScript variant**:
```javascript
// CORRECT
const page = items.slice(offset, offset + pageSize);

// INJECTED BUG (loses last item):
const page = items.slice(offset, offset + pageSize - 1);
```

**Detectability**: Low-medium — UI shows one fewer item than expected; user rarely notices unless
counting carefully or processing exactly at boundary.

**BCT**: 2 | **Injection priority**: High (very common in API response pagination)

---

### BP-003 | Zero-Based vs One-Based Index Confusion
**Tags**: `boundary`, `index`, `universal`
**Status**: [EMPIRICAL] **Confidence**: 0.90
**Source**: NIST Software Error Analysis 2023
**Last Updated**: Project Init

**Pattern**: Mixing 0-based array indexing with 1-based human counting.

```python
# CORRECT (get Nth item, 1-indexed from user input):
def get_nth_item(items, n):
    return items[n - 1]  # Convert from 1-based to 0-based

# INJECTED BUG (double-subtracts when n is 1, returns wrong item):
def get_nth_item(items, n):
    return items[n]  # Off by one, throws IndexError at end
```

**BCT**: 2 | **Language priority**: Python, JavaScript, Java

---

## 2. Bug Pattern Library — Type & Coercion

### BP-101 | JavaScript Loose Equality Trap
**Tags**: `type`, `coercion`, `javascript`, `typescript`
**Status**: [VERIFIED] **Confidence**: 0.96
**Source**: ECMAScript Specification; "JavaScript: The Good Parts" — Crockford
**Last Updated**: Project Init

**Pattern**: Using `==` instead of `===` in security-critical comparisons.

```javascript
// CORRECT (strict equality):
if (userId === requestUserId) { grantAccess(); }

// INJECTED BUG (loose equality — "0" == 0 is true!):
if (userId == requestUserId) { grantAccess(); }
```

**Why dangerous**: `"0" == 0` is `true`, `null == undefined` is `true`,
`"" == false` is `true`. In authentication contexts, this is a security bug.

**Detectability**: Very low — code looks identical at a glance; only `=` vs `==` vs `===` differs.

**BCT**: 2–3 | Security overlap: OWASP A01 (Broken Access Control)

---

### BP-102 | Python Integer Division Surprise
**Tags**: `type`, `division`, `python`
**Status**: [EMPIRICAL] **Confidence**: 0.93
**Source**: Python bug tracker analysis; StackOverflow mining study
**Last Updated**: Project Init

**Pattern**: Unintended float-to-int truncation.

```python
# CORRECT (float division):
average = total / count

# INJECTED BUG (Python 3 integer division — only if both ints):
average = total // count  # Silent floor division
```

**Alternate injection** (more subtle):
```python
# INJECTED: force integer context prematurely
average = int(total) / count  # If total was 99.9, becomes 99
```

**BCT**: 1–2 | Especially dangerous in statistical calculations, financial rounding.

---

### BP-103 | Null/None/Undefined Falsy Chain
**Tags**: `type`, `null`, `python`, `javascript`
**Status**: [EMPIRICAL] **Confidence**: 0.91
**Source**: "Null References: The Billion Dollar Mistake" — Tony Hoare; GitHub mining
**Last Updated**: Project Init

**Python pattern**:
```python
# CORRECT:
if user_count is None:
    return default_count

# INJECTED BUG (fails when user_count is 0 — falsy but valid!):
if not user_count:
    return default_count
```

**JavaScript pattern**:
```javascript
// CORRECT:
const name = user.name ?? 'Anonymous';

// INJECTED BUG (empty string '' triggers fallback unintentionally):
const name = user.name || 'Anonymous';
```

**BCT**: 2 | Very common in form validation, API response handling.

---

## 3. Bug Pattern Library — Async & Concurrency

### BP-201 | Missing Await — The Silent Async Bug
**Tags**: `async`, `javascript`, `typescript`, `python`
**Status**: [EMPIRICAL] **Confidence**: 0.95
**Source**: "Async/Await vs Promises" empirical study — ICSE 2023
**Last Updated**: Project Init

**Pattern**: Forgetting `await` causes function to return a Promise object instead of resolved value.

```javascript
// CORRECT:
async function getUser(id) {
  const user = await fetchUser(id);  // resolves to User object
  return user.name;
}

// INJECTED BUG (user is a Promise, not User):
async function getUser(id) {
  const user = fetchUser(id);  // Missing await!
  return user.name;  // Returns undefined — no error thrown
}
```

**Python variant** (`asyncio`):
```python
# CORRECT:
async def process():
    result = await fetch_data()
    
# INJECTED BUG:
async def process():
    result = fetch_data()  # Returns coroutine object, not result
```

**Why devious**: No exception is thrown. Code "works" but returns wrong values.
The bug only manifests when the returned value is used downstream.

**BCT**: 3 | **Detection hint**: Check if function returns Promise-like values unexpectedly.

---

### BP-202 | Race Condition via Shared Mutable State
**Tags**: `concurrency`, `race_condition`, `python`, `javascript`
**Status**: [VERIFIED] **Confidence**: 0.88
**Source**: "Race Condition Detection" — PLDI 2022; Thread Sanitizer documentation
**Last Updated**: Project Init

**Pattern**: Non-atomic read-modify-write on shared counter in concurrent context.

```python
# CORRECT (atomic):
import threading
counter_lock = threading.Lock()
def increment():
    with counter_lock:
        counter += 1

# INJECTED BUG (non-atomic, race condition):
def increment():
    global counter
    temp = counter      # Read
    time.sleep(0.0001)  # Agent can insert tiny delay to make race more likely
    counter = temp + 1  # Write (another thread may have incremented between)
```

**BCT**: 4 | Hard to reproduce consistently — classic Heisenbug pattern.
Use `time.sleep(0.0001)` insertion to make race condition more reliably triggerable in sandbox.

---

### BP-203 | Stale Closure in JavaScript Loop
**Tags**: `async`, `closure`, `javascript`
**Status**: [EMPIRICAL] **Confidence**: 0.94
**Source**: MDN Documentation; JavaScript bug tracker mining
**Last Updated**: Project Init

**Pattern**: Classic closure-in-loop bug — all callbacks share the same variable reference.

```javascript
// CORRECT (block-scoped let):
for (let i = 0; i < 5; i++) {
  setTimeout(() => console.log(i), 100);  // Prints 0,1,2,3,4
}

// INJECTED BUG (function-scoped var — all print 5):
for (var i = 0; i < 5; i++) {
  setTimeout(() => console.log(i), 100);  // All print 5!
}
```

**Real-world variant** (more realistic injection):
```javascript
// CORRECT:
const handlers = items.map((item) => () => processItem(item));

// INJECTED: item captured by reference in outer scope
let item;
const handlers = items.map(() => () => processItem(item));
// (Only last item is ever processed)
```

**BCT**: 3

---

## 4. Bug Pattern Library — State & Mutation

### BP-301 | Mutable Default Argument (Python)
**Tags**: `state`, `mutation`, `python`
**Status**: [VERIFIED] **Confidence**: 0.98
**Source**: Python official documentation; Python Anti-Patterns Guide
**Last Updated**: Project Init

**Pattern**: Using mutable object as default argument — shared across all calls.

```python
# CORRECT:
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items

# INJECTED BUG (classic Python gotcha):
def add_item(item, items=[]):  # Same list reused every call!
    items.append(item)
    return items
```

**Why it matters**: Second call to `add_item("b")` returns `["a", "b"]` not `["b"]`.
Silent data accumulation bug — no error raised, wrong results accumulate.

**BCT**: 2 | Very common in Python codebases, especially data processing pipelines.

---

### BP-302 | Shallow Copy Bug
**Tags**: `state`, `copy`, `python`, `javascript`
**Status**: [EMPIRICAL] **Confidence**: 0.92
**Source**: Python copy module documentation; Real-world bug report mining
**Last Updated**: Project Init

**Python pattern**:
```python
# CORRECT (deep copy for nested structures):
import copy
def update_config(base_config, overrides):
    config = copy.deepcopy(base_config)
    config.update(overrides)
    return config

# INJECTED BUG (shallow copy — nested objects still shared):
def update_config(base_config, overrides):
    config = base_config.copy()  # Only top-level copied!
    config.update(overrides)
    return config
    # Mutation of nested dict in `config` modifies `base_config`
```

**BCT**: 3 | Especially dangerous in configuration management, state management systems.

---

## 5. Bug Pattern Library — Security (OWASP-aligned)

> ⚠️ All security patterns in this section are designed for **sandboxed injection only**.
> In-memory SQLite only. No real credentials. No real network calls.
> Governed by safety rules in CLAUDE.md §3.4.

### BP-401 | SQL Injection Vector (Sandboxed)
**Tags**: `security`, `sql_injection`, `owasp_a03`, `python`
**Status**: [COMMUNITY] **Confidence**: 0.96
**Source**: OWASP Top 10 2021 — A03: Injection
**Last Updated**: Project Init

**Pattern**: String concatenation instead of parameterized query.

```python
# CORRECT (parameterized):
cursor.execute("SELECT * FROM users WHERE email = ?", (email,))

# INJECTED BUG (SQL injection vector):
cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")
# email = "x' OR '1'='1" → returns all users
```

**Sandbox implementation**: Uses in-memory SQLite only. No real database connection.
**Teaching value**: OWASP A03 is the #3 most critical web application vulnerability.

**BCT**: 3–4 | Only inject for developers at DSS ≥ 1400.

---

### BP-402 | Insecure Randomness for Token Generation
**Tags**: `security`, `cryptography`, `python`, `javascript`
**Status**: [VERIFIED] **Confidence**: 0.94
**Source**: OWASP Cryptographic Failures (A02); Python `secrets` module documentation
**Last Updated**: Project Init

**Python pattern**:
```python
# CORRECT (cryptographically secure):
import secrets
token = secrets.token_hex(32)

# INJECTED BUG (predictable randomness):
import random
token = ''.join(random.choices('abcdef0123456789', k=32))
```

**JavaScript pattern**:
```javascript
// CORRECT:
const token = crypto.randomBytes(32).toString('hex');

// INJECTED BUG:
const token = Math.random().toString(36).substring(2);
```

**BCT**: 3 | Silent bug — generates valid-looking tokens that are cryptographically weak.

---

### BP-403 | Path Traversal (Sandboxed VFS)
**Tags**: `security`, `path_traversal`, `owasp_a01`, `python`
**Status**: [COMMUNITY] **Confidence**: 0.91
**Source**: OWASP Path Traversal; CWE-22
**Last Updated**: Project Init

**Pattern**: Missing path sanitization allows directory escape.

```python
# CORRECT:
import os
def read_file(filename):
    safe_path = os.path.join('/sandbox/files', os.path.basename(filename))
    with open(safe_path) as f:
        return f.read()

# INJECTED BUG (path traversal possible):
def read_file(filename):
    path = f'/sandbox/files/{filename}'  # filename = '../../etc/passwd'
    with open(path) as f:
        return f.read()
```

**Sandbox**: VFS (virtual filesystem) is used — no real filesystem access.
**BCT**: 4

---

## 6. Bug Pattern Library — Logic & Algorithm

### BP-501 | Wrong Logical Operator (AND vs OR)
**Tags**: `logic`, `boolean`, `universal`
**Status**: [EMPIRICAL] **Confidence**: 0.93
**Source**: Static analysis tool false-positive studies; GitHub mining
**Last Updated**: Project Init

**Pattern**: Substituting `and`/`&&` for `or`/`||` in guard conditions.

```python
# CORRECT (reject if either field is empty):
if not username or not password:
    raise ValueError("All fields required")

# INJECTED BUG (only rejects if BOTH empty — either alone passes!):
if not username and not password:
    raise ValueError("All fields required")
```

**BCT**: 2 | Especially dangerous in authentication, input validation.
Detectability: Low — looks correct at first glance, only logic is wrong.

---

### BP-502 | Wrong Comparison Operator in Business Rule
**Tags**: `logic`, `comparison`, `universal`
**Status**: [EMPIRICAL] **Confidence**: 0.91
**Source**: Code review study — IEEE Transactions on Software Engineering 2022
**Last Updated**: Project Init

**Pattern**: `>` vs `>=` in business threshold checks.

```python
# CORRECT (discount applies to orders of exactly 100 or more):
if order_total >= 100:
    apply_discount()

# INJECTED BUG (discount misses exact 100):
if order_total > 100:
    apply_discount()
```

**Real-world impact**: Off-by-one in financial thresholds is a classic fintech bug.
Customer at exactly the boundary gets wrong behavior; no error, no log.

**BCT**: 2

---

## 7. Debugging Psychology & Pedagogy

### DP-001 | The Einstellung Effect in Debugging
**Tags**: `psychology`, `pedagogy`, `debugging_cognition`
**Status**: [VERIFIED] **Confidence**: 0.87
**Source**: "Cognitive Aspects of Software Debugging" — Vessey, 1985; replicated 2019
**Last Updated**: Project Init

**Finding**: Developers who form an initial hypothesis about a bug's cause are 40% slower to
find the real cause when their hypothesis is wrong — they keep looking for evidence that confirms
their first guess (confirmation bias / Einstellung effect).

**Implication for BugHunterAgent**:
- Inject bugs in files/functions the developer is NOT currently working on to trigger this effect
- Hint Level 1 ("The bug is in the data transformation layer") should redirect their mental model
  without giving away the specific location
- Session reports should highlight if the developer showed Einstellung behavior (long time in
  wrong file before pivot)

---

### DP-002 | Optimal Difficulty for Skill Development (Flow State)
**Tags**: `psychology`, `pedagogy`, `difficulty`, `elo`
**Status**: [VERIFIED] **Confidence**: 0.92
**Source**: Csikszentmihalyi's Flow Theory; "Deliberate Practice" — Ericsson 1993, 2016
**Last Updated**: Project Init

**Finding**: Skill improves fastest when challenge is slightly above current skill level.
Too easy → boredom, no learning. Too hard → frustration, no learning.
Optimal zone: 70–80% success rate with genuine effort.

**Implication for BugHunterAgent**:
- ELO system targets 72% unaided bug-find rate across all sessions
- If developer wins 3 sessions in a row unaided → increase BCT
- If developer fails 2 sessions in a row → decrease BCT and add optional warmup session
- Spaced repetition prevents over-training on comfortable patterns

---

### DP-003 | The Testing Illusion — Why Passing Tests Don't Mean No Bugs
**Tags**: `psychology`, `pedagogy`, `testing`
**Status**: [VERIFIED] **Confidence**: 0.90
**Source**: "Why Mutation Testing Works" — Jia & Harman, IEEE TSE 2011
**Last Updated**: Project Init

**Finding**: Test suites with 90%+ line coverage still miss 30–40% of real bugs.
Mutation testing reveals test suite quality far better than coverage metrics.

**Implication for BugHunterAgent**:
- Always inject bugs that PASS the existing test suite (this is a validation requirement)
- The fact that the dev's tests pass despite the injected bug is itself a teaching moment
- Session report should note: "Your test suite didn't catch this — here's why"
- Recommend specific test cases to add that would have caught the bug

---

## 8. Mutation Testing Research

### MT-001 | Mutation Operators with Highest Real-Bug Correlation
**Tags**: `mutation_testing`, `research`, `operator_selection`
**Status**: [VERIFIED] **Confidence**: 0.89
**Source**: "An Analysis of Mutation Operators" — Andrews et al., ICSE 2005; replicated 2021
**Last Updated**: Project Init

**Finding**: Not all mutation operators are equally valuable. The following operators produce
mutations that most closely resemble real bugs:

| Operator | Correlation to Real Bugs | Priority |
|---|---|---|
| AOR (Arithmetic Operator Replacement) | 0.78 | High |
| ROR (Relational Operator Replacement) | 0.82 | High |
| LCR (Logical Connector Replacement) | 0.75 | High |
| SDL (Statement Deletion) | 0.71 | Medium |
| SVR (Scalar Variable Replacement) | 0.68 | Medium |
| BCR (Boolean to Constant Replacement) | 0.55 | Low |

**Implication for BugHunterAgent**: Prioritize ROR (BP-502, BP-503) and LCR (BP-501) operators
in mutation generation. Avoid pure statement deletion — too obvious to developers.

---

### MT-002 | Subsumption Hierarchy — Reducing Equivalent Mutations
**Tags**: `mutation_testing`, `equivalent_mutations`, `research`
**Status**: [VERIFIED] **Confidence**: 0.85
**Source**: "Mutation Subsumption" — Kurtz et al., ISSTA 2016
**Last Updated**: Project Init

**Finding**: ~30% of generated mutations are "equivalent mutations" — syntactically different
but semantically identical to the original (i.e., not actually bugs). These waste training value.

**Common equivalent mutation patterns to AVOID**:
- Replacing `x + 0` mutation → still computes same value
- Replacing `x * 1` → same result
- Negating condition in dead code branch

**Implication for BugHunterAgent**: The mutation validation pipeline must include semantic
equivalence checking. LLM-based realism scoring helps here — equivalent mutations score low
on "likely to cause behavioral difference."

---

## 9. Language-Specific Pitfalls

### LP-001 | Python: `is` vs `==` for Value Comparison
**Tags**: `python`, `identity`, `equality`, `common_mistake`
**Status**: [VERIFIED] **Confidence**: 0.97
**Source**: Python documentation; CPython implementation
**Last Updated**: Project Init

**Pattern**:
```python
# CORRECT (value equality):
if response_code == 200:
    handle_success()

# INJECTED BUG (identity check — works "by accident" for small integers due to
#               CPython integer caching, but fails for larger values):
if response_code is 200:  # Works for -5 to 256, fails outside that range!
    handle_success()
```

**Why tricky**: In interactive Python, `response_code is 200` is often `True` because CPython
caches small integers. In production with larger codes or different runtime, fails.

**BCT**: 2 | Detectability: Very low (works in tests, fails in production edge cases).

---

### LP-002 | JavaScript: `this` Context Loss in Callbacks
**Tags**: `javascript`, `this`, `context`, `arrow_functions`
**Status**: [VERIFIED] **Confidence**: 0.94
**Source**: MDN JavaScript Reference; ECMAScript specification
**Last Updated**: Project Init

**Pattern**:
```javascript
class EventHandler {
  constructor() {
    this.count = 0;
  }
  
  // CORRECT (arrow function preserves `this`):
  handleClick = () => {
    this.count++;
  }
  
  // INJECTED BUG (regular function loses `this` in callback):
  // handleClick() { this.count++; }  // `this` is undefined in strict mode
  
  // More subtle injection — convert method to regular function in addEventListener:
  setup() {
    // CORRECT: document.addEventListener('click', this.handleClick);
    // INJECTED: document.addEventListener('click', function() { this.count++; });
  }
}
```

**BCT**: 3

---

## 10. Crawl Log

```
[Project Init] Seeded knowledge base:
  - Bug Pattern Library: 15 patterns across 6 categories
  - Debugging Psychology: 3 research-backed pedagogical findings
  - Mutation Testing Research: 2 key papers summarized
  - Language-Specific: 2 entries (Python, JavaScript)
  Total knowledge atoms: 22 (manual seed)

  Automated crawl: NOT YET RUNNING (activates after Sprint 2.4)
  Target crawl sources: arXiv cs.SE, NVD CVE, OWASP, GitHub trending bug-fix PRs
  Next scheduled crawl: After Phase 2 completion

--- AUTOMATED CRAWL ENTRIES WILL BE APPENDED BELOW THIS LINE ---
```

---

## Appendix: Knowledge Atom Templates

### Bug Pattern Template
```markdown
### BP-XXX | [Pattern Name]
**Tags**: `category`, `language`, `keywords`
**Status**: [VERIFIED/EMPIRICAL/COMMUNITY/INFERRED]
**Confidence**: 0.XX
**Source**: [Paper title, conference, year] or [Source name]
**Last Updated**: YYYY-MM-DD

**Pattern**: [Description of the bug pattern]

```[language]
// CORRECT:
[correct code]

// INJECTED BUG (explanation):
[buggy code with inline comment]
```

**Why realistic**: [Explanation of real-world occurrence]
**Detectability**: Low/Medium/High — [reason]
**BCT**: [1-5] | [Additional context]
**Teaching point**: [What developer should learn]
```

### Research Template
```markdown
### MT-XXX | [Paper/Finding Title]
**Tags**: `research`, `category`, `keywords`
**Status**: [VERIFIED/EMPIRICAL]
**Confidence**: 0.XX
**Source**: [Full citation]
**Last Updated**: YYYY-MM-DD

**Finding**: [Key finding in 1-3 sentences]

**Implication for BugHunterAgent**: [Concrete action or system design impact]
```

---

*Auto-updated by `scripts/knowledge_updater.py` (weekly, Monday 3AM local).*
*Total atoms: 22 (seed) | Crawl runs: 0 | Agent version: 0.1.0*
