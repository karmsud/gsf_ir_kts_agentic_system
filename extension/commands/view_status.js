const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');
const { openStatusReportPanel } = require('../panels/status_report');

module.exports = async function viewStatus({ vscode, outputChannel, workspaceRoot, runCli = runCliJson } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);
  const status = await runCli({ workspaceRoot: root, args: ['status'] });

  outputChannel.appendLine('[KTS] status');
  outputChannel.appendLine(JSON.stringify(status, null, 2));
  outputChannel.show(true);

  vscode.window.showInformationMessage(
    `KTS status: ${status.documents ?? 0} docs, ${status.graph_nodes ?? 0} graph nodes.`
  );

  await openStatusReportPanel({ vscode, workspaceRoot: root, runCli, statusData: status });

  return status;
};
