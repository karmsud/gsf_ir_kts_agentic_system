# GSF IR KTS — Top 50 User Queries Test Pack

**Version:** 1.0  
**Date:** 2026-02-14  
**Purpose:** Comprehensive query scenarios covering all agent types, doc types, and intent categories

---

## Query Pack Structure

Each query specifies:
- **Query Text**: What the user asks
- **Intent**: QUESTION | TRAINING | IMPACT | AUDIT
- **Expected Doc Types**: Which doc types should be cited
- **Expected Doc IDs**: Specific documents that must appear in citations
- **Required Citation Fields**: file:// URI, doc_id, version, section/page (if applicable)
- **Expected Confidence**: HIGH (>0.7) | MEDIUM (0.5-0.7) | LOW (<0.5, should escalate)
- **Expected Failure Mode**: None | ESCALATION_LOW_CONFIDENCE | ESCALATION_MISSING_INFO | UNKNOWN

---

## Category 1: Error Code Queries (10 queries)

### Q1: AUTH401 Error Lookup
- **Query**: "What does error AUTH401 mean for ToolX?"
- **Intent**: QUESTION
- **Expected Doc Types**: TROUBLESHOOT, REFERENCE
- **Expected Doc IDs**: `Troubleshoot_ToolX_AUTH401.md`, `error_code_catalog.json`
- **Required Citations**: Both docs with file:// URIs, doc_id, version
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q2: HTTP504 Timeout Troubleshooting
- **Query**: "How do I fix HTTP 504 timeout errors in ToolX?"
- **Intent**: QUESTION
- **Expected Doc Types**: TROUBLESHOOT
- **Expected Doc IDs**: `Troubleshoot_ToolX_HTTP504_Timeout.md`
- **Required Citations**: Troubleshooting doc with file:// URI, section references
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q3: Upload Error ERR-UPL-013
- **Query**: "ToolY upload is blocked with ERR-UPL-013"
- **Intent**: QUESTION
- **Expected Doc Types**: TROUBLESHOOT, TRAINING
- **Expected Doc IDs**: `Troubleshoot_ToolY_Upload_ERR-UPL-013.md`, possibly `Training_ToolY_Upload_Policy.pptx`
- **Required Citations**: Troubleshooting doc, optional training material
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q4: Password Error ERR-PWD-007
- **Query**: "What causes ERR-PWD-007 in ToolZ?"
- **Intent**: QUESTION
- **Expected Doc Types**: TROUBLESHOOT, REFERENCE
- **Expected Doc IDs**: `Troubleshoot_ToolZ_Password_ERR-PWD-007.md`, `error_code_catalog.json`
- **Required Citations**: Both docs with file:// URIs
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q5: Generic Authentication Error
- **Query**: "I'm getting authentication errors in ToolX"
- **Intent**: QUESTION
- **Expected Doc Types**: TROUBLESHOOT, SOP, REFERENCE
- **Expected Doc IDs**: `Troubleshoot_ToolX_AUTH401.md`, `SOP_ToolX_Login_Failures_v1.docx`
- **Required Citations**: Both docs with file:// URIs
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q6: Unknown Error Code
- **Query**: "What is error code XYZ-999?"
- **Intent**: QUESTION
- **Expected Doc Types**: None (unknown error)
- **Expected Doc IDs**: None
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO (suggest checking recent release notes, contacting SME)

### Q7: Error Code List Request
- **Query**: "List all error codes for ToolX"
- **Intent**: QUESTION
- **Expected Doc Types**: REFERENCE
- **Expected Doc IDs**: `error_code_catalog.json`
- **Required Citations**: JSON file with file:// URI
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q8: Login Failure Root Cause
- **Query**: "Why am I unable to login to ToolX?"
- **Intent**: QUESTION
- **Expected Doc Types**: SOP, TROUBLESHOOT
- **Expected Doc IDs**: `SOP_ToolX_Login_Failures_v1.docx`, `Troubleshoot_ToolX_AUTH401.md`
- **Required Citations**: Both docs with section references
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q9: Timeout Configuration
- **Query**: "How do I configure timeout settings to prevent 504 errors?"
- **Intent**: QUESTION
- **Expected Doc Types**: TROUBLESHOOT, SOP
- **Expected Doc IDs**: `Troubleshoot_ToolX_HTTP504_Timeout.md`
- **Required Citations**: Troubleshooting doc with configuration instructions
- **Expected Confidence**: MEDIUM (depends on content detail)
- **Expected Failure Mode**: Possible ESCALATION_LOW_CONFIDENCE if no configuration guidance found

