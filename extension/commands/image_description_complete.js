const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');
const { openImageDescriptionPanel } = require('../panels/image_description');

module.exports = async function imageDescriptionComplete({ vscode, outputChannel, workspaceRoot, runCli = runCliJson } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);
  const pending = await runCli({ workspaceRoot: root, args: ['describe', 'pending'] });

  const documents = Array.isArray(pending.documents) ? pending.documents : [];
  if (!documents.length) {
    vscode.window.showInformationMessage('KTS: No documents have pending image descriptions.');
    return { cancelled: true, reason: 'no_pending' };
  }

  const selectedDoc = await vscode.window.showQuickPick(
    documents.map((doc) => ({
      label: doc.doc_id,
      description: `pending: ${doc.pending_count ?? 0}, described: ${doc.described_count ?? 0}`,
      docId: doc.doc_id,
    })),
    {
      title: 'KTS: Select document to complete image descriptions',
      ignoreFocusOut: true,
    }
  );

  if (!selectedDoc) {
    return { cancelled: true, reason: 'doc_not_selected' };
  }

  const pickedFiles = await vscode.window.showOpenDialog({
    title: 'Select descriptions JSON file',
    defaultUri: vscode.Uri.file(root),
    canSelectMany: false,
    canSelectFiles: true,
    canSelectFolders: false,
    filters: {
      JSON: ['json'],
    },
  });

  if (!pickedFiles || !pickedFiles.length) {
    return { cancelled: true, reason: 'file_not_selected' };
  }

  const descriptionsFile = pickedFiles[0].fsPath;
  const completion = await runCli({
    workspaceRoot: root,
    args: ['describe', 'complete', '--doc-id', selectedDoc.docId, '--descriptions-file', descriptionsFile],
  });

  outputChannel.appendLine(`[KTS] describe complete --doc-id ${selectedDoc.docId} --descriptions-file ${descriptionsFile}`);
  outputChannel.appendLine(JSON.stringify(completion, null, 2));
  outputChannel.show(true);

  await openImageDescriptionPanel({ vscode, workspaceRoot: root, runCli });

  const indexedCount = Array.isArray(completion.newly_indexed) ? completion.newly_indexed.length : 0;
  vscode.window.showInformationMessage(`KTS: Image description completion applied. Newly indexed: ${indexedCount}.`);

  return completion;
};
