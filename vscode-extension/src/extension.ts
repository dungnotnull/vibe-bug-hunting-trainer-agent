import * as vscode from 'vscode';
import * as path from 'path';

const API_BASE = vscode.workspace.getConfiguration('bughunter').get<string>('serverUrl', 'http://localhost:8000');

let statusBarItem: vscode.StatusBarItem;
let sessionViewProvider: SessionViewProvider;
let profileViewProvider: ProfileViewProvider;
let historyViewProvider: HistoryViewProvider;

export function activate(context: vscode.ExtensionContext) {
    console.log('BugHunterAgent extension activated');

    // Status bar DSS indicator
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'bughunter.showProfile';
    statusBarItem.tooltip = 'BugHunterAgent — DSS Score';
    context.subscriptions.push(statusBarItem);
    updateStatusBar();

    // Tree view providers
    sessionViewProvider = new SessionViewProvider();
    profileViewProvider = new ProfileViewProvider();
    historyViewProvider = new HistoryViewProvider();

    vscode.window.registerTreeDataProvider('bughunter.sessionView', sessionViewProvider);
    vscode.window.registerTreeDataProvider('bughunter.profileView', profileViewProvider);
    vscode.window.registerTreeDataProvider('bughunter.historyView', historyViewProvider);

    // Commands
    context.subscriptions.push(
        vscode.commands.registerCommand('bughunter.showProfile', showProfile),
        vscode.commands.registerCommand('bughunter.showSession', showSession),
        vscode.commands.registerCommand('bughunter.requestHint', requestHint),
        vscode.commands.registerCommand('bughunter.claimSolved', claimSolved),
        vscode.commands.registerCommand('bughunter.surrender', surrender)
    );

    // Auto-check session on startup
    if (vscode.workspace.getConfiguration('bughunter').get<boolean>('autoCheckSession', true)) {
        checkActiveSession();
    }

    // Periodic refresh
    setInterval(updateStatusBar, 60000);
}

export function deactivate() {
    console.log('BugHunterAgent extension deactivated');
}

function getApiUrl(endpoint: string): string {
    return `${API_BASE}/api${endpoint}`;
}

async function apiFetch(endpoint: string, options: RequestInit = {}): Promise<any> {
    const url = getApiUrl(endpoint);
    try {
        const response = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`API call failed: ${endpoint}`, error);
        throw error;
    }
}

async function updateStatusBar() {
    try {
        const profile = await apiFetch('/profile');
        statusBarItem.text = `$(bug) ${profile.dss}`;
        statusBarItem.tooltip = `DSS: ${profile.dss}/3000 | Sessions: ${profile.sessions_total} | Win Rate: ${(profile.win_rate * 100).toFixed(0)}%`;
        statusBarItem.show();
        await vscode.commands.executeCommand('setContext', 'bughunter:dss', profile.dss);
    } catch {
        statusBarItem.text = '$(bug) --';
        statusBarItem.hide();
    }
}

async function checkActiveSession() {
    try {
        const status = await apiFetch('/hunt/status');
        await vscode.commands.executeCommand(
            'setContext',
            'bughunter:sessionActive',
            status.phase === 'hunting' || status.phase === 'injected'
        );
    } catch {
        await vscode.commands.executeCommand('setContext', 'bughunter:sessionActive', false);
    }
}

async function showProfile() {
    try {
        const profile = await apiFetch('/profile');
        const panel = vscode.window.createWebviewPanel(
            'bughunterProfile',
            'BugHunterAgent — Developer Profile',
            vscode.ViewColumn.One,
            { enableScripts: true }
        );
        panel.webview.html = generateProfileHtml(profile);
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to load profile: ${error}`);
    }
}

async function showSession() {
    try {
        const status = await apiFetch('/hunt/status');
        const panel = vscode.window.createWebviewPanel(
            'bughunterSession',
            'BugHunterAgent — Active Session',
            vscode.ViewColumn.Two,
            { enableScripts: true }
        );
        panel.webview.html = generateSessionHtml(status);
    } catch (error) {
        vscode.window.showInformationMessage('No active bug hunt session.');
    }
}

async function requestHint() {
    try {
        const response = await apiFetch('/hunt/hint', { method: 'POST' });
        const hintLevel = response.hint?.level || 1;
        const hintContent = response.hint?.content || 'Keep debugging...';

        const style = vscode.workspace.getConfiguration('bughunter').get<string>('hintsDisplayStyle', 'panel');
        if (style === 'panel') {
            const panel = vscode.window.createWebviewPanel(
                'bughunterHint',
                `BugHunter Hint — Level ${hintLevel}`,
                vscode.ViewColumn.Beside,
                { enableScripts: false }
            );
            panel.webview.html = generateHintHtml(hintLevel, hintContent);
        } else if (style === 'notification') {
            vscode.window.showInformationMessage(`Hint (Level ${hintLevel}): ${hintContent}`);
        } else {
            vscode.window.showInformationMessage(`Hint (Level ${hintLevel}): ${hintContent}`, 'OK');
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to get hint: ${error}`);
    }
}

