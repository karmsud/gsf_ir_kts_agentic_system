const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');

module.exports = async function changeImpact({ vscode, outputChannel, workspaceRoot, runCli = runCliJson } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourcePath');
  const entity = await vscode.window.showInputBox({
    prompt: 'Entity to analyze impact (e.g., ToolX)',
    value: 'ToolX',
    ignoreFocusOut: true,
  });

  if (!entity) {
    return { cancelled: true };
  }

  const result = await runCli({ workspaceRoot: root, sourcePath, args: ['impact', '--entity', entity] });

  outputChannel.appendLine(`[KTS] impact --entity ${entity}`);
  outputChannel.appendLine(JSON.stringify(result, null, 2));
  outputChannel.show(true);

  const directDocs = Array.isArray(result.direct_docs) ? result.direct_docs.length : 0;
  vscode.window.showInformationMessage(`KTS impact complete. Directly affected docs: ${directDocs}.`);

  return result;
};
