const test = require('node:test');
const assert = require('node:assert/strict');

const { toMarkdown } = require('../chat/participant');

test('toMarkdown renders error states', () => {
  const output = toMarkdown({ status: 'error', error: 'boom' });
  assert.match(output, /KTS retrieval failed/);
  assert.match(output, /boom/);
});

test('toMarkdown renders context and citations', () => {
  const output = toMarkdown({
    status: 'ok',
    search_result: {
      confidence: 0.82,
      context_chunks: [
        { content: 'Reset ToolX password from Security tab.' },
      ],
      citations: [
        { doc_name: 'ToolX_UserGuide.md', uri: 'file:///tmp/ToolX_UserGuide.md' },
      ],
    },
  });

  assert.match(output, /confidence: 0.82/);
  assert.match(output, /Context 1/);
  assert.match(output, /ToolX_UserGuide.md/);
});
