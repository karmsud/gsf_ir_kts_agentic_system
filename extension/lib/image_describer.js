/**
 * Image Auto-Describer — Uses VS Code Language Model API (Copilot)
 * to automatically describe images extracted from documents.
 *
 * Approach C: Fully automated via vscode.lm API.
 * Falls back gracefully when no model is available.
 */

const fs = require('fs');
const path = require('path');

const MIME_MAP = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  bmp: 'image/bmp',
  tiff: 'image/tiff',
  emf: 'image/emf',
};

const SYSTEM_PROMPT = [
  'You are an expert technical documentation analyst.',
  'Describe this image for a knowledge base index.',
  'Focus on: what the image shows (diagram, screenshot, chart, etc.),',
  'key UI elements or labels visible, tool/application names,',
  'error messages or codes if any, workflow steps depicted.',
  'Be concise but thorough (2-5 sentences).',
  'If the image is a screenshot of an application, name the application if identifiable.',
  'Do NOT start with "This image shows" — just describe directly.',
].join(' ');

/**
 * Attempt to select a vision-capable Copilot model.
 * Returns the model or null if unavailable.
 */
async function selectVisionModel(vscode) {
  if (!vscode.lm || typeof vscode.lm.selectChatModels !== 'function') {
    return null;
  }

  // Try vision-capable models in preference order
  const families = ['gpt-4o', 'gpt-4o-mini', 'claude-3.5-sonnet', 'claude-3-5-sonnet'];
  for (const family of families) {
    try {
      const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
      if (models && models.length > 0) {
        return models[0];
      }
    } catch (_) {
      // Try next family
    }
  }

  // Fallback: try any copilot model
  try {
    const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    if (models && models.length > 0) {
      return models[0];
    }
  } catch (_) {
    // No model available
  }

  return null;
}

/**
 * Get MIME type from file extension.
 */
function getMimeType(filePath) {
  const ext = path.extname(filePath).replace('.', '').toLowerCase();
  return MIME_MAP[ext] || 'image/png';
}

/**
 * Describe a single image using the VS Code LM API.
 *
 * @param {object} vscode - The vscode API
 * @param {object} model - The LanguageModelChat instance
 * @param {string} imagePath - Absolute path to the image file
 * @param {string} [context] - Optional context about the source document
 * @returns {Promise<string|null>} Description text or null on failure
 */
async function describeImage(vscode, model, imagePath, context) {
  try {
    const imageUri = vscode.Uri.file(imagePath);
    const imageData = await vscode.workspace.fs.readFile(imageUri);
    const mimeType = getMimeType(imagePath);

    const promptText = context
      ? `${SYSTEM_PROMPT}\n\nSource document context: ${context}`
      : SYSTEM_PROMPT;

    const messages = [
      vscode.LanguageModelChatMessage.User([
        new vscode.LanguageModelTextPart(promptText),
        vscode.LanguageModelDataPart.image(imageData, mimeType),
      ]),
    ];

    const cts = new vscode.CancellationTokenSource();
    const response = await model.sendRequest(messages, {}, cts.token);

    let result = '';
    for await (const chunk of response.text) {
      result += chunk;
    }

    return result.trim() || null;
  } catch (err) {
    // Graceful failure — return null so fallback approaches can handle it
    return null;
  }
}

/**
 * Auto-describe all pending images for a set of ingested documents.
 * This is Approach C — fully automated.
 *
 * @param {object} options
 * @param {object} options.vscode - The vscode API module
 * @param {function} options.runCli - The CLI runner function (runCliJson)
 * @param {object} options.outputChannel - The output channel for logging
 * @param {string} options.sourcePath - The source folder path
 * @param {string} [options.backendChannel] - Backend channel (bundled/venv)
 * @returns {Promise<{described: number, failed: number, skipped: number, modelAvailable: boolean}>}
 */
async function autoDescribeImages({ vscode, runCli, outputChannel, sourcePath, backendChannel } = {}) {
  const result = { described: 0, failed: 0, skipped: 0, modelAvailable: false };

  // 1. Check if LM API is available
  const model = await selectVisionModel(vscode);
  if (!model) {
    outputChannel.appendLine('[KTS] Vision model not available — images saved as pending (use @kts /describe_images for manual fallback)');
    return result;
  }

  result.modelAvailable = true;
  outputChannel.appendLine(`[KTS] Vision model selected: ${model.id || model.family || 'copilot'}`);

  // 2. Get pending images from backend
  let pendingData;
  try {
    pendingData = await runCli({
      backendChannel,
      sourcePath,
      args: ['describe', 'pending'],
      timeoutMs: 30000,
    });
  } catch (err) {
    outputChannel.appendLine(`[KTS] Failed to fetch pending images: ${err.message}`);
    return result;
  }

  const documents = Array.isArray(pendingData.documents) ? pendingData.documents : [];
  if (!documents.length) {
    outputChannel.appendLine('[KTS] No pending images to describe.');
    return result;
  }

  // 3. Process each document's pending images
  for (const doc of documents) {
    const docId = doc.doc_id;
    const pendingImages = Array.isArray(doc.pending_images) ? doc.pending_images : [];

    if (!pendingImages.length) continue;

    outputChannel.appendLine(`[KTS] Describing ${pendingImages.length} image(s) for ${docId}...`);

    const descriptions = {};
    for (const img of pendingImages) {
      const imageId = img.image_id;
      const imagePath = img.path;

      if (!imagePath || !fs.existsSync(imagePath)) {
        outputChannel.appendLine(`[KTS]   ⚠ Image not found: ${imagePath}`);
        result.skipped++;
        continue;
      }

      const docTitle = docId.replace(/_/g, ' ');
      const description = await describeImage(vscode, model, imagePath, `From document: ${docTitle}`);

      if (description && description.length >= 12) {
        descriptions[imageId] = description;
        result.described++;
        outputChannel.appendLine(`[KTS]   ✓ ${imageId}: ${description.substring(0, 80)}...`);
      } else {
        result.failed++;
        outputChannel.appendLine(`[KTS]   ✗ ${imageId}: description too short or failed`);
      }
    }

    // 4. Submit descriptions back to backend
    if (Object.keys(descriptions).length > 0) {
      try {
        // Write descriptions to a temp file for the CLI
        const tempDir = path.join(sourcePath, '.kts', 'temp');
        if (!fs.existsSync(tempDir)) {
          fs.mkdirSync(tempDir, { recursive: true });
        }
        const tempFile = path.join(tempDir, `desc_${docId}.json`);
        fs.writeFileSync(tempFile, JSON.stringify(descriptions, null, 2), 'utf-8');

        await runCli({
          backendChannel,
          sourcePath,
          args: ['describe', 'complete', '--doc-id', docId, '--descriptions-file', tempFile],
          timeoutMs: 30000,
        });

        // Clean up temp file
        try { fs.unlinkSync(tempFile); } catch (_) {}
      } catch (err) {
        outputChannel.appendLine(`[KTS]   ✗ Failed to save descriptions for ${docId}: ${err.message}`);
      }
    }
  }

  outputChannel.appendLine(`[KTS] Image description complete: ${result.described} described, ${result.failed} failed, ${result.skipped} skipped`);
  return result;
}

module.exports = {
  selectVisionModel,
  describeImage,
  autoDescribeImages,
  getMimeType,
  SYSTEM_PROMPT,
};
