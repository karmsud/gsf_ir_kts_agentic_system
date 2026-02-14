const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');

module.exports = async function freshnessAudit({ vscode, outputChannel, workspaceRoot, runCli = runCliJson } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);

  const scope = await vscode.window.showInputBox({
    prompt: 'Freshness scope (all, doc_type, or tool)',
    value: 'all',
    ignoreFocusOut: true,
  });

  if (!scope) {
    return { cancelled: true };
  }

  const thresholdInput = await vscode.window.showInputBox({
    prompt: 'Stale threshold days (optional)',
    value: '180',
    ignoreFocusOut: true,
  });

  const args = ['freshness', '--scope', scope];
  const thresholdDays = Number.parseInt(thresholdInput || '', 10);
  if (!Number.isNaN(thresholdDays) && thresholdDays > 0) {
    args.push('--threshold-days', String(thresholdDays));
  }

  const result = await runCli({ workspaceRoot: root, args });

  outputChannel.appendLine(`[KTS] ${args.join(' ')}`);
  outputChannel.appendLine(JSON.stringify(result, null, 2));
  outputChannel.show(true);

  vscode.window.showInformationMessage(`KTS freshness audit complete. Stale docs: ${result.stale ?? 0}.`);
  return result;
};
