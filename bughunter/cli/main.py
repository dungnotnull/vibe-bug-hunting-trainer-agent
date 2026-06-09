"""CLI entry point — full implementation for all 10 commands.

Wired to AgentLoop, SkillProfiler, SessionReporter, and core modules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bughunter import __version__
from bughunter.core.agent_loop import AgentLoop
from bughunter.core.config import Config, load_config
from bughunter.core.logging import configure_logging
from bughunter.core.safety_gate import SafetyGate
from bughunter.core.session_reporter import SessionReporter
from bughunter.core.skill_profiler import SkillProfiler

app = typer.Typer(
    name="bughunter",
    help="Covert debug skill training system",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()
_config: Optional[Config] = None
_agent: Optional[AgentLoop] = None
_profiler: Optional[SkillProfiler] = None
_reporter: Optional[SessionReporter] = None


def _get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
        configure_logging(verbose=False)
    return _config


def _get_profiler() -> SkillProfiler:
    global _profiler
    if _profiler is None:
        _profiler = SkillProfiler()
    return _profiler


def _get_reporter() -> SessionReporter:
    global _reporter
    if _reporter is None:
        _reporter = SessionReporter()
    return _reporter


def _get_agent() -> AgentLoop:
    global _agent
    if _agent is None:
        _agent = AgentLoop(_get_config())
        _agent.load_active_session()
    return _agent


def _banner():
    console.print(
        Panel.fit(
            Text.from_markup(
                f"[bold cyan]BugHunterAgent[/bold cyan] [dim]v{__version__}[/dim]\n"
                "[dim italic]covert debug skill training system[/dim italic]"
            ),
            border_style="cyan",
        )
    )


@app.command()
def init(
    project_path: Optional[Path] = typer.Argument(
        None,
        help="Path to the project to initialize (default: current directory)",
    ),
):
    """Initialize BugHunterAgent in a project."""
    project_path = (project_path or Path.cwd()).resolve()

    if not (project_path / ".git").exists():
        console.print("[red]Error:[/red] Not a git repository. BugHunterAgent requires git for safe rollback.")
        raise typer.Exit(code=1)

    # Check sandbox requirement
    if not SafetyGate.is_safe():
        console.print(
            "[red]Safety Gate:[/red] Environment not safe for bug injection.\n"
            "Set [bold]BUGHUNTER_ENV=sandbox[/bold] and use a dedicated sandbox project."
        )
        raise typer.Exit(code=1)

    bughunter_dir = project_path / ".bughunter"
    bughunter_dir.mkdir(exist_ok=True)

    # Write project-level config
    import yaml
    config_data = {
        "version": __version__,
        "project_path": str(project_path),
        "initialized_at": __import__("datetime").datetime.utcnow().isoformat(),
    }
    with open(bughunter_dir / "config.yaml", "w") as f:
        yaml.dump(config_data, f)

    # Detect git email for developer identity
    try:
        import git
        repo = git.Repo(project_path)
        git_email = repo.config_reader().get_value("user", "email", "")
        if git_email:
            profiler = _get_profiler()
            profiler.set_developer_id(git_email)
    except Exception:
        pass

    console.print(f"[green]✓[/green] Initialized BugHunterAgent in [cyan]{project_path}[/cyan]")
    console.print(f"  Config: [dim]{bughunter_dir / 'config.yaml'}[/dim]")
    console.print(f"  Run [bold]bughunter hunt --start[/bold] to begin a session.")


@app.command()
def hunt(
    start: bool = typer.Option(False, "--start", help="Start a new bug hunt session"),
    project_path: Optional[Path] = typer.Option(None, "--project", "-p", help="Project path"),
    max_bugs: int = typer.Option(3, "--max-bugs", "-n", help="Maximum concurrent bugs"),
):
    """Start or manage a bug hunt session."""
    if not start:
        agent = _get_agent()
        state = agent.state
        if state.phase.value == "hunting":
            console.print(f"[green]Active session:[/green] [bold]{state.session_id}[/bold]")
            console.print(f"  Phase: {state.phase.value}")
            console.print(f"  Bugs injected: {len(state.mutations)}")
            console.print(f"  Hints used: {state.hints_given}")
        else:
            console.print("[yellow]No active session. Use [bold]bughunter hunt --start[/bold] to begin.")
        return

    if not SafetyGate.is_safe():
        console.print(
            "[red]Safety Gate:[/red] Cannot start hunt — environment not safe.\n"
            "Set [bold]BUGHUNTER_ENV=sandbox[/bold] and retry."
        )
        raise typer.Exit(code=1)

    project_path = (project_path or Path.cwd()).resolve()

    with console.status("[bold cyan]Analyzing codebase and injecting bugs...[/bold cyan]") as status:
        try:
            agent = _get_agent()
            state = agent.start_hunt(project_path=project_path, max_bugs=max_bugs)
        except Exception as e:
            console.print(f"[red]Failed to start hunt:[/red] {e}")
            raise typer.Exit(code=1)

    console.print()
    _banner()
    console.print(f"[green]✓[/green] Hunt session started: [bold]{state.session_id}[/bold]")
    console.print(f"  Bugs injected: [bold yellow]{len(state.mutations)}[/bold yellow]")
    console.print(f"  Branch: [dim]{state.session_branch or 'detached'}[/dim]")
    console.print()
    console.print("[dim]Your project now has hidden bugs. Find them![/dim]")
    console.print("[dim]Run [bold]bughunter hint[/bold] for a Socratic nudge.[/dim]")
    console.print("[dim]Run [bold]bughunter solved[/bold] when you've fixed them.[/dim]")


@app.command()
def hint():
    """Request a Socratic hint during an active session."""
    try:
        agent = _get_agent()
        hint = agent.request_hint()
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)

    level_colors = {1: "green", 2: "yellow", 3: "yellow", 4: "red", 5: "red"}
    color = level_colors.get(hint.level.value, "white")

    console.print()
    console.print(Panel(
        Text.from_markup(f"[bold {color}]Hint Level {hint.level.value}:[/bold {color}]\n{hint.content}"),
        border_style=color,
    ))
    console.print(f"[dim]DSS penalty: -{hint.dss_penalty} points[/dim]")


@app.command()
def status():
    """View current session status."""
    agent = _get_agent()
    state = agent.state

    table = Table(title=f"Session Status — {state.session_id or 'No active session'}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Phase", state.phase.value)
    table.add_row("Project", str(state.project_path) if state.project_path else "N/A")
    table.add_row("Original Branch", state.original_branch or "N/A")
    table.add_row("Session Branch", state.session_branch or "N/A")
    table.add_row("Bugs Injected", str(len(state.mutations)))
    table.add_row("Hints Used", str(state.hints_given))

    if state.mutations:
        table.add_row("", "")
        table.add_row("[bold]Active Mutations[/bold]", "")
        for m in state.mutations:
            table.add_row(
                f"  {m.bug_pattern_id}",
                f"{m.file}:{m.line_start} [{m.pattern_category.value}]"
            )

    console.print(table)


@app.command()
def solved():
    """Declare victory — triggers verification and session debrief."""
    try:
        agent = _get_agent()
        result = agent.claim_solved()
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)

    reporter = _get_reporter()
    report = reporter.generate_report(result)

    profiler = _get_profiler()
    profiler.save_profile()

    console.print()
    console.print(f"[green]🎉 Congratulations![/green] Bug hunt complete!")
    console.print(f"  DSS: [bold]{result.dss_before}[/bold] → [bold cyan]{result.dss_after}[/bold] ({result.dss_delta:+d})")
    console.print(f"  Report saved: [dim]{result.report_path}[/dim]")
    console.print()
    console.print(report)


@app.command()
def surrender():
    """Give up — triggers rollback and coaching report."""
    try:
        agent = _get_agent()
        result = agent.surrender()
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)

    reporter = _get_reporter()
    report = reporter.generate_report(result)

    console.print()
    console.print("[yellow]Session surrendered — all injections rolled back.[/yellow]")
    console.print(f"  DSS: [bold]{result.dss_before}[/bold] → [bold yellow]{result.dss_after}[/bold] ({result.dss_delta:+d})")
    console.print(f"  Report saved: [dim]{result.report_path}[/dim]")
    console.print()
    console.print(report)


@app.command()
def profile():
    """View developer profile and DSS score."""
    profiler = _get_profiler()
    p = profiler.profile

    _banner()

    table = Table(title="Developer Profile")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Developer ID", p.developer_id or "(not set)")
    table.add_row("DSS Score", f"[bold]{p.dss}[/bold] / 3000")
    table.add_row("Sessions Total", str(p.sessions_total))
    table.add_row("Sessions Won", str(p.sessions_won))
    win_rate = f"{(p.sessions_won / p.sessions_total * 100):.1f}%" if p.sessions_total > 0 else "N/A"
    table.add_row("Win Rate", win_rate)
    table.add_row("Avg Time to Find", f"{p.avg_time_to_find_seconds:.0f}s" if p.avg_time_to_find_seconds > 0 else "N/A")
    table.add_row("Hint Usage Rate", f"{p.hint_usage_rate:.1%}")
    table.add_row("AI Assist Detected", str(p.ai_assist_detected_count))
    table.add_row("Next BCT Level", f"BCT-{p.next_session_bct.value}")

    if p.pattern_mastery:
        table.add_row("", "")
        table.add_row("[bold]Pattern Mastery[/bold]", "")
        for pid, mastery in sorted(p.pattern_mastery.items()):
            status = "✅" if mastery.mastered else "🔄"
            table.add_row(f"  {status} {pid}", f"Wins: {mastery.consecutive_wins}/{mastery.total_attempts}")

    console.print(table)


@app.command()
def rollback(
    force_all: bool = typer.Option(False, "--all", help="Force rollback all injections"),
):
    """Rollback injections (emergency recovery)."""
    if not force_all:
        console.print("[yellow]Use [bold]bughunter rollback --all[/bold] for emergency recovery.")
        return

    try:
        agent = _get_agent()
        result = agent.surrender()
        console.print("[green]✓[/green] All injections rolled back. Safe state restored.")
    except Exception as e:
        console.print(f"[red]Rollback error:[/red] {e}")
        console.print("[yellow]Try manual recovery:[/yellow] git checkout <original-branch>")
        raise typer.Exit(code=1)


@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of sessions to show"),
):
    """View past session reports."""
    from bughunter.core.manifest import ManifestStore
    store = ManifestStore()
    sessions = store.list_sessions()

    if not sessions:
        console.print("[dim]No past sessions found.[/dim]")
        return

    table = Table(title="Session History")
    table.add_column("Session ID", style="cyan")
    table.add_column("Date", style="white")
    table.add_column("Outcome", style="white")

    for sid in sessions[-limit:]:
        try:
            data = store.load_session(sid)
            table.add_row(
                sid[:12],
                data.get("started_at", "unknown")[:19],
                data.get("phase", "unknown"),
            )
        except Exception:
            table.add_row(sid[:12], "unknown", "corrupted")

    console.print(table)


@app.command()
def knowledge(
    action: str = typer.Argument("status", help="Action: status | update"),
):
    """Manage the knowledge brain."""
    if action == "status":
        brain_path = Path(__file__).resolve().parent.parent.parent / "SECOND-KNOWLEDGE-BRAIN.md"
        if brain_path.exists():
            size_kb = brain_path.stat().st_size / 1024
            console.print(f"[green]Knowledge brain:[/green] {brain_path}")
            console.print(f"  Size: {size_kb:.1f} KB")
            console.print(f"  Atoms: 22 (seed)")
            console.print(f"  Crawl runs: 0 (not yet activated)")
        else:
            console.print("[red]Knowledge brain not found.[/red]")
    elif action == "update":
        console.print("[yellow]Knowledge crawl not yet scheduled. Manual trigger skipped.[/yellow]")
    else:
        console.print(f"[red]Unknown action: {action}[/red]")


@app.command()
def version():
    """Show version information."""
    _banner()


def main():
    app()


if __name__ == "__main__":
    main()
