const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');

module.exports = async function trainingPath({ vscode, outputChannel, workspaceRoot, runCli = runCliJson } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourcePath');
  const topic = await vscode.window.showInputBox({
    prompt: 'Training topic (e.g., onboarding, ToolX)',
    value: 'onboarding',
    ignoreFocusOut: true,
  });

  if (!topic) {
    return { cancelled: true };
  }

  const level = await vscode.window.showQuickPick(['beginner', 'intermediate', 'advanced'], {
    placeHolder: 'Select learning level',
    ignoreFocusOut: true,
  });

  if (!level) {
    return { cancelled: true };
  }

  const result = await runCli({ workspaceRoot: root, sourcePath, args: ['training', '--topic', topic, '--level', level] });

  outputChannel.appendLine(`[KTS] training --topic ${topic} --level ${level}`);
  outputChannel.appendLine(JSON.stringify(result, null, 2));
  outputChannel.show(true);

  const steps = Array.isArray(result.steps) ? result.steps.length : 0;
  vscode.window.showInformationMessage(`KTS training path generated with ${steps} step(s).`);

  return result;
};
