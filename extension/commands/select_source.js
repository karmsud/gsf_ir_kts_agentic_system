/**
 * Select Source Folder Command
 * Lets user select the network/local folder containing raw KB documents
 */
module.exports = async function selectSource({ vscode } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const currentPath = config.get('sourcePath') || '';

  const options = {
    canSelectFiles: false,
    canSelectFolders: true,
    canSelectMany: false,
    openLabel: 'Select Source Folder',
    defaultUri: currentPath ? vscode.Uri.file(currentPath) : undefined,
  };

  const result = await vscode.window.showOpenDialog(options);

  if (result && result.length > 0) {
    const selectedPath = result[0].fsPath;
    await config.update('sourcePath', selectedPath, vscode.ConfigurationTarget.Global);
    vscode.window.showInformationMessage(`KTS Source Path updated: ${selectedPath}`);
    return { sourcePath: selectedPath };
  }

  return { cancelled: true };
};
