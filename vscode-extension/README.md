# BugHunterAgent VS Code Extension

Covert debug skill training directly in your editor.

## Features

- **DSS Status Bar**: Real-time Developer Skill Score in the status bar
- **Socratic Hints**: 5-level hint system delivered as panel, notification, or inline
- **Session Dashboard**: Tree views for active session, profile, and history
- **Inline Reports**: Rich HTML session reports rendered in WebView panels
- **One-Click Actions**: Request hint, claim solved, or surrender from the editor toolbar

## Usage

1. Start the BugHunterAgent API server: `bughunter hunt --start`
2. Open VS Code in your sandbox project
3. Use the BugHunterAgent activity bar icon or commands palette:
   - `BugHunter: Show Profile & DSS Score`
   - `BugHunter: Request Hint` (during active session)
   - `BugHunter: I Found the Bug!` (when you fix it)
   - `BugHunter: Give Up` (surrender and see the solution)

## Requirements

- BugHunterAgent Python package installed and running
- VS Code 1.85+
