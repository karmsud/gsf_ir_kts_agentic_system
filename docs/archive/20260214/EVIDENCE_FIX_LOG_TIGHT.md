# Evidence Fix Log (Tight)

## Changes Applied

| Change | Scope | Failing Query IDs (baseline) | Proof Artifact |
| :-- | :-- | :-- | :-- |
| Fix 1: Evidence matcher correctness (NFKC, whitespace, punctuation, hyphen/underscore, regex, group semantics) | tests/score_queries.py | V1:2 V2:17 Mixed:16 | data/accuracy_scores_baseline_*.json, data/evidence_ledger_baseline_*.json |
| Fix 2: Retrieval output completeness fallback (content/excerpt/pointer) | tests/score_queries.py | V1:2 V2:17 Mixed:16 | data/accuracy_scores_after_*.json, data/evidence_ledger_after_*.json |
| Fix 3: Section-aware chunking | Not applied (no Class C failures in baseline) | N/A | docs/EVIDENCE_FAILURES_TIGHT.md |
| Fix 4: Metadata anchoring header (title/section/tool/error_codes from existing metadata) | backend/vector/chunker.py | V2 + Mixed persistent failures | data/raw_console/after_*_console.txt |

## Final Validation (Before → After)

| Scenario | Top-1 | Top-3 | Evidence@Top-3 | Evidence@Top-5 | Citations |
| :-- | :-- | :-- | :-- | :-- | :-- |
| V1 Isolated | 98.0% → 98.0% | 100.0% → 100.0% | 92.0% → 96.0% | 96.0% → 98.0% | 100.0% → 100.0% |
| V2 Isolated | 100.0% → 100.0% | 100.0% → 100.0% | 64.0% → 68.0% | 66.0% → 72.0% | 100.0% → 100.0% |
| Mixed (Realism) | 100.0% → 100.0% | 100.0% → 100.0% | 64.0% → 68.0% | 68.0% → 74.0% | 100.0% → 100.0% |

## Previously Failing Queries (Evidence@Top-5)

- V1 Isolated baseline failing query_ids (2): Q11, Q12
- V2 Isolated baseline failing query_ids (17): V2-Q02, V2-Q06, V2-Q18, V2-Q19, V2-Q26, V2-Q27, V2-Q29, V2-Q30, V2-Q31, V2-Q32, V2-Q34, V2-Q36, V2-Q43, V2-Q46, V2-Q47, V2-Q48, V2-Q50
- Mixed (Realism) baseline failing query_ids (16): V2-Q02, V2-Q06, V2-Q19, V2-Q26, V2-Q27, V2-Q29, V2-Q30, V2-Q31, V2-Q32, V2-Q34, V2-Q36, V2-Q43, V2-Q46, V2-Q47, V2-Q48, V2-Q50

- V1 Isolated after failing query_ids (1): Q12
- V2 Isolated after failing query_ids (14): V2-Q02, V2-Q06, V2-Q18, V2-Q19, V2-Q26, V2-Q27, V2-Q30, V2-Q31, V2-Q32, V2-Q34, V2-Q43, V2-Q46, V2-Q47, V2-Q48
- Mixed (Realism) after failing query_ids (13): V2-Q02, V2-Q06, V2-Q19, V2-Q26, V2-Q27, V2-Q30, V2-Q31, V2-Q32, V2-Q34, V2-Q43, V2-Q46, V2-Q47, V2-Q48

## Queries with Top Result Changed

