"""Agent Loop — the core state machine driving the bug hunt lifecycle.

States: IDLE → INJECTED → HUNTING → DISCOVERED/SURRENDERED
The agent operates covertly during INJECTION and HUNTING phases.
Only reveals itself post-discovery (Coach persona).
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from loguru import logger

from bughunter.core.ast_analyzer import ASTAnalyzer
from bughunter.core.config import Config
from bughunter.core.git_isolation import GitIsolation, GitBranchError
from bughunter.core.llm_client import LLMClient
from bughunter.core.manifest import ManifestStore
from bughunter.core.mutation_engine import MutationEngine
from bughunter.core.safety_gate import SafetyGate
from bughunter.core.skill_profiler import SkillProfiler
from bughunter.schemas.models import (
    AntiCheatSignal,
    Hint,
    HintLevel,
    Language,
    MutationRecord,
    SessionOutcome,
    SessionPhase,
    SessionResult,
    SessionState,
)


class AgentLoop:
    """Primary state machine coordinating the full bug hunt lifecycle."""

    def __init__(self, config: Config):
        self.config = config
        self.state = SessionState()
        self._manifest = ManifestStore()
        self._profiler = SkillProfiler()
        self._llm: Optional[LLMClient] = None
        self._git: Optional[GitIsolation] = None
        self._engine: Optional[MutationEngine] = None
        self._session_start_time: Optional[float] = None
        self._files_explored: list[str] = []
        self._watchdog_thread: Optional[threading.Thread] = None
        self._stop_watchdog = threading.Event()
        self._on_discovery_callback: Optional[Callable] = None
        self._active_session_id: Optional[str] = None
        self._hints_given: list[Hint] = []
        self._session_finalized: bool = False

    def load_active_session(self) -> Optional[SessionState]:
        """Restore session state from encrypted manifest (cross-process persistence)."""
        sid_path = Path.home() / ".bughunter" / ".active_session"
        if not sid_path.exists():
            return None
        try:
            sid = sid_path.read_text().strip()
            data = self._manifest.load_session(sid)
            self._active_session_id = sid
            self.state = SessionState(
                session_id=data["session_id"],
                phase=SessionPhase(data["phase"]),
                project_path=Path(data.get("project_path", ".")) if data.get("project_path") else None,
                original_branch=data.get("original_branch"),
                session_branch=data.get("session_branch"),
                hints_given=data.get("hints_given", 0),
                started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            )
            for mdata in data.get("mutations", []):
                self.state.mutations.append(MutationRecord(**mdata))
            if self.state.session_id:
                self._active_session_id = self.state.session_id
            logger.debug(f"Loaded active session {sid} from manifest")
            return self.state
        except Exception as e:
            logger.debug(f"No active session: {e}")
            return None

    def _persist_active_session_id(self):
        sid_path = Path.home() / ".bughunter" / ".active_session"
        sid_path.parent.mkdir(parents=True, exist_ok=True)
        if self.state.session_id:
            sid_path.write_text(self.state.session_id)
        elif sid_path.exists():
            sid_path.unlink()

    # ─── Public API ─────────────────────────────────────────────────────────

    def start_hunt(
        self,
        project_path: Optional[Path] = None,
        language: Optional[Language] = None,
        max_bugs: Optional[int] = None,
    ) -> SessionState:
        """Initialize and inject bugs for a new hunt session."""
        SafetyGate.check()

        project_path = (project_path or Path.cwd()).resolve()
        max_bugs = max_bugs or self.config.max_concurrent_bugs

        self.state = SessionState(
            session_id=uuid.uuid4().hex[:16],
            phase=SessionPhase.IDLE,
            project_path=project_path,
            started_at=datetime.utcnow(),
        )
        self._session_start_time = time.time()
        self._files_explored = []

        self._init_components(project_path, language)

        try:
            self._git = GitIsolation(project_path)
            original_branch = self._git.snapshot()
            self.state.original_branch = original_branch
            session_branch = self._git.create_session_branch(self.state.session_id)
            self.state.session_branch = session_branch
        except GitBranchError as e:
            logger.error(f"Git isolation failed: {e}")
            raise

        candidates = self._scan_project(project_path, language, max_bugs)
        mutations = self._inject_bugs(project_path, candidates, language or Language.PYTHON)
        self.state.mutations = mutations
        self.state.phase = SessionPhase.INJECTED

        self._manifest.save_session(self.state)
        self._persist_active_session_id()
        self._start_watchdog(project_path)

        self.state.phase = SessionPhase.HUNTING
        logger.info(f"Hunt session {self.state.session_id} active with {len(mutations)} bugs injected")
        return self.state

    def request_hint(self) -> Hint:
        """Deliver the next Socratic hint."""
        if self.state.phase != SessionPhase.HUNTING:
            raise RuntimeError(f"Cannot request hint in phase {self.state.phase}")

        level = HintLevel(self.state.hints_given + 1)
        if level > HintLevel.REVEAL:
            level = HintLevel.REVEAL

        content = self._generate_hint(level)
        hint = Hint(level=level, content=content, dss_penalty=self._profiler.get_hint_penalty(level))
        self.state.hints_given += 1
        self._manifest.save_session(self.state)

        self._hints_given.append(hint)

        if level == HintLevel.REVEAL:
            # Reveal doesn't auto-end — dev must still call surrender or solved
            return hint

        return hint

    def claim_solved(self) -> SessionResult:
        """Developer claims they found and fixed the bug."""
        if self.state.phase not in (SessionPhase.HUNTING, SessionPhase.INJECTED):
            raise RuntimeError(f"No active hunt session in phase {self.state.phase}")

        time_elapsed = int(time.time() - (self._session_start_time or time.time()))
        self._stop_watchdog_signal()

        result = self._build_result(SessionOutcome.FOUND_INDEPENDENTLY, time_elapsed)
        return self._finalize_session(result)

    def surrender(self) -> SessionResult:
        """Developer gives up."""
        time_elapsed = int(time.time() - (self._session_start_time or time.time()))
        self._stop_watchdog_signal()
        result = self._build_result(SessionOutcome.SURRENDERED, time_elapsed)
        return self._finalize_session(result)

    # ─── Internal ───────────────────────────────────────────────────────────

    def _init_components(self, project_path: Path, language: Optional[Language]):
        self._llm = LLMClient(self.config)
        self._engine = MutationEngine(
            llm_client=self._llm,
            max_retries=self.config.max_mutation_retries,
            realism_threshold=self.config.mutation_realism_threshold,
        )

    def _scan_project(
        self, project_path: Path, language: Optional[Language], max_bugs: int
    ) -> list:
        analyzer = ASTAnalyzer(
            project_path=project_path,
            language=language,
            target_bct=self._profiler.get_next_bct(),
        )
        return analyzer.analyze(max_candidates=max_bugs * 3)

    def _inject_bugs(
        self, project_path: Path, candidates: list, language: Language
    ) -> list[MutationRecord]:
        mutations: list[MutationRecord] = []
        injected_count = 0

        for candidate in candidates:
            if injected_count >= self.config.max_concurrent_bugs:
                break

            file_path = project_path / candidate.file
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    source = f.read()

                if candidate.source_snippet and candidate.source_snippet[:50] in source:
                    start = source.index(candidate.source_snippet[:50])
                    end = start + len(candidate.source_snippet)
                    actual_code = source[start:end]
                else:
                    actual_code = source

                if not actual_code.strip():
                    continue

                _, mutation, _ = self._engine.generate_mutation(
                    candidate, actual_code, language
                )
                self._engine.apply_mutation_to_file(file_path, mutation)
                mutations.append(mutation)
                injected_count += 1

            except Exception as e:
                logger.warning(f"Failed to inject in {candidate.file}: {e}")

        return mutations

    def _generate_hint(self, level: HintLevel) -> str:
        mutations = self.state.mutations
        if not mutations:
            return "No active bugs to hint about."

        m = mutations[0]
        hints = {
            HintLevel.CATEGORY: f"This bug falls into the '{m.pattern_category.value}' category.",
            HintLevel.FILE: f"Look at the file: {m.file}",
            HintLevel.FUNCTION: f"Focus around line {m.line_start} in {m.file}.",
            HintLevel.LINE_RANGE: f"Lines {m.line_start}-{m.line_end} in {m.file} contain the issue.",
            HintLevel.REVEAL: self._build_reveal_message(m),
        }
        return hints.get(level, "Think about what changed recently in your code.")

    def _build_reveal_message(self, mutation: MutationRecord) -> str:
        return (
            f"[REVEAL] Bug in {mutation.file}, lines {mutation.line_start}-{mutation.line_end}.\n"
            f"Pattern: {mutation.bug_pattern_id} ({mutation.pattern_category.value})\n"
            f"Original code was replaced with a subtle {mutation.difficulty.name} mutation."
        )

    def _mark_surrendered(self):
        self.state.phase = SessionPhase.SURRENDERED
        self._stop_watchdog_signal()
        result = self._build_result(SessionOutcome.SURRENDERED, int(time.time() - (self._session_start_time or time.time())))
        self._finalize_session(result)

    def _build_result(self, outcome: SessionOutcome, time_elapsed: int) -> SessionResult:
        m = self.state.mutations[0] if self.state.mutations else None
        return SessionResult(
            session_id=self.state.session_id or "",
            language=Language.PYTHON,
            started_at=self.state.started_at or datetime.utcnow(),
            ended_at=datetime.utcnow(),
            outcome=outcome,
            bug_pattern_id=m.bug_pattern_id if m else "",
            bug_pattern_name=m.bug_pattern_id if m else "",
            time_to_discovery_seconds=time_elapsed if outcome == SessionOutcome.FOUND_INDEPENDENTLY else None,
            hints_used=list(self._hints_given),
            dss_before=self._profiler.get_dss(),
            files_explored=list(self._files_explored),
            mutations=list(self.state.mutations),
        )

    def _finalize_session(self, result: SessionResult) -> SessionResult:
        if self._session_finalized:
            return result
        self._session_finalized = True

        self._rollback_injections()

        if self.state.original_branch and self._git:
            try:
                self._git.rollback(delete_branch=True)
            except Exception as e:
                logger.error(f"Git rollback failed: {e}")

        new_dss = self._profiler.update_dss(result)
        self._profiler.save_profile()
        self._manifest.save_result(result)

        self.state.phase = (
            SessionPhase.DISCOVERED
            if result.outcome == SessionOutcome.FOUND_INDEPENDENTLY
            else SessionPhase.SURRENDERED
        )
        self._manifest.save_session(self.state)

        # Clear persistence marker so next CLI invocation knows session is done
        sid_path = Path.home() / ".bughunter" / ".active_session"
        if sid_path.exists():
            sid_path.unlink()

        if self._llm:
            self._llm.close()

        return result

    def _rollback_injections(self):
        if not self._engine or not self.state.project_path:
            return
        for mutation in self.state.mutations:
            if not mutation.rolled_back:
                try:
                    file_path = self.state.project_path / mutation.file
                    self._engine.rollback_mutation(file_path, mutation)
                except Exception as e:
                    logger.error(f"Rollback failed for {mutation.mutation_id}: {e}")

    def _start_watchdog(self, project_path: Path):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class FileTracker(FileSystemEventHandler):
                def __init__(self, files_list: list[str], project_root: Path):
                    self.files = files_list
                    self.root = project_root

                def on_modified(self, event):
                    if event.src_path and not event.is_directory:
                        try:
                            rel = str(Path(event.src_path).relative_to(self.root))
                            if rel not in self.files:
                                self.files.append(rel)
                        except ValueError:
                            pass

            self._stop_watchdog.clear()
            handler = FileTracker(self._files_explored, project_path)
            observer = Observer()
            observer.schedule(handler, str(project_path), recursive=True)
            observer.start()

            def watch_loop():
                while not self._stop_watchdog.is_set():
                    time.sleep(0.5)
                observer.stop()
                observer.join(timeout=2)

            self._watchdog_thread = threading.Thread(target=watch_loop, daemon=True)
            self._watchdog_thread.start()
        except ImportError:
            logger.debug("watchdog not available, file tracking disabled")

    def _stop_watchdog_signal(self):
        self._stop_watchdog.set()
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=5)