### Q10: Upload Policy Details
- **Query**: "What files are allowed for upload in ToolY?"
- **Intent**: QUESTION
- **Expected Doc Types**: TRAINING
- **Expected Doc IDs**: `Training_ToolY_Upload_Policy.pptx`
- **Required Citations**: Training material with file:// URI
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

---

## Category 2: How-To Queries (10 queries)

### Q11: ToolX Onboarding Steps
- **Query**: "How do I get started with ToolX?"
- **Intent**: QUESTION
- **Expected Doc Types**: USER_GUIDE, TRAINING
- **Expected Doc IDs**: `UserGuide_ToolX_Onboarding.md`
- **Required Citations**: User guide with file:// URI, section references
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q12: Login Process
- **Query**: "Step-by-step instructions for logging into ToolX"
- **Intent**: QUESTION
- **Expected Doc Types**: SOP, USER_GUIDE
- **Expected Doc IDs**: `SOP_ToolX_Login_Failures_v1.docx`, `UserGuide_ToolX_Onboarding.md`
- **Required Citations**: Both docs with section references
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q13: Upload File to ToolY
- **Query**: "How to upload a file to ToolY"
- **Intent**: QUESTION
- **Expected Doc Types**: TRAINING, USER_GUIDE
- **Expected Doc IDs**: `Training_ToolY_Upload_Policy.pptx`
- **Required Citations**: Training material with upload steps
- **Expected Confidence**: HIGH
- **Expected Confidence**: None

### Q14: Reset Password in ToolZ
- **Query**: "How do I reset my password in ToolZ?"
- **Intent**: QUESTION
- **Expected Doc Types**: USER_GUIDE, TROUBLESHOOT
- **Expected Doc IDs**: `Troubleshoot_ToolZ_Password_ERR-PWD-007.md` (if contains reset instructions)
- **Required Citations**: Relevant doc with reset process
- **Expected Confidence**: MEDIUM
- **Expected Failure Mode**: Possible ESCALATION_LOW_CONFIDENCE if no reset instructions in corpus

### Q15: Configure ToolX Settings
- **Query**: "How to configure ToolX settings"
- **Intent**: QUESTION
- **Expected Doc Types**: SOP, USER_GUIDE
- **Expected Doc IDs**: `UserGuide_ToolX_Onboarding.md`, `SOP_ToolX_Login_Failures_v1.docx`
- **Required Citations**: Relevant docs with configuration sections
- **Expected Confidence**: MEDIUM
- **Expected Failure Mode**: Possible ESCALATION_LOW_CONFIDENCE if no settings guidance

### Q16: Deploy ToolX (Unknown)
- **Query**: "How do I deploy ToolX to production?"
- **Intent**: QUESTION
- **Expected Doc Types**: SOP (if exists)
- **Expected Doc IDs**: None (not in corpus)
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO (no deployment SOP in corpus)

### Q17: Archive Old Files in ToolY
- **Query**: "What's the process for archiving old files in ToolY?"
- **Intent**: QUESTION
- **Expected Doc Types**: SOP, USER_GUIDE
- **Expected Doc IDs**: None (likely not in corpus)
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO (no archiving process documented)

### Q18: Backup ToolZ Data
- **Query**: "How to backup data from ToolZ"
- **Intent**: QUESTION
- **Expected Doc Types**: SOP
- **Expected Doc IDs**: None (not in corpus)
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO

### Q19: Monitor ToolX Performance
- **Query**: "How can I monitor ToolX performance metrics?"
- **Intent**: QUESTION
- **Expected Doc Types**: SOP, USER_GUIDE
- **Expected Doc IDs**: None (not in corpus)
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO

### Q20: Onboarding Checklist
- **Query**: "What are the onboarding steps for new team members?"
- **Intent**: QUESTION
- **Expected Doc Types**: USER_GUIDE
- **Expected Doc IDs**: `UserGuide_ToolX_Onboarding.md`
- **Required Citations**: User guide with onboarding sections
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

---

## Category 3: Release Note Queries (5 queries)