- V1 Isolated top-result changes (50): Q1:doc_5826854→doc_4124289, Q2:doc_3073331→doc_8734941, Q3:doc_0901179→doc_7766698, Q4:doc_0935936→doc_4237935, Q5:doc_3073331→doc_8734941, Q6:doc_4843481→doc_4804264, Q7:doc_6272574→doc_9693873, Q8:doc_8630007→doc_4561969, Q9:doc_7774454→doc_9982356, Q10:doc_2700947→doc_9962438, Q11:doc_8630007→doc_4561969, Q12:doc_8630007→doc_4561969, Q13:doc_3073331→doc_8734941, Q14:doc_8630007→doc_4561969, Q15:doc_3073331→doc_8734941, Q16:doc_4843481→doc_4804264, Q17:doc_4843481→doc_4804264, Q18:doc_5826854→doc_4124289, Q19:doc_3073331→doc_8734941, Q20:doc_8630007→doc_4561969, Q21:doc_5826854→doc_4124289, Q22:doc_8630007→doc_4561969, Q23:doc_4843481→doc_4804264, Q24:doc_2700947→doc_9962438, Q25:doc_7774454→doc_9982356, Q26:doc_6608752→doc_0609446, Q27:doc_3073331→doc_8734941, Q28:doc_4843481→doc_4804264, Q29:doc_3073331→doc_8734941, Q30:doc_5826854→doc_4124289, Q31:doc_8630007→doc_4561969, Q32:doc_8630007→doc_4561969, Q33:doc_6608752→doc_0609446, Q34:doc_8630007→doc_4561969, Q35:doc_6608752→doc_0609446, Q36:doc_8630007→doc_4561969, Q37:doc_3073331→doc_8734941, Q38:doc_2700947→doc_9962438, Q39:doc_5826854→doc_4124289, Q40:doc_5826854→doc_4124289, Q41:doc_0901179→doc_7766698, Q42:doc_5826854→doc_4124289, Q43:doc_5826854→doc_4124289, Q44:doc_5826854→doc_4124289, Q45:doc_8630007→doc_4561969, Q46:doc_2700947→doc_9962438, Q47:doc_0901179→doc_7766698, Q48:doc_0901179→doc_7766698, Q49:doc_0901179→doc_7766698, Q50:doc_6608752→doc_0609446
- V2 Isolated top-result changes (50): V2-Q01:doc_3254544→doc_2712454, V2-Q02:doc_7594425→doc_5638532, V2-Q03:doc_3254544→doc_2712454, V2-Q04:doc_0481592→doc_3324027, V2-Q05:doc_7180098→doc_2773229, V2-Q06:doc_0481592→doc_3324027, V2-Q07:doc_3154314→doc_8889880, V2-Q08:doc_7188612→doc_3431314, V2-Q09:doc_3154314→doc_8889880, V2-Q10:doc_2397856→doc_9461028, V2-Q11:doc_3138757→doc_7367700, V2-Q12:doc_7016225→doc_4910331, V2-Q13:doc_5310494→doc_8591897, V2-Q14:doc_4497288→doc_2772990, V2-Q15:doc_9039050→doc_6473532, V2-Q16:doc_1630777→doc_5849657, V2-Q17:doc_9693041→doc_2714103, V2-Q18:doc_7447053→doc_7521176, V2-Q19:doc_7447053→doc_7521176, V2-Q20:doc_7016225→doc_4910331, V2-Q21:doc_4582988→doc_9045502, V2-Q22:doc_1630777→doc_2714103, V2-Q23:doc_4497288→doc_2772990, V2-Q24:doc_3158773→doc_1674715, V2-Q25:doc_0799576→doc_4815363, V2-Q26:doc_2448499→doc_6068553, V2-Q27:doc_2448499→doc_6068553, V2-Q28:doc_5363701→doc_0425013, V2-Q29:doc_2448499→doc_6068553, V2-Q30:doc_0594944→doc_1735474, V2-Q31:doc_2448499→doc_6068553, V2-Q32:doc_2448499→doc_6068553, V2-Q33:doc_3633942→doc_7158577, V2-Q34:doc_2448499→doc_6068553, V2-Q35:doc_0346463→doc_3286770, V2-Q36:doc_4660264→doc_6392641, V2-Q37:doc_2448499→doc_6068553, V2-Q38:doc_2370364→doc_5660539, V2-Q39:doc_3633942→doc_7158577, V2-Q40:doc_4497288→doc_2772990, V2-Q41:doc_0481592→doc_3324027, V2-Q42:doc_3158773→doc_1674715, V2-Q43:doc_2448499→doc_6068553, V2-Q44:doc_7594425→doc_5638532, V2-Q45:doc_3138757→doc_7367700, V2-Q46:doc_5085837→doc_8829610, V2-Q47:doc_2448499→doc_6068553, V2-Q48:doc_7447053→doc_7521176, V2-Q49:doc_4497288→doc_2772990, V2-Q50:doc_4660264→doc_0390788
- Mixed (Realism) top-result changes (50): V2-Q01:doc_4505736→doc_3585431, V2-Q02:doc_7064022→doc_9365837, V2-Q03:doc_4505736→doc_3585431, V2-Q04:doc_3509776→doc_2978098, V2-Q05:doc_4577420→doc_9859668, V2-Q06:doc_3509776→doc_2978098, V2-Q07:doc_8753087→doc_5482629, V2-Q08:doc_6607544→doc_9445116, V2-Q09:doc_8753087→doc_5482629, V2-Q10:doc_6002097→doc_9468751, V2-Q11:doc_4013709→doc_4724364, V2-Q12:doc_5878766→doc_1440788, V2-Q13:doc_6633780→doc_4780151, V2-Q14:doc_5199495→doc_8171219, V2-Q15:doc_2263379→doc_0855195, V2-Q16:doc_9238520→doc_8648099, V2-Q17:doc_3714313→doc_6591405, V2-Q18:doc_3684253→doc_1624710, V2-Q19:doc_4468773→doc_4320676, V2-Q20:doc_5878766→doc_1440788, V2-Q21:doc_2412097→doc_9233379, V2-Q22:doc_9238520→doc_6591405, V2-Q23:doc_5199495→doc_8171219, V2-Q24:doc_7463185→doc_8185158, V2-Q25:doc_2156233→doc_1877226, V2-Q26:doc_5077281→doc_3315320, V2-Q27:doc_4112515→doc_7990224, V2-Q28:doc_3977135→doc_8248106, V2-Q29:doc_5077281→doc_3315320, V2-Q30:doc_6347289→doc_1487018, V2-Q31:doc_5077281→doc_3315320, V2-Q32:doc_4112515→doc_7990224, V2-Q33:doc_5278085→doc_2984410, V2-Q34:doc_5077281→doc_3315320, V2-Q35:doc_7795557→doc_8533845, V2-Q36:doc_9493895→doc_7433112, V2-Q37:doc_5077281→doc_3315320, V2-Q38:doc_8469478→doc_4142419, V2-Q39:doc_5278085→doc_2984410, V2-Q40:doc_5199495→doc_8171219, V2-Q41:doc_8469478→doc_4142419, V2-Q42:doc_7463185→doc_8185158, V2-Q43:doc_7998278→doc_2160884, V2-Q44:doc_7064022→doc_9365837, V2-Q45:doc_4013709→doc_4724364, V2-Q46:doc_4277722→doc_0566457, V2-Q47:doc_5077281→doc_3315320, V2-Q48:doc_4468773→doc_4320676, V2-Q49:doc_5199495→doc_8171219, V2-Q50:doc_9493895→doc_0363626

## Gate Status

- V1 gate met: Evidence@Top-5 >=95%.
- V2 gate NOT met: Evidence@Top-5 remains below 95%.
- Mixed gate NOT met: Evidence@Top-5 remains below 95%.
- Safe targets preserved (Top-1/Top-3, citations).

## Root Cause and Next Safe Fix (Not Implemented)

- Dominant remaining failure class is D (Extraction gap): top-ranked chunks still do not contain all required terms in one chunk for many queries.
- Next safe fix: improve ingestion extraction fidelity for DOCX/PDF/PPTX/CSV/JSON/INI/YAML so indexed chunk text consistently includes evidence tokens currently missed in converted text.