async function claimSolved() {
    const answer = await vscode.window.showInformationMessage(
        'Are you sure you found the bug?',
        { modal: true },
        'Yes, I fixed it!',
        'No, keep hunting'
    );
    if (answer !== 'Yes, I fixed it!') { return; }

    try {
        const result = await apiFetch('/hunt/claim', { method: 'POST' });
        const panel = vscode.window.createWebviewPanel(
            'bughunterSolved',
            'BugHunterAgent — Bug Found!',
            vscode.ViewColumn.One,
            { enableScripts: true }
        );
        panel.webview.html = generateResultHtml(result);
        updateStatusBar();
        await vscode.commands.executeCommand('setContext', 'bughunter:sessionActive', false);
    } catch (error) {
        vscode.window.showErrorMessage(`Verification failed: ${error}`);
    }
}

async function surrender() {
    const answer = await vscode.window.showWarningMessage(
        'Are you sure you want to give up? All injected bugs will be revealed.',
        { modal: true },
        'Yes, I give up',
        'No, keep trying'
    );
    if (answer !== 'Yes, I give up') { return; }

    try {
        const result = await apiFetch('/hunt/surrender', { method: 'POST' });
        const panel = vscode.window.createWebviewPanel(
            'bughunterSurrender',
            'BugHunterAgent — Session Surrendered',
            vscode.ViewColumn.One,
            { enableScripts: true }
        );
        panel.webview.html = generateResultHtml(result);
        updateStatusBar();
        await vscode.commands.executeCommand('setContext', 'bughunter:sessionActive', false);
    } catch (error) {
        vscode.window.showErrorMessage(`Surrender failed: ${error}`);
    }
}

