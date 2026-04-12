/**
 * Golden Answer Scorer — LLM-as-Judge
 *
 * Scores each golden test answer on 5 dimensions using a Copilot LLM model.
 * Compares results against a baseline to detect regressions.
 *
 * Dimensions (each 1-5):
 *   completeness, accuracy, grounding, usability, no_hallucination
 *
 * Composite:
 *   overall = completeness×0.25 + accuracy×0.30 + grounding×0.20
 *           + usability×0.15 + no_hallucination×0.10
 */
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Weights for composite score
// ---------------------------------------------------------------------------
const WEIGHTS = {
  completeness: 0.25,
  accuracy: 0.30,
  grounding: 0.20,
  usability: 0.15,
  no_hallucination: 0.10,
};

// ---------------------------------------------------------------------------
// Judge prompt
// ---------------------------------------------------------------------------
function buildJudgePrompt(test, actualAnswer) {
  return `You are an expert judge evaluating the quality of a RAG system's answer about a structured-finance document (PSA — Pooling and Servicing Agreement).

## Question
${test.question}

## Expected Answer Content
${test.ideal_answer_summary}

## Must Contain
${JSON.stringify(test.expected_answer_contains)}

## Must NOT Contain
${JSON.stringify(test.expected_answer_not_contains)}

## System's Answer
${actualAnswer}

## Scoring Rubric
${Object.entries(test.scoring_rubric).map(([k, v]) => `- ${k}: ${v}`).join('\n')}

Score the answer on each dimension from 1 to 5. Return ONLY a JSON object with no markdown fencing:

{
  "completeness": { "score": <1-5>, "reason": "<one sentence>" },
  "accuracy": { "score": <1-5>, "reason": "<one sentence>" },
  "grounding": { "score": <1-5>, "reason": "<one sentence>" },
  "usability": { "score": <1-5>, "reason": "<one sentence>" },
  "no_hallucination": { "score": <1-5>, "reason": "<one sentence>" },
  "critical_failures": ["<any critical issues, or empty array>"]
}`;
}

