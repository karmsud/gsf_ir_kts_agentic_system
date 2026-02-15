# Evidence Baseline (Tight / Safe)

## Baseline Metrics

| Scenario | Top-1 | Top-3 | Evidence @Top-3 | Evidence @Top-5 | Citations |
| :-- | --: | --: | --: | --: | --: |
| V1 Isolated | 98.0% | 100.0% | 92.0% | 96.0% | 100.0% |
| V2 Isolated | 100.0% | 100.0% | 64.0% | 66.0% | 100.0% |
| Mixed (Realism) | 100.0% | 100.0% | 64.0% | 68.0% | 100.0% |

## Notes

- Evidence matching uses strict per-chunk ALL-of evaluation with NFKC, whitespace normalization, punctuation tolerance, hyphen/underscore equivalence, and simple plural equivalence.
- Baseline artifacts were produced without ranking-weight or answer-generation changes.
- Raw console logs are in data/raw_console/.