function generateProfileHtml(profile: any): string {
    const winRate = (profile.win_rate * 100).toFixed(1);
    const dssPercent = (profile.dss / 3000 * 100).toFixed(1);
    return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>BugHunter Profile</title>
<style>
  body { font-family: var(--vscode-font-family, monospace); padding: 20px; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
  h1 { color: var(--vscode-textLink-foreground); }
  .dss-bar { width: 100%; height: 20px; background: var(--vscode-input-background); border-radius: 10px; overflow: hidden; margin: 10px 0; }
  .dss-fill { height: 100%; background: linear-gradient(90deg, #4ade80, #fbbf24, #ef4444); border-radius: 10px; transition: width 0.5s; }
  .metric { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--vscode-panel-border); }
  .label { opacity: 0.7; }
  .value { font-weight: bold; }
</style></head><body>
<h1>BugHunterAgent — Developer Profile</h1>
<h2>DSS: ${profile.dss}/3000</h2>
<div class="dss-bar"><div class="dss-fill" style="width:${dssPercent}%"></div></div>
<div class="metric"><span class="label">Total Sessions</span><span class="value">${profile.sessions_total}</span></div>
<div class="metric"><span class="label">Sessions Won</span><span class="value">${profile.sessions_won}</span></div>
<div class="metric"><span class="label">Win Rate</span><span class="value">${winRate}%</span></div>
<div class="metric"><span class="label">Avg Time to Find</span><span class="value">${profile.avg_time_to_find_seconds.toFixed(0)}s</span></div>
<div class="metric"><span class="label">Hint Usage Rate</span><span class="value">${(profile.hint_usage_rate * 100).toFixed(1)}%</span></div>
<div class="metric"><span class="label">AI Assist Detected</span><span class="value">${profile.ai_assist_detected_count}</span></div>
<div class="metric"><span class="label">Next BCT Level</span><span class="value">BCT-${profile.next_session_bct}</span></div>
<div style="margin-top:20px;">
  <button onclick="vscode.postMessage({command:'refresh'})">Refresh</button>
</div>
</body></html>`;
}

function generateSessionHtml(status: any): string {
    return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Active Session</title>
<style>
  body { font-family: var(--vscode-font-family); padding: 20px; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
  .stat { padding: 12px; margin: 8px 0; background: var(--vscode-input-background); border-radius: 6px; }
  .stat-label { font-size: 12px; opacity: 0.7; }
  .stat-value { font-size: 24px; font-weight: bold; }
  .phase-active { color: #4ade80; }
  .bugs { color: #fbbf24; font-size: 36px; }
</style></head><body>
<h1>Active Bug Hunt Session</h1>
<div class="stat"><div class="stat-label">Session ID</div><div class="stat-value">${status.session_id || 'N/A'}</div></div>
<div class="stat"><div class="stat-label">Phase</div><div class="stat-value phase-active">${status.phase || 'idle'}</div></div>
<div class="stat"><div class="stat-label">Bugs Injected</div><div class="stat-value bugs">${status.bugs_injected || 0}</div></div>
<div class="stat"><div class="stat-label">Hints Used</div><div class="stat-value">${status.hints_used || 0}</div></div>
</body></html>`;
}

function generateHintHtml(level: number, content: string): string {
    const colors = ['#4ade80', '#fbbf24', '#f59e0b', '#ef4444', '#dc2626'];
    const color = colors[Math.min(level - 1, 4)];
    return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Hint</title>
<style>
  body { font-family: var(--vscode-font-family); padding: 20px; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
  .hint-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; color: white; font-weight: bold; margin-bottom: 16px; }
  .hint-content { font-size: 16px; line-height: 1.6; padding: 20px; border-left: 4px solid ${color}; background: var(--vscode-input-background); border-radius: 0 8px 8px 0; }
</style></head><body>
<div class="hint-badge" style="background:${color}">Level ${level}</div>
<div class="hint-content">${content}</div>
<p style="opacity:0.5;margin-top:20px;">Each hint costs DSS points. Use sparingly.</p>
</body></html>`;
}

function generateResultHtml(result: any): string {
    const delta = result.dss_delta || 0;
    const deltaColor = delta > 0 ? '#4ade80' : '#ef4444';
    return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Session Result</title>
<style>
  body { font-family: var(--vscode-font-family); padding: 20px; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
  h1 { font-size: 24px; }
  .result-card { padding: 20px; margin: 10px 0; background: var(--vscode-input-background); border-radius: 8px; }
  .dss { font-size: 32px; font-weight: bold; }
  .dss-delta { color: ${deltaColor}; font-size: 20px; }
</style></head><body>
<h1>${result.outcome === 'found_independently' ? '🎉 Bug Found!' : 'Session Ended'}</h1>
<div class="result-card">
  <div class="dss">DSS: ${result.dss_before} → ${result.dss_after} <span class="dss-delta">${delta > 0 ? '+' : ''}${delta}</span></div>
</div>
<div class="result-card">
  <p>Outcome: ${result.outcome}</p>
  <p>Time: ${result.time_to_discovery_seconds ? result.time_to_discovery_seconds + 's' : 'N/A'}</p>
  <p>Hints Used: ${(result.hints_used || []).length}</p>
</div>
<p style="opacity:0.5;">Report saved. Keep practicing!</p>
</body></html>`;
}

class SessionViewProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    refresh() { this._onDidChangeTreeData.fire(); }

    getTreeItem(element: vscode.TreeItem): vscode.TreeItem { return element; }

    async getChildren(): Promise<vscode.TreeItem[]> {
        try {
            const status = await apiFetch('/hunt/status');
            if (!status.session_id) {
                return [new vscode.TreeItem('No active session', vscode.TreeItemCollapsibleState.None)];
            }
            return [
                new vscode.TreeItem(`Session: ${status.session_id?.substring(0, 12)}`, vscode.TreeItemCollapsibleState.None),
                new vscode.TreeItem(`Phase: ${status.phase}`, vscode.TreeItemCollapsibleState.None),
                new vscode.TreeItem(`Bugs: ${status.bugs_injected}`, vscode.TreeItemCollapsibleState.None),
                new vscode.TreeItem(`Hints: ${status.hints_used}`, vscode.TreeItemCollapsibleState.None),
            ];
        } catch {
            return [new vscode.TreeItem('API server not reachable', vscode.TreeItemCollapsibleState.None)];
        }
    }
}

class ProfileViewProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    refresh() { this._onDidChangeTreeData.fire(); }

    getTreeItem(element: vscode.TreeItem): vscode.TreeItem { return element; }

    async getChildren(): Promise<vscode.TreeItem[]> {
        try {
            const profile = await apiFetch('/profile');
            return [
                new vscode.TreeItem(`DSS: ${profile.dss}/3000`, vscode.TreeItemCollapsibleState.None),
                new vscode.TreeItem(`Sessions: ${profile.sessions_won}/${profile.sessions_total} won`, vscode.TreeItemCollapsibleState.None),
                new vscode.TreeItem(`Win Rate: ${(profile.win_rate * 100).toFixed(0)}%`, vscode.TreeItemCollapsibleState.None),
                new vscode.TreeItem(`Next: BCT-${profile.next_session_bct}`, vscode.TreeItemCollapsibleState.None),
            ];
        } catch {
            return [new vscode.TreeItem('Profile not available', vscode.TreeItemCollapsibleState.None)];
        }
    }
}

class HistoryViewProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    refresh() { this._onDidChangeTreeData.fire(); }

    getTreeItem(element: vscode.TreeItem): vscode.TreeItem { return element; }

    async getChildren(): Promise<vscode.TreeItem[]> {
        try {
            const data = await apiFetch('/sessions?limit=10');
            const sessions = data.sessions || [];
            if (sessions.length === 0) {
                return [new vscode.TreeItem('No past sessions', vscode.TreeItemCollapsibleState.None)];
            }
            return sessions.map((s: any) =>
                new vscode.TreeItem(
                    `${s.session_id?.substring(0, 12)} — ${s.phase || 'unknown'}`,
                    vscode.TreeItemCollapsibleState.None
                )
            );
        } catch {
            return [new vscode.TreeItem('History not available', vscode.TreeItemCollapsibleState.None)];
        }
    }
}
