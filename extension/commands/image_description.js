const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');
const { openImageDescriptionPanel } = require('../panels/image_description');

module.exports = async function imageDescription({ vscode, outputChannel, workspaceRoot, runCli = runCliJson } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);
  const pending = await openImageDescriptionPanel({ vscode, workspaceRoot: root, runCli });

  outputChannel.appendLine('[KTS] describe pending');
  outputChannel.appendLine(JSON.stringify(pending, null, 2));
  outputChannel.show(true);

  vscode.window.showInformationMessage(`KTS image queue loaded. Documents pending: ${pending.count ?? 0}.`);
  return pending;
};
