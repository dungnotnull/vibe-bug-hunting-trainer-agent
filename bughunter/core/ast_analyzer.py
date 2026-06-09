"""Multi-language AST analyzer using tree-sitter.

Identifies injection candidates by walking AST and scoring nodes for:
- detectability (how hard to notice the bug)
- realism (how plausible in real code)
- difficulty (BCT tier matching)

Phase 1: Python. Phase 2: JS/TS, Go, Rust.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
import tree_sitter_go as tsgo
import tree_sitter_rust as tsrust
from loguru import logger
from tree_sitter import Language, Node, Parser, Tree

from bughunter.schemas.models import (
    BugComplexityTier,
    InjectionCandidate,
    Language as LangEnum,
    PatternCategory,
)

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())
GO_LANGUAGE = Language(tsgo.language())
RUST_LANGUAGE = Language(tsrust.language())

LANGUAGE_MAP = {
    LangEnum.PYTHON: PY_LANGUAGE,
    LangEnum.JAVASCRIPT: JS_LANGUAGE,
    LangEnum.TYPESCRIPT: TS_LANGUAGE,
    LangEnum.GO: GO_LANGUAGE,
    LangEnum.RUST: RUST_LANGUAGE,
}

EXTENSION_MAP = {
    ".py": LangEnum.PYTHON,
    ".js": LangEnum.JAVASCRIPT,
    ".mjs": LangEnum.JAVASCRIPT,
    ".cjs": LangEnum.JAVASCRIPT,
    ".ts": LangEnum.TYPESCRIPT,
    ".tsx": LangEnum.TYPESCRIPT,
    ".go": LangEnum.GO,
    ".rs": LangEnum.RUST,
}

IGNORE_PATTERNS = [
    "test_", "conftest", "__init__", "setup.py",
    "migrations/", "node_modules/", "vendor/",
    ".spec.", ".test.", "_test.",
]

FUNCTIONAL_NODE_TYPES = {
    "function_definition", "function_declaration", "method_declaration",
    "method_definition", "arrow_function", "function",
}

CONDITIONAL_NODE_TYPES = {
    "if_statement", "elif_clause", "else_clause",
    "switch_statement", "case_clause", "match_statement",
    "ternary_expression", "conditional_expression",
}

LOOP_NODE_TYPES = {
    "for_statement", "for_in_statement", "while_statement",
    "do_statement", "list_comprehension", "dictionary_comprehension",
}

ASSIGNMENT_NODE_TYPES = {
    "assignment", "augmented_assignment", "variable_declaration",
    "variable_declarator", "lexical_declaration",
}

EXCLUDE_NODE_TYPES = {
    "comment", "string", "string_fragment", "ERROR",
    "pass_statement", "expression_statement",
    "import_statement", "import_declaration",
    "export_statement", "decorator",
}


class ASTAnalyzer:
    """Parses source files and extracts scored injection candidates."""

    def __init__(
        self,
        project_path: Path,
        language: Optional[LangEnum] = None,
        target_bct: BugComplexityTier = BugComplexityTier.BCT_2,
        recent_files: Optional[list[str]] = None,
    ):
        self.project_path = project_path.resolve()
        self.language = language or self._detect_language()
        self.target_bct = target_bct
        self.recent_files = set(recent_files or [])
        self._parser = Parser(LANGUAGE_MAP[self.language])

    def _detect_language(self) -> LangEnum:
        """Detect primary language by scanning file extensions."""
        counts: dict[str, int] = {}
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", "__pycache__")]
            for f in files:
                ext = Path(f).suffix
                if ext in EXTENSION_MAP:
                    lang = EXTENSION_MAP[ext]
                    counts[lang.value] = counts.get(lang.value, 0) + 1
        best = max(counts, key=counts.get, default="python")
        return LangEnum(best)

    def analyze(self, max_candidates: int = 20) -> list[InjectionCandidate]:
        """Scan project and return ranked injection candidates."""
        candidates: list[InjectionCandidate] = []
        for file_path in self._walk_project():
            try:
                candidates.extend(self._analyze_file(file_path))
            except Exception as e:
                logger.debug(f"AST skipped {file_path}: {e}")

        candidates = self._deduplicate(candidates)
        candidates.sort(key=lambda c: (c.realism_score + c.detectability_score) / 2, reverse=True)
        return candidates[:max_candidates]

    def _should_skip(self, file_path: Path) -> bool:
        path_str = str(file_path).replace("\\", "/")
        for pattern in IGNORE_PATTERNS:
            if pattern in path_str.lower():
                return True
        return False

    def _walk_project(self) -> Iterator[Path]:
        ext_map = {ext: lang for ext, lang in EXTENSION_MAP.items() if lang == self.language}
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d not in ("node_modules", "venv", "__pycache__", ".git", "dist", "build", "target")
            ]
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix in ext_map and not self._should_skip(fpath):
                    yield fpath

    def _analyze_file(self, file_path: Path) -> list[InjectionCandidate]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        if not source.strip():
            return []

        tree = self._parser.parse(source.encode("utf-8"))
        candidates: list[InjectionCandidate] = []
        rel_path = str(file_path.relative_to(self.project_path))

        self._walk_node(tree.root_node, source, rel_path, candidates)
        return candidates

    def _walk_node(
        self,
        node: Node,
        source: str,
        rel_path: str,
        candidates: list[InjectionCandidate],
        depth: int = 0,
    ):
        if depth > 30:
            return
        node_type = node.type

        if node_type in EXCLUDE_NODE_TYPES:
            for child in node.children:
                self._walk_node(child, source, rel_path, candidates, depth + 1)
            return

        candidate = self._score_node(node, source, rel_path)
        if candidate:
            candidates.append(candidate)

        for child in node.children:
            self._walk_node(child, source, rel_path, candidates, depth + 1)

    def _score_node(
        self,
        node: Node,
        source: str,
        rel_path: str,
    ) -> Optional[InjectionCandidate]:
        node_type = node.type

        if node_type in EXCLUDE_NODE_TYPES:
            return None

        line_count = node.end_point[0] - node.start_point[0] + 1
        if line_count < 2:
            return None

        snippet = source[node.start_byte : node.end_byte]
        if len(snippet) < 20:
            return None

        category = self._classify_category(node_type, snippet)
        detectability = self._score_detectability(node_type, snippet)
        realism = self._score_realism(node_type, snippet, rel_path)
        difficulty = self._score_difficulty(node_type, snippet, category)

        is_recent = rel_path in self.recent_files
        if is_recent:
            realism += 0.15
            detectability += 0.10

        complexity = self._cyclomatic_complexity_gate(node_type, snippet)
        if complexity < 3 and category != PatternCategory.TYPE_COERCION:
            realism -= 0.15

        return InjectionCandidate(
            file=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            ast_node_type=node_type,
            pattern_category=category,
            detectability_score=min(1.0, max(0.0, detectability)),
            realism_score=min(1.0, max(0.0, realism)),
            difficulty_level=difficulty,
            function_name=self._extract_function_name(node, source),
            source_snippet=snippet[:500],
        )

    def _classify_category(self, node_type: str, snippet: str) -> PatternCategory:
        if node_type in LOOP_NODE_TYPES:
            return PatternCategory.BOUNDARY
        if "async" in snippet.lower() or "await" in snippet:
            return PatternCategory.ASYNC_CONCURRENCY
        if node_type in CONDITIONAL_NODE_TYPES:
            if any(kw in snippet for kw in ("password", "token", "auth", "secret", "key")):
                return PatternCategory.SECURITY
            return PatternCategory.LOGIC_ALGORITHM
        if node_type in ASSIGNMENT_NODE_TYPES:
            if any(kw in snippet for kw in ("copy", "deepcopy", "clone")):
                return PatternCategory.STATE_MUTATION
        if any(kw in snippet for kw in ("==", "===", "!==", "type", "typeof", "int(", "str(")):
            return PatternCategory.TYPE_COERCION
        if any(kw in snippet for kw in ("slice", "[:", "[0:", "[1:", "range(")):
            return PatternCategory.BOUNDARY
        return PatternCategory.LOGIC_ALGORITHM

    def _score_detectability(self, node_type: str, snippet: str) -> float:
        score = 0.5
        if node_type in CONDITIONAL_NODE_TYPES:
            score += 0.15
        if node_type in ASSIGNMENT_NODE_TYPES:
            score += 0.05
        if len(snippet) > 200:
            score += 0.10
        if "//" in snippet or "#" in snippet:
            score -= 0.10
        return min(1.0, max(0.0, score))

    def _score_realism(self, node_type: str, snippet: str, rel_path: str) -> float:
        score = 0.55
        if node_type in FUNCTIONAL_NODE_TYPES:
            score += 0.15
        if node_type in CONDITIONAL_NODE_TYPES | LOOP_NODE_TYPES:
            score += 0.10
        if any(kw in rel_path.lower() for kw in ("service", "handler", "controller", "util", "core")):
            score += 0.10
        if len(snippet) > 100:
            score += 0.10
        if "raise" in snippet or "throw" in snippet:
            score -= 0.10
        return min(1.0, max(0.0, score))

    def _score_difficulty(
        self, node_type: str, snippet: str, category: PatternCategory
    ) -> BugComplexityTier:
        if category in (PatternCategory.SECURITY,):
            return BugComplexityTier.BCT_4
        if category == PatternCategory.ASYNC_CONCURRENCY:
            if "race" in snippet.lower() or "mutex" in snippet.lower():
                return BugComplexityTier.BCT_4
            return BugComplexityTier.BCT_3
        if category == PatternCategory.STATE_MUTATION:
            return BugComplexityTier.BCT_3
        if node_type in CONDITIONAL_NODE_TYPES and len(snippet) > 300:
            return BugComplexityTier.BCT_3
        if node_type in LOOP_NODE_TYPES:
            return BugComplexityTier.BCT_2
        return BugComplexityTier.BCT_1

    def _cyclomatic_complexity_gate(self, node_type: str, snippet: str) -> int:
        count = 1
        for keyword in ("if ", "elif ", "else:", "for ", "while ", "&&", "||", "match ", "case "):
            count += snippet.count(keyword)
        return count

    def _extract_function_name(self, node: Node, source: str) -> Optional[str]:
        for child in node.children:
            if child.type in ("identifier", "name", "property_identifier"):
                return source[child.start_byte : child.end_byte]
        for child in node.children:
            if child.type in ("def", "function", "async"):
                for sibling in child.parent.children if child.parent else []:
                    if sibling.type in ("identifier", "name"):
                        return source[sibling.start_byte : sibling.end_byte]
        return None

    def _deduplicate(self, candidates: list[InjectionCandidate]) -> list[InjectionCandidate]:
        seen: set[tuple[str, int]] = set()
        result: list[InjectionCandidate] = []
        for c in candidates:
            key = (c.file, c.line_start)
            if key not in seen:
                seen.add(key)
                result.append(c)
        return result