### Q21: Latest ToolX Release
- **Query**: "What's new in the latest ToolX release?"
- **Intent**: QUESTION
- **Expected Doc Types**: RELEASE_NOTE
- **Expected Doc IDs**: `ReleaseNotes_ToolX_2026Q1.md`
- **Required Citations**: Release note with version info
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q22: 2026 Q1 Release Features
- **Query**: "List all features released in 2026 Q1"
- **Intent**: QUESTION
- **Expected Doc Types**: RELEASE_NOTE
- **Expected Doc IDs**: `ReleaseNotes_ToolX_2026Q1.md`
- **Required Citations**: Release note with feature list
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q23: Version History
- **Query**: "Show me version history for ToolX"
- **Intent**: QUESTION
- **Expected Doc Types**: RELEASE_NOTE
- **Expected Doc IDs**: `ReleaseNotes_ToolX_2026Q1.md` (may have version chain in graph)
- **Required Citations**: Release note(s) with version info
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q24: Breaking Changes
- **Query**: "Are there any breaking changes in ToolX 2026 Q1?"
- **Intent**: QUESTION
- **Expected Doc Types**: RELEASE_NOTE
- **Expected Doc IDs**: `ReleaseNotes_ToolX_2026Q1.md`
- **Required Citations**: Release note with breaking changes section
- **Expected Confidence**: MEDIUM (depends on content)
- **Expected Failure Mode**: Possible ESCALATION_LOW_CONFIDENCE if no breaking changes section

### Q25: ToolY Release Notes (Unknown)
- **Query**: "What's new in ToolY version 5.0?"
- **Intent**: QUESTION
- **Expected Doc Types**: RELEASE_NOTE
- **Expected Doc IDs**: None (no ToolY release notes in corpus)
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO

---

## Category 4: Training Path Queries (10 queries)

### Q26: ToolX Beginner Training
- **Query**: "Generate a training path for learning ToolX as a beginner"
- **Intent**: TRAINING
- **Expected Doc Types**: USER_GUIDE, TRAINING, SOP
- **Expected Doc IDs**: `UserGuide_ToolX_Onboarding.md`, `Training_ToolX_Troubleshooting_Pack.pdf`
- **Required Citations**: TrainingPath with ordered LearningStep list, each step citing a doc
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q27: ToolX Troubleshooting Training
- **Query**: "I need training on troubleshooting ToolX issues"
- **Intent**: TRAINING
- **Expected Doc Types**: TRAINING, TROUBLESHOOT, SOP
- **Expected Doc IDs**: `Training_ToolX_Troubleshooting_Pack.pdf`, troubleshooting docs
- **Required Citations**: TrainingPath with troubleshooting-focused steps
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q28: ToolY Upload Training
- **Query**: "Training path for ToolY file uploads"
- **Intent**: TRAINING
- **Expected Doc Types**: TRAINING
- **Expected Doc IDs**: `Training_ToolY_Upload_Policy.pptx`
- **Required Citations**: TrainingPath with upload-focused steps
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q29: ToolZ Authentication Training
- **Query**: "Learning path for ToolZ password and authentication"
- **Intent**: TRAINING
- **Expected Doc Types**: TROUBLESHOOT, USER_GUIDE
- **Expected Doc IDs**: `Troubleshoot_ToolZ_Password_ERR-PWD-007.md`
- **Required Citations**: TrainingPath with authentication-focused steps
- **Expected Confidence**: MEDIUM
- **Expected Failure Mode**: Possible ESCALATION_LOW_CONFIDENCE (limited content)

### Q30: Advanced ToolX Training
- **Query**: "Advanced training for ToolX power users"
- **Intent**: TRAINING
- **Expected Doc Types**: TRAINING
- **Expected Doc IDs**: `Training_ToolX_Troubleshooting_Pack.pdf` (may be categorized as advanced)
- **Required Citations**: TrainingPath with difficulty=advanced
- **Expected Confidence**: MEDIUM
- **Expected Failure Mode**: Possible ESCALATION_LOW_CONFIDENCE (limited advanced content)

### Q31: Onboarding New Hires
- **Query**: "Training path for onboarding new team members"
- **Intent**: TRAINING
- **Expected Doc Types**: USER_GUIDE, TRAINING
- **Expected Doc IDs**: `UserGuide_ToolX_Onboarding.md`, training materials
- **Required Citations**: TrainingPath with onboarding progression
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q32: Error Resolution Training
- **Query**: "I need to learn how to resolve common errors"
- **Intent**: TRAINING
- **Expected Doc Types**: TROUBLESHOOT, TRAINING
- **Expected Doc IDs**: All troubleshooting docs, training materials
- **Required Citations**: TrainingPath with error-focused steps
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q33: ToolX Admin Training (Unknown)
- **Query**: "Training path for ToolX administrators"
- **Intent**: TRAINING
- **Expected Doc Types**: SOP, TRAINING (if exists)
- **Expected Doc IDs**: None (no admin-specific content)
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO

### Q34: Security Best Practices Training
- **Query**: "Security training for using ToolX securely"
- **Intent**: TRAINING
- **Expected Doc Types**: SOP, TRAINING
- **Expected Doc IDs**: Possibly `SOP_ToolX_Login_Failures_v1.docx` (if contains security guidance)
- **Required Citations**: TrainingPath with security-focused steps
- **Expected Confidence**: LOW to MEDIUM
- **Expected Failure Mode**: Possible ESCALATION_LOW_CONFIDENCE or ESCALATION_MISSING_INFO

### Q35: Prerequisite Check
- **Query**: "What should I learn before tackling ToolX troubleshooting?"
- **Intent**: TRAINING
- **Expected Doc Types**: USER_GUIDE, TRAINING
- **Expected Doc IDs**: `UserGuide_ToolX_Onboarding.md` (as prerequisite)
- **Required Citations**: TrainingPath showing prerequisite order
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

---

## Category 5: Impact Queries (10 queries)

### Q36: ToolX Change Impact
- **Query**: "What documentation will be affected if ToolX login process changes?"
- **Intent**: IMPACT
- **Expected Doc Types**: All types mentioning ToolX
- **Expected Doc IDs**: `SOP_ToolX_Login_Failures_v1.docx`, `UserGuide_ToolX_Onboarding.md`, `Training_ToolX_Troubleshooting_Pack.pdf`, troubleshooting docs
- **Required Citations**: ImpactReport with direct_docs and indirect_docs lists
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q37: ToolY Upload Process Change
- **Query**: "Impact of changing ToolY upload policy"
- **Intent**: IMPACT
- **Expected Doc Types**: TRAINING, TROUBLESHOOT
- **Expected Doc IDs**: `Training_ToolY_Upload_Policy.pptx`, `Troubleshoot_ToolY_Upload_ERR-UPL-013.md`
- **Required Citations**: ImpactReport with affected_training and affected_processes
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q38: ToolZ Password Policy Update
- **Query**: "If ToolZ password policy changes, what docs need updating?"
- **Intent**: IMPACT
- **Expected Doc Types**: TROUBLESHOOT
- **Expected Doc IDs**: `Troubleshoot_ToolZ_Password_ERR-PWD-007.md`
- **Required Citations**: ImpactReport with direct_docs
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q39: Authentication Method Change
- **Query**: "Impact analysis for switching to SSO authentication"
- **Intent**: IMPACT
- **Expected Doc Types**: SOP, USER_GUIDE, TROUBLESHOOT
- **Expected Doc IDs**: All authentication-related docs
- **Required Citations**: ImpactReport with severity=HIGH, recommended_actions
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q40: Error Code Deprecation
- **Query**: "What if error code AUTH401 is deprecated?"
- **Intent**: IMPACT
- **Expected Doc Types**: TROUBLESHOOT, REFERENCE
- **Expected Doc IDs**: `Troubleshoot_ToolX_AUTH401.md`, `error_code_catalog.json`
- **Required Citations**: ImpactReport with affected docs
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q41: UI Redesign Impact
- **Query**: "ToolX UI is being redesigned, what images will be outdated?"
- **Intent**: IMPACT
- **Expected Doc Types**: All types with images
- **Expected Doc IDs**: All docs with image references
- **Required Citations**: ImpactReport with stale_images list
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q42: Unknown Tool Impact
- **Query**: "What's the impact of updating ToolABC?"
- **Intent**: IMPACT
- **Expected Doc Types**: N/A
- **Expected Doc IDs**: None (ToolABC not in corpus)
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO (unknown entity)

### Q43: Process Change Impact
- **Query**: "If the deployment process changes, which docs are affected?"
- **Intent**: IMPACT
- **Expected Doc Types**: SOP (if exists)
- **Expected Doc IDs**: None (no deployment SOP in corpus)
- **Required Citations**: N/A
- **Expected Confidence**: LOW
- **Expected Failure Mode**: ESCALATION_MISSING_INFO

