const path = require('path');
const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');

module.exports = async function crawlIngest({ vscode, outputChannel, workspaceRoot, runCli = runCliJson } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);
  const defaultPath = path.join('tests', 'fixtures', 'simple');

  const sourcePath = await vscode.window.showInputBox({
    prompt: 'Enter file or folder path to crawl and ingest',
    value: defaultPath,
    ignoreFocusOut: true,
  });

  if (!sourcePath) {
    return { cancelled: true };
  }

  const crawlResult = await runCli({ workspaceRoot: root, args: ['crawl', '--paths', sourcePath] });
  const ingestResult = await runCli({ workspaceRoot: root, args: ['ingest', '--paths', sourcePath] });

  outputChannel.appendLine('[KTS] crawl --paths ' + sourcePath);
  outputChannel.appendLine(JSON.stringify(crawlResult, null, 2));
  outputChannel.appendLine('[KTS] ingest --paths ' + sourcePath);
  outputChannel.appendLine(JSON.stringify(ingestResult, null, 2));
  outputChannel.show(true);

  const ingestedCount = ingestResult.count ?? 0;
  vscode.window.showInformationMessage(`KTS crawl+ingest complete. Ingested ${ingestedCount} document(s).`);

  return { crawl: crawlResult, ingest: ingestResult };
};
