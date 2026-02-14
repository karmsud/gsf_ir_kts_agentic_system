const vscode = require('vscode');
const crawlIngest = require('./commands/crawl_ingest');
const viewStatus = require('./commands/view_status');
const trainingPath = require('./commands/training_path');
const changeImpact = require('./commands/change_impact');
const freshnessAudit = require('./commands/freshness_audit');
const imageDescription = require('./commands/image_description');
const imageDescriptionComplete = require('./commands/image_description_complete');
const { registerChatParticipant } = require('./chat/participant');
const { getWorkspaceRoot } = require('./lib/kts_backend');

function register(context, command, handler, shared) {
  const disposable = vscode.commands.registerCommand(command, async () => {
    try {
      await handler(shared);
    } catch (error) {
      shared.outputChannel.appendLine(`[KTS] ${command} failed: ${error.message}`);
      shared.outputChannel.show(true);
      vscode.window.showErrorMessage(`KTS command failed: ${error.message}`);
    }
  });
  context.subscriptions.push(disposable);
}

function activate(context) {
  const outputChannel = vscode.window.createOutputChannel('KTS');
  context.subscriptions.push(outputChannel);

  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || getWorkspaceRoot();
  const shared = { vscode, outputChannel, workspaceRoot };

  register(context, 'kts.crawlIngest', crawlIngest, shared);
  register(context, 'kts.viewStatus', viewStatus, shared);
  register(context, 'kts.trainingPath', trainingPath, shared);
  register(context, 'kts.changeImpact', changeImpact, shared);
  register(context, 'kts.freshnessAudit', freshnessAudit, shared);
  register(context, 'kts.imageDescription', imageDescription, shared);
  register(context, 'kts.imageDescriptionComplete', imageDescriptionComplete, shared);

  registerChatParticipant(vscode, context, shared);
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
};
