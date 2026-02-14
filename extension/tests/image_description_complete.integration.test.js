const test = require('node:test');
const assert = require('node:assert/strict');

const imageDescriptionComplete = require('../commands/image_description_complete');

function createOutputChannelMock() {
  return {
    lines: [],
    appendLine(message) {
      this.lines.push(message);
    },
    show() {},
  };
}

test('imageDescriptionComplete exits when no pending docs exist', async () => {
  const messages = [];
  const vscode = {
    window: {
      showInformationMessage(message) {
        messages.push(message);
      },
      async showQuickPick() {
        throw new Error('showQuickPick should not be called when no pending docs exist');
      },
      async showOpenDialog() {
        throw new Error('showOpenDialog should not be called when no pending docs exist');
      },
      createWebviewPanel() {
        return { webview: { html: '' } };
      },
    },
    Uri: {
      file(filePath) {
        return { fsPath: filePath };
      },
    },
    ViewColumn: { Beside: 2 },
  };

  const runCli = async ({ args }) => {
    if (args[0] === 'describe' && args[1] === 'pending') {
      return { documents: [], count: 0 };
    }
    throw new Error('Unexpected CLI invocation');
  };

  const result = await imageDescriptionComplete({
    vscode,
    outputChannel: createOutputChannelMock(),
    workspaceRoot: process.cwd(),
    runCli,
  });

  assert.equal(result.cancelled, true);
  assert.equal(result.reason, 'no_pending');
  assert.match(messages[0], /No documents have pending image descriptions/);
});

test('imageDescriptionComplete completes selected doc and refreshes panel', async () => {
  const infoMessages = [];
  const runCliCalls = [];

  const vscode = {
    window: {
      async showQuickPick(items) {
        return items[0];
      },
      async showOpenDialog() {
        return [{ fsPath: 'C:/temp/descriptions.json' }];
      },
      showInformationMessage(message) {
        infoMessages.push(message);
      },
      createWebviewPanel() {
        return { webview: { html: '' } };
      },
    },
    Uri: {
      file(filePath) {
        return { fsPath: filePath };
      },
    },
    ViewColumn: { Beside: 2 },
  };

  const runCli = async ({ args }) => {
    runCliCalls.push(args);
    if (args[0] === 'describe' && args[1] === 'pending') {
      return { documents: [{ doc_id: 'doc_1', pending_count: 2, described_count: 0 }], count: 1 };
    }
    if (args[0] === 'describe' && args[1] === 'complete') {
      return { newly_indexed: ['img_001'] };
    }
    throw new Error('Unexpected CLI invocation');
  };

  const result = await imageDescriptionComplete({
    vscode,
    outputChannel: createOutputChannelMock(),
    workspaceRoot: process.cwd(),
    runCli,
  });

  assert.deepEqual(result.newly_indexed, ['img_001']);
  assert.equal(runCliCalls.length, 3);
  assert.deepEqual(runCliCalls[1], [
    'describe',
    'complete',
    '--doc-id',
    'doc_1',
    '--descriptions-file',
    'C:/temp/descriptions.json',
  ]);
  assert.match(infoMessages[0], /Image description completion applied/);
});