// ---------------------------------------------------------------------------
// Parse judge response
// ---------------------------------------------------------------------------
function parseJudgeResponse(text) {
  // Strip markdown code fences if present
  let cleaned = text.replace(/```json\s*/gi, '').replace(/```\s*/g, '').trim();

  // Try to extract JSON object
  const match = cleaned.match(/\{[\s\S]*\}/);
  if (!match) {
    return null;
  }

  try {
    const parsed = JSON.parse(match[0]);
    // Validate expected keys
    const dims = ['completeness', 'accuracy', 'grounding', 'usability', 'no_hallucination'];
    for (const dim of dims) {
      if (!parsed[dim] || typeof parsed[dim].score !== 'number') {
        return null;
      }
      // Clamp to 1-5
      parsed[dim].score = Math.max(1, Math.min(5, Math.round(parsed[dim].score)));
    }
    return parsed;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Compute composite score
// ---------------------------------------------------------------------------
function computeOverall(scores) {
  let total = 0;
  for (const [dim, weight] of Object.entries(WEIGHTS)) {
    total += (scores[dim]?.score || 1) * weight;
  }
  return Math.round(total * 100) / 100;
}

// ---------------------------------------------------------------------------
// Score a single result
// ---------------------------------------------------------------------------
async function scoreSingleResult(vscode, model, test, result, token) {
  const prompt = buildJudgePrompt(test, result.actual_answer);

  const messages = [
    vscode.LanguageModelChatMessage.User(prompt),
  ];

  let responseText = '';
  try {
    const resp = await model.sendRequest(messages, {}, token);
    for await (const part of resp.text) {
      responseText += part;
    }
  } catch (err) {
    return {
      test_id: test.test_id,
      scores: null,
      overall: 0,
      error: `LLM judge call failed: ${err.message}`,
    };
  }

  const scores = parseJudgeResponse(responseText);
  if (!scores) {
    return {
      test_id: test.test_id,
      scores: null,
      overall: 0,
      error: `Failed to parse judge response: ${responseText.substring(0, 200)}`,
      raw_response: responseText,
    };
  }

  const overall = computeOverall(scores);

  return {
    test_id: test.test_id,
    category: test.category,
    scores: {
      completeness: scores.completeness,
      accuracy: scores.accuracy,
      grounding: scores.grounding,
      usability: scores.usability,
      no_hallucination: scores.no_hallucination,
    },
    critical_failures: scores.critical_failures || [],
    overall,
  };
}

// ---------------------------------------------------------------------------
// Score all results
// ---------------------------------------------------------------------------

/**
 * Score an array of golden test results using LLM-as-judge.
 *
 * @param {object}   vscode    - The vscode API
 * @param {object}   model     - VS Code LanguageModel to use as judge
 * @param {object[]} results   - Array from golden_answer_runner
 * @param {object}   outputChannel
 * @param {object}   [options] - { baselinePath }
 * @returns {object}           - { scores, average, by_category, regressions }
 */
async function scoreResults(vscode, model, results, outputChannel, options = {}) {
  // Load tests for rubrics
  const testsPath = path.join(__dirname, 'golden_answer_tests.json');
  const tests = JSON.parse(fs.readFileSync(testsPath, 'utf-8'));
  const testMap = new Map(tests.map(t => [t.test_id, t]));

  // Load baseline if available
  let baseline = null;
  const baselinePath = options.baselinePath || path.join(__dirname, 'golden_answer_baseline.json');
  if (fs.existsSync(baselinePath)) {
    try {
      const baselineData = JSON.parse(fs.readFileSync(baselinePath, 'utf-8'));
      baseline = new Map((baselineData.scores || []).map(s => [s.test_id, s]));
      outputChannel.appendLine(`Loaded baseline with ${baseline.size} scores from ${baselinePath}`);
    } catch {
      outputChannel.appendLine('Failed to load baseline — scoring without comparison.');
    }
  }

  const token = new vscode.CancellationTokenSource().token;
  const scored = [];

  for (let i = 0; i < results.length; i++) {
    const result = results[i];
    const test = testMap.get(result.test_id);
    if (!test) {
      outputChannel.appendLine(`  [${result.test_id}] SKIP — no matching test definition`);
      continue;
    }

    outputChannel.appendLine(`  Scoring ${result.test_id}...`);
    const score = await scoreSingleResult(vscode, model, test, result, token);
    scored.push(score);

    if (score.error) {
      outputChannel.appendLine(`    ERROR: ${score.error}`);
    } else {
      outputChannel.appendLine(
        `    Overall: ${score.overall.toFixed(2)} | ` +
        `C=${score.scores.completeness.score} A=${score.scores.accuracy.score} ` +
        `G=${score.scores.grounding.score} U=${score.scores.usability.score} ` +
        `H=${score.scores.no_hallucination.score}`
      );
    }
  }

  // Aggregate
  const validScores = scored.filter(s => s.overall > 0);
  const average = validScores.length > 0
    ? validScores.reduce((sum, s) => sum + s.overall, 0) / validScores.length
    : 0;

  // By category
  const catMap = new Map();
  for (const s of validScores) {
    if (!catMap.has(s.category)) catMap.set(s.category, []);
    catMap.get(s.category).push(s.overall);
  }
  const byCategory = [...catMap.entries()].map(([name, vals]) => ({
    name,
    count: vals.length,
    average: vals.reduce((a, b) => a + b, 0) / vals.length,
  }));

  // Regression detection
  const regressions = [];
  if (baseline) {
    for (const s of validScores) {
      const b = baseline.get(s.test_id);
      if (!b) continue;

      // Overall drop ≥ 1.0
      if (b.overall - s.overall >= 1.0) {
        regressions.push({
          test_id: s.test_id,
          dimension: 'overall',
          baseline: b.overall,
          current: s.overall,
          delta: s.overall - b.overall,
        });
      }

      // Any dimension drop ≥ 2
      if (b.scores && s.scores) {
        for (const dim of Object.keys(WEIGHTS)) {
          const bScore = b.scores[dim]?.score || 0;
          const cScore = s.scores[dim]?.score || 0;
          if (bScore - cScore >= 2) {
            regressions.push({
              test_id: s.test_id,
              dimension: dim,
              baseline: bScore,
              current: cScore,
              delta: cScore - bScore,
            });
          }
        }
      }

      // New critical failures
      const bCritical = new Set(b.critical_failures || []);
      for (const cf of (s.critical_failures || [])) {
        if (!bCritical.has(cf)) {
          regressions.push({
            test_id: s.test_id,
            dimension: 'critical_failure',
            baseline: null,
            current: cf,
            delta: null,
          });
        }
      }
    }
  }

  return {
    scores: scored,
    average: Math.round(average * 100) / 100,
    by_category: byCategory,
    regressions,
    total: results.length,
    scored: validScores.length,
    errors: scored.length - validScores.length,
  };
}

/**
 * Save scored results alongside the runner output.
 */
function saveScores(scores, resultsDir) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const outputPath = path.join(resultsDir || __dirname, 'golden_answer_results', `${timestamp}_scores.json`);
  const dir = path.dirname(outputPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(scores, null, 2));
  return outputPath;
}

/**
 * Save current scores as the baseline for future comparisons.
 */
function saveAsBaseline(scores) {
  const baselinePath = path.join(__dirname, 'golden_answer_baseline.json');
  fs.writeFileSync(baselinePath, JSON.stringify({
    timestamp: new Date().toISOString(),
    scores: scores.scores,
    average: scores.average,
    by_category: scores.by_category,
  }, null, 2));
  return baselinePath;
}

module.exports = {
  scoreResults,
  scoreSingleResult,
  parseJudgeResponse,
  computeOverall,
  saveScores,
  saveAsBaseline,
  WEIGHTS,
};