### Q44: Training Material Update Impact
- **Query**: "If I update the troubleshooting training PDF, what else needs review?"
- **Intent**: IMPACT
- **Expected Doc Types**: TRAINING, TROUBLESHOOT
- **Expected Doc IDs**: `Training_ToolX_Troubleshooting_Pack.pdf`, related troubleshooting docs
- **Required Citations**: ImpactReport with affected_training
- **Expected Confidence**: MEDIUM to HIGH
- **Expected Failure Mode**: None

### Q45: Release Note Dependency
- **Query**: "What training materials reference the 2026 Q1 release?"
- **Intent**: IMPACT
- **Expected Doc Types**: TRAINING, USER_GUIDE
- **Expected Doc IDs**: Possibly training/user guide docs mentioning version
- **Required Citations**: ImpactReport with indirect_docs
- **Expected Confidence**: MEDIUM
- **Expected Failure Mode**: None

---

## Category 6: Freshness/Audit Queries (5 queries)

### Q46: Stale Content Audit
- **Query**: "Which documents haven't been updated in over 6 months?"
- **Intent**: AUDIT
- **Expected Doc Types**: All types
- **Expected Doc IDs**: All corpus docs (filtered by age)
- **Required Citations**: FreshnessReport with stale_documents list, freshness badges
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q47: ToolX Documentation Freshness
- **Query**: "Check freshness of all ToolX documentation"
- **Intent**: AUDIT
- **Expected Doc Types**: All types mentioning ToolX
- **Expected Doc IDs**: ToolX-related docs
- **Required Citations**: FreshnessReport with scope=ToolX filter
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q48: Training Material Freshness
- **Query**: "Are our training materials up to date?"
- **Intent**: AUDIT
- **Expected Doc Types**: TRAINING
- **Expected Doc IDs**: All training docs
- **Required Citations**: FreshnessReport with scope=TRAINING filter
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q49: Troubleshooting Guide Currency
- **Query**: "Review freshness of troubleshooting guides"
- **Intent**: AUDIT
- **Expected Doc Types**: TROUBLESHOOT
- **Expected Doc IDs**: All troubleshooting docs
- **Required Citations**: FreshnessReport with scope=TROUBLESHOOT filter
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

### Q50: Critical Content Staleness
- **Query**: "Show me STALE-rated documents that need urgent review"
- **Intent**: AUDIT
- **Expected Doc Types**: All types
- **Expected Doc IDs**: Docs with freshness=STALE badge
- **Required Citations**: FreshnessReport with stale_documents prioritized
- **Expected Confidence**: HIGH
- **Expected Failure Mode**: None

---

## Validation Criteria Summary

### Citation Validation
- **Required fields present**: doc_id, doc_name, source_path, uri (file://), version
- **URI format**: `file:///C:/Users/.../kts_test_corpus/...`
- **Version accurate**: Matches ingested document version
- **Section/page (if applicable)**: Accurate within ±1 page/section

### Confidence Validation
- **HIGH (>0.7)**: Clear match with corpus content, no escalation
- **MEDIUM (0.5-0.7)**: Partial match, may include escalation with suggestions
- **LOW (<0.5)**: No match or very weak match, MUST include escalation

### Escalation Validation
- **ESCALATION_LOW_CONFIDENCE**: Includes human-readable message, suggested_action
- **ESCALATION_MISSING_INFO**: Includes suggested_sme (if available) or next steps
- **ESCALATION_AGENT_ERROR**: Includes agent_name, error details

### Special Case Validation
- **Image notes**: Must reference specific image ID and location (e.g., "See toolx_auth_401.png showing...")
- **Freshness badges**: 🟢 CURRENT / 🟡 AGING / 🔴 STALE / ⚪ UNKNOWN correctly computed
- **Training path ordering**: Prerequisites come before dependent steps
- **Impact severity**: LOW/MEDIUM/HIGH based on number of affected docs

---

## Scoring Rubric

**Per Query:**
- **Citation Correct (0-4 points)**: All required citations present and accurate
- **Confidence Appropriate (0-2 points)**: Confidence level matches result quality
- **Escalation Correct (0-2 points)**: Escalation triggered when appropriate, includes helpful info
- **Doc Type Match (0-2 points)**: Cited docs match expected types

**Overall (50 queries × 10 points = 500 points total):**
- **450+ (90%)**: Excellent, production-ready
- **400-449 (80-89%)**: Good, minor tuning needed
- **350-399 (70-79%)**: Fair, significant gaps to address
- **<350 (<70%)**: Fail, major rework required

---

See `TEST_QUERIES_TOP_50.json` for machine-readable version with full expected output schemas.
